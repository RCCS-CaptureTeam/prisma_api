"""
Send v1 case-study screening results to the PrISMa platform, one batch at a time.

A batch is a folder of screening results, e.g. PrISMa_Platform's
``results/screening_results/physisorbent_paper_liquefaction_26``, laid out as
``Screening_{Source}/{CaseStudy}/{ProcessConditions}/{Simulated|Analytical}/``.
Each batch is packed into its own zip, holding only the ``*_L2-KPIs.csv`` and
``*_L2_screening-Analysis.csv`` files the platform reads, under the batch
folder's name, and sent to ingest pipeline 13. On the platform every case
study / conditions / type of the batch becomes a scenario of that batch (the
study page's scenario picker), so batches that ran the same conditions are
kept side by side. Sending a batch again replaces its rows.

    scan(root)                 -> the batches under root and their files
    repeats(batches)           -> scenarios that appear in more than one batch
    pack(batch, out)           -> the batch's zip
    send(batches, api)         -> the server's report for each batch

Command line::

    prisma-outputs list ../PrISMa_Platform/results/screening_results
    prisma-outputs send ../PrISMa_Platform/results/screening_results --dev --batch prisma_paper_v1
    prisma-outputs send ../PrISMa_Platform/results/screening_results --dev --all

There is no dry run on the server: ``list`` shows what would be sent, and
``send`` asks before writing unless ``--yes``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

KPI_SUFFIX = "_L2-KPIs.csv"
ANALYSIS_SUFFIX = "_L2_screening-Analysis.csv"
# The platform drops this from case-study folder names before matching them.
_YEAR_MEAN = re.compile(r"(_\d{4})?_year_mean$", re.IGNORECASE)


@dataclass
class Batch:
    name: str
    path: Path
    files: list[str] = field(default_factory=list)      # paths relative to the batch folder
    skipped: list[str] = field(default_factory=list)    # result files not in the layout the platform reads

    @property
    def size(self) -> int:
        return sum((self.path / f).stat().st_size for f in self.files)

    @property
    def scenarios(self) -> set[tuple[str, str, str]]:
        """(case study, process conditions, type) of each KPI file, as the platform names them."""
        out = set()
        for f in self.files:
            if f.endswith(KPI_SUFFIX):
                _, case, cond, kind, _ = Path(f).parts
                out.add((_YEAR_MEAN.sub("", case).strip("_"), cond, kind))
        return out


def _is_batch(path: Path) -> bool:
    return any(p.is_dir() and p.name.startswith("Screening_") for p in path.iterdir())


def read_batch(path: str | Path) -> Batch:
    path = Path(path)
    batch = Batch(path.name, path)
    for f in sorted(path.rglob("*")):
        if not f.is_file() or not f.name.endswith((KPI_SUFFIX, ANALYSIS_SUFFIX)) or f.name.startswith("."):
            continue
        rel = f.relative_to(path)
        if len(rel.parts) == 5 and rel.parts[0].startswith("Screening_"):
            batch.files.append(rel.as_posix())
        else:
            batch.skipped.append(rel.as_posix())
    return batch


def scan(root: str | Path) -> list[Batch]:
    """The batches in ``root``: root itself when it holds Screening_* folders, else each such subfolder."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"{root} is not a folder")
    if _is_batch(root):
        return [read_batch(root)]
    return [read_batch(p) for p in sorted(root.iterdir())
            if p.is_dir() and not p.name.startswith(".") and _is_batch(p)]


def repeats(batches: list[Batch]) -> dict[tuple[str, str, str], list[str]]:
    """Scenarios found in more than one batch, with the batches (each is kept as its own scenario)."""
    seen: dict[tuple[str, str, str], list[str]] = {}
    for b in batches:
        for key in b.scenarios:
            seen.setdefault(key, []).append(b.name)
    return {k: v for k, v in sorted(seen.items()) if len(v) > 1}


