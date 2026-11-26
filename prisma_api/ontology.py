"""
Send a curated ontology folder to the PrISMa platform, with its provenance and hashes.

The ontology is a folder of small YAML files (today PrISMa-Platform-v2's ``src/ontology``, later its own
repository; its README describes the files):

    <root>/tree/_node.yaml              the top navigation node; children in order ({folder: …} or inline nodes)
    <root>/tree/**/_node.yaml           one navigation node per folder
    <root>/tree/**/<key>-<label>.yaml   one block: key, label, summary, groups (title, note, items), unmatched_definitions
    <root>/tree/_data/sources.yaml      the published ontologies that item matches name
    <root>/tree/_data/*.json            page data (not edited by hand)
    <root>/simpletree/**/<key>-….yaml   the simpler version: kept blocks, groups and items (profile "simple")
    <root>/ontology.yaml                optional: slug, name, description, version, base_iri

``build_payload(path)`` reads it into a ``prisma_v2.ontology.v1`` document (the format the server checks, see
prisma_cloud/ontology.py) with:

- provenance: the git repository (name and address, without credentials), folder within it, branch, commit,
  release tag (``git describe --tags``) and exact tag, commit date and author, the last commit that changed
  the folder, whether the folder has uncommitted changes, links to the commit / folder / tag, the
  calling tool and its version (e.g. prisma-v2), the installed prisma_api (version, and the git tag / commit
  it was installed from when known), the sender's git user name and the time sent;
- hashes: sha256 of every file under tree/ and simpletree/, the hash of that manifest, and the content hash
  (sha256 of the canonical JSON of the content) which the server recomputes and checks.

On the server, a send whose content differs from the current release becomes the next release; the same
content makes none. Sending needs an API key of a staff user in the server's ontology curators group.

    payload = build_payload("../PrISMa-Platform-v2/src/ontology")
    api.v2.push_ontology("../PrISMa-Platform-v2/src/ontology", dry_run=True)

Command line (``prisma-ontology``)::

    prisma-ontology build src/ontology --out ontology.json    # no network: the document and its hashes
    prisma-ontology status src/ontology --dev                 # in step with the server's current release?
    prisma-ontology push src/ontology --dev --dry-run         # what would change
    prisma-ontology push src/ontology --prod                  # asks before writing
    prisma-ontology list --prod

Exit codes: 0 done, 1 error, 2 a decision is needed (run without --yes in a terminal) or a conflict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

SCHEMA = "prisma_v2.ontology.v1"
CONTENT = ("sources", "nav", "blocks", "profiles", "data")
MANIFEST_NAMES = ("ontology.yaml", "ontology.yml", "_ontology.yaml")
ITEM_FIELDS = ("item", "definition", "source", "basis", "matches")
DEFAULT_SLUG = "prisma"
DEFAULT_PROFILES = {"simple": ("simpletree", "Simpler version (sorbents)")}


class OntologyError(RuntimeError):
    """The folder is not an ontology this client can read, or the send needs a decision."""


# ── YAML ──────────────────────────────────────────────────────────────────────

class _Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    """Safe YAML that refuses a key repeated in one mapping (as tools/build.py) and keeps dates as text."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for k, _ in node.value:
            key = self.construct_object(k, deep)
            if key in seen:
                raise yaml.MarkedYAMLError(problem=f"field {key!r} repeated", problem_mark=k.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in rs if tag != "tag:yaml.org,2002:timestamp"]
    for ch, rs in _Loader.yaml_implicit_resolvers.copy().items()
}


def _yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
    except (OSError, yaml.YAMLError) as exc:
        raise OntologyError(f"{path}: {exc}") from exc


# ── Canonical form and hashes (must match prisma_cloud/ontology.py) ──────────

def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def content_hash(doc: dict) -> str:
    """sha256 of the ontology content: the canonical JSON of sources, nav, blocks, profiles and data."""
    return sha256_of({k: doc[k] for k in CONTENT})


def files_hash(files: dict[str, str]) -> str:
    """sha256 of a file manifest {path: sha256}: one 'path<TAB>hash' line per file, sorted by path."""
    return hashlib.sha256("".join(f"{p}\t{h}\n" for p, h in sorted(files.items())).encode("utf-8")).hexdigest()


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == []


def _compact(d: dict) -> dict:
    return {k: v for k, v in d.items() if not _empty(v)}


def name_of(text: str) -> str:
    return text.removeprefix("+").split(" · ", 1)[0]


