"""
Bring your own dataset folder to the PrISMa platform as one zip.

You keep your files exactly as they are and add one file to the folder,
``prisma_manifest.yaml``, saying what each file is and where it goes on the
platform. prisma_api knows the package format but nothing about the
platform's tables: it asks the server which targets (tables) exist and what
fields they take (``prisma-dataset targets``), and the server, which checks
every package in full, is the authority on whether one applies.

    validate(root)               -> path, column and id problems found locally
    pack(root, out=...)          -> zip of the manifest, the files it reads and a
                                    listing of the whole folder
    upload(zip, local_dev=...)   -> the server's report (a dry run unless dry_run=False)

Command line, from your dataset folder::

    prisma-dataset guide                       # the manifest format
    prisma-dataset install-skill .             # a Claude Code skill that drafts the manifest with you
    prisma-dataset targets --prod              # what the platform can store, with fields and units
    prisma-dataset validate . --prod           # check the manifest against your files and the targets
    prisma-dataset pack . --out ../my_dataset.zip
    prisma-dataset upload ../my_dataset.zip --prod           # dry run: nothing is written
    prisma-dataset upload ../my_dataset.zip --prod --apply   # write

``--dev`` instead of ``--prod`` uses a local development server.

Path patterns: ``{name}`` captures part of one path segment (and may be reused
in run keys), ``*`` matches within a segment, ``**/`` any number of folders.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

MANIFEST_SCHEMA = "prisma.dataset.ingest.v1"
MANIFEST_NAME = "prisma_manifest.yaml"
#: Listing of the whole source folder (packed or not), shown on the platform's uploads page.
SOURCE_TREE_NAME = "prisma_source_tree.json"
SOURCE_TREE_SCHEMA = "prisma.dataset.source_tree.v1"
#: Format-level target: files deliberately not ingested. Every other target name
#: belongs to the server and comes from its catalogue (GET /datasets/targets/).
SKIP = "skip"
ROW_KINDS = {"rows", "run_rows"}
DOCS = Path(__file__).resolve().parent / "dataset_docs"
FORMATS = {".csv": "csv", ".json": "json", ".yaml": "yaml", ".yml": "yaml"}
_SKIP_DIR_NAMES = {".git", "__pycache__", "__MACOSX", ".ipynb_checkpoints"}
_SKIP_FILE_NAMES = {".DS_Store", "Thumbs.db"}
_TOKEN = re.compile(r"(\{\w+\}|\*\*/|\*\*|\*|\?)")

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


def compile_pattern(pattern: str) -> re.Pattern:
    """Path pattern -> regex (mirrors prisma_cloud dataset_ingest.compile_pattern)."""
    parts, seen = [], set()
    for tok in _TOKEN.split(pattern.strip().lstrip("/")):
        if not tok:
            continue
        if tok.startswith("{"):
            name = tok[1:-1]
            parts.append(f"(?P={name})" if name in seen else f"(?P<{name}>[^/]+?)")
            seen.add(name)
        elif tok == "**/":
            parts.append("(?:.*/)?")
        elif tok == "**":
            parts.append(".*")
        elif tok == "*":
            parts.append("[^/]*")
        elif tok == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(tok))
    return re.compile("^" + "".join(parts) + "$")


def list_files(root: Path) -> list[str]:
    """Every file under root (POSIX, relative), minus VCS/OS clutter and the manifest itself."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        rel = Path(dirpath).relative_to(root)
        for name in filenames:
            if name in _SKIP_FILE_NAMES or name.startswith("._"):
                continue
            if not rel.parts and name in (MANIFEST_NAME, "prisma_manifest.yml", "prisma_manifest.json"):
                continue
            out.append(str(PurePosixPath(*rel.parts, name)))
    return sorted(out)


def load_manifest(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh) if str(path).endswith(".json") else yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"{path}: the manifest must be a mapping")
    return data


def _manifest_path(root: Path, manifest: str | Path | None) -> Path:
    if manifest:
        return Path(manifest)
    for name in (MANIFEST_NAME, "prisma_manifest.yml", "prisma_manifest.json"):
        if (root / name).is_file():
            return root / name
    raise FileNotFoundError(f"no {MANIFEST_NAME} in {root}; pass --manifest")


