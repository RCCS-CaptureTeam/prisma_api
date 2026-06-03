"""
Cross-check script: cases bundle — dev vs production
=====================================================
Fetches the full cases bundle (CaseStudy + all related objects + Property
records) from both the dev instance and the production service for one or
more cases, then reports any difference right down to individual Property
values.

The bundle structure checked is:

    CaseStudy
    ├── source        → Source         + properties (GFK)
    ├── sink          → Sink            + properties (GFK)
    ├── region        → Region          + properties (GFK, ambient params)
    ├── utilities     → Utility[]       + properties (GFK) each
    ├── subsystems    → Subsystem[]     + properties (GFK) each
    └── scenarios     → Scenario[]
            └── process_conditions → ProcessConditions + properties (GFK)
                        └── configurations → ProcessConfiguration[] + properties (GFK)

Usage
-----
    # Check by case name substring (checks all matching cases)
    python tests/crosscheck_cases_bundle.py --name "UK Coal"

    # Check by source / sink / region filter
    python tests/crosscheck_cases_bundle.py --source DAC --region GB

    # Check first N cases from dev
    python tests/crosscheck_cases_bundle.py --n 3

    # Combine filters
    python tests/crosscheck_cases_bundle.py --name carbfix --n 5 --json

Arguments
---------
--name NAME          Substring filter on case name (client-side).
--source SOURCE      Substring filter on source name (server-side).
--sink SINK          Substring filter on sink name (server-side).
--region REGION      Exact ISO region code filter (server-side).
--n N                Maximum number of cases to check (default: 5).
--dev-host-port      HOST:PORT of the local dev server.
                     Falls back to dev_host_port in config.yaml.
--key KEY            PrISMa API key (falls back to config.yaml).
--json               Emit results as JSON to stdout.

Exit codes
----------
0  all checked cases match exactly between dev and prod
1  differences found or an error occurred
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import prisma_api
from prisma_api.prisma_api_v2 import PrismaAPIv2
from prisma_api.config import load_config
from tests.crosscheck_dev_vs_prod import _to_json, _diff_excerpt


# ── Colour helpers ────────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _USE_COLOUR else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _USE_COLOUR else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _USE_COLOUR else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _USE_COLOUR else s


def _header(title: str) -> str:
    line = "═" * 72
    return f"\n{_bold(line)}\n{_bold(title)}\n{_bold(line)}"


# ── Normalisation ─────────────────────────────────────────────────────────────

_PK_FIELDS = frozenset({"id", "object_id", "content_type_id", "content_type"})
_FK_SENTINEL = "<set>"
_TS_SUFFIXES = ("_at", "_on", "_date", "_time", "_created", "_updated",
                "_modified", "_timestamp")
_TS_EXACT    = frozenset({"date_created", "date_updated", "date_modified",
                           "created", "updated", "modified", "timestamp",
                           "last_modified", "created_at", "updated_at"})


def _is_timestamp_field(key: str) -> bool:
    kl = key.lower()
    return kl in _TS_EXACT or any(kl.endswith(s) for s in _TS_SUFFIXES)


def _normalise_record(rec: Any) -> Any:
    """
    Strip PK / GFK / timestamp fields from a record dict so that two records
    that are semantically identical but live in different databases (or were
    created at different times) compare equal.

    - ``id``, ``object_id``, ``content_type_id``, ``content_type`` → dropped
    - ``*_id`` integer FK fields                                    → "<set>"
    - timestamp / date fields (date_created, updated_at, …)        → dropped
    - Nested lists / dicts are recursed into.
    """
    if isinstance(rec, list):
        normalised = [_normalise_record(r) for r in rec]
        # Sort by 'name' field if present, otherwise fall back to full JSON repr
        # so that property lists compare alphabetically by name on both sides.
        def _sort_key(x: Any) -> str:
            if isinstance(x, dict) and "name" in x:
                return str(x["name"]).lower()
            return json.dumps(x, sort_keys=True, default=str)
        return sorted(normalised, key=_sort_key)
    if isinstance(rec, dict):
        out: dict = {}
        for k, v in rec.items():
            if k in _PK_FIELDS:
                continue
            if _is_timestamp_field(k):
                continue
            if isinstance(v, int) and k.endswith("_id"):
                out[k] = _FK_SENTINEL
            else:
                out[k] = _normalise_record(v)
        return {k: out[k] for k in sorted(out)}
    return rec


def _canon(obj: Any) -> str:
    return json.dumps(_normalise_record(obj), sort_keys=True, default=str)


# ── Diff helpers ──────────────────────────────────────────────────────────────

def _compare(label: str, dev_obj: Any, prod_obj: Any, results: list[dict]) -> bool:
    """
    Compare dev_obj vs prod_obj after normalisation.
    Appends a result dict to *results* and returns True if they match.
    """
    dev_s  = _canon(dev_obj)
    prod_s = _canon(prod_obj)
    if dev_s == prod_s:
        results.append({"path": label, "status": "match"})
        return True
    excerpt = _diff_excerpt(dev_s, prod_s)
    results.append({"path": label, "status": "diff", "excerpt": excerpt})
    return False


# ── Per-case bundle comparison ────────────────────────────────────────────────

def _compare_properties(path: str, dev_props: list[dict], prod_props: list[dict],
                         results: list[dict]) -> None:
    """
    Compare two property lists keyed by 'name', independent of list order.
    Reports:
      - properties only present on dev
      - properties only present on prod
      - properties present on both sides but with differing values/fields
    Each is a separate result entry for actionable output.
    """
    dev_map  = {p.get("name", f"__idx{i}"): p for i, p in enumerate(dev_props)}
    prod_map = {p.get("name", f"__idx{i}"): p for i, p in enumerate(prod_props)}

    all_names = sorted(set(dev_map) | set(prod_map))
    any_diff = False
    for name in all_names:
        p = f"{path}.properties[{name}]"
        if name not in dev_map:
            results.append({"path": p, "status": "diff", "excerpt": "only in prod"})
            any_diff = True
        elif name not in prod_map:
            results.append({"path": p, "status": "diff", "excerpt": "only in dev"})
            any_diff = True
        else:
            d = _canon(dev_map[name])
            r = _canon(prod_map[name])
            if d == r:
                results.append({"path": p, "status": "match"})
            else:
                excerpt = _diff_excerpt(d, r)
                results.append({"path": p, "status": "diff", "excerpt": excerpt})
                any_diff = True

    if not any_diff:
        # Consolidate into a single pass entry for cleaner output
        for name in all_names:
            results[:] = [r for r in results if r["path"] != f"{path}.properties[{name}]"]
        results.append({"path": f"{path}.properties", "status": "match"})


def _check_object_node(path: str, dev_node: dict, prod_node: dict,
                        results: list[dict]) -> None:
    """Compare a single {record, properties} node."""
    _compare(f"{path}.record", dev_node.get("record"), prod_node.get("record"), results)
    _compare_properties(path, dev_node.get("properties") or [],
                        prod_node.get("properties") or [], results)


def _check_bundle_pair(case_name: str, dev_bundle: dict,
                        prod_bundle: dict) -> list[dict]:
    """
    Walk the full bundle tree and compare every node between dev and prod.
    Returns a flat list of result dicts: {path, status, [excerpt]}.
    """
    results: list[dict] = []

    # Top-level case record
    _compare("case", dev_bundle.get("case"), prod_bundle.get("case"), results)

    # Direct FK nodes
    for key in ("source", "sink", "region"):
        _check_object_node(key, dev_bundle.get(key, {}), prod_bundle.get(key, {}), results)

    # Utility list — compare by position after sorting by record name
    for side, nodes in (("dev", dev_bundle.get("utilities", [])),
                         ("prod", prod_bundle.get("utilities", []))):
        pass  # just used for alignment below
    dev_utils  = sorted(dev_bundle.get("utilities",  []),
                        key=lambda n: (n.get("record") or {}).get("name", ""))
    prod_utils = sorted(prod_bundle.get("utilities", []),
                        key=lambda n: (n.get("record") or {}).get("name", ""))

    if len(dev_utils) != len(prod_utils):
        results.append({
            "path":    "utilities.count",
            "status":  "diff",
            "excerpt": f"dev={len(dev_utils)}  prod={len(prod_utils)}",
        })
    for i, (du, pu) in enumerate(zip(dev_utils, prod_utils)):
        _check_object_node(f"utilities[{i}]", du, pu, results)

    # Subsystem list
    dev_subs  = sorted(dev_bundle.get("subsystems",  []),
                       key=lambda n: (n.get("record") or {}).get("name", ""))
    prod_subs = sorted(prod_bundle.get("subsystems", []),
                       key=lambda n: (n.get("record") or {}).get("name", ""))
    if len(dev_subs) != len(prod_subs):
        results.append({
            "path":    "subsystems.count",
            "status":  "diff",
            "excerpt": f"dev={len(dev_subs)}  prod={len(prod_subs)}",
        })
    for i, (ds, ps) in enumerate(zip(dev_subs, prod_subs)):
        _check_object_node(f"subsystems[{i}]", ds, ps, results)

    # Scenarios — match by scenario name
    dev_scen_map  = {(s.get("record") or {}).get("name", f"__idx{i}"): s
                     for i, s in enumerate(dev_bundle.get("scenarios", []))}
    prod_scen_map = {(s.get("record") or {}).get("name", f"__idx{i}"): s
                     for i, s in enumerate(prod_bundle.get("scenarios", []))}

    all_scen_names = sorted(set(dev_scen_map) | set(prod_scen_map))
    for scen_name in all_scen_names:
        path_s = f"scenarios[{scen_name}]"
        if scen_name not in dev_scen_map:
            results.append({"path": path_s, "status": "diff",
                             "excerpt": "missing from dev"})
            continue
        if scen_name not in prod_scen_map:
            results.append({"path": path_s, "status": "diff",
                             "excerpt": "missing from prod"})
            continue

        dev_sn  = dev_scen_map[scen_name]
        prod_sn = prod_scen_map[scen_name]

        _compare(f"{path_s}.record", dev_sn.get("record"), prod_sn.get("record"), results)

        dev_pc  = dev_sn.get("process_conditions")
        prod_pc = prod_sn.get("process_conditions")

        if dev_pc is None and prod_pc is None:
            pass
        elif dev_pc is None or prod_pc is None:
            results.append({
                "path":    f"{path_s}.process_conditions",
                "status":  "diff",
                "excerpt": f"dev={'present' if dev_pc else 'None'}  "
                           f"prod={'present' if prod_pc else 'None'}",
            })
        else:
            _compare(f"{path_s}.process_conditions.record",
                     dev_pc.get("record"), prod_pc.get("record"), results)
            _compare_properties(f"{path_s}.process_conditions",
                                dev_pc.get("properties") or [],
                                prod_pc.get("properties") or [], results)

            # Configurations — match by record name
            dev_cfg_map  = {(c.get("record") or {}).get("name", f"__idx{i}"): c
                            for i, c in enumerate(dev_pc.get("configurations", []))}
            prod_cfg_map = {(c.get("record") or {}).get("name", f"__idx{i}"): c
                            for i, c in enumerate(prod_pc.get("configurations", []))}
            for cfg_name in sorted(set(dev_cfg_map) | set(prod_cfg_map)):
                path_c = f"{path_s}.process_conditions.configurations[{cfg_name}]"
                if cfg_name not in dev_cfg_map:
                    results.append({"path": path_c, "status": "diff",
                                    "excerpt": "missing from dev"})
                    continue
                if cfg_name not in prod_cfg_map:
                    results.append({"path": path_c, "status": "diff",
                                    "excerpt": "missing from prod"})
                    continue
                _check_object_node(path_c, dev_cfg_map[cfg_name],
                                   prod_cfg_map[cfg_name], results)

    return results


# ── Main comparison runner ────────────────────────────────────────────────────

def run_bundle_check(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    dev_label: str,
    prod_label: str,
    name: str | None,
    source: str | None,
    sink: str | None,
    region: str | None,
    n: int,
    emit_json: bool,
) -> int:
    """Fetch bundles from dev and prod and compare them. Returns 0 or 1."""

    fetch_kwargs = dict(name=name, source=source, sink=sink, region=region,
                        limit_cases=n)

    print(f"\n  Fetching bundles from {dev_label} …", end="", flush=True)
    try:
        dev_bundles: list[dict] = dev_api.get_cases_bundle(**fetch_kwargs)
        print(f" {len(dev_bundles)} case(s).")
    except Exception as exc:
        print(_red(f"\n  ERROR: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1

    # Build a name → bundle map for dev
    dev_map: dict[str, dict] = {
        b["case"].get("name", f"__idx{i}"): b
        for i, b in enumerate(dev_bundles)
    }

    if not dev_map:
        print(_yellow("  No cases matched on dev — nothing to check."))
        return 0

    overall_rc = 0
    all_json_results: list[dict] = []

    for case_name, dev_bundle in dev_map.items():
        print(_header(f"Case: {case_name}"))

        # Fetch the same case from prod by exact name
        print(f"  Fetching from {prod_label} …", end="", flush=True)
        try:
            prod_bundles = prod_api.get_cases_bundle(name=case_name, limit_cases=50)
            # Require an exact name match; a substring hit for a different case
            # is not acceptable (it would produce false-positive diffs).
            exact = [b for b in prod_bundles
                     if b["case"].get("name") == case_name]
            prod_bundle = exact[0] if exact else None
            print(f" {'found' if prod_bundle else 'NOT FOUND'}.")
        except Exception as exc:
            print(_red(f"\n  ERROR: {type(exc).__name__}: {exc}"), file=sys.stderr)
            overall_rc = 1
            continue

        if prod_bundle is None:
            print(_red(f"  ✗ Case '{case_name}' not found on prod — skipping."))
            overall_rc = 1
            continue

        results = _check_bundle_pair(case_name, dev_bundle, prod_bundle)

        diffs   = [r for r in results if r["status"] == "diff"]
        matches = [r for r in results if r["status"] == "match"]

        if emit_json:
            all_json_results.append({
                "case":    case_name,
                "total":   len(results),
                "matches": len(matches),
                "diffs":   len(diffs),
                "details": results,
            })
        else:
            print(f"\n  Checks: {len(results)}  "
                  f"{_green(f'pass: {len(matches)}')}  "
                  f"{(_red if diffs else _green)(f'fail: {len(diffs)}')}\n")

            if diffs:
                for d in diffs:
                    print(_red(f"  ✗ {d['path']}"))
                    if d.get("excerpt"):
                        print(f"      {d['excerpt']}")
            else:
                print(_green("  ✓ All nodes match exactly."))

        if diffs:
            overall_rc = 1

    if emit_json:
        print(json.dumps(all_json_results, indent=2))

    return overall_rc


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cross-check the full cases bundle between dev and prod.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--name",   default=None, help="Case name substring filter.")
    p.add_argument("--source", default=None, help="Source name substring filter.")
    p.add_argument("--sink",   default=None, help="Sink name substring filter.")
    p.add_argument("--region", default=None, help="Exact ISO region code filter.")
    p.add_argument("--n", type=int, default=5, metavar="N",
                   help="Maximum number of cases to check (default: 5).")
    p.add_argument("--dev-host-port", default="", metavar="HOST:PORT",
                   help="Dev server host:port.")
    p.add_argument("--key", default=None, metavar="KEY", help="PrISMa API key.")
    p.add_argument("--json", action="store_true", dest="emit_json",
                   help="Emit results as JSON.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not any([args.name, args.source, args.sink, args.region]) and args.n <= 0:
        print("Specify at least one filter (--name/--source/--sink/--region) "
              "or a positive --n.", file=sys.stderr)
        return 1

    # ── Config ────────────────────────────────────────────────────────────────
    cfg = load_config() or {}
    api_key     = args.key or str(cfg.get("api_key") or "").strip()
    dev_api_key = str(cfg.get("dev_api_key") or api_key).strip()

    _DEFAULT_HP = "localhost:8000"
    cli_hp = (args.dev_host_port or "").strip()
    cfg_hp = str(cfg.get("dev_host_port") or "").strip()
    dev_hp = (cli_hp or cfg_hp or _DEFAULT_HP)
    dev_hp = dev_hp.replace("http://", "").replace("https://", "").strip() or _DEFAULT_HP

    dev_label  = f"DEV  (http://{dev_hp}/api/v2)"
    prod_label = f"PROD ({prisma_api.prisma_api_v2._BASE_PROD})"

    if not args.emit_json:
        print(_bold(_header("PrISMa Cases Bundle Cross-Check: dev vs prod")))
        print(f"  Dev : http://{dev_hp}/api/v2")
        print(f"  Prod: {prisma_api.prisma_api_v2._BASE_PROD}")
        filters = {k: v for k, v in [("name", args.name), ("source", args.source),
                                       ("sink", args.sink), ("region", args.region)] if v}
        print(f"  Filters : {filters if filters else '(none — first {args.n} cases)'}")
        print(f"  Max cases: {args.n}")

    dev_api  = PrismaAPIv2(key=dev_api_key, dev=True,  dev_host_port=dev_hp, return_format="json")
    prod_api = PrismaAPIv2(key=api_key,     dev=False,                        return_format="json")

    rc = run_bundle_check(
        dev_api=dev_api, prod_api=prod_api,
        dev_label=dev_label, prod_label=prod_label,
        name=args.name, source=args.source, sink=args.sink, region=args.region,
        n=args.n, emit_json=args.emit_json,
    )

    if not args.emit_json:
        print(_header("Summary"))
        if rc == 0:
            print(_green("\n  ✓ All cases match between dev and prod.\n"))
        else:
            print(_red("\n  ✗ Differences found in one or more cases.\n"))

    return rc


if __name__ == "__main__":
    sys.exit(main())