# ── Reading the folder ────────────────────────────────────────────────────────

def find_root(path: str | Path) -> tuple[Path, Path]:
    """(ontology root, its tree folder) from the root (holding tree/) or the tree folder itself."""
    p = Path(path).expanduser().resolve()
    if (p / "tree" / "_node.yaml").is_file():
        return p, p / "tree"
    if (p / "_node.yaml").is_file():
        return p.parent, p
    raise OntologyError(f"{path} holds no ontology: expected tree/_node.yaml (or _node.yaml) in it")


def _item(entry: Any) -> Any:
    if not isinstance(entry, dict):
        return entry                                     # the server reports it
    out = {k: entry.get(k) for k in ("item", "definition", "source", "basis")}
    if entry.get("matches"):
        m = entry["matches"]
        out["matches"] = [_compact(x) if isinstance(x, dict) else x for x in m] if isinstance(m, list) else m
    out.update({k: v for k, v in entry.items() if k not in ITEM_FIELDS})
    return _compact(out)


def _block(doc: Any, rel: str) -> Any:
    if not isinstance(doc, dict):
        raise OntologyError(f"{rel}: a block file must hold a mapping")
    groups = []
    for g in doc.get("groups") or []:
        if not isinstance(g, dict):
            groups.append(g)
            continue
        group = {"title": g.get("title"), "note": g.get("note", False),
                 "items": [_item(x) for x in g.get("items") or []]}
        group.update({k: v for k, v in g.items() if k not in ("title", "note", "items")})
        groups.append(group)
    out = {"key": doc.get("key"), "label": doc.get("label"), "summary": doc.get("summary") or "", "path": rel,
           "groups": groups}
    if "unmatched_definitions" in doc:
        out["unmatched_definitions"] = [_compact({f: u.get(f) for f in ("group", "name", "definition", "source", "basis")})
                                        if isinstance(u, dict) else u for u in doc["unmatched_definitions"] or []]
    out.update({k: v for k, v in doc.items() if k not in out and k not in ("unmatched_definitions",)})
    return {k: v for k, v in out.items() if not (v is None or v == "") or k == "summary"}


def _nav(folder: Path, root: Path, name: str | None = None) -> dict:
    path = folder / "_node.yaml"
    node = _yaml(path)
    if not isinstance(node, dict) or not isinstance(node.get("children", []), list):
        raise OntologyError(f"{path.relative_to(root)}: a node needs its fields and a children list")
    kids = node.pop("children", []) or []
    out = {k: v for k, v in node.items() if not (v is None or v == "")}
    if name:
        out["folder"] = name
    out["children"] = []
    for kid in kids:
        if isinstance(kid, dict) and "folder" in kid:
            out["children"].append(_nav(folder / str(kid["folder"]), root, str(kid["folder"])))
        elif isinstance(kid, dict):
            child = {k: v for k, v in kid.items() if not (v is None or v == "") and k != "children"}
            child["children"] = []
            out["children"].append(child)
        else:
            raise OntologyError(f"{path.relative_to(root)}: children must be mappings")
    return out


def _placed(nav: dict) -> list[str]:
    keys = [nav["k"]] if "k" in nav else []
    for c in nav.get("children") or []:
        keys += _placed(c)
    return keys


def _profile(name: str, label: str, folder: Path, root: Path, blocks: list[dict]) -> dict:
    """A profile from a simpletree-like folder, in tree order (the server checks every entry against the tree)."""
    kept: dict[str, dict[str, set]] = {}
    for path in sorted(folder.rglob("*.yaml")):
        doc = _yaml(path)
        if not isinstance(doc, dict):
            raise OntologyError(f"{path.relative_to(root)}: must hold key, label and groups")
        key = doc.get("key")
        if key in kept:
            raise OntologyError(f"{path.relative_to(root)}: block {key!r} listed twice")
        kept[key] = {g.get("title"): set(g.get("items") or []) for g in doc.get("groups") or [] if isinstance(g, dict)}
    by_key = {b.get("key"): b for b in blocks}
    unknown = sorted(str(k) for k in kept if k not in by_key)
    if unknown:
        raise OntologyError(f"{folder.relative_to(root)}: no tree block for {', '.join(unknown)}")
    listed = []
    for b in blocks:
        if b["key"] not in kept:
            continue
        titles = kept[b["key"]]
        tree_groups = {g["title"]: {x["item"] for x in g["items"] if isinstance(x, dict)} for g in b["groups"]}
        missing = sorted(str(t) for t in titles if t not in tree_groups)
        stray = sorted(str(i) for t, items in titles.items() if t in tree_groups for i in items if i not in tree_groups[t])
        if missing or stray:
            problems = ([f"groups not in the tree: {missing}"] if missing else []) + \
                       ([f"items not in the tree: {stray[:5]}"] if stray else [])
            raise OntologyError(f"{folder.relative_to(root)} block {b['key']!r}: " + "; ".join(problems))
        groups = [{"title": g["title"], "items": [x["item"] for x in g["items"] if x["item"] in titles[g["title"]]]}
                  for g in b["groups"] if g["title"] in titles]
        groups = [g for g in groups if g["items"]]
        if groups:
            listed.append({"key": b["key"], "groups": groups})
    return {"name": name, "label": label, "blocks": listed}


