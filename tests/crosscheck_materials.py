"""
Cross-check script: material catalogue — dev vs production
==========================================================
Compares the set of material names present in the dev instance and the
production service and reports which names are missing from either side.
Optionally cross-checks full property bundles for the first N materials.

Usage
-----
    python tests/crosscheck_materials.py --list
    python tests/crosscheck_materials.py --bundle [--bundle-n N]
    python tests/crosscheck_materials.py --list --bundle [--dev-host-port HOST:PORT] [--key KEY]

Arguments
---------
--list           Fetch all materials from both services, compare by name, and
                 report materials missing from dev, missing from prod, or
                 present on both.
--bundle         Fetch the first N materials from dev, call
                 get_material_property_bundle for each on both dev and prod,
                 and cross-check the returned science data.
--bundle-n N     Number of materials to bundle-check (default: 5).
--dev-host-port  HOST:PORT of the local dev server (default: localhost:8000).
                 Falls back to ``dev_host_port`` in config.yaml if not given.
--key            PrISMa API key.  Falls back to config.yaml if omitted.
--json           Emit results as JSON to stdout instead of human-readable text.

Exit codes
----------
0  all checks passed
1  one or more names/bundles differ or an error occurred
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

# Reuse normalisation and diff helpers from the main cross-check module
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
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
    print(_bold("═" * 72))
    print(_bold("  Material name comparison"))
    print(_bold("═" * 72))
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

    print(_bold("═" * 72))
    print(_bold("  Summary"))
    print(_bold("═" * 72))
    if not only_in_dev and not only_in_prod:
        print(f"  {_green('Both services have identical material catalogues ✓')}")
        return 0
    else:
        if only_in_dev:
            print(f"  {_yellow(f'{len(only_in_dev)} material(s) exist only on DEV'  )}")
        if only_in_prod:
            print(f"  {_red(   f'{len(only_in_prod)} material(s) exist only on PROD')}")
        return 1


# ── Bundle cross-check ────────────────────────────────────────────────────────


def run_bundle_check(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    dev_label: str,
    prod_label: str,
    n: int,
    emit_json: bool,
) -> int:
    """
    Fetch the first *n* materials from dev, call ``get_material_property_bundle``
    for each on both dev and prod, normalise and compare the payloads, and
    report PASS/FAIL per material and per sub-dataset.

    Returns 0 if all bundles match, 1 if any differ or error.
    """
    print(f"  Fetching first {n} material names from {dev_label} …", end="", flush=True)
    try:
        dev_sample = dev_api.list_materials(limit=n)
        if isinstance(dev_sample, pd.DataFrame):
            target_names: list[str] = dev_sample["name"].dropna().astype(str).tolist()[:n]
        elif isinstance(dev_sample, list):
            target_names = [str(r["name"]) for r in dev_sample if r.get("name")][:n]
        else:
            target_names = []
    except Exception as exc:
        print(_red(f"\nERROR: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 1
    print(f" {len(target_names)} names resolved.")

    if not target_names:
        print(_yellow("  No materials found on dev — skipping bundle check."))
        return 0

    _bundle_keys = ("isotherms", "zeopp_simulated", "zeopp_experimental", "water_kpis")
    results: list[dict] = []
    _sep = "  " + "-" * 40

    if not emit_json:
        print()
        print(_bold("═" * 72))
        print(_bold("  Property bundle cross-check"))
        print(_bold("═" * 72))

    for name in target_names:
        entry: dict = {"material": name}

        # Fetch bundle from dev
        try:
            dev_bundle = dev_api.get_material_property_bundle(name)
            entry["dev_ok"] = True
        except Exception as exc:
            entry["dev_ok"] = False
            entry["dev_error"] = f"{type(exc).__name__}: {exc}"
            entry["passed"] = False
            results.append(entry)
            if not emit_json:
                print(f"  [{_red('FAIL')}] {name}")
                print(f"        DEV error: {entry['dev_error']}")
                print(_sep)
            continue

        # Fetch bundle from prod
        try:
            prod_bundle = prod_api.get_material_property_bundle(name)
            entry["prod_ok"] = True
        except Exception as exc:
            entry["prod_ok"] = False
            entry["prod_error"] = f"{type(exc).__name__}: {exc}"
            entry["passed"] = False
            results.append(entry)
            if not emit_json:
                print(f"  [{_red('FAIL')}] {name}")
                print(f"        PROD error: {entry['prod_error']}")
                print(_sep)
            continue

        # Compare each sub-dataset
        sub_results: dict[str, bool] = {}
        sub_notes:   dict[str, str]  = {}
        all_pass = True

        for key in _bundle_keys:
            dev_val   = dev_bundle.get(key)
            prod_val  = prod_bundle.get(key)
            dev_json  = _to_json(dev_val)
            prod_json = _to_json(prod_val)
            ok = dev_json == prod_json
            sub_results[key] = ok
            if not ok:
                all_pass = False
                sub_notes[key] = _diff_excerpt(dev_json, prod_json)

        entry["passed"]      = all_pass
        entry["sub_results"] = sub_results
        entry["sub_notes"]   = sub_notes
        results.append(entry)

        if not emit_json:
            status = _green("PASS") if all_pass else _red("FAIL")
            print(f"  [{status}] {name}")
            for key, ok in sub_results.items():
                sub_icon = _green("\u2713") if ok else _red("\u2717")
                line = f"        {sub_icon} {key}"
                if not ok and key in sub_notes:
                    line += f"\n          {sub_notes[key]}"
                print(line)
            print(_sep)

    failed = [r for r in results if not r.get("passed")]

    if emit_json:
        print(json.dumps({
            "checked": len(results),
            "passed":  len(results) - len(failed),
            "failed":  len(failed),
            "results": results,
        }, indent=2, default=str))
    else:
        print()
        print(_bold("═" * 72))
        print(_bold("  Bundle summary"))
        print(_bold("═" * 72))
        print(f"  Checked : {len(results)}")
        print(f"  {_green('Passed')} : {len(results) - len(failed)}")
        if failed:
            print(f"  {_red('Failed')} : {len(failed)}")
            for r in failed:
                print(f"    \u2022 {r['material']}")

    return 0 if not failed else 1


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
        "--bundle",
        action="store_true",
        dest="bundle_check",
        help="Cross-check get_material_property_bundle for the first N materials from dev.",
    )
    p.add_argument(
        "--bundle-n",
        type=int,
        default=5,
        metavar="N",
        dest="bundle_n",
        help="Number of materials to bundle-check (default: 5).",
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

    if not args.list_check and not args.bundle_check:
        print("No action specified.  Use --list and/or --bundle.", file=sys.stderr)
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
        print(_bold("\n" + "═" * 72))
        print(_bold("  PrISMa Material Catalogue Cross-Check: dev vs prod"))
        print(_bold("═" * 72))
        print(f"  Dev server : http://{dev_hp}/api/v2")
        print(f"  Prod server: {prisma_api.prisma_api_v2._BASE_PROD}")
        print()

    dev_api = PrismaAPIv2(key=dev_api_key, dev=True,  dev_host_port=dev_hp, return_format="json")
    prod_api = PrismaAPIv2(key=api_key,    dev=False,                        return_format="json")

    exit_code = 0

    if args.list_check:
        result = run_list_check(dev_api, prod_api, dev_label, prod_label, args.emit_json)
        exit_code = exit_code or result

    if args.bundle_check:
        if not args.emit_json:
            print()
        result = run_bundle_check(dev_api, prod_api, dev_label, prod_label, args.bundle_n, args.emit_json)
        exit_code = exit_code or result

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