def _run_matches(run: dict, where: dict, captures: dict) -> bool:
    for key, expected in where.items():
        expected = str(expected).format(**captures)
        actual = ((run.get("conditions") or {}).get(key.split(".", 1)[1])
                  if key.startswith("conditions.") else run.get(key))
        if str(actual) != expected:
            return False
    return True


def resolve(manifest: dict, files: list[str]) -> tuple[list[dict], list[str]]:
    """[{source, files: [{path, captures, runs}]}] plus binding errors."""
    errors: list[str] = []
    runs = {r.get("key"): r for r in manifest.get("runs") or [] if isinstance(r, dict)}
    claimed: dict[str, str] = {}
    out = []
    for src in manifest.get("sources") or []:
        sid = src.get("id")
        rx = compile_pattern(str(src.get("path", "")))
        excludes = [compile_pattern(str(p)) for p in src.get("exclude") or []]
        bound = []
        for path in files:
            m = rx.match(path)
            if not m or any(x.match(path) for x in excludes):
                continue
            captures = m.groupdict()
            if src.get("target") != "skip":
                if path in claimed:
                    errors.append(f"source '{sid}': '{path}' is also read by source '{claimed[path]}'")
                claimed[path] = sid
            run_keys: list[str] = []
            try:
                if src.get("run"):
                    run_keys = [str(src["run"]).format(**captures)]
                    if run_keys[0] not in runs:
                        errors.append(f"source '{sid}': '{path}' belongs to run '{run_keys[0]}', which is not declared")
                elif src.get("runs_where"):
                    run_keys = [k for k, r in runs.items() if _run_matches(r, src["runs_where"], captures)]
                    if not run_keys:
                        errors.append(f"source '{sid}': no run matches {src['runs_where']} for '{path}'")
            except (KeyError, IndexError) as exc:
                errors.append(f"source '{sid}': placeholder {exc} is not captured by path '{src.get('path')}'")
            bound.append({"path": path, "captures": captures, "runs": run_keys})
        if not bound:
            errors.append(f"source '{sid}': no file matches '{src.get('path')}'")
        out.append({"source": src, "files": bound})
    return out, errors


def _header_and_ids(path: Path, fmt: str, id_col: str) -> tuple[list[str], list[str]]:
    if fmt == "csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = [h.strip() for h in next(reader, [])]
            idx = header.index(id_col) if id_col in header else None
            ids = [row[idx].strip() for row in reader if idx is not None and len(row) > idx]
        return header, ids
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    records = [data] if isinstance(data, dict) else data
    header = list(dict.fromkeys(str(k).strip() for r in records if isinstance(r, dict) for k in r))
    ids = [str(r.get(id_col, "")).strip() for r in records if isinstance(r, dict)]
    return header, ids


def load_targets(source: str | Path | dict | None = None, api: Any = None) -> dict | None:
    """
    The server's target catalogue (``prisma.dataset.targets.v1``): a dict
    passed through, a JSON file saved with ``prisma-dataset targets --save``,
    or fetched with ``api`` (a client from ``prisma_api.init``). None if neither.
    """
    if isinstance(source, dict):
        return source
    if source:
        return json.loads(Path(source).read_text(encoding="utf-8"))
    if api is not None:
        return getattr(api, "v2", api).get_dataset_targets()
    return None


def _row_shaped(src: dict, targets: dict | None) -> bool:
    """Does this source map records (one per material) rather than a whole file?"""
    if targets:
        return (targets["targets"].get(src.get("target")) or {}).get("kind") in ROW_KINDS
    return src.get("target") != SKIP and not src.get("layout") and any(
        k in src for k in ("id_column", "columns", "match_field_names", "run", "runs_where"))


