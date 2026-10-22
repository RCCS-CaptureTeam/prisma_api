"""
Compose and check third-party dataset packages for the PrISMa platform.

A package is the authors' files as they are plus a ``prisma_manifest.yaml``
(schema ``prisma.dataset.ingest.v1``) saying what each file is and where it
goes. The server (ingest pipeline 15, ``POST /api/v2/datasets/ingest/``) is
the authority on whether a package applies; this module catches what it can
locally and builds the zip:

    validate(root, manifest)    -> report of path, column and id problems
    pack(root, manifest, out)   -> zip with the manifest (package + checksums
                                   filled in) and only the files it reads
    upload(zip, dry_run=True)   -> the server's report (via api.v2.ingest_dataset)

Command line::

    prisma-dataset validate ../Hydrogen_v2 --manifest integration/datasets/hydrogen_v2/prisma_manifest.yaml
    prisma-dataset pack ../Hydrogen_v2 --manifest ... --out hydrogen_v2.zip
    prisma-dataset upload hydrogen_v2.zip [--apply]     # target: prisma_api.update_dev_mode()

Path patterns: ``{name}`` captures part of one path segment (and may be reused
in run keys), ``*`` matches within a segment, ``**/`` any number of folders.
The same rules run on the server (prisma_cloud dataset_ingest.compile_pattern).
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
ROW_TARGETS = {"mof_h2", "h2_results", "run_inputs"}
TARGETS = ROW_TARGETS | {"parameters", "skip"}
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
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        rel = Path(dirpath).relative_to(root)
        for name in filenames:
            if name in _SKIP_FILE_NAMES or name.startswith("._"):
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


def validate(root: str | Path, manifest: str | Path | None = None) -> dict:
    """
    Check a package folder against its manifest, without the server.

    Reports: unknown targets and undeclared runs/parameter sets, patterns
    matching nothing, files read by two sources, missing id columns, columns
    the manifest does not map (where it can tell), repeated ids per file,
    material ids missing from the feature sources, and files no source
    mentions. ``ok`` is False when there are errors.
    """
    root = Path(root)
    manifest_path = _manifest_path(root, manifest)
    data = load_manifest(manifest_path)
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("_schema") != MANIFEST_SCHEMA:
        errors.append(f"_schema must be '{MANIFEST_SCHEMA}'")
    if not (data.get("dataset") or {}).get("slug"):
        errors.append("dataset.slug is required")
    sets = {s.get("key") for s in data.get("parameter_sets") or []}
    ids_seen = Counter()
    for src in data.get("sources") or []:
        ids_seen[src.get("id")] += 1
        if src.get("target") not in TARGETS:
            errors.append(f"source '{src.get('id')}': target must be one of {sorted(TARGETS)}")
        if src.get("target") == "parameters" and src.get("parameter_set") not in sets:
            errors.append(f"source '{src.get('id')}': parameter_set '{src.get('parameter_set')}' is not declared")
        if src.get("target") == "skip" and not src.get("reason"):
            errors.append(f"source '{src.get('id')}': say why the files are skipped ('reason')")
    errors += [f"duplicate source id '{k}'" for k, n in ids_seen.items() if n > 1]

    files = list_files(root)
    resolved, bind_errors = resolve(data, files)
    errors += bind_errors

    strip = [str(s) for s in (data.get("material_id") or {}).get("strip_suffixes") or []]
    refs = {str(a).strip() for r in data.get("reference_systems") or []
            for a in [r.get("name"), *(r.get("aliases") or [])]}

    def norm(i: str) -> str:
        for s in strip:
            if s and i.endswith(s):
                return i[: -len(s)]
        return i

    feature_ids: set[str] = set()
    result_ids: Counter = Counter()
    summary = []
    mentioned: set[str] = set()
    for item in resolved:
        src = item["source"]
        mentioned.update(f["path"] for f in item["files"])
        records = 0
        if src.get("target") in ROW_TARGETS:
            id_col = str(src.get("id_column") or "MOF").strip()
            mapped = {str(c).strip() for c in (src.get("columns") or {})} \
                | {str(c).strip() for c in src.get("ignore_columns") or []} \
                | {str(c).strip() for c in (src.get("properties_columns") or {})} | {id_col}
            for f in item["files"]:
                fmt = src.get("format") or FORMATS.get(PurePosixPath(f["path"]).suffix.lower())
                try:
                    header, ids = _header_and_ids(root / f["path"], fmt, id_col)
                except (OSError, ValueError, UnicodeDecodeError) as exc:
                    errors.append(f"source '{src['id']}': cannot read '{f['path']}': {exc}")
                    continue
                if id_col not in header:
                    errors.append(f"source '{src['id']}': '{f['path']}' has no id column '{id_col}'")
                    continue
                if not src.get("match_field_names"):
                    for col in header:
                        if col not in mapped:
                            errors.append(f"source '{src['id']}': column '{col}' in '{f['path']}' is not mapped")
                ids = [norm(i) for i in ids if i]
                dupes = [i for i, n in Counter(ids).items() if n > 1]
                if dupes:
                    warnings.append(f"source '{src['id']}': {len(dupes)} id(s) repeat in '{f['path']}', "
                                    f"e.g. {dupes[:3]} (the server rejects differing repeats)")
                records += len(ids)
                if src["target"] == "mof_h2":
                    feature_ids.update(i for i in ids if i not in refs)
                else:
                    result_ids.update(i for i in ids if i not in refs)
        summary.append({"id": src.get("id"), "target": src.get("target"),
                        "files": len(item["files"]), "records": records})
    if feature_ids:
        orphans = sorted(set(result_ids) - feature_ids)
        if orphans:
            warnings.append(f"{len(orphans)} material id(s) have results or inputs but no features, "
                            f"e.g. {orphans[:5]} (on_missing: {(data.get('material_id') or {}).get('on_missing', 'create')})")
    unmentioned = [f for f in files if f not in mentioned]
    if unmentioned:
        warnings.append(f"{len(unmentioned)} file(s) are not mentioned by any source (not packed), "
                        f"e.g. {unmentioned[:5]}")
    return {
        "ok": not errors, "manifest": str(manifest_path), "root": str(root),
        "files_total": len(files), "sources": summary,
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


def pack(root: str | Path, manifest: str | Path | None = None, out: str | Path = "package.zip",
         allow_errors: bool = False) -> dict:
    """
    Validate, then zip the manifest and every file a non-skip source reads
    (plus skip sources with ``pack: true``) under their package paths.

    The packed manifest gains ``package.git_commit`` / ``git_dirty`` /
    ``packed_at`` / ``packed_by`` from the folder's git state and a ``files``
    map of sha256 checksums, which the server verifies. Returns the
    validation report plus ``zip``, ``zip_bytes`` and ``files_packed``.
    """
    root = Path(root)
    report = validate(root, manifest)
    if not report["ok"] and not allow_errors:
        raise ValueError("package does not validate:\n  " + "\n  ".join(report["errors"][:20]))
    data = load_manifest(report["manifest"])
    resolved, _ = resolve(data, list_files(root))
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
    data["files"] = {p: _sha256(root / p) for p in paths}

    out = Path(out)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(MANIFEST_NAME, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        for p in paths:
            zf.write(root / p, arcname=p)
    report.update(zip=str(out), zip_bytes=out.stat().st_size, files_packed=len(paths), package=package)
    return report


def upload(zip_path: str | Path, dry_run: bool = True, api: Any = None, timeout: int = 1800) -> dict:
    """Send a packed zip; returns the server report (``ok: false`` with errors when rejected)."""
    if api is None:
        from . import init
        api = init()
    v2 = getattr(api, "v2", api)
    return v2.ingest_dataset(str(zip_path), dry_run=dry_run, timeout=timeout)


def _print_report(report: dict) -> None:
    for key in ("zip", "zip_bytes", "files_packed", "files_read", "dry_run", "sync_run"):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prisma-dataset", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "pack"):
        p = sub.add_parser(name)
        p.add_argument("root", help="Package folder (the authors' repository)")
        p.add_argument("--manifest", help=f"Manifest file (default: <root>/{MANIFEST_NAME})")
        p.add_argument("--json", action="store_true", help="Print the report as JSON")
        if name == "pack":
            p.add_argument("--out", default="package.zip")
    p = sub.add_parser("upload")
    p.add_argument("zip")
    p.add_argument("--apply", action="store_true", help="Write (default: dry run)")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "validate":
        report = validate(args.root, args.manifest)
    elif args.command == "pack":
        try:
            report = pack(args.root, args.manifest, args.out)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    else:
        # Prod or the local dev server, as set with prisma_api.update_dev_mode().
        report = upload(args.zip, dry_run=not args.apply)
    if getattr(args, "json", False):
        print(json.dumps({k: v for k, v in report.items() if k != "unmentioned_files"}, indent=2, default=str))
    else:
        _print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
