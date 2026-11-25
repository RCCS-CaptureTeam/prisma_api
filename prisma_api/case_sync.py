"""
Publish a local case study to the PrISMa platform's case study builder, and keep the two in step.

A local case is a process-graph document (``prisma_v2.flowsheet.process_graph.v6``, e.g.
PrISMa-Platform-v2's ``cases/<name>/<name>.json``) plus optional study settings in a sidecar
``<name>.study.yaml`` (or ``.study.json``) next to it: name, desc, locs, time, scen, tea, lca,
kpis, samp, group, systems. On the platform it becomes a builder draft with the same metadata as
one drawn at /studies/builder-next/, and publishing it makes the v2 study.

The link between the two is kept in ``<name>.cloud.json`` next to the case, one entry per server
(``prod`` / ``dev``): the build id, the hash of the local files and the build's design hash when
the two last agreed. From those, ``check`` tells:

    unlinked      no build yet                        -> push / publish creates one
    in_sync       nothing changed on either side (a build only re-saved by the page, with the same
                  values, counts as unchanged; push then refreshes the link and the build's provenance)
    local_ahead   the local case changed              -> push (draft) or fork (published)
    online_ahead  the build changed on the platform   -> pull
    diverged      both changed                        -> fork the local case, pull, or overwrite (draft)
    missing       the linked build is gone            -> push creates a new one

Nothing is overwritten unseen: updates send the design hash last seen and the server refuses
(409) when the build moved on. The local files are only written by ``pull``.

    check(api, case)                    -> Status
    push(api, case, publish=False)      -> link entry (creates or updates the draft; publishes)
    pull(api, case)                     -> link entry (writes the case and study files)
    fork(api, case, name=None)          -> link entry (a new draft from the local case)

Command line (``prisma-case``)::

    prisma-case status cases/dac_min/dac_min.json --dev
    prisma-case publish cases/dac_min/dac_min.json --prod        # asks before writing
    prisma-case push cases/dac_min/dac_min.json --dev --yes      # draft only
    prisma-case pull cases/dac_min/dac_min.json --dev
    prisma-case fork cases/dac_min/dac_min.json --dev --name "DAC min UK r2"
    prisma-case install-skill .                                   # Claude Code skill /prisma-case

Exit codes: 0 done, 1 error, 2 a decision is needed (run without --yes in a terminal, or pass
--on-conflict).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

GRAPH_FORMAT = "prisma_v2.flowsheet.process_graph.v6"
STUDY_KEYS = ("name", "desc", "locs", "time", "scen", "tea", "lca", "kpis", "samp", "group", "systems", "system_name")
LINK_SUFFIX = ".cloud.json"
DOCS = Path(__file__).parent / "case_docs"

STATES = ("unlinked", "in_sync", "local_ahead", "online_ahead", "diverged", "missing")
VOLATILE = ("aud", "mode", "gStep", "gScript", "seq")   # the page's view settings: not part of a design (as on the server)
PROVENANCE = ("tool", "tool_version", "repo", "git_commit", "git_tag")


class SyncError(RuntimeError):
    """The case cannot be synced as asked (bad files, a decision needed, placeholders on pull…)."""


# ── Local files ───────────────────────────────────────────────────────────────

def study_path_for(case: str | Path) -> Path | None:
    """The study sidecar next to the case (``<stem>.study.yaml|yml|json``), or None."""
    case = Path(case)
    for ext in (".study.yaml", ".study.yml", ".study.json"):
        p = case.with_name(case.stem + ext)
        if p.is_file():
            return p
    return None


def load_case(case: str | Path, study: str | Path | None = None) -> tuple[dict, dict]:
    """(graph document, study settings) of a local case."""
    case = Path(case)
    try:
        graph = json.loads(case.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SyncError(f"cannot read {case}: {exc}") from exc
    if not isinstance(graph, dict) or graph.get("format") != GRAPH_FORMAT:
        raise SyncError(f"{case} is not a {GRAPH_FORMAT} document")
    path = Path(study) if study else study_path_for(case)
    settings: dict = {}
    if path is not None:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            settings = json.loads(text)
        else:
            import yaml
            settings = yaml.safe_load(text) or {}
        if not isinstance(settings, dict):
            raise SyncError(f"{path} must hold a mapping of study settings")
        unknown = sorted(set(settings) - set(STUDY_KEYS))
        if unknown:
            raise SyncError(f"{path}: unknown study settings {unknown}; allowed: {', '.join(STUDY_KEYS)}")
        systems = []
        for alt in settings.get("systems") or []:     # alternative systems: graph inline, or a path next to the study
            if isinstance(alt, dict) and isinstance(alt.get("graph"), str):
                alt = {**alt, "graph": json.loads((path.parent / alt["graph"]).read_text(encoding="utf-8"))}
            systems.append(alt)
        if systems:
            settings["systems"] = systems
    return graph, settings


def source_hash(graph: dict, study: dict) -> str:
    """sha256 of the case's content (key order and formatting do not count)."""
    body = json.dumps({"graph": graph, "study": study or {}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def link_path(case: str | Path) -> Path:
    case = Path(case)
    return case.with_name(case.stem + LINK_SUFFIX)


def read_link(case: str | Path, target: str) -> dict | None:
    path = link_path(case)
    if not path.is_file():
        return None
    return (json.loads(path.read_text(encoding="utf-8")).get("targets") or {}).get(target)


def write_link(case: str | Path, target: str, entry: dict | None) -> Path:
    """Store (or with None remove) the link for one server, keeping the others."""
    path = link_path(case)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    doc.setdefault("_about", "Link between this case and its study build on the PrISMa platform (prisma-case). "
                             "No secrets; safe to commit.")
    targets = doc.setdefault("targets", {})
    if entry is None:
        targets.pop(target, None)
    else:
        targets[target] = entry
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _write_json(path: Path, doc: dict) -> None:
    # PrISMa-Platform-v2 case files: 2-space indent, ASCII escapes, trailing newline
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _git(folder: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _git_commit(folder: Path) -> str | None:
    return _git(folder, "rev-parse", "--short", "HEAD")


def _git_tag(folder: Path) -> str | None:
    """The release the case's checkout is at: 'v2.0.1' on a tagged commit, 'v2.0.1-3-g70eaa92' three commits on."""
    return _git(folder, "describe", "--tags")


def _git_repo(folder: Path) -> str | None:
    """The repository's name from its origin remote ('PrISMa-Platform-v2'), never the URL (it can hold a token)."""
    url = _git(folder, "remote", "get-url", "origin")
    if not url:
        return None
    name = url.rstrip("/").replace(":", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".git") else name or None


def _client_info(case: Path, graph: dict, lhash: str, tool: str, tool_version: str | None = None) -> dict:
    """The build's provenance link: who sent the case and from which checkout (servers keep the keys they know)."""
    info = {"tool": tool, "case_id": graph.get("template_id") or case.stem, "source_hash": lhash}
    if tool_version:
        info["tool_version"] = str(tool_version)
    for key, value in (("repo", _git_repo(case.parent)), ("git_commit", _git_commit(case.parent)),
                       ("git_tag", _git_tag(case.parent))):
        if value:
            info[key] = value
    return info


def merge_graph(local: dict, remote: dict) -> dict:
    """``remote`` laid out like ``local``: local key order and node/edge order kept, so a pull diffs minimally."""
    def ordered(old: dict, new: dict) -> dict:
        out = {k: new[k] for k in old if k in new and (new[k] is not None or old[k] is None)}
        out.update({k: v for k, v in new.items() if k not in out and (v is not None or k in old)})
        return out

    merged = ordered(local, remote)
    lg, rg = local.get("graph") or {}, remote.get("graph") or {}
    r_nodes = {n["node_id"]: n for n in rg.get("nodes") or []}
    nodes = [ordered(n, r_nodes.pop(n["node_id"])) for n in lg.get("nodes") or [] if n.get("node_id") in r_nodes]
    nodes += list(r_nodes.values())
    key = lambda e: (e.get("src_node_id"), e.get("dst_node_id"))  # noqa: E731
    r_edges = {key(e): e for e in rg.get("edges") or []}
    edges = [ordered(e, r_edges.pop(key(e))) for e in lg.get("edges") or [] if key(e) in r_edges]
    edges += list(r_edges.values())
    graph = {**lg, "nodes": nodes, "edges": edges}
    merged["graph"] = {k: graph[k] for k in list(lg) + [k for k in graph if k not in lg]}
    return merged


def _same_design(v2, build: dict, graph: dict, settings: dict) -> bool:
    """True when ``build`` holds the design the local case makes, though its design hash moved on.

    Opening a build on the page can save it again (e.g. switching guide/expert view), and the browser writes
    40000.0 back as 40000, which changes the hash without changing a value. The server's dry run of the local
    case gives the design it would store; Python's ``==`` treats 40000.0 and 40000 as the same number."""
    online = build.get("state")
    if not isinstance(online, dict):
        return False
    try:
        fresh = v2.create_study_build(graph=graph, study=settings, dry_run=True).get("state")
    except requests.HTTPError:
        return False
    if not isinstance(fresh, dict):
        return False
    design = lambda st: {k: v for k, v in st.items() if k not in VOLATILE}
    return design(online) == design(fresh)


def provenance_changes(build: dict | None, client: dict) -> dict:
    """``{key: (on the build, now)}`` for provenance the build records differently from the local checkout.

    A key the build lacks counts only for ``git_commit``, so a server that does not store the newer keys is
    not updated on every push."""
    online = (build or {}).get("client") or {}
    return {k: (online.get(k), client[k]) for k in PROVENANCE
            if k in client and (k in online or k == "git_commit") and online.get(k) != client[k]}


# ── Status ────────────────────────────────────────────────────────────────────

@dataclass
class Status:
    state: str
    case: str
    target: str
    local_hash: str
    link: dict | None = None
    build: dict | None = None                  # the server's summary of the linked build
    actions: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def target_of(api) -> str:
    v2 = getattr(api, "v2", api)
    return f"dev:{v2._dev_host_port}" if getattr(v2, "_dev", False) else "prod"


def check(api, case: str | Path, study: str | Path | None = None) -> Status:
    """Where the local case stands against its build on the server ``api`` points at."""
    v2 = getattr(api, "v2", api)
    case = Path(case)
    graph, settings = load_case(case, study)
    lhash, target = source_hash(graph, settings), target_of(api)
    link = read_link(case, target)
    st = Status("unlinked", str(case), target, lhash, link)
    if not link:
        st.actions, st.message = ["push", "publish"], "not on the platform yet"
        return st
    try:
        st.build = v2.get_study_build(link["build_id"])
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            st.state, st.actions = "missing", ["push", "publish", "unlink"]
            st.message = f"build {link['build_id']} no longer exists on {target}"
            return st
        raise
    local_changed = lhash != link.get("source_hash")
    online_changed = st.build["design_hash"] != link.get("design_hash")
    draft = st.build["status"] == "draft"
    where = f"build {st.build['id']} ({st.build['status']})"
    if local_changed and online_changed:
        st.state, st.actions = "diverged", ["fork", "pull"] + (["overwrite"] if draft else [])
        st.message = f"both the local case and {where} changed since they last agreed"
    elif local_changed:
        st.state, st.actions = "local_ahead", ["push", "publish"] if draft else ["fork"]
        st.message = f"the local case is ahead of {where}" + ("" if draft else "; a published build cannot change")
    elif online_changed and not _same_design(v2, st.build, graph, settings):
        st.state, st.actions = "online_ahead", ["pull"]
        st.message = f"{where} is ahead of the local case (changed on the platform)"
    else:
        st.state, st.actions = "in_sync", ["publish"] if draft else []
        st.message = f"in step with {where}"
    return st


# ── Operations ────────────────────────────────────────────────────────────────

def _entry(build: dict, lhash: str, history: list | None = None) -> dict:
    entry = {"build_id": build["id"], "status": build["status"], "source_hash": lhash, "design_hash": build["design_hash"],
             "edit_url": (build.get("urls") or {}).get("edit"), "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if build.get("analysis"):
        entry["study_url"] = build["analysis"]["url"]
    if history:
        entry["history"] = history
    return entry


def push(api, case: str | Path, study: str | Path | None = None, publish: bool = False,
         overwrite: bool = False, tool: str = "prisma_api", tool_version: str | None = None) -> dict:
    """Create the draft (unlinked/missing) or update it (local ahead / in sync), then publish if asked.

    Raises SyncError when the status needs another action (pull or fork); ``overwrite`` replaces a draft that
    changed online with the local case. Returns the new link entry."""
    v2 = getattr(api, "v2", api)
    case = Path(case)
    st = check(api, case, study)
    graph, settings = load_case(case, study)
    client = _client_info(case, graph, st.local_hash, tool, tool_version)
    history = (st.link or {}).get("history")
    if st.state in ("unlinked", "missing"):
        if st.state == "missing":
            history = (history or []) + [st.link["build_id"]]
        build = v2.create_study_build(graph=graph, study=settings, client=client)
    elif st.state in ("local_ahead", "in_sync") and st.build["status"] == "draft" or st.state == "diverged" and overwrite:
        if st.build["status"] != "draft":
            raise SyncError(f"build {st.build['id']} is {st.build['status']}: fork instead")
        if st.state == "in_sync" and not provenance_changes(st.build, client):
            build = st.build                    # nothing to send; the link takes the build's current hash
        elif st.state == "in_sync":             # same design, newer checkout: the build's provenance is refreshed
            build = v2.update_study_build(st.build["id"], st.build["design_hash"], graph=graph, study=settings,
                                          client=client)
        else:
            base = st.build["design_hash"] if overwrite else st.link["design_hash"]
            build = v2.update_study_build(st.build["id"], base, graph=graph, study=settings, client=client)
    else:
        raise SyncError(f"{st.message}: {' / '.join(st.actions) or 'nothing to push'}")
    if publish and build["status"] == "draft":
        if build.get("fixes"):
            write_link(case, st.target, _entry(build, st.local_hash, history))
            raise SyncError(f"draft {build['id']} saved but not published: {build['fixes'][0]}")
        build = v2.publish_study_build(build["id"], build["design_hash"])
    entry = _entry(build, st.local_hash, history)
    write_link(case, st.target, entry)
    return entry


def pull(api, case: str | Path, study: str | Path | None = None, allow_placeholders: bool = False,
         force: bool = False) -> dict:
    """Write the build's design into the local case (and study sidecar). Refuses when the local case changed
    since the last sync unless ``force``, and when the build has nodes with no platform model unless
    ``allow_placeholders``. Returns the new link entry."""
    v2 = getattr(api, "v2", api)
    case = Path(case)
    st = check(api, case, study)
    if st.state in ("unlinked", "missing"):
        raise SyncError(st.message)
    if st.state in ("local_ahead", "diverged") and not force:
        raise SyncError(f"{st.message}: pulling would discard the local changes (force to do so, or fork)")
    out = v2.get_study_build_graph(st.build["id"])
    if out.get("placeholders") and not allow_placeholders:
        raise SyncError(f"the build has nodes with no platform model yet ({', '.join(out['placeholders'])}); "
                        "the local runner cannot run them")
    local, _ = load_case(case, study)
    graph = merge_graph(local, out["graph"])
    spath = Path(study) if study else study_path_for(case) or case.with_name(case.stem + ".study.yaml")
    raw = {}
    if spath.is_file():   # as written (system graphs may be paths): local-only keys are kept from it
        import yaml
        raw = (json.loads(spath.read_text(encoding="utf-8")) if spath.suffix == ".json"
               else yaml.safe_load(spath.read_text(encoding="utf-8"))) or {}
    settings = {k: raw[k] for k in ("systems", "system_name") if k in raw}
    settings.update({k: v for k, v in (out.get("study") or {}).items() if v not in (None, "", [], {})})
    _write_json(case, graph)
    if spath.suffix == ".json":
        spath.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        import yaml
        spath.write_text(yaml.safe_dump(settings, sort_keys=False, allow_unicode=True), encoding="utf-8")
    graph, settings = load_case(case, spath)
    build = {**st.build, "design_hash": out["design_hash"]}
    entry = _entry(build, source_hash(graph, settings), st.link.get("history"))
    write_link(case, st.target, entry)
    return entry


def fork(api, case: str | Path, study: str | Path | None = None, name: str | None = None,
         publish: bool = False, tool: str = "prisma_api", tool_version: str | None = None) -> dict:
    """A new draft from the local case, forked from the linked build (kept as it is); the link moves to it."""
    v2 = getattr(api, "v2", api)
    case = Path(case)
    st = check(api, case, study)
    if st.state in ("unlinked", "missing"):
        raise SyncError(f"{st.message}: nothing to fork from (push instead)")
    graph, settings = load_case(case, study)
    build = v2.fork_study_build(st.build["id"], name=name, graph=graph, study=settings,
                                client=_client_info(case, graph, st.local_hash, tool, tool_version))
    history = (st.link.get("history") or []) + [st.build["id"]]
    if publish:
        if build.get("fixes"):
            write_link(case, st.target, _entry(build, st.local_hash, history))
            raise SyncError(f"fork {build['id']} saved but not published: {build['fixes'][0]}")
        build = v2.publish_study_build(build["id"], build["design_hash"])
    entry = _entry(build, st.local_hash, history)
    write_link(case, st.target, entry)
    return entry


def link(api, case: str | Path, build_id: int) -> dict:
    """Link the case to an existing build (e.g. drawn on the page). The local case then counts as changed:
    status shows what differs, and push/pull/fork resolve it."""
    v2 = getattr(api, "v2", api)
    build = v2.get_study_build(build_id)
    entry = {**_entry(build, ""), "source_hash": None}
    write_link(case, target_of(api), entry)
    return entry


def install_skill(folder: str | Path = ".", force: bool = False) -> Path:
    """Copy the Claude Code skill ``/prisma-case`` into ``<folder>/.claude/skills/prisma-case/``."""
    dest = Path(folder) / ".claude" / "skills" / "prisma-case"
    if (dest / "SKILL.md").exists() and not force:
        raise FileExistsError(f"{dest / 'SKILL.md'} exists; pass force=True (--force) to replace it")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text((DOCS / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    return dest


# ── Command line ──────────────────────────────────────────────────────────────

_CHOICE_HELP = {
    "push": "send the local case to the draft", "publish": "send the local case and publish the v2 study",
    "fork": "send the local case as a new draft forked from the build (the build stays as it is)",
    "pull": "replace the local case with the build's design", "overwrite": "replace the draft's design with the local case",
    "unlink": "forget the link", "abort": "do nothing",
}


def _ask(st: Status, choices: list[str], args) -> str:
    """The action to take: --on-conflict when it applies, else a prompt in a terminal, else 'abort' (exit 2)."""
    if args.on_conflict and args.on_conflict in choices:
        return args.on_conflict
    if args.yes and len(choices) == 1:
        return choices[0]
    if not sys.stdin.isatty():
        return "abort"
    print(f"{st.case} [{st.target}]: {st.message}.")
    for i, c in enumerate(choices + ["abort"], 1):
        print(f"  {i}. {c:<9} {_CHOICE_HELP.get(c, '')}")
    ans = input("Choose: ").strip().lower()
    opts = choices + ["abort"]
    return opts[int(ans) - 1] if ans.isdigit() and 0 < int(ans) <= len(opts) else ans if ans in opts else "abort"


def _confirm(question: str, args) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def _print_entry(verb: str, entry: dict, args) -> None:
    if args.json:
        print(json.dumps({"done": verb, **entry}, indent=2))
        return
    print(f"{verb}: build {entry['build_id']} ({entry['status']})")
    for key in ("edit_url", "study_url"):
        if entry.get(key):
            print(f"  {key.replace('_', ' ')}: {entry[key]}")


def main(argv: list[str] | None = None, tool: str = "prisma_api", tool_version: str | None = None) -> int:
    """The prisma-case command. ``tool`` names the caller in the build's provenance (e.g. "prisma-v2") and
    ``tool_version`` its installed version; the case's repo, commit and release tag are read from its git checkout."""
    parser = argparse.ArgumentParser(prog="prisma-case", description=__doc__.strip().split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def server(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--dev", action="store_true", help="Local dev server (localhost:<dev_host_port>, dev_api_key)")
        g.add_argument("--prod", action="store_true", help="Production (prisma-platform.org)")
        p.add_argument("--json", action="store_true", help="Machine-readable output")

    def case_args(p):
        p.add_argument("case", help="The case's process-graph JSON, e.g. cases/dac_min/dac_min.json")
        p.add_argument("--study", help="Study settings file (default: <case>.study.yaml|json next to it)")
        server(p)

    p = sub.add_parser("status", help="Is the local case ahead of, behind or in step with its build?")
    case_args(p)
    for name, text in [("push", "Send the case to its draft (creates one if needed)"),
                       ("publish", "Send the case and publish the v2 study")]:
        p = sub.add_parser(name, help=text)
        case_args(p)
        p.add_argument("--yes", action="store_true", help="Do not ask before writing")
        p.add_argument("--on-conflict", choices=["fork", "pull", "overwrite", "abort"],
                       help="What to do when the build changed online or is published (default: ask)")
        p.add_argument("--name", help="Study name for a fork")
        p.add_argument("--dry-run", action="store_true",
                       help="Show the design the server would make, its checks and the sync state; write nothing")
    p = sub.add_parser("pull", help="Write the build's design into the local case")
    case_args(p)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true", help="Discard local changes made since the last sync")
    p.add_argument("--allow-placeholders", action="store_true", help="Pull nodes that have no platform model yet")
    p = sub.add_parser("fork", help="Send the local case as a new draft forked from its build")
    case_args(p)
    p.add_argument("--name", help="Study name (default '<name> rN')")
    p.add_argument("--publish", action="store_true", help="Publish the fork too")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("link", help="Link the case to an existing build")
    case_args(p)
    p.add_argument("build_id", type=int)
    p = sub.add_parser("unlink", help="Forget the link to the build on this server")
    case_args(p)
    p = sub.add_parser("list", help="Builds on the server (optionally for one case id)")
    server(p)
    p.add_argument("--case-id")
    p.add_argument("--status", choices=["draft", "published", "abandoned"])
    p = sub.add_parser("catalogue", help="Node catalogue and study choices the builder accepts")
    server(p)
    p = sub.add_parser("install-skill", help="Install the /prisma-case Claude Code skill into a folder")
    p.add_argument("folder", nargs="?", default=".")
    p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "install-skill":
        try:
            print(f"installed {install_skill(args.folder, args.force) / 'SKILL.md'}")
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    from . import init
    api = init(local_dev=args.dev)
    v2 = api.v2
    v2.set_return_format("json")
    from .prisma_api_v2 import PrismaConflictError
    try:
        if args.command == "list":
            out = v2.list_study_builds(status=args.status, case_id=args.case_id)
            if args.json:
                print(json.dumps(out, indent=2))
            else:
                for b in out["records"]:
                    case_id = (b.get("client") or {}).get("case_id") or "-"
                    print(f"{b['id']:>6}  {b['status']:<10} {case_id:<24} {b['title']}")
            return 0
        if args.command == "catalogue":
            out = v2.study_build_catalogue()
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                for c in out["catalogue"]:
                    print(f"{c['id']:<22} {c['group']:<12} {c['model_path'] or '(no model yet)'}")
            return 0
        if args.command == "unlink":
            write_link(args.case, target_of(api), None)
            print(f"unlinked {args.case} from {target_of(api)}")
            return 0
        if args.command == "link":
            _print_entry("linked", link(api, args.case, args.build_id), args)
            return 0

        st = check(api, args.case, args.study)
        if args.command == "status":
            if args.json:
                print(json.dumps(st.to_dict(), indent=2))
            else:
                print(f"{st.state}: {st.message}")
                if st.actions:
                    print(f"  next: {' / '.join(st.actions)}")
            return 0 if st.state == "in_sync" else 2 if st.state == "diverged" else 0

        if args.command in ("push", "publish"):
            publish = args.command == "publish"
            if args.dry_run:
                graph, settings = load_case(args.case, args.study)
                out = v2.create_study_build(graph=graph, study=settings, dry_run=True)
                report = {"status": st.to_dict(), "fixes": out["fixes"], "warns": out["warns"],
                          "design": {k: out["state"][k] for k in ("name", "desc", "locs", "time", "scen", "tea", "lca", "kpis")},
                          "nodes": [n["u"] for n in out["state"]["placed"]], "systems": [y["name"] for y in out["state"]["systems"]]}
                if args.json:
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print(f"{st.state}: {st.message}")
                    print(f"  study {report['design']['name']!r}: {len(report['nodes'])} nodes, systems {report['systems']}")
                    for f in out["fixes"]:
                        print(f"  must fix: {f}")
                    for w in out["warns"]:
                        print(f"  warning:  {w}")
                return 0
            if st.state in ("online_ahead", "diverged") or st.state == "local_ahead" and "fork" in st.actions:
                choice = _ask(st, [a for a in st.actions if a in ("fork", "pull", "overwrite")], args)
                if choice == "fork":
                    _print_entry("forked", fork(api, args.case, args.study, args.name, publish, tool=tool, tool_version=tool_version), args)
                elif choice == "pull":
                    _print_entry("pulled", pull(api, args.case, args.study, force=st.state == "diverged"), args)
                elif choice == "overwrite":
                    _print_entry("pushed", push(api, args.case, args.study, publish, overwrite=True, tool=tool, tool_version=tool_version), args)
                else:
                    print(f"{st.state}: {st.message}. Nothing done; choose with --on-conflict "
                          f"{'|'.join(st.actions)}", file=sys.stderr)
                    return 2
                return 0
            if st.state == "in_sync" and not (publish and st.build and st.build["status"] == "draft"):
                graph, _ = load_case(args.case, args.study)
                changes = {} if st.build["status"] != "draft" else provenance_changes(
                    st.build, _client_info(Path(args.case), graph, st.local_hash, tool, tool_version))
                if not changes:
                    if st.link.get("design_hash") != st.build["design_hash"]:
                        push(api, args.case, args.study, tool=tool, tool_version=tool_version)  # link only
                    print(f"in step with build {st.build['id']} ({st.build['status']}): nothing to send")
                    return 0
                what = f"refresh draft {st.build['id']}'s provenance (" + ", ".join(
                    f"{k} {a or '-'} -> {b}" for k, (a, b) in changes.items()) + ")"
            else:
                what = "create a draft" if st.state in ("unlinked", "missing") else f"update draft {st.build['id']}"
            if not _confirm(f"{what}{' and publish it' if publish else ''} on {st.target}?", args):
                print("Nothing sent (pass --yes to skip this question).", file=sys.stderr)
                return 2
            _print_entry("published" if publish else "pushed", push(api, args.case, args.study, publish, tool=tool, tool_version=tool_version), args)
            return 0

        if args.command == "pull":
            if st.state == "in_sync":
                print(f"in step with build {st.build['id']}: nothing to pull")
                return 0
            if not _confirm(f"{st.message}. Overwrite {args.case} with build {st.build['id']}?", args):
                print("Nothing written.", file=sys.stderr)
                return 2
            _print_entry("pulled", pull(api, args.case, args.study, args.allow_placeholders, args.force), args)
            return 0

        if args.command == "fork":
            if not _confirm(f"send {args.case} as a new draft forked from build {(st.build or {}).get('id')}?", args):
                print("Nothing sent.", file=sys.stderr)
                return 2
            _print_entry("forked", fork(api, args.case, args.study, args.name, args.publish, tool=tool, tool_version=tool_version), args)
            return 0
    except (SyncError, PrismaConflictError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except requests.HTTPError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