def validate(root: str | Path, manifest: str | Path | None = None,
             targets: str | Path | dict | None = None) -> dict:
    """
    Check a dataset folder against its manifest, before sending anything.

    Always checks: the manifest's shape, path patterns matching nothing,
    files read by two sources, undeclared runs and parameter sets, readable
    files with their id column, unmapped columns, repeated ids, and files no
    source mentions. With the server's ``targets`` catalogue (see
    :func:`load_targets`) it also checks target names, allowed keys and that
    mapped columns name real fields. ``ok`` is False when there are errors.
    The server's dry run remains the final word.
    """
    root = Path(root)
    catalogue = load_targets(targets)
    manifest_path = _manifest_path(root, manifest)
    data = load_manifest(manifest_path)
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("_schema") != MANIFEST_SCHEMA:
        errors.append(f"_schema must be '{MANIFEST_SCHEMA}'")
    if not (data.get("dataset") or {}).get("slug"):
        errors.append("dataset.slug is required")
    if catalogue is None:
        warnings.append("no target catalogue: target names and fields were not checked "
                        "(pass --prod/--dev, or --targets <saved catalogue>)")
    elif catalogue.get("manifest_schema") not in (None, MANIFEST_SCHEMA):
        warnings.append(f"the server reads manifests '{catalogue['manifest_schema']}', this prisma_api "
                        f"writes '{MANIFEST_SCHEMA}': upgrade prisma_api")
    sets = {s.get("key") for s in data.get("parameter_sets") or []}
    known = (catalogue or {}).get("targets") or {}
    ids_seen = Counter()
    for src in data.get("sources") or []:
        sid, target = src.get("id"), src.get("target")
        ids_seen[sid] += 1
        if target == SKIP and not src.get("reason"):
            errors.append(f"source '{sid}': say why the files are skipped ('reason')")
        if src.get("parameter_set") and src["parameter_set"] not in sets:
            errors.append(f"source '{sid}': parameter_set '{src['parameter_set']}' is not declared")
        if catalogue is None or target == SKIP:
            continue
        spec = known.get(target)
        if spec is None:
            errors.append(f"source '{sid}': the server has no target '{target}' "
                          f"(it has: {', '.join(sorted(known))}; see prisma-dataset targets)")
            continue
        for key in sorted(set(src) - set(spec.get("keys") or src)):
            errors.append(f"source '{sid}': key '{key}' is not used by target '{target}'")
        if spec.get("fields") is not None:
            for col, dest in (src.get("columns") or {}).items():
                if dest not in spec["fields"]:
                    errors.append(f"source '{sid}': column '{col}' maps to '{dest}', which target "
                                  f"'{target}' does not have")
    errors += [f"duplicate source id '{k}'" for k, n in ids_seen.items() if n > 1]

    files = list_files(root)
    resolved, bind_errors = resolve(data, files)
    errors += bind_errors

    strip = [str(s) for s in (data.get("material_id") or {}).get("strip_suffixes") or []]
    refs = {str(a).strip() for r in data.get("reference_systems") or []
            for a in [r.get("name"), *(r.get("aliases") or [])]}
    default_id = ((catalogue or {}).get("defaults") or {}).get("id_column")

    def norm(i: str) -> str:
        for s in strip:
            if s and i.endswith(s):
                return i[: -len(s)]
        return i

    ids_by_kind: dict[str, set[str]] = {"rows": set(), "run_rows": set()}
    summary = []
    mentioned: set[str] = set()
    for item in resolved:
        src = item["source"]
        mentioned.update(f["path"] for f in item["files"])
        records = 0
        if _row_shaped(src, catalogue):
            id_col = str(src.get("id_column") or default_id or "").strip()
            if not id_col:
                # The server's default id column is in its catalogue; without it the
                # id and column checks would only produce false alarms.
                warnings.append(f"source '{src['id']}': no id_column given, so its columns were not checked "
                                "(the server's default applies; pass the target catalogue to check them)")
                summary.append({"id": src.get("id"), "target": src.get("target"),
                                "files": len(item["files"]), "records": None})
                continue
            spec = known.get(src.get("target")) or {}
            fields = spec.get("fields")
            mapped = {str(c).strip() for c in (src.get("columns") or {})} \
                | {str(c).strip() for c in src.get("ignore_columns") or []} \
                | {str(c).strip() for c in (src.get("properties_columns") or {})} | {id_col}
            for f in item["files"]:
                fmt = src.get("format") or FORMATS.get(PurePosixPath(f["path"]).suffix.lower())
                try:
                    header, ids = _header_and_ids(root / f["path"], fmt, id_col or "\0")
                except (OSError, ValueError, UnicodeDecodeError) as exc:
                    errors.append(f"source '{src['id']}': cannot read '{f['path']}': {exc}")
                    continue
                if id_col and id_col not in header:
                    errors.append(f"source '{src['id']}': '{f['path']}' has no id column '{id_col}'")
                    continue
                for col in header:
                    if col in mapped:
                        continue
                    if src.get("match_field_names") and (fields is None or col in fields):
                        continue          # unknown without the catalogue: the server dry run decides
                    errors.append(f"source '{src['id']}': column '{col}' in '{f['path']}' is not mapped; "
                                  "add it to 'columns' or 'ignore_columns'")
                ids = [norm(i) for i in ids if i]
                dupes = [i for i, n in Counter(ids).items() if n > 1]
                if dupes:
                    warnings.append(f"source '{src['id']}': {len(dupes)} id(s) repeat in '{f['path']}', "
                                    f"e.g. {dupes[:3]} (the server rejects differing repeats)")
                records += len(ids)
                if spec.get("kind") in ids_by_kind:
                    ids_by_kind[spec["kind"]].update(i for i in ids if i not in refs)
        summary.append({"id": src.get("id"), "target": src.get("target"),
                        "files": len(item["files"]), "records": records})
    if ids_by_kind["rows"]:
        orphans = sorted(ids_by_kind["run_rows"] - ids_by_kind["rows"])
        if orphans:
            warnings.append(f"{len(orphans)} id(s) have run rows but no per-material row, e.g. {orphans[:5]} "
                            f"(material_id.on_missing: {(data.get('material_id') or {}).get('on_missing', 'create')})")
    unmentioned = [f for f in files if f not in mentioned]
    if unmentioned:
        warnings.append(f"{len(unmentioned)} file(s) are not mentioned by any source (not packed), "
                        f"e.g. {unmentioned[:5]}")
    return {
        "ok": not errors, "manifest": str(manifest_path), "root": str(root),
        "files_total": len(files), "sources": summary, "targets_checked": catalogue is not None,
        "unmentioned_files": unmentioned, "errors": errors, "warnings": warnings,
    }


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              check=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tag_list(tag: Any) -> list[str]:
    names = [tag] if isinstance(tag, str) else list(tag or [])
    return [str(n).strip() for n in names if str(n).strip()]


