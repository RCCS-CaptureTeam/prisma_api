"""
Cross-check script: dev instance vs production service
=======================================================
Runs every read-only v2 API wrapper against both a local dev server and the
production service, normalises the response payloads, and reports PASS/FAIL
for each check to stdout.

Usage
-----
    python tests/crosscheck_dev_vs_prod.py [--dev-host-port HOST:PORT] [--key KEY] [--limit N]

Arguments
---------
--dev-host-port  HOST:PORT of the local dev server  (default: localhost:8000)
--key            PrISMa API key.  Falls back to the value stored in
                 config.yaml if omitted.
--limit          Max records to fetch per list endpoint  (default: 20).
                 Lowering this makes the run faster; raise it for a deeper
                 data-parity check.
--verbose        Also print a short diff excerpt on FAIL.
--skip-upsert    Skip any PUT/upsert wrappers (default: True; upserts are
                 always skipped to avoid mutating data).

Exit codes
----------
0  all checks passed
1  one or more checks failed or errored
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

import pandas as pd

# Allow running from the repo root without installation
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import prisma_api
from prisma_api.prisma_api_v2 import PrismaAPIv2


# ── Colour helpers (degrade gracefully on Windows / no-tty) ──────────────────

_USE_COLOUR = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _USE_COLOUR else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _USE_COLOUR else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _USE_COLOUR else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _USE_COLOUR else s


# ── Payload normalisation ─────────────────────────────────────────────────────



# Own primary-key fields — dropped entirely from comparison because the
# auto-increment value carries no semantic meaning across databases.
_PK_FIELDS: frozenset[str] = frozenset({
    "id",
})

# Foreign-key / content-type id fields whose *exact integer value* can differ
# between dev and prod (they reference rows in another table whose own PK may
# differ) but whose *presence or absence* is meaningful.
# These are replaced with the sentinel "<set>" when non-null, or kept as None.
_FK_FIELDS: frozenset[str] = frozenset({
    # generic Django content-type framework
    "content_type",
    "content_type_id",
    "object_id",
    # explicit FK suffixes used across v2 models
    "material_id",
    "molecule_id",
    "element_id",
    "region_id",
    "source_id",
    "sink_id",
    "transport_scenario_id",
    "utility_id",
    "reference_id",
    "transport_id",
    "subsystem_id",
    "equipment_id",
    "property_id",
    "tea_equipment_id",
    "cost_id",
    "design_id",
    "condition_id",
    "config_id",
    "index_id",
    "constant_id",
    "mea_id",
    "kpi_id",
    "rc_id",
    "ap_id",
    "case_id",
    "scenario_id",
    "summary_id",
    "ts_id",
    "item_id",
    # any field whose name ends with _id is treated as an FK
})

_FK_SENTINEL = "<set>"

# Leading path prefixes that are deployment-specific and should be stripped
# before comparing paths.  Each entry is tried in order; all matching leading
# segments are removed so that, e.g.:
#   /media/cifs/foo.cif  →  /cifs/foo.cif
#   /srv/app/media/cifs/foo.cif  →  /cifs/foo.cif
#   /cifs/foo.cif  →  /cifs/foo.cif   (no stripping needed — already matches)
_PATH_PREFIXES: tuple[str, ...] = (
    "/media",
    "/static",
    "/files",
    "/uploads",
    "/data",
    "/storage",
    "/srv",
    "/home",
    "/opt",
    "/var",
    "/app",
    "/deploy",
)

# Segments whose presence anywhere in a string value indicates it is a path
_PATH_SEGMENTS: tuple[str, ...] = (
    "/media/",
    "/static/",
    "/files/",
    "/uploads/",
    "/data/",
    "/storage/",
    "/cifs/",
)


def _normalise_path(value: str) -> str:
    """
    Reduce a file-path or URL to a canonical relative form by:

    1. Extracting the URL path component (strips scheme + host).
    2. Normalising backslashes to forward slashes.
    3. Repeatedly stripping any leading deployment-specific prefix segment
       (``/media``, ``/static``, ``/srv``, etc.) until none remain.

    Examples::

        /media/cifs/foo.cif              → /cifs/foo.cif
        /cifs/foo.cif                    → /cifs/foo.cif   (unchanged)
        /srv/app/media/cifs/foo.cif      → /cifs/foo.cif
        https://prod.example.com/media/cifs/foo.cif → /cifs/foo.cif
    """
    from urllib.parse import urlparse
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme else value
    path = path.replace("\\", "/")
    # Strip known leading deployment prefixes (repeat until stable)
    changed = True
    while changed:
        changed = False
        lower = path.lower()
        for prefix in _PATH_PREFIXES:
            if lower.startswith(prefix + "/") or lower == prefix:
                path = path[len(prefix):]
                if not path.startswith("/"):
                    path = "/" + path
                changed = True
                break  # restart loop after each strip
    return path


def _is_fk_field(key: str) -> bool:
    """Return True if *key* is a known FK field or follows the *_id convention."""
    return key in _FK_FIELDS or (key.endswith("_id") and key != "id")


def _looks_like_path(value: str) -> bool:
    """Return True if *value* appears to be a filesystem path or media URL."""
    v = value.replace("\\", "/")
    lower = v.lower()
    return any(seg in lower for seg in _PATH_SEGMENTS)


def _normalise(payload: Any) -> Any:
    """
    Convert a payload (DataFrame, list, dict) to a canonical, comparable form.

    * DataFrames  → list of dicts (rows), sorted by their JSON repr so that
      ordering differences do not cause false failures.
    * Lists       → sorted by JSON repr.
    * Dicts       → recursively sort keys with the following field rules:

        - Own PK (``id``) is dropped — auto-increment values are meaningless
          across databases.
        - FK / content-type id fields are replaced with ``"<set>"`` when
          non-null, or kept as ``None``.  This asserts *presence* without
          comparing the specific integer value, which can differ between dev
          and prod.
        - URL/path fields (``cif_url``, any field ending in ``_url``,
          ``_path``, ``_file``) and any string value that contains a
          recognised media/storage path segment are normalised to strip the
          host-specific root prefix so that deployment-root differences do
          not cause spurious failures.
    """
    if isinstance(payload, pd.DataFrame):
        return _normalise(payload.to_dict(orient="records"))
    if isinstance(payload, list):
        items = [_normalise(item) for item in payload]
        try:
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))
        except TypeError:
            return items
    if isinstance(payload, dict):
        cleaned: dict = {}
        for k, v in payload.items():
            # Drop own PK
            if k in _PK_FIELDS:
                continue
            # FK / content-type ids: assert presence only
            if _is_fk_field(k):
                cleaned[k] = _FK_SENTINEL if v is not None else None
            elif isinstance(v, str) and (
                k.endswith(("_url", "_path", "_file", "_uri"))
                or k in ("cif_url", "file", "path", "url", "uri", "media")
                or _looks_like_path(v)
            ):
                cleaned[k] = _normalise_path(v)
            else:
                cleaned[k] = _normalise(v)
        return {k: cleaned[k] for k in sorted(cleaned)}
    return payload


def _to_json(payload: Any) -> str:
    return json.dumps(_normalise(payload), sort_keys=True, default=str)


def _diff_excerpt(a: str, b: str, max_chars: int = 400) -> str:
    """Return a brief human-readable summary of where two JSON strings differ."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            start = max(0, i - 60)
            snippet_a = a[start : i + 80]
            snippet_b = b[start : i + 80]
            return (
                f"  First difference at char {i}:\n"
                f"  DEV : …{snippet_a}…\n"
                f"  PROD: …{snippet_b}…"
            )
    len_diff = len(a) - len(b)
    if len_diff:
        return f"  Payloads differ only in length (dev {len(a)} chars, prod {len(b)} chars)."
    return "  Payloads are identical."


