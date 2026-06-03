# PrISMa API — Development Summary

## Overview

`prisma_api` is a Python client package providing a clean, tested interface to the PrISMa (Platform for the Integration of Sorbent Materials) REST API. It exposes both the original v1 endpoint (material screening data) and the full v2 endpoint surface (catalog, science, and TEA/LCA data), with automatic authentication, pagination handling, and structured `pandas` DataFrame outputs.

---

## Package Architecture

```
prisma_api/
├── prisma_api/
│   ├── __init__.py          # Package entry point, exposes init()
│   ├── config.py            # API key config wizard (reads/writes ~/.config/prisma_api/config.yaml)
│   ├── prisma_api.py        # v1 client class; attaches api.v2 on init
│   └── prisma_api_v2.py     # v2 client class (PrismaAPIv2)
├── tests/
│   ├── test_prisma_api.py   # v1 tests (20 tests)
│   └── test_prisma_api_v2.py# v2 tests (59 tests)
├── examples/
│   └── prisma_api_demo.ipynb# Interactive demo notebook
├── API_REFERENCE.md         # Full endpoint reference documentation
├── pyproject.toml           # Build config, dependencies, pytest settings
└── .github/workflows/ci.yml # CI pipeline (Python 3.10 / 3.11 / 3.12)
```

---

## Work Carried Out

### 1. v1 Client — `get_materials_data`

The original v1 endpoint returns a complex nested JSON structure. The `get_materials_data` method was built to:

- **Unpack nested fields** — `carbon_isotherm` sub-dict entries are promoted to top-level columns.
- **Coalesce Zeo++ columns** — `carbon_zeopp` (simulated) takes priority over `carbon_zeopp_experimental`; the experimental-only column is removed.
- **Insert `sim_or_exp` flag** — prepended as the first column (`'sim'` or `'exp'`), enabling easy filtering.
- **Rename columns** — verbose API field names are shortened to concise display names.
- **Resolve `cif_file` URLs** — relative paths are prepended with the base host URL to produce absolute download links.
- **Split experimental/simulated** — `separate_experimental=True` (default) returns `{'simulated': df, 'experimental': df, 'meta': {...}}`; `False` returns a single combined DataFrame.
- **URL fallback** — tries `prisma-platform.org` then the legacy `dun-eideann-labs.co.uk` host, recording the successful source in `meta['source']`.

---

### 2. v2 Client — `PrismaAPIv2`

A fully separate class (`prisma_api_v2.py`) was built to wrap the entire v2 REST surface, instantiated automatically as `api.v2`.

#### Internal helpers

| Helper | Purpose |
|--------|---------|
| `_get(path, params)` | Authenticated GET; single prod URL or `localhost` in dev mode |
| `_put(path, data)` | Authenticated PUT (upsert) |
| `_to_df(response)` | Unwraps paginated envelope `{count, results}` into a DataFrame |
| `_resolve_cif_url_df(df)` | Prepends host to relative `cif_url` values in a DataFrame |
| `_resolve_cif_url_dict(d)` | Same for a single detail dict |
| `_base_url()` | Returns prod or dev base URL |

The `_resolve_cif_url_*` helpers were added after discovering that the Django dev server returns relative `/cifs/...` paths from `FileField.url` when `MEDIA_URL` is not an absolute URL. All four material methods apply these helpers so `cif_url` is always an absolute, usable URL regardless of environment.

#### Endpoints implemented

**Catalog (read-only)**

| Wrapper | Endpoint |
|---------|---------|
| `get_materials` / `get_material` | `GET /api/v2/materials/[{id}/]` |
| `get_materials_psdi` / `get_material_psdi` | `GET /api/v2/materials-psdi/[{id}/]` |
| `get_molecules` / `get_molecule` | `GET /api/v2/molecules/[{id}/]` |
| `get_elements` / `get_element` | `GET /api/v2/elements/[{id}/]` |
| `get_regions` / `get_region` | `GET /api/v2/regions/[{id}/]` |
| `get_sources` / `get_source` | `GET /api/v2/sources/[{id}/]` |
| `get_sinks` / `get_sink` | `GET /api/v2/sinks/[{id}/]` |
| `get_transport_scenarios` / `get_transport_scenario` | `GET /api/v2/transport-scenarios/[{id}/]` |
| `get_utilities` / `get_utility` | `GET /api/v2/utilities/[{id}/]` |
| `get_references` / `get_reference` | `GET /api/v2/references/[{id}/]` |

**Science data**

| Wrapper | Endpoint |
|---------|---------|
| `get_isotherms` | `GET /api/v2/isotherms/` |
| `get_water_kpis` | `GET /api/v2/water-kpis/` |

**TEA / LCA data (read + upsert)**