def _base_iri(root: Path) -> str:
    """BASE of the ontology's own build script (tools/build.py), when it has one."""
    build = root / "tools" / "build.py"
    if build.is_file():
        m = re.search(r'^BASE\s*=\s*"([^"]+)"', build.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return ""


def _file_hashes(root: Path, folders: list[Path], extra: list[Path]) -> dict[str, str]:
    files = {}
    for path in [p for f in folders if f.is_dir() for p in sorted(f.rglob("*")) if p.is_file()] + \
            [p for p in extra if p.is_file()]:
        if path.name.startswith(".") or "__pycache__" in path.parts:
            continue
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


# ── Provenance from git ───────────────────────────────────────────────────────

def _git(folder: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def clean_url(url: str | None) -> str:
    """A repository address without credentials (an origin can hold a token); ssh forms become https."""
    url = (url or "").strip()
    m = re.fullmatch(r"(?:ssh://)?git@([^:/]+)[:/](.+)", url)
    if m:
        url = f"https://{m.group(1)}/{m.group(2)}"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    path = parts.path[:-4] if parts.path.endswith(".git") else parts.path
    return urlunsplit((parts.scheme, host, path.rstrip("/"), "", ""))


def _links(repo_url: str, commit: str | None, path: str, tag: str | None) -> dict:
    if not repo_url:
        return {}
    links = {"repo": repo_url}
    host = urlsplit(repo_url).hostname or ""
    sep = "/-" if "gitlab" in host else ""
    if "github" in host or "gitlab" in host:
        if commit:
            links["commit"] = f"{repo_url}{sep}/commit/{commit}"
            links["tree"] = f"{repo_url}{sep}/tree/{commit}" + (f"/{path}" if path else "")
        if tag:
            links["tag"] = f"{repo_url}/releases/tag/{tag}" if "github" in host else f"{repo_url}/-/tags/{tag}"
    return links


def git_provenance(root: str | Path) -> dict:
    """Where the folder comes from: repository, folder, branch, commit, tags, dates, authors, local changes."""
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return {"path": root.name, "dirty": False}
    rel = root.relative_to(Path(top).resolve()).as_posix()
    rel = "" if rel == "." else rel
    origin = _git(root, "remote", "get-url", "origin")
    repo_url = clean_url(origin)
    name = (origin or "").rstrip("/").replace(":", "/").rsplit("/", 1)[-1] if origin else Path(top).name
    name = name[:-4] if name.endswith(".git") else name
    head = (_git(root, "log", "-1", "--format=%H%x1f%cI%x1f%an", "HEAD") or "").split("\x1f")
    last = (_git(root, "log", "-1", "--format=%H%x1f%cI%x1f%an", "--", ".") or "").split("\x1f")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    exact = _git(root, "describe", "--tags", "--exact-match", "HEAD")
    nearest = _git(root, "describe", "--tags", "--abbrev=0", "HEAD")
    commit = head[0] if len(head) == 3 else None
    out = {
        "repo": name, "repo_url": repo_url, "path": rel, "branch": None if branch == "HEAD" else branch,
        "commit": commit, "tag": _git(root, "describe", "--tags", "HEAD"), "exact_tag": exact,
        "committed_at": head[1] if len(head) == 3 else None, "commit_author": head[2] if len(head) == 3 else None,
        "path_commit": last[0] if len(last) == 3 else None, "path_committed_at": last[1] if len(last) == 3 else None,
        "path_commit_author": last[2] if len(last) == 3 else None,
        "dirty": bool(_git(root, "status", "--porcelain", "--", ".")),
        "links": _links(repo_url, commit, rel, exact or nearest),
    }
    return {k: v for k, v in out.items() if v is not None}


def client_provenance() -> dict:
    """
    The installed prisma_api that builds and sends the document: its version and, where known, the git tag and
    commit it was installed from (an editable install or a run from a checkout of the prisma_api repository, or
    ``pip install git+…@<tag>``), and how it was installed.
    """
    from . import __version__
    out: dict[str, Any] = {"name": "prisma_api", "version": __version__}
    pkg = Path(__file__).resolve().parent
    try:
        from importlib.metadata import PackageNotFoundError, distribution
        try:
            dist = distribution("prisma_api")
            direct = json.loads(dist.read_text("direct_url.json") or "{}")
            if not (direct.get("dir_info") or {}).get("editable") \
                    and Path(dist.locate_file("prisma_api/__init__.py")).resolve().parent != pkg:
                direct = None                                       # an install exists, but not the one running
        except PackageNotFoundError:
            direct = None
    except (ImportError, ValueError, OSError):
        direct = {}
    vcs = (direct or {}).get("vcs_info") or {}
    if direct is None:
        out["install"] = "source"                                   # imported from a folder, not installed
    elif vcs:
        out.update(install="vcs", commit=vcs.get("commit_id"), tag=vcs.get("requested_revision"),
                   repo_url=clean_url(direct.get("url")) or None)
    elif (direct.get("dir_info") or {}).get("editable"):
        out["install"] = "editable"
    elif direct:
        out["install"] = "local"
    else:
        out["install"] = "index"
    # the package folder in a checkout of the prisma_api repository (not some other repository around a venv)
    top = _git(pkg, "rev-parse", "--show-toplevel")
    if top and pkg.parent == Path(top).resolve() and (pkg.parent / "pyproject.toml").is_file() \
            and re.search(r'^name\s*=\s*"prisma[_-]api"', (pkg.parent / "pyproject.toml").read_text(encoding="utf-8"), re.M):
        origin = clean_url(_git(pkg, "remote", "get-url", "origin"))
        out.update(commit=_git(pkg, "rev-parse", "HEAD"), tag=_git(pkg, "describe", "--tags", "HEAD"),
                   exact_tag=_git(pkg, "describe", "--tags", "--exact-match", "HEAD"),
                   dirty=bool(_git(pkg, "status", "--porcelain", "--", ".")), repo_url=origin or out.get("repo_url"))
        if out["install"] in ("index", "local", "source"):
            out["install"] = "checkout"                             # run from the repository folder itself
    return {k: v for k, v in out.items() if v not in (None, "")}


# ── The document ──────────────────────────────────────────────────────────────

def _manifest(root: Path) -> dict:
    for name in MANIFEST_NAMES:
        if (root / name).is_file():
            doc = _yaml(root / name)
            if not isinstance(doc, dict):
                raise OntologyError(f"{root / name}: must hold a mapping (slug, name, description, version, base_iri)")
            return doc
    return {}


def build_payload(path: str | Path, slug: str | None = None, name: str | None = None,
                  description: str | None = None, version: str | None = None, include_data: bool = True,
                  profiles: dict[str, tuple[str, str]] | None = None, tool: str = "prisma_api",
                  tool_version: str | None = None) -> dict:
    """
    The ``prisma_v2.ontology.v1`` document of an ontology folder, with provenance and hashes.

    Args:
        path: the ontology folder (holding ``tree/``) or its ``tree/`` folder.
        slug, name, description, version: override ``ontology.yaml`` at the root (defaults: slug 'prisma').
        include_data: send ``tree/_data/*.json`` (the page data) too.
        profiles: ``{name: (folder relative to the root, label)}``; default ``simpletree/`` as 'simple'.
        tool, tool_version: the caller, recorded in the provenance (e.g. 'prisma-v2').
    """
    root, tree = find_root(path)
    meta = _manifest(root)
    data_dir = tree / "_data"

    nav = _nav(tree, root)
    blocks, seen = {}, {}
    for p in sorted(tree.rglob("*.yaml")):
        if p.name.startswith("_") or data_dir in p.parents:
            continue
        rel = p.relative_to(root).as_posix()
        block = _block(_yaml(p), rel)
        key = block.get("key")
        if key in seen:
            raise OntologyError(f"{rel}: key {key!r} already used by {seen[key]}")
        seen[key] = rel
        blocks[key] = block
    order = _placed(nav)
    ordered = [blocks[k] for k in order if k in blocks] + [b for k, b in blocks.items() if k not in order]

    sources_path = data_dir / "sources.yaml"
    sources = []
    if sources_path.is_file():
        for s in _yaml(sources_path) or []:
            sources.append(_compact({k: s.get(k) for k in ("name", "version", "licence", "source")})
                           | {k: v for k, v in s.items() if k not in ("name", "version", "licence", "source")}
                           if isinstance(s, dict) else s)
    data = {}
    if include_data and data_dir.is_dir():
        for p in sorted(data_dir.glob("*.json")):
            try:
                data[p.name] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise OntologyError(f"{p.relative_to(root)}: {exc}") from exc

    wanted = DEFAULT_PROFILES if profiles is None else profiles
    profile_docs, folders = [], [tree]
    for pname, (folder, label) in wanted.items():
        pdir = root / folder
        if pdir.is_dir():
            profile_docs.append(_profile(pname, label, pdir, root, ordered))
            folders.append(pdir)

    if tool_version is None:
        try:
            from . import __version__ as tool_version
        except ImportError:
            tool_version = None
    files = _file_hashes(root, folders, [root / n for n in MANIFEST_NAMES])
    source = git_provenance(root)
    doc = {
        "_schema": SCHEMA,
        "ontology": _compact({
            "slug": slug or meta.get("slug") or DEFAULT_SLUG,
            "name": name or meta.get("name") or "PrISMa ontology",
            "description": description if description is not None else meta.get("description"),
            "version": version or (str(meta["version"]) if meta.get("version") is not None else None),
            "base_iri": meta.get("base_iri") or _base_iri(root),
        }),
        "provenance": _compact({
            "tool": tool, "tool_version": str(tool_version) if tool_version else None,
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sent_by": _git(root, "config", "user.name"),
            "client": client_provenance(),
            "source": source,
        }),
        "hashes": {"algorithm": "sha256", "files": files, "files_hash": files_hash(files)},
        "sources": sources, "nav": nav, "blocks": ordered, "profiles": profile_docs, "data": data,
    }
    doc["hashes"]["content"] = content_hash(doc)
    return doc


def summarise(doc: dict) -> dict:
    """Counts and hashes of a built document (no network)."""
    blocks = doc["blocks"]
    items = [x for b in blocks for g in b.get("groups", []) for x in g.get("items", [])]
    return {"slug": doc["ontology"]["slug"], "blocks": len(blocks), "groups": sum(len(b.get("groups", [])) for b in blocks),
            "items": len(items), "matches": sum(len(x.get("matches") or []) for x in items if isinstance(x, dict)),
            "profiles": [p["name"] for p in doc["profiles"]], "data_files": sorted(doc["data"]),
            "files": len(doc["hashes"]["files"]), "content_hash": doc["hashes"]["content"],
            "files_hash": doc["hashes"]["files_hash"], "source": doc["provenance"].get("source", {}),
            "client": doc["provenance"].get("client", {})}


def status(api, path: str | Path, slug: str | None = None) -> dict:
    """``in_sync`` / ``local_changed`` / ``unpublished``: the local folder against the server's current release."""
    doc = build_payload(path, slug=slug, include_data=True)
    local = doc["hashes"]["content"]
    try:
        online = api.v2.get_ontology(doc["ontology"]["slug"])
    except requests.HTTPError as exc:
        if getattr(exc.response, "status_code", None) == 404:
            return {"state": "unpublished", "slug": doc["ontology"]["slug"], "local_hash": local, "release": None}
        raise
    state = "in_sync" if online["hashes"]["content"] == local else "local_changed"
    return {"state": state, "slug": doc["ontology"]["slug"], "local_hash": local,
            "online_hash": online["hashes"]["content"], "release": online["release"]["number"],
            "online_commit": online["release"]["source"].get("commit"), "page": (online["release"].get("urls") or {}).get("page")}


# ── Command line ──────────────────────────────────────────────────────────────

def _confirm(question: str, args) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def _print_result(out: dict, args) -> None:
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    verb = "would make" if out.get("dry_run") and out.get("changed") else "made" if out.get("created") else "matches"
    print(f"{out['ontology']}: {verb} release {out['release']}"
          + ("" if out.get("changed") else " (content unchanged)"))
    d = out.get("diff")
    if d:
        for what in ("blocks", "items", "sources", "profiles", "data"):
            c = d.get(what) or {}
            if c.get("added") or c.get("removed") or c.get("changed"):
                print(f"  {what:<9} +{c['added']} -{c['removed']} ~{c['changed']}")
        if d.get("nav_changed"):
            print("  navigation changed")
    elif out.get("changed"):
        c = out.get("counts") or {}
        print(f"  first release: {c.get('blocks')} blocks, {c.get('items')} items, {c.get('matches')} matches")
    page = (out.get("urls") or {}).get("page")
    if page:
        print(f"  page: {page}")


def main(argv: list[str] | None = None, tool: str = "prisma_api", tool_version: str | None = None) -> int:
    """The prisma-ontology command. ``tool`` names the caller in the provenance (e.g. "prisma-v2")."""
    parser = argparse.ArgumentParser(prog="prisma-ontology", description=__doc__.strip().split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def server(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--dev", action="store_true", help="Local dev server (localhost:<dev_host_port>, dev_api_key)")
        g.add_argument("--prod", action="store_true", help="Production (prisma-platform.org)")
        p.add_argument("--json", action="store_true", help="Machine-readable output")

    def folder(p):
        p.add_argument("path", help="The ontology folder (holding tree/), e.g. src/ontology")
        p.add_argument("--slug", help="Ontology slug (default: ontology.yaml, else 'prisma')")

    p = sub.add_parser("build", help="Read the folder into the document the server takes (no network)")
    folder(p)
    p.add_argument("--out", help="Write the document to this file")
    p.add_argument("--no-data", action="store_true", help="Leave out tree/_data/*.json")
    p = sub.add_parser("status", help="Is the folder in step with the server's current release?")
    folder(p)
    server(p)
    p = sub.add_parser("push", help="Send the folder; a changed ontology becomes the next release")
    folder(p)
    server(p)
    p.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing")
    p.add_argument("--force", action="store_true", help="Send even when older than the current release")
    p.add_argument("--no-data", action="store_true", help="Leave out tree/_data/*.json")
    p.add_argument("--yes", action="store_true", help="Do not ask before writing")
    p = sub.add_parser("list", help="Ontologies on the server")
    server(p)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            doc = build_payload(args.path, slug=args.slug, include_data=not args.no_data, tool=tool,
                                tool_version=tool_version)
            if args.out:
                Path(args.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps(summarise(doc), indent=2, ensure_ascii=False))
            return 0

        from . import init
        api = init(local_dev=args.dev)
        api.v2.set_return_format("json")
        from .prisma_api_v2 import PrismaConflictError

        if args.command == "list":
            out = api.v2.list_ontologies()
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                for o in out["records"]:
                    r = o.get("current_release") or {}
                    src = r.get("source") or {}
                    print(f"{o['slug']:<16} r{r.get('number', '-'):<4} {src.get('tag') or '':<22} "
                          f"{(src.get('commit') or '')[:10]:<11} {o['name']}")
            return 0
        if args.command == "status":
            st = status(api, args.path, args.slug)
            if args.json:
                print(json.dumps(st, indent=2))
            else:
                print(f"{st['state']}: {st['slug']}" + (f" release {st['release']}" if st.get("release") else ""))
            return 0

        # push: a dry run first, then (unless --dry-run) the send itself after a confirmation
        doc = build_payload(args.path, slug=args.slug, include_data=not args.no_data, tool=tool,
                            tool_version=tool_version)
        try:
            preview = api.v2.send_ontology(doc, dry_run=True, force=args.force)
        except PrismaConflictError as exc:
            print(exc, file=sys.stderr)
            print("Pass --force to send it anyway.", file=sys.stderr)
            return 2
        if args.dry_run or not preview["changed"]:
            if not preview["changed"] and not args.dry_run:
                preview = api.v2.send_ontology(doc, force=args.force)      # logged on the server; no new release
            _print_result(preview, args)
            return 0
        _print_result(preview, args)
        src = doc["provenance"].get("source", {})
        if src.get("dirty") and not args.json:
            print("  note: the folder has uncommitted changes; the release will be marked so", file=sys.stderr)
        target = "dev" if args.dev else "prod"
        if not _confirm(f"Send it as release {preview['release']} of {preview['ontology']!r} on {target}?", args):
            print("Nothing sent (pass --yes to skip this question).", file=sys.stderr)
            return 2
        _print_result(api.v2.send_ontology(doc, force=args.force), args)
        return 0
    except OntologyError as exc:
        print(exc, file=sys.stderr)
        return 1
    except requests.HTTPError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