# ── Check runner ──────────────────────────────────────────────────────────────


class CheckResult:
    def __init__(self, label: str, passed: bool, note: str = ""):
        self.label = label
        self.passed = passed
        self.note = note

    def __str__(self) -> str:
        status = _green("PASS") if self.passed else _red("FAIL")
        line = f"  [{status}] {self.label}"
        if self.note:
            line += f"\n        {self.note}"
        return line


def _run_check(
    label: str,
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    method: str,
    kwargs: dict,
    verbose: bool,
) -> CheckResult:
    """Call *method* on both APIs and compare normalised payloads."""
    try:
        dev_raw = getattr(dev_api, method)(**kwargs)
    except Exception as exc:
        return CheckResult(label, False, f"DEV error: {type(exc).__name__}: {exc}")

    try:
        prod_raw = getattr(prod_api, method)(**kwargs)
    except Exception as exc:
        return CheckResult(label, False, f"PROD error: {type(exc).__name__}: {exc}")

    dev_json = _to_json(dev_raw)
    prod_json = _to_json(prod_raw)

    if dev_json == prod_json:
        return CheckResult(label, True)

    note = ""
    if verbose:
        note = _diff_excerpt(dev_json, prod_json)
    else:
        note = "Payloads differ (run with --verbose for details)."
    return CheckResult(label, False, note)


