"""
Cross-check script: material catalogue — dev vs production
==========================================================
Compares the set of material names present in the dev instance and the
production service and reports which names are missing from either side.

Usage
-----
    python tests/crosscheck_materials.py --list
    python tests/crosscheck_materials.py --list [--dev-host-port HOST:PORT] [--key KEY]

Arguments
---------
--list           Fetch all materials from both services, compare by name, and
                 report materials missing from dev, missing from prod, or
                 present on both.
--dev-host-port  HOST:PORT of the local dev server (default: localhost:8000).
                 Falls back to ``dev_host_port`` in config.yaml if not given.
--key            PrISMa API key.  Falls back to config.yaml if omitted.
--verbose        Also print the full sorted list of common names.
--json           Emit results as JSON to stdout instead of human-readable text.

Exit codes
----------
0  sets are identical
1  one or more names differ or an error occurred
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import prisma_api
from prisma_api.prisma_api_v2 import PrismaAPIv2


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



# ── Core logic ────────────────────────────────────────────────────────────────


def _fetch_material_names(api: PrismaAPIv2, label: str) -> set[str]:
    """Fetch all materials and return their names as a set."""
    print(f"  Fetching all materials from {label} …", end="", flush=True)
    result = api.list_materials(limit=0)  # limit=0 → no cap
    if isinstance(result, pd.DataFrame):
        names = set(result["name"].dropna().astype(str).tolist()) if "name" in result.columns else set()
    elif isinstance(result, list):
        names = {str(r["name"]) for r in result if r.get("name") is not None}
    else:
        names = set()
    print(f" {len(names)} materials found.")
    return names


def run_list_check(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    dev_label: str,
    prod_label: str,
    emit_json: bool,
) -> int:
    """
    Compare material name sets between dev and prod.

    Returns 0 if identical, 1 if there are any differences or errors.
    """
    try:
        dev_names = _fetch_material_names(dev_api, dev_label)
    except Exception as exc:
        print(_red(f"\nERROR fetching dev materials: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1

    try:
        prod_names = _fetch_material_names(prod_api, prod_label)
    except Exception as exc:
        print(_red(f"\nERROR fetching prod materials: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1

    only_in_dev  = sorted(dev_names - prod_names)
    only_in_prod = sorted(prod_names - dev_names)
    common       = sorted(dev_names & prod_names)

    if emit_json:
        output = {
            "dev_total":        len(dev_names),
            "prod_total":       len(prod_names),
            "common_count":     len(common),
            "only_in_dev":      only_in_dev,
            "only_in_prod":     only_in_prod,
        }
        print(json.dumps(output, indent=2))
        return 0 if (not only_in_dev and not only_in_prod) else 1

    # ── Human-readable report ─────────────────────────────────────────────────
    print()
    print(_bold("── Material name comparison ─────────────────────────────────────"))
    print(f"  Dev  total : {len(dev_names)}")
    print(f"  Prod total : {len(prod_names)}")
    print(f"  Common     : {len(common)}")
    print()

    if only_in_dev:
        print(_bold(_yellow(f"  Materials in DEV only ({len(only_in_dev)}):")))
        for name in only_in_dev:
            print(f"    {_yellow('+')} {name}")
        print()
    else:
        print(f"  {_green('No materials are in DEV only.'  )}")

    if only_in_prod:
        print(_bold(_red(f"  Materials in PROD only ({len(only_in_prod)}):")))
        for name in only_in_prod:
            print(f"    {_red('-')} {name}")
        print()
    else:
        print(f"  {_green('No materials are in PROD only.')}")

    print(_bold("── Summary ─────────────────────────────────────────────────────"))
    if not only_in_dev and not only_in_prod:
        print(f"  {_green('Both services have identical material catalogues ✓')}")
        return 0
    else:
        if only_in_dev:
            print(f"  {_yellow(f'{len(only_in_dev)} material(s) exist only on DEV'  )}")
        if only_in_prod:
            print(f"  {_red(   f'{len(only_in_prod)} material(s) exist only on PROD')}")
        return 1


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cross-check PrISMa material catalogues: dev vs production."
    )
    p.add_argument(
        "--list",
        action="store_true",
        dest="list_check",
        help="Compare full material name sets between dev and prod.",
    )
    p.add_argument(
        "--dev-host-port",
        default="localhost:8000",
        metavar="HOST:PORT",
        help="Host and port of the local dev server (default: localhost:8000).",
    )
    p.add_argument(
        "--key",
        default=None,
        metavar="API_KEY",
        help="PrISMa API key (falls back to config.yaml if omitted).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit results as JSON to stdout.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.list_check:
        print("No action specified.  Use --list to compare material catalogues.", file=sys.stderr)
        return 1

    # ── Resolve config ────────────────────────────────────────────────────────
    from prisma_api.config import load_config
    cfg = load_config() or {}

    api_key = args.key or cfg.get("api_key") or cfg.get("key")
    if not api_key:
        print(_red("ERROR: No API key found.  Pass --key KEY or configure config.yaml."), file=sys.stderr)
        return 1
    dev_api_key = cfg.get("dev_api_key") or api_key

    _DEFAULT_HP = "localhost:8000"
    _cli_hp = args.dev_host_port or ""
    _cfg_hp = str(cfg.get("dev_host_port") or "").strip()
    dev_hp = _cli_hp if _cli_hp and _cli_hp != _DEFAULT_HP else (_cfg_hp or _DEFAULT_HP)
    dev_hp = dev_hp.replace("http://", "").replace("https://", "").strip() or _DEFAULT_HP

    dev_label  = f"DEV  (http://{dev_hp}/api/v2)"
    prod_label = f"PROD ({prisma_api.prisma_api_v2._BASE_PROD})"

    if not args.emit_json:
        print(_bold("\n═══ PrISMa Material Catalogue Cross-Check: dev vs prod ═══"))
        print(f"  Dev server : http://{dev_hp}/api/v2")
        print(f"  Prod server: {prisma_api.prisma_api_v2._BASE_PROD}")
        print()

    dev_api = PrismaAPIv2(key=dev_api_key, dev=True,  dev_host_port=dev_hp, return_format="json")
    prod_api = PrismaAPIv2(key=api_key,    dev=False,                        return_format="json")

    return run_list_check(dev_api, prod_api, dev_label, prod_label, args.emit_json)


if __name__ == "__main__":
    sys.exit(main())
