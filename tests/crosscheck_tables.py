"""
Cross-check script: lookup tables — dev vs production
======================================================
Fetches all records from individual lookup tables on both the dev instance
and the production service, then reports entries that are present in one but
not the other.

Currently supported tables
--------------------------
    references      – compared by (name, doi)
    molecules       – compared by name
    elements        – compared by symbol
    regions         – compared by code
    sources         – compared by name
    sinks           – compared by name
    transport_scenarios – compared by name
    utilities       – compared by name
    properties      – compared by (name, domain, category)
    cases           – compared by name

Usage
-----
    # Compare all supported tables
    python tests/crosscheck_tables.py --all

    # Compare individual tables
    python tests/crosscheck_tables.py --references
    python tests/crosscheck_tables.py --molecules
    python tests/crosscheck_tables.py --references --molecules --sources

    # Optional flags
    python tests/crosscheck_tables.py --all --json
    python tests/crosscheck_tables.py --all --dev-host-port localhost:8001
    python tests/crosscheck_tables.py --all --key MY_API_KEY

Arguments
---------
--all                Check every supported table.
--references         Check the references table.
--molecules          Check the molecules table.
--elements           Check the elements table.
--regions            Check the regions table.
--sources            Check the sources table.
--sinks              Check the sinks table.
--transport-scenarios  Check the transport_scenarios table.
--utilities          Check the utilities table.
--properties         Check the properties table.
--cases              Check the cases table.
--dev-host-port      HOST:PORT of the local dev server (default: localhost:8000).
                     Falls back to ``dev_host_port`` in config.yaml if omitted.
--key                PrISMa API key.  Falls back to config.yaml if omitted.
--json               Emit results as JSON to stdout instead of human-readable text.

Exit codes
----------
0  all checked tables are identical
1  one or more differences were found, or an error occurred
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any, Callable

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from prisma_api.prisma_api_v2 import PrismaAPIv2
from prisma_api.config import load_config


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


# ── Helpers ───────────────────────────────────────────────────────────────────

_LARGE_LIMIT = 100_000


def _records_to_list(result: pd.DataFrame | list[dict]) -> list[dict]:
    """Normalise the return value of any PrismaAPIv2 list method to list[dict]."""
    if isinstance(result, pd.DataFrame):
        return result.to_dict(orient="records")
    if isinstance(result, list):
        return result
    return []


def _count_keys(records: list[dict], key_fields: list[str]) -> Counter:
    """Return a Counter of key-tuples from a list of records (detects duplicates)."""
    return Counter(
        tuple(str(rec.get(f, "")) for f in key_fields)
        for rec in records
    )


# ── Table definitions ─────────────────────────────────────────────────────────


# Each entry: (flag_name, display_title, api_method_name, key_fields, fetch_kwargs)
_TABLE_REGISTRY: list[tuple[str, str, str, list[str], dict]] = [
    (
        "references",
        "References",
        "get_references",
        ["Name", "Doi"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "molecules",
        "Molecules",
        "get_molecules",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "elements",
        "Elements",
        "get_elements",
        ["symbol"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "regions",
        "Regions",
        "get_regions",
        ["code"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "sources",
        "Sources",
        "get_sources",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "sinks",
        "Sinks",
        "get_sinks",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "transport_scenarios",
        "Transport Scenarios",
        "get_transport_scenarios",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "utilities",
        "Utilities",
        "get_utilities",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "properties",
        "Properties",
        "get_properties",
        ["name", "domain", "category"],
        {"limit": _LARGE_LIMIT},
    ),
    (
        "cases",
        "Cases",
        "get_cases",
        ["name"],
        {"limit": _LARGE_LIMIT},
    ),
]

# Registry as a plain dict for lookup: flag_name → (display_title, method, key_fields, kwargs)
TABLE_MAP: dict[str, tuple[str, str, list[str], dict]] = {
    flag: (title, method, key_fields, kwargs)
    for flag, title, method, key_fields, kwargs in _TABLE_REGISTRY
}


# ── Core comparison logic ─────────────────────────────────────────────────────


def _fetch_table(api: PrismaAPIv2, method_name: str, kwargs: dict, label: str) -> list[dict]:
    """Call the named PrismaAPIv2 method and return results as list[dict]."""
    method: Callable = getattr(api, method_name)
    result = method(**kwargs)
    return _records_to_list(result)


def _key_label(key_fields: list[str], key: tuple) -> str:
    """Format a key-tuple for display."""
    if len(key_fields) == 1:
        return key[0]
    return "  " + "  |  ".join(f"{f}={v}" for f, v in zip(key_fields, key))


def run_table_check(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    dev_label: str,
    prod_label: str,
    flag: str,
    emit_json: bool,
) -> int:
    """
    Compare a single lookup table between dev and prod.

    Returns 0 if sets are equal, 1 if there are differences or errors.
    """
    title, method_name, key_fields, kwargs = TABLE_MAP[flag]

    print(_header(f"Table: {title}"))
    print(f"  Key field(s): {', '.join(key_fields)}\n")

    # Fetch from dev
    try:
        print(f"  Fetching from {dev_label} …", end="", flush=True)
        dev_records = _fetch_table(dev_api, method_name, kwargs, dev_label)
        print(f" {len(dev_records)} records.")
    except Exception as exc:
        print(_red(f"\n  ERROR fetching {title} from dev: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1

    # Fetch from prod
    try:
        print(f"  Fetching from {prod_label} …", end="", flush=True)
        prod_records = _fetch_table(prod_api, method_name, kwargs, prod_label)
        print(f" {len(prod_records)} records.")
    except Exception as exc:
        print(_red(f"\n  ERROR fetching {title} from prod: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1

    dev_counter  = _count_keys(dev_records,  key_fields)
    prod_counter = _count_keys(prod_records, key_fields)

    dev_keys  = set(dev_counter)
    prod_keys = set(prod_counter)

    only_in_dev  = sorted(dev_keys  - prod_keys)
    only_in_prod = sorted(prod_keys - dev_keys)

    # Keys that exist on both sides but with different counts (duplicates on one side)
    count_mismatches = sorted(
        k for k in dev_keys & prod_keys
        if dev_counter[k] != prod_counter[k]
    )

    # Duplicate keys within a single side
    dev_dupes  = sorted(k for k, n in dev_counter.items()  if n > 1)
    prod_dupes = sorted(k for k, n in prod_counter.items() if n > 1)

    has_diff = bool(only_in_dev or only_in_prod or count_mismatches)

    if emit_json:
        output = {
            "table":             flag,
            "dev_raw_total":     len(dev_records),
            "prod_raw_total":    len(prod_records),
            "dev_unique":        len(dev_keys),
            "prod_unique":       len(prod_keys),
            "common_count":      len(dev_keys & prod_keys),
            "only_in_dev":       [list(k) if len(k) > 1 else k[0] for k in only_in_dev],
            "only_in_prod":      [list(k) if len(k) > 1 else k[0] for k in only_in_prod],
            "count_mismatches":  [
                {"key": list(k) if len(k) > 1 else k[0],
                 "dev_count": dev_counter[k], "prod_count": prod_counter[k]}
                for k in count_mismatches
            ],
            "dev_duplicates":    [list(k) if len(k) > 1 else k[0] for k in dev_dupes],
            "prod_duplicates":   [list(k) if len(k) > 1 else k[0] for k in prod_dupes],
        }
        print(json.dumps(output, indent=2))
        return 0 if not has_diff else 1

    # ── Human-readable output ──────────────────────────────────────────────
    print(f"\n  {_bold('dev')}:  {len(dev_records)} records  ({len(dev_keys)} unique keys)")
    print(f"  {_bold('prod')}: {len(prod_records)} records  ({len(prod_keys)} unique keys)")
    print(f"  {_bold('common')}: {len(dev_keys & prod_keys)} unique keys\n")

    if only_in_dev:
        print(_yellow(f"  Only in dev ({len(only_in_dev)}):"))
        for k in only_in_dev:
            print(f"    {_yellow(_key_label(key_fields, k))}")
    else:
        print(_green("  ✓ No keys only in dev"))

    if only_in_prod:
        print(_yellow(f"\n  Only in prod ({len(only_in_prod)}):"))
        for k in only_in_prod:
            print(f"    {_yellow(_key_label(key_fields, k))}")
    else:
        print(_green("  ✓ No keys only in prod"))

    if count_mismatches:
        print(_yellow(f"\n  Count mismatches (same key, different occurrence count) ({len(count_mismatches)}):"))
        for k in count_mismatches:
            print(f"    {_yellow(_key_label(key_fields, k))}  "
                  f"(dev×{dev_counter[k]}  prod×{prod_counter[k]})")
    else:
        print(_green("  ✓ No count mismatches"))

    if dev_dupes:
        print(_yellow(f"\n  Duplicate keys in dev ({len(dev_dupes)}):"))
        for k in dev_dupes:
            print(f"    {_yellow(_key_label(key_fields, k))}  ×{dev_counter[k]}")

    if prod_dupes:
        print(_yellow(f"\n  Duplicate keys in prod ({len(prod_dupes)}):"))
        for k in prod_dupes:
            print(f"    {_yellow(_key_label(key_fields, k))}  ×{prod_counter[k]}")

    return 0 if not has_diff else 1


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Cross-check PrISMa lookup tables between dev and prod.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--all", action="store_true", help="Check every supported table.")
    for flag, title, *_ in _TABLE_REGISTRY:
        flag_cli = "--" + flag.replace("_", "-")
        p.add_argument(flag_cli, action="store_true", help=f"Check the {title} table.")
    p.add_argument(
        "--dev-host-port",
        default="",
        metavar="HOST:PORT",
        help="Dev server host:port (default: localhost:8000 or config.yaml).",
    )
    p.add_argument("--key", default="", metavar="KEY", help="PrISMa API key.")
    p.add_argument("--json", action="store_true", help="Output results as JSON.")
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Determine which tables to check
    requested: list[str] = []
    if args.all:
        requested = [flag for flag, *_ in _TABLE_REGISTRY]
    else:
        for flag, *_ in _TABLE_REGISTRY:
            if getattr(args, flag, False):
                requested.append(flag)

    if not requested:
        parser.print_help()
        return 0

    # ── Config / credentials ───────────────────────────────────────────────
    cfg: dict[str, Any] = {}
    try:
        cfg = load_config() or {}
    except Exception:
        pass

    api_key     = args.key or str(cfg.get("api_key") or "").strip()
    dev_api_key = str(cfg.get("dev_api_key") or api_key).strip()

    cfg_dev_hp  = str(cfg.get("dev_host_port") or "").strip()
    cli_dev_hp  = args.dev_host_port.strip()
    dev_hp      = cli_dev_hp or cfg_dev_hp or "localhost:8000"
    dev_label  = f"dev ({dev_hp})"
    prod_label = "prod (prisma-platform.org)"

    dev_api  = PrismaAPIv2(key=dev_api_key, dev=True,  dev_host_port=dev_hp, return_format="json")
    prod_api = PrismaAPIv2(key=api_key,     dev=False,                        return_format="json")

    print(_bold(f"\nPrISMa table cross-check: {dev_label}  ↔  {prod_label}"))
    print(_bold(f"Tables to check: {', '.join(requested)}\n"))

    overall_rc = 0
    json_results: list[dict] = []

    for flag in requested:
        rc = run_table_check(
            dev_api=dev_api,
            prod_api=prod_api,
            dev_label=dev_label,
            prod_label=prod_label,
            flag=flag,
            emit_json=args.json,
        )
        overall_rc = max(overall_rc, rc)

    # ── Summary ────────────────────────────────────────────────────────────
    if not args.json:
        print(_header("Summary"))
        if overall_rc == 0:
            print(_green(f"\n  ✓ All {len(requested)} table(s) match between dev and prod.\n"))
        else:
            print(_red(f"\n  ✗ Differences found in one or more tables.\n"))

    return overall_rc


if __name__ == "__main__":
    sys.exit(main())