# ── Endpoint catalogue ────────────────────────────────────────────────────────
# Each entry: (label, method_name, kwargs_dict)
# List endpoints use a small `limit` to keep the run fast while still
# exercising the full serialisation path.


def _build_catalogue(limit: int) -> list[tuple[str, str, dict]]:
    L = limit
    return [
        # ── Health ──────────────────────────────────────────────────────────
        ("health()",                       "health",                        {}),

        # ── Catalog: list endpoints ─────────────────────────────────────────
        (f"list_materials(limit={L})",     "list_materials",                {"limit": L}),
        (f"get_materials_psdi(limit={L})", "get_materials_psdi",            {"limit": L}),
        (f"get_molecules(limit={L})",      "get_molecules",                 {"limit": L}),
        (f"get_elements(limit={L})",       "get_elements",                  {"limit": L}),
        (f"get_regions(limit={L})",        "get_regions",                   {"limit": L}),
        (f"get_sources(limit={L})",        "get_sources",                   {"limit": L}),
        (f"get_sinks(limit={L})",          "get_sinks",                     {"limit": L}),
        (f"get_transport_scenarios(limit={L})",
                                           "get_transport_scenarios",       {"limit": L}),
        (f"get_utilities(limit={L})",      "get_utilities",                 {"limit": L}),
        (f"get_references(limit={L})",     "get_references",                {"limit": L}),
        (f"get_transports(limit={L})",     "get_transports",                {"limit": L}),
        (f"get_subsystems(limit={L})",     "get_subsystems",                {"limit": L}),
        (f"get_equipment(limit={L})",      "get_equipment",                 {"limit": L}),

        # ── Properties / TEA lookup tables ──────────────────────────────────
        # get_properties skipped: GenericForeignKey (content_type_id, object_id)
        # differs between dev and prod even when data is consistent; covered by
        # crosscheck_tables.py --properties for membership checks.
        (f"get_tea_equipment(limit={L})",  "get_tea_equipment",             {"limit": L}),
        (f"get_tea_equipment_costs(limit={L})",
                                           "get_tea_equipment_costs",       {"limit": L}),
        (f"get_tea_equipment_designs(limit={L})",
                                           "get_tea_equipment_designs",     {"limit": L}),
        (f"get_process_conditions(limit={L})",
                                           "get_process_conditions",        {"limit": L}),
        (f"get_process_configurations(limit={L})",
                                           "get_process_configurations",    {"limit": L}),
        (f"get_contactor_configurations(limit={L})",
                                           "get_contactor_configurations",  {"limit": L}),
        (f"get_cost_indices(limit={L})",   "get_cost_indices",              {"limit": L}),
        (f"get_constants(limit={L})",      "get_constants",                 {"limit": L}),
        (f"get_mea_baselines(limit={L})",  "get_mea_baselines",             {"limit": L}),
        (f"get_mea_kpis(limit={L})",       "get_mea_kpis",                  {"limit": L}),

        # ── Science data ─────────────────────────────────────────────────────
        (f"get_isotherm(limit={L})",       "get_isotherm",                  {"limit": L}),
        (f"get_water_kpis(limit={L})",     "get_water_kpis",                {"limit": L}),
        (f"get_carbon_zeopp(limit={L})",   "get_carbon_zeopp",              {"limit": L}),
        (f"get_carbon_zeopp_experimental(limit={L})",
                                           "get_carbon_zeopp_experimental", {"limit": L}),

        # ── TEA / LCA ────────────────────────────────────────────────────────
        (f"get_output_kpis(limit={L})",    "get_output_kpis",               {"limit": L}),
        (f"get_region_costs(limit={L})",   "get_region_costs",              {"limit": L}),
        (f"get_ambient_parameters(limit={L})",
                                           "get_ambient_parameters",        {"limit": L}),

        # ── Cases & Scenarios ────────────────────────────────────────────────
        (f"get_scenarios(limit={L})",      "get_scenarios",                 {"limit": L}),
        (f"get_screening_summaries(limit={L})",
                                           "get_screening_summaries",       {"limit": L}),
    ]