| Wrapper | Endpoint |
|---------|---------|
| `get_output_kpis` / `get_output_kpi` / `upsert_output_kpis` | `GET/PUT /api/v2/output-kpis/` |
| `get_region_costs` / `get_region_cost` / `upsert_region_costs` | `GET/PUT /api/v2/region-costs/` |
| `get_ambient_parameters` / `get_ambient_parameter` / `upsert_ambient_parameters` | `GET/PUT /api/v2/ambient-parameters/` |
| `get_cases` / `get_case` | `GET /api/v2/cases/[{id}/]` |
| `get_scenarios` / `get_scenario` | `GET /api/v2/scenarios/[{id}/]` |

#### PSDI endpoint — `materials-psdi`

The `materials-psdi` endpoint was identified in the dev server source (`api_v2.py`, `serializers_v2.py`) and added as a separate wrapper pair. It returns the full extended MOF record:

- **List fields (20):** `id`, `name`, `cif_url`, `cif_filename`, `formula_*` (×6), `chemical_name`, `periodic_dimensions`, `smiles`, `spacegroup_hm/hall/number`, `cell_volume/lengths/angles/ratios`, `unit_cell`
- **Detail adds (8):** `smiles_linker`, `formula_linker`, `smiles_linker_PubChem`, `formula_linker_PubChem`, `count_dict_PubChem`, `smiles_node`, `formula_node`, `elements` (nested list)

---

### 3. Dev Mode

All v2 requests route to `http://localhost:{port}/api/v2` when `api.update_dev_mode(True)` is called. This is plumbed through the `_base_url()` helper and used consistently by `_get`, `_put`, and the `cif_url` resolvers.

---

### 4. Test Suite

Tests use `pytest` with the `responses` library for HTTP mocking — no real network calls are made.

| File | Tests | Coverage |
|------|-------|---------|
| `test_prisma_api.py` | 20 | v1 `get_materials_data`: URL fallback, field unpacking, column renaming, sim/exp split, dev mode, auth header |
| `test_prisma_api_v2.py` | 59 | Every v2 wrapper: happy path, filters, detail records, upsert 201/207, HTTP error propagation, PSDI list/filter/detail/empty |

**Total: 79 tests, all passing.**

Key test patterns:
- `responses.activate` decorator intercepts all `requests` calls
- Mock payloads mirror actual serializer field sets (confirmed against dev server source)
- `test_health_http_error_raises` confirms `raise_for_status()` propagates on 5xx
- PSDI tests include a comprehensive `_PSDI_RECORD` fixture covering all 20 list fields plus all 8 detail-only fields

---

### 5. CI Pipeline

`.github/workflows/ci.yml` runs on every push and pull request:

- Matrix: **Python 3.10, 3.11, 3.12**
- Steps: checkout → setup Python → install package + dev dependencies → `pytest`
- Coverage upload to **Codecov** on the Python 3.11 run

`pyproject.toml` was extended with:
```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "responses"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

### 6. API Reference Documentation

`API_REFERENCE.md` provides a full reference for all endpoints, including:

- Method signatures with typed parameters
- Return type (DataFrame or dict)
- Column/field listings
- Example calls
- Notes on pagination, dev mode, and URL resolution

---

### 7. Demo Notebook

`examples/prisma_api_demo.ipynb` is a runnable walkthrough of the entire client:

| Section | Content |
|---------|---------|
| 1 · Setup | `prisma_api.init()`, version/key/dev-mode display |
| 2 · v1 | `get_materials_data` — split and combined, column inspection |
| 3 · v2 Health | `api.v2.health()` |
| 4 · v2 Catalog | Materials, PSDI, Molecules, Elements, Regions, Sources, Sinks, Transport, Utilities, References |
| 5 · v2 Science | Isotherms (filters: molecule, sim/exp, good_structure, temperature range), Water KPIs |
| 6 · v2 TEA/LCA | Cases, Scenarios, Output KPIs + upsert, Region Costs + upsert, Ambient Parameters + upsert |
| 7 · Pagination | Manual `limit`/`offset` pattern with `pd.concat` |
| 8 · Dev Mode | Toggling between prod and localhost |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `api.v2` as a sub-object | Keeps v1 and v2 namespaces clean; v1 `init()` remains the single entry point |
| Always return DataFrames from list endpoints | Consistent, immediately usable in pandas workflows |
| `_resolve_cif_url_*` applied at the wrapper level | Dev server returns relative paths; resolution is transparent to callers |
| Single prod URL for v2 (no fallback loop) | v2 is only on `prisma-platform.org`; the loop added complexity with no benefit |
| v1 retains URL fallback | v1 data is still served from the legacy host during transition |
| Mock-only tests | Deterministic, fast, no dependency on live API or VPN |