def pack(root: str | Path, manifest: str | Path | None = None, out: str | Path = "package.zip",
         allow_errors: bool = False, targets: str | Path | dict | None = None,
         tags: list[str] | str | None = None) -> dict:
    """
    Validate, then zip the manifest and every file a non-skip source reads
    (plus skip sources with ``pack: true``) under their package paths.

    The packed manifest gains ``package.git_commit`` / ``git_dirty`` /
    ``packed_at`` / ``packed_by`` from the folder's git state and a ``files``
    map of sha256 checksums, which the server verifies. Returns the
    validation report plus ``zip``, ``zip_bytes`` and ``files_packed``.

    ``tags`` adds tag names to the manifest's ``dataset.tag``; the platform
    tags everything the package writes with all of them.
    """
    root = Path(root)
    report = validate(root, manifest, targets)
    if Path(out).resolve().parent == root.resolve() or root.resolve() in Path(out).resolve().parents:
        report["warnings"].append("the zip is written inside the dataset folder; it will show up in the "
                                  "next pack's file listing (write it next to the folder instead)")
    if not report["ok"] and not allow_errors:
        raise ValueError("package does not validate:\n  " + "\n  ".join(report["errors"][:20]))
    data = load_manifest(report["manifest"])
    all_files = list_files(root)
    resolved, _ = resolve(data, all_files)
    paths = sorted({f["path"] for item in resolved
                    if item["source"].get("target") != "skip" or item["source"].get("pack")
                    for f in item["files"]})
    package = dict(data.get("package") or {})
    commit = _git(root, "rev-parse", "HEAD")
    if commit:
        package["git_commit"] = commit
        package["git_dirty"] = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
        package.setdefault("git_repo", _git(root, "config", "--get", "remote.origin.url"))
    package["packed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    package["packed_by"] = getpass.getuser()
    data["package"] = package
    all_tags = list(dict.fromkeys(_tag_list((data.get("dataset") or {}).get("tag")) + _tag_list(tags)))
    if all_tags:
        data.setdefault("dataset", {})["tag"] = all_tags[0] if len(all_tags) == 1 else all_tags
    data["files"] = {p: _sha256(root / p) for p in paths}

    out = Path(out)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(MANIFEST_NAME, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        zf.writestr(SOURCE_TREE_NAME, json.dumps(source_tree(root, all_files, resolved, data["files"])))
        for p in paths:
            zf.write(root / p, arcname=p)
    report.update(zip=str(out), zip_bytes=out.stat().st_size, files_packed=len(paths), package=package,
                  tags=all_tags)
    return report


def source_tree(root: Path, files: list[str], resolved: list[dict], checksums: dict[str, str]) -> dict:
    """
    Every file of the source folder with its size and what the manifest does
    with it: ``read`` (by a source, packed), ``skipped`` (a skip source, with
    its reason) or ``unmentioned``. The platform shows this tree on the
    uploads page, where staff choose per file whether it is in the dataset and
    whether its data is by others (kept out of Zenodo). The server re-derives
    the status from the manifest; this copy is informational.
    """
    status: dict[str, dict] = {}
    for item in resolved:
        src = item["source"]
        for f in item["files"]:
            if src.get("target") == "skip":
                status.setdefault(f["path"], {"status": "skipped", "source": src.get("id"),
                                              "reason": src.get("reason", "")})
            else:
                status[f["path"]] = {"status": "read", "source": src.get("id"), "target": src.get("target")}
    entries = []
    for path in files:
        entry = {"path": path, "size": (root / path).stat().st_size,
                 **status.get(path, {"status": "unmentioned"})}
        if path in checksums:
            entry["sha256"] = checksums[path]
        entries.append(entry)
    return {"_schema": SOURCE_TREE_SCHEMA, "root": root.resolve().name, "files": entries,
            "total_files": len(entries), "total_bytes": sum(e["size"] for e in entries)}


def upload(zip_path: str | Path, dry_run: bool = True, api: Any = None, timeout: int = 1800,
           local_dev: bool | None = None, tags: list[str] | str | None = None) -> dict:
    """
    Send a packed zip; returns the server report (``ok: false`` with errors when rejected).

    Pass a client as ``api``, or ``local_dev=True`` (dev server on
    ``localhost:<dev_host_port>`` with ``dev_api_key``) / ``local_dev=False``
    (production). With neither, it refuses rather than guess the target.
    ``tags`` adds tag names to those in the packed manifest.
    """
    if api is None:
        if local_dev is None:
            raise ValueError("say where to upload: pass api=..., or local_dev=True (dev) / False (production)")
        from . import init
        api = init(local_dev=local_dev)
    v2 = getattr(api, "v2", api)
    return v2.ingest_dataset(str(zip_path), dry_run=dry_run, timeout=timeout, tags=_tag_list(tags))


def _print_report(report: dict) -> None:
    for key in ("zip", "zip_bytes", "files_packed", "files_read", "dry_run", "tags", "sync_run"):
        if key in report:
            print(f"{key}: {report[key]}")
    for src in report.get("sources") or []:
        print(f"  {src['id']:<28} {src['target']:<11} files {src['files']:>6}  records {src.get('records', 0)}")
    for model, counts in (report.get("counts") or {}).items():
        print(f"  {model:<18} " + "  ".join(f"{k} {v}" for k, v in counts.items()))
    for w in report.get("warnings") or []:
        print(f"  warning: {w}")
    for e in report.get("errors") or []:
        print(f"  ERROR: {e}")
    print("OK" if report.get("ok") else "REJECTED")


def guide() -> str:
    """The manifest format guide shipped with prisma_api."""
    return (DOCS / "manifest_guide.md").read_text(encoding="utf-8")


def install_skill(folder: str | Path = ".", force: bool = False) -> Path:
    """
    Copy the Claude Code skill for writing a manifest into ``<folder>/.claude/skills/prisma-dataset/``.

    Run Claude Code in the dataset folder afterwards and ask it to prepare the
    folder for PrISMa (or type ``/prisma-dataset``). The manifest guide is
    copied next to the skill so it works offline.
    """
    dest = Path(folder) / ".claude" / "skills" / "prisma-dataset"
    if (dest / "SKILL.md").exists() and not force:
        raise FileExistsError(f"{dest / 'SKILL.md'} exists; pass force=True (--force) to replace it")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("SKILL.md", "manifest_guide.md"):
        (dest / name).write_text((DOCS / name).read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def _client(dev: bool, prod: bool):
    if not (dev or prod):
        return None
    from . import init
    return init(local_dev=dev)


def _print_targets(catalogue: dict) -> None:
    print(f"manifest schema: {catalogue.get('manifest_schema')}")
    for name, spec in sorted(catalogue["targets"].items()):
        print(f"\n{name}  [{spec.get('kind')}]  {spec.get('description', '')}")
        fields = spec.get("fields")
        if fields is None:
            if spec.get("kind") in ROW_KINDS:
                print("  fields: any names you choose (give their units in 'units')")
            continue
        for field, info in fields.items():
            print(f"  {field:<36} {info.get('type', ''):<6} {info.get('help', '')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prisma-dataset", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def server_flags(p, required: bool):
        g = p.add_mutually_exclusive_group(required=required)
        g.add_argument("--dev", action="store_true",
                       help="Local dev server: localhost:<dev_host_port> with dev_api_key from config.yaml")
        g.add_argument("--prod", action="store_true", help="Production (prisma-platform.org)")
        return g

    for name in ("validate", "pack"):
        p = sub.add_parser(name, help=f"{name.capitalize()} a dataset folder")
        p.add_argument("root", help="The dataset folder")
        p.add_argument("--manifest", help=f"Manifest file (default: <root>/{MANIFEST_NAME})")
        server_flags(p, required=False).add_argument(
            "--targets", help="A target catalogue saved with 'prisma-dataset targets --save' (works offline)")
        p.add_argument("--json", action="store_true", help="Print the report as JSON")
        if name == "pack":
            p.add_argument("--out", default="package.zip", help="Zip to write (put it next to the folder, not in it)")
            p.add_argument("--tag", action="append", default=[], metavar="NAME",
                           help="Tag the dataset's records with NAME (adds to dataset.tag; repeatable)")
    p = sub.add_parser("upload", help="Send a packed zip (a dry run unless --apply)")
    p.add_argument("zip")
    p.add_argument("--apply", action="store_true", help="Write (default: dry run)")
    p.add_argument("--tag", action="append", default=[], metavar="NAME",
                   help="Also tag the records with NAME (adds to the packed manifest's tags; repeatable)")
    server_flags(p, required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("targets", help="What the platform can store: targets, fields and units")
    server_flags(p, required=True)
    p.add_argument("--save", help="Also save the catalogue to this JSON file (for offline validate)")
    p.add_argument("--json", action="store_true")
    sub.add_parser("guide", help="Print the manifest format guide")
    p = sub.add_parser("install-skill", help="Add a Claude Code skill that drafts the manifest with you")
    p.add_argument("folder", nargs="?", default=".", help="The dataset folder (default: here)")
    p.add_argument("--force", action="store_true", help="Replace an existing copy")
    args = parser.parse_args(argv)

    if args.command == "guide":
        print(guide())
        return 0
    if args.command == "install-skill":
        try:
            dest = install_skill(args.folder, args.force)
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"installed: {dest}\nIn that folder, run Claude Code and type /prisma-dataset.")
        return 0
    if args.command == "targets":
        catalogue = load_targets(api=_client(args.dev, args.prod))
        if args.save:
            Path(args.save).write_text(json.dumps(catalogue, indent=2), encoding="utf-8")
        if args.json:
            print(json.dumps(catalogue, indent=2))
        else:
            _print_targets(catalogue)
        return 0

    if args.command == "upload":
        report = upload(args.zip, dry_run=not args.apply, local_dev=args.dev, tags=args.tag)
        print(f"target: {'dev server' if args.dev else 'PRODUCTION'}")
    else:
        targets = load_targets(args.targets, api=_client(args.dev, args.prod))
        if args.command == "validate":
            report = validate(args.root, args.manifest, targets)
        else:
            try:
                report = pack(args.root, args.manifest, args.out, targets=targets, tags=args.tag)
            except ValueError as exc:
                print(exc, file=sys.stderr)
                return 1
    if getattr(args, "json", False):
        print(json.dumps({k: v for k, v in report.items() if k != "unmentioned_files"}, indent=2, default=str))
    else:
        _print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