# ── Name-only filter ──────────────────────────────────────────────────────────


def _has_name_key(response: Any) -> bool:
    """Return True if the response contains at least one record with a 'name' key."""
    if isinstance(response, pd.DataFrame):
        return "name" in response.columns
    if isinstance(response, list):
        return bool(response) and isinstance(response[0], dict) and "name" in response[0]
    if isinstance(response, dict):
        return "name" in response
    return False


def _filter_nameonly(
    catalogue: list[tuple[str, str, dict]],
    prod_api: PrismaAPIv2,
) -> list[tuple[str, str, dict]]:
    """
    Probe prod with limit=1 for each catalogue entry and keep only those
    whose response payload contains a top-level 'name' key.
    Endpoints that error or return empty results are silently skipped.
    """
    kept: list[tuple[str, str, dict]] = []
    for label, method, kwargs in catalogue:
        try:
            sample = getattr(prod_api, method)(**{**kwargs, "limit": 1})
            if _has_name_key(sample):
                kept.append((label, method, kwargs))
        except Exception:
            pass  # leave out endpoints that can't be probed
    return kept


# ── Detail-endpoint probing ───────────────────────────────────────────────────


def _probe_detail_checks(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    limit: int,
    verbose: bool,
    nameonly: bool = False,
) -> list[CheckResult]:
    """
    For a handful of detail (single-record) endpoints, fetch the list from
    prod to discover a target name, then look that name up on both dev and
    prod to obtain the correct side-specific PK before calling the detail
    method.  This avoids cross-database PK mismatches.

    Only endpoints that have a straightforward integer-PK detail method are
    probed here.  If the list is empty on prod the check is skipped.
    """
    import inspect

    probes: list[tuple[str, str, str, dict]] = [
        # (list_method, id_field, detail_method, list_kwargs)
        ("get_molecules",          "id", "get_molecule",              {"limit": 1}),
        ("get_elements",           "id", "get_element",               {"limit": 1}),
        ("get_regions",            "id", "get_region",                {"limit": 1}),
        ("get_sources",            "id", "get_source",                {"limit": 1}),
        ("get_sinks",              "id", "get_sink",                  {"limit": 1}),
        ("get_references",         "id", "get_reference",             {"limit": 1}),
        ("get_constants",          "id", "get_constant",              {"limit": 1}),
        ("get_cost_indices",       "id", "get_cost_index",            {"limit": 1}),
        ("get_process_conditions", "id", "get_process_condition",     {"limit": 1}),
        ("get_scenarios",          "id", "get_scenario",              {"limit": 1}),
    ]

    def _pk_from(records: Any, id_field: str) -> int | None:
        if isinstance(records, pd.DataFrame):
            records = records.to_dict(orient="records")
        if isinstance(records, list) and records:
            return int(records[0][id_field])
        return None

    def _resolve_pk_by_name(api: PrismaAPIv2, list_method: str,
                             name: str, id_field: str) -> int | None:
        """Look up *name* on *api* using the list endpoint's name= filter."""
        try:
            result = getattr(api, list_method)(name=name, limit=5)
            rows: list = result.to_dict(orient="records") if isinstance(result, pd.DataFrame) else (result or [])
            # Prefer exact match, fall back to first result
            exact = next((r for r in rows if r.get("name") == name), None)
            row = exact or (rows[0] if rows else None)
            return int(row[id_field]) if row else None
        except Exception:
            return None

    results: list[CheckResult] = []
    for list_method, id_field, detail_method, lkwargs in probes:
        # ── Fetch one record from prod to get the target name ────────────────
        try:
            prod_sample = getattr(prod_api, list_method)(**lkwargs)
            prod_records: list = (
                prod_sample.to_dict(orient="records")
                if isinstance(prod_sample, pd.DataFrame)
                else (prod_sample or [])
            )
            if not prod_records:
                continue
            first_record: dict = prod_records[0]
        except Exception:
            continue

        # --nameonly filter
        if nameonly and not (isinstance(first_record, dict) and "name" in first_record):
            continue

        sig = inspect.signature(getattr(prod_api, detail_method))
        param_name = list(sig.parameters.keys())[0]

        target_name: str | None = first_record.get("name") if isinstance(first_record, dict) else None

        # ── Resolve PKs using name lookup on each side ───────────────────────
        if target_name:
            prod_pk = _resolve_pk_by_name(prod_api, list_method, target_name, id_field)
            dev_pk  = _resolve_pk_by_name(dev_api,  list_method, target_name, id_field)
            label = f"{detail_method}(name='{target_name}')"
        else:
            # No name field — fall back to position-based PK resolution
            prod_pk = _pk_from(prod_records, id_field)
            try:
                dev_sample = getattr(dev_api, list_method)(**lkwargs)
                dev_pk = _pk_from(dev_sample, id_field)
            except Exception:
                dev_pk = None
            label = f"{detail_method}({param_name}=<prod:{prod_pk}/dev:{dev_pk}>)"

        if prod_pk is None:
            results.append(CheckResult(label, False, "PROD error: could not resolve PK"))
            continue
        if dev_pk is None:
            results.append(CheckResult(label, False, f"DEV error: no record matching name='{target_name}' found on dev"))
            continue

        # ── Fetch detail records and compare ────────────────────────────────
        try:
            dev_raw = getattr(dev_api, detail_method)(**{param_name: dev_pk})
        except Exception as exc:
            results.append(CheckResult(label, False, f"DEV error: {type(exc).__name__}: {exc}"))
            continue
        try:
            prod_raw = getattr(prod_api, detail_method)(**{param_name: prod_pk})
        except Exception as exc:
            results.append(CheckResult(label, False, f"PROD error: {type(exc).__name__}: {exc}"))
            continue

        dev_json  = _to_json(dev_raw)
        prod_json = _to_json(prod_raw)
        if dev_json == prod_json:
            results.append(CheckResult(label, True))
        else:
            note = _diff_excerpt(dev_json, prod_json) if verbose else "Payloads differ (run with --verbose for details)."
            results.append(CheckResult(label, False, note))

    return results