def pack(batch: Batch, out: str | Path) -> Path:
    """Zip the batch's files under its folder name, as the platform expects."""
    out = Path(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in batch.files:
            zf.write(batch.path / f, f"{batch.name}/{f}")
    return out


def send(batches: list[Batch], api: Any, keep: str | Path | None = None,
         progress: Callable[[str], None] = print) -> list[dict]:
    """Pack and send each batch in turn; returns the server's report for each.

    ``keep`` is a folder to leave the zips in (default: temporary files).
    A batch with no files is skipped.
    """
    v2 = getattr(api, "v2", api)
    reports = []
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(keep) if keep else Path(tmp)
        folder.mkdir(parents=True, exist_ok=True)
        for b in batches:
            if not b.files:
                progress(f"{b.name}: no result files, skipped")
                continue
            progress(f"{b.name}: packing {len(b.files)} files …")
            zipped = pack(b, folder / f"{b.name}.zip")
            progress(f"{b.name}: sending {zipped.stat().st_size / 1e6:.1f} MB …")
            report = v2.ingest_screening_outputs(str(zipped))
            reports.append({"batch": b.name, **report})
            progress(summary(report, b.name))
    return reports


def summary(report: dict, name: str) -> str:
    scenarios = report.get("scenarios") or []
    lines = [f"{name}: {'ok' if report.get('ok') else 'PROBLEMS'} · {len(scenarios)} scenarios "
             f"({sum(1 for s in scenarios if s.get('created'))} new) · "
             f"{sum(s.get('rows') or 0 for s in scenarios)} rows · upload #{report.get('zip_upload')}"]
    lines += [f"  warning: {w}" for w in report.get("warnings") or []]
    lines += [f"  error: {e.get('file')}: {e.get('error')}" for e in report.get("errors") or []]
    return "\n".join(lines)


def _print_listing(batches: list[Batch]) -> None:
    width = max([len(b.name) for b in batches] + [5])
    print(f"{'batch':{width}}  files  scenarios      MB")
    for b in batches:
        print(f"{b.name:{width}}  {len(b.files):5d}  {len(b.scenarios):9d}  {b.size / 1e6:6.1f}"
              + (f"   ({len(b.skipped)} result files outside the layout, not sent)" if b.skipped else ""))
    rep = repeats(batches)
    total = len(set().union(*(b.scenarios for b in batches))) if batches else 0
    print(f"\n{total} scenarios; {len(rep)} appear in more than one batch (each batch keeps its own).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prisma-outputs", description=__doc__.split("\n\n")[0].strip())
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="The batches in a folder: files, scenarios and size (nothing is sent)")
    p.add_argument("root", help="results/screening_results, or one batch folder")
    p.add_argument("--repeats", action="store_true", help="Also list the scenarios found in several batches")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("send", help="Pack and send batches (writes; asks first unless --yes)")
    p.add_argument("root", help="results/screening_results, or one batch folder")
    which = p.add_mutually_exclusive_group()
    which.add_argument("--batch", action="append", default=[], metavar="NAME",
                       help="Send this batch (repeatable; sent in the order given)")
    which.add_argument("--all", action="store_true", help="Send every batch, in name order")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dev", action="store_true",
                   help="Local dev server: localhost:<dev_host_port> with dev_api_key from config.yaml")
    g.add_argument("--prod", action="store_true", help="Production (prisma-platform.org)")
    p.add_argument("--keep", metavar="DIR", help="Keep the zips in DIR (default: temporary files)")
    p.add_argument("--yes", action="store_true", help="Do not ask before sending")
    p.add_argument("--json", action="store_true", help="Print the reports as JSON")
    args = parser.parse_args(argv)

    try:
        batches = scan(args.root)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not batches:
        print(f"no batches in {args.root} (a batch holds Screening_* folders)", file=sys.stderr)
        return 1

    if args.command == "list":
        if args.json:
            print(json.dumps([{"batch": b.name, "files": len(b.files), "scenarios": len(b.scenarios),
                               "bytes": b.size, "skipped": b.skipped} for b in batches], indent=2))
        else:
            _print_listing(batches)
            if args.repeats:
                for (case, cond, kind), names in repeats(batches).items():
                    print(f"  {case} · {cond} · {kind}: {', '.join(names)}")
        return 0

    by_name = {b.name: b for b in batches}
    if args.all:
        chosen = batches
    elif args.batch:
        missing = [n for n in args.batch if n not in by_name]
        if missing:
            print(f"no such batch: {', '.join(missing)} (see 'prisma-outputs list {args.root}')", file=sys.stderr)
            return 1
        chosen = [by_name[n] for n in args.batch]
    elif len(batches) == 1:
        chosen = batches
    else:
        print("say which batches: --batch NAME (repeatable) or --all", file=sys.stderr)
        return 1

    target = "the dev server" if args.dev else "PRODUCTION"
    files = sum(len(b.files) for b in chosen)
    if not args.yes:
        print(f"Send {len(chosen)} batch(es), {files} files, to {target}? "
              "Each replaces the rows of the scenarios it holds.")
        if input("[y/N] ").strip().lower() not in ("y", "yes"):
            print("nothing sent")
            return 1

    from . import init
    api = init(local_dev=args.dev)
    reports = send(chosen, api, keep=args.keep, progress=(lambda _m: None) if args.json else print)
    if args.json:
        print(json.dumps(reports, indent=2, default=str))
    return 0 if all(r.get("ok") for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