# ── Count checks ─────────────────────────────────────────────────────────────


def _count_records(api: PrismaAPIv2, method: str) -> int | None:
    """
    Fetch all records for a list endpoint using a large limit and return the
    total count.  Returns None if the call fails.
    """
    try:
        result = getattr(api, method)(limit=100_000)
        if isinstance(result, pd.DataFrame):
            return len(result)
        if isinstance(result, list):
            return len(result)
        if isinstance(result, dict):
            # health or similar — not a list endpoint
            return None
    except Exception:
        return None
    return None


def _run_count_checks(
    dev_api: PrismaAPIv2,
    prod_api: PrismaAPIv2,
    catalogue: list[tuple[str, str, dict]],
    verbose: bool,
) -> list[CheckResult]:
    """
    For every list endpoint in *catalogue*, fetch the full record count from
    both dev and prod and report PASS when they match.
    """
    results: list[CheckResult] = []
    for _label, method, _kwargs in catalogue:
        dev_n = _count_records(dev_api, method)
        prod_n = _count_records(prod_api, method)

        if dev_n is None and prod_n is None:
            continue  # not a list endpoint (e.g. health)

        label = f"{method}() record count"
        if dev_n is None:
            results.append(CheckResult(label, False, "DEV error: could not retrieve count"))
        elif prod_n is None:
            results.append(CheckResult(label, False, "PROD error: could not retrieve count"))
        elif dev_n == prod_n:
            note = f"{dev_n} records" if verbose else ""
            results.append(CheckResult(label, True, note))
        else:
            results.append(CheckResult(
                label, False,
                f"count mismatch — dev: {dev_n}, prod: {prod_n} ({prod_n - dev_n:+d})",
            ))
    return results


# ── Main ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cross-check PrISMa v2 API: dev instance vs production."
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
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Max records per list endpoint (default: 20).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print a diff excerpt for each FAIL.",
    )
    p.add_argument(
        "--skip-detail",
        action="store_true",
        help="Skip the single-record detail endpoint probes.",
    )
    p.add_argument(
        "--nameonly",
        action="store_true",
        help="Only cross-check endpoints whose responses include a 'name' key.",
    )
    p.add_argument(
        "--count",
        action="store_true",
        help="Cross-check that dev and prod return the same total record count per table.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Load config once; CLI flags override config values
    from prisma_api.config import load_config
    cfg = load_config() or {}

    # Resolve API key (prod key used for prod; dev key used for dev when present)
    api_key = args.key or cfg.get("api_key") or cfg.get("key")
    if not api_key:
        print(
            _red("ERROR: No API key found.  Pass --key KEY or configure config.yaml."),
            file=sys.stderr,
        )
        return 1
    # Dev instances may require a separate key
    dev_api_key = cfg.get("dev_api_key") or api_key

    # Resolve dev host:port — CLI flag takes priority, then config.yaml
    _DEFAULT_DEV_HP = "localhost:8000"
    _cli_hp = args.dev_host_port or ""
    _cfg_hp = str(cfg.get("dev_host_port") or "").strip()
    dev_hp = _cli_hp if _cli_hp and _cli_hp != _DEFAULT_DEV_HP else (_cfg_hp or _DEFAULT_DEV_HP)
    dev_hp = dev_hp.replace("http://", "").replace("https://", "").strip() or _DEFAULT_DEV_HP

    print(_bold("\n" + "═" * 72))
    print(_bold("  PrISMa v2 API Cross-Check: dev vs prod"))
    print(_bold("═" * 72))
    print(f"  Dev server : http://{dev_hp}/api/v2")
    print(f"  Prod server: {prisma_api.prisma_api_v2._BASE_PROD}")
    print(f"  List limit : {args.limit} records per endpoint")
    if args.count:
        print(f"  Count check: {'yes — comparing total records per table (no limit)' }")
    print()

    # Build the two client instances
    dev_api = PrismaAPIv2(
        key=dev_api_key,
        dev=True,
        dev_host_port=dev_hp,
        return_format="json",  # work with plain lists for clean comparison
    )
    prod_api = PrismaAPIv2(
        key=api_key,
        dev=False,
        return_format="json",
    )

    catalogue = _build_catalogue(args.limit)

    if args.nameonly:
        catalogue = _filter_nameonly(catalogue, prod_api)

    all_results: list[CheckResult] = []
    _sep = "  " + "-" * 32

    # ── List / aggregate endpoints ────────────────────────────────────────────
    print(_bold("═" * 72))
    print(_bold("  List & aggregate endpoints"))
    print(_bold("═" * 72))
    for label, method, kwargs in catalogue:
        result = _run_check(label, dev_api, prod_api, method, kwargs, args.verbose)
        all_results.append(result)
        print(str(result))
        if args.verbose:
            print(_sep)

    # ── Detail endpoints ──────────────────────────────────────────────────────
    if not args.skip_detail:
        print()
        print(_bold("═" * 72))
        print(_bold("  Detail (single-record) endpoints"))
        print(_bold("═" * 72))
        detail_results = _probe_detail_checks(
            dev_api, prod_api, args.limit, args.verbose, args.nameonly
        )
        if detail_results:
            for result in detail_results:
                print(str(result))
                if args.verbose:
                    print(_sep)
            all_results.extend(detail_results)
        else:
            print(f"  {_yellow('(no records found on prod to probe — skipped)')}")

    # ── Count checks ─────────────────────────────────────────────────────────
    if args.count:
        print()
        print(_bold("═" * 72))
        print(_bold("  Record count checks (dev vs prod, no limit)"))
        print(_bold("═" * 72))
        count_results = _run_count_checks(dev_api, prod_api, catalogue, args.verbose)
        if count_results:
            for result in count_results:
                print(str(result))
                if args.verbose:
                    print(_sep)
            all_results.extend(count_results)
        else:
            print(f"  {_yellow('(no list endpoints to count — skipped)')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed

    print()
    print(_bold("═" * 72))
    print(_bold("  Summary"))
    print(_bold("═" * 72))
    print(f"  Total checks : {total}")
    print(f"  {_green('Passed')}       : {passed}")
    if failed:
        print(f"  {_red('Failed')}       : {failed}")
        print()
        print(_red("  Failed checks:"))
        for r in all_results:
            if not r.passed:
                print(f"    • {r.label}")
    else:
        print(f"  {_green('All checks passed ✓')}")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
