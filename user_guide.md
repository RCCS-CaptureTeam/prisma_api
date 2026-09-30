# PrISMa API v2 — User Guide

## Contents

1. [Installation & Setup](#1-installation--setup)
2. [Initialisation](#2-initialisation)
3. [Output Format](#3-output-format)
4. [Materials](#4-materials)
5. [Science Data](#5-science-data)
6. [Case Studies & Scenarios](#6-case-studies--scenarios)
7. [TEA / LCA Reference Data](#7-tea--lca-reference-data)
8. [Flowsheets](#8-flowsheets)
9. [Write Endpoints (Upsert)](#9-write-endpoints-upsert)
10. [Utility Lookups](#10-utility-lookups)
11. [Advanced Filtering](#11-advanced-filtering)

---

## 1. Installation & Setup

```bash
pip install prisma-api
```

An API key is required. Store it in the config file (recommended) or pass it directly:

```python
import prisma_api
prisma_api.locate_config()   # shows config file location
```

---

## 2. Initialisation

The v2 client is exposed as `api.v2` after the standard initialisation:

```python
import prisma_api

api = prisma_api.init()      # reads API key from config
v2  = api.v2                 # PrismaAPIv2 instance
```

Check connectivity:

```python
v2.health()
# {'status': 'ok', ...}
```

---

## 3. Output Format

All **list** endpoints return a `pandas.DataFrame` by default. Switch to plain
`list[dict]` at any time:

```python
v2.set_return_format('json')       # list endpoints → list[dict]
v2.set_return_format('dataframe')  # back to DataFrames (default)
```

Detail endpoints (single-record lookups by integer PK) always return `dict`.

---

## 4. Materials

### 4.1 List all materials

```python
df = v2.list_materials()
# Returns a DataFrame with id, name, cif_url, gas_basis, …
```

Filter by name substring and limit the result set:

```python
df = v2.list_materials(name='ABEXEM', limit=50)
```

### 4.2 Material detail (with bundled science data)

Fetch a single MOF by name together with all its related data in one call:

```python
record = v2.get_material(name='ABEXEM')
# keys: id, name, cif_url, isotherms, zeopp, water_kpis, cif, …
```

Control which sub-sections are included with `bundle`:

```python
# All bundles (default — isotherms, zeopp, water_kpis, cif)
record = v2.get_material(name='ABEXEM')

# Only isotherms
record = v2.get_material(name='ABEXEM', bundle=['isotherms'])

# Root fields only (no sub-sections)
record = v2.get_material(name='ABEXEM', bundle=None)
```

Fetch multiple MOFs at once:

```python
records = v2.get_material(name=['ABEXEM', 'KAXNAP'])
# Returns list[dict]
```

Fetch by integer PK:

```python
record = v2.get_material(material_id=42)
```

### 4.3 Extended crystallographic data (PSDI)

```python
df  = v2.get_materials_psdi(name='ABEXEM')    # list → DataFrame
rec = v2.get_material_psdi(material_id=42)    # single → dict
# Extra fields: chemical formulae, SMILES, space group, cell geometry, CIF URL/filename
```

### 4.4 All science data for one MOF

```python
bundle = v2.get_material_property_bundle('ABEXEM')
# keys: isotherms, zeopp_simulated, zeopp_experimental, water_kpis

# Narrow to simulated data only
bundle = v2.get_material_property_bundle('ABEXEM', sim_or_exp='sim')

# Narrow to good structures
bundle = v2.get_material_property_bundle('ABEXEM', good_structure=True)
```

### 4.5 Full material + PSDI + science bundle in one call

```python
full = v2.get_material_bundle('ABEXEM')
# keys: material, material_psdi, property_bundle, cif

# Include CIF file URL and download CIF text
full = v2.get_material_bundle('ABEXEM', include_cif=True, include_cif_text=True)
```

### 4.6 Server-side bundles for one or many materials

`get_material_bundles` calls the bundle endpoints, which return every
per-material section in a single request — no client-side fan-out.

```python
# One material → the bundle dict itself
b = v2.get_material_bundles('Zeolite_13X')
b['sections']          # which of the 12 sections this response carries
b['counts']            # rows per section
b['material']          # material detail
pd.DataFrame(b['isotherms'])

b = v2.get_material_bundles(84368)      # by material id

# Many materials → an envelope
env = v2.get_material_bundles(['Zeolite_13X', 'ABEXEM'])
env['count'], env['missing'], env['results']

# Trim the payload
v2.get_material_bundles('Zeolite_13X', sections=['cifs', 'isotherms'])
v2.get_material_bundles('Zeolite_13X', exclude='water_kpis')
v2.get_material_bundles('Zeolite_13X', include_cif_content=True)   # raw CIF text

# Substring matching, and a zip download (one JSON per material + manifest)
v2.get_material_bundles(['Zeolite'], match='contains')
v2.get_material_bundles(['Zeolite_13X'], output='zip', save_path='bundles.zip')
```

Every section is a list except `mof_h2`, which is a single object or `None`.
Read the response's `sections` key rather than assuming all twelve are present.
`missing` lists names that matched nothing — a partial success, not an error.
Requests over 200 materials are batched automatically (the server caps a single
request at 200); `output='zip'` is one request, so it is capped at 200.

### 4.7 Writing a bundle back

`upsert_material_bundles` is the write counterpart of `get_material_bundles`:
it takes the same document the read endpoint returns, so a bundle can be read,
edited and posted back. Every row matches on its `id`, so only the edited value
changes. Computed keys (`_schema`, `sections`, `counts`, `cif_url`, `mof`, …)
are ignored by the server and can be left in place.

```python
b = v2.get_material_bundles('Zeolite_13X')
b['isotherms'][0]['T_ref_K'] = 298.15
v2.upsert_material_bundles(b)
# → {'materials': 1, 'created': {}, 'updated': {'isotherms': 1}, 'results': [...]}

# Several materials in one call
v2.upsert_material_bundles([bundle_a, bundle_b])
```

Sending a bundle to a *different* database than it was read from: its ids and
tag ids mean nothing there, so strip them and pass tag names.

```python
v2.upsert_material_bundles(
    b, strip_ids=True, tag_names={2: 'MOFevaluator', 1: 'PrISMa V1'})
```

CIF files travel with the payload, either as multipart parts or inline:

```python
v2.upsert_material_bundles(b, cif_files='Zeolite_13X.cif')                # upload
v2.upsert_material_bundles(b, cif_files='Zeolite_13X.cif', inline_cifs=True)
v2.upsert_material_bundles([b1, b2], cif_files={'Zeolite_13X': 'Zeolite_13X.cif'})
```

Each file attaches to the `cifs` row whose `filename` it matches, or is appended
as a new row. A CIF the database does not already have needs its file — a
metadata-only row is rejected.

Each row's structural metadata — formulae, cell lengths, angles, volume,
symmetry and space group — is derived from the CIF text itself, so the row
describes the file being sent:

```python
# default: derived values overwrite the row, the file being the source of truth
v2.upsert_material_bundles(b, cif_files='Zeolite_13X.cif')

# keep values already on the row, fill only what is missing or None
v2.upsert_material_bundles(b, cif_files='Zeolite_13X.cif',
                           derive_cif_metadata='fill')

# send the metadata exactly as given
v2.upsert_material_bundles(b, cif_files='Zeolite_13X.cif',
                           derive_cif_metadata=False)
```

Derivation also applies to rows that already carry `content` (a bundle read with
`include_cif_content=True`). Formulae are counted from the atom-site loop and
listed alphabetically with explicit counts (`Al86 Na86 O384 Si106`); fields the
file does not carry are left alone, and `material` is never touched.

Notes:

- Writable sections: `material`, `cifs`, `isotherms`, `water_kpis`,
  `carbon_zeopp`, `carbon_zeopp_experimental`, `zeopp_metrics`, `mof_h2`,
  `h2_results`. `adsorption_singlepoint`, `heat_capacity`, `isotherm_h2` and
  `mofchecker` are read-only here — use their own `upsert_*` methods. Empty is
  fine; populated raises.
- `create_materials=False` makes an unknown material name an error instead of
  creating it.
- Nothing is ever deleted: re-posting a payload with a row removed leaves that
  row in place.
- A 207 (partial success) returns the body with an `errors` list and raises a
  `UserWarning`. Each bundle is its own transaction, so retry only the failed
  indices — re-sending everything re-applies the bundles that succeeded.

### 4.8 Check a material exists

```python
v2.preflight_material_check('ABEXEM')   # → True / False
```

---

## 5. Science Data

All list endpoints support `limit` and `offset` for pagination.

### Isotherms

```python
df = v2.get_isotherm(mof='ABEXEM', molecule='CO2')
df = v2.get_isotherm(mof='ABEXEM', sim_or_exp='sim', good_structure=True)
df = v2.get_isotherm(temperature_min=293, temperature_max=333)
```

### Water KPIs

```python
df = v2.get_water_kpis(mof='ABEXEM')
df = v2.get_water_kpis(mof='ABEXEM', sim_or_exp='exp')
```

### Zeo++ geometric characterisation

```python
# Simulated
df = v2.get_carbon_zeopp(mof='ABEXEM', good_structure=True)

# Experimental
df = v2.get_carbon_zeopp_experimental(mof='ABEXEM')
```

### Output KPIs (TEA results)

```python
df = v2.get_output_kpis(mof='ABEXEM')
df = v2.get_output_kpis(scenario_id=7)
```

---

## 6. Case Studies & Scenarios

### List case studies

```python
df = v2.list_case_studies()
df = v2.list_case_studies(name='DAC')
```

### List and fetch cases

```python
df   = v2.get_cases()
df   = v2.get_cases(source='Coal', sink='EOR', region='GB')
case = v2.get_case(case_id=3)
```

### Scenarios

```python
df   = v2.get_scenarios(case_id=3)
df   = v2.get_scenarios(type='TEA')
scen = v2.get_scenario(scenario_id=12)
```

### Full case bundle

Fetches a case together with its source, sink, region, utilities, subsystems,
and the full scenario → process conditions → process configuration hierarchy:

```python
bundles = v2.get_cases_bundle(name='DAC Minimal')
# Each entry: case, source, sink, region, utilities, subsystems, scenarios

# Filter by source / sink / region
bundles = v2.get_cases_bundle(source='Coal', sink='EOR', region='GB')
```

Each bundle entry is a nested dict:

```
{
  "case":       { ...case fields... },
  "source":     { "record": {...}, "properties": [...] },
  "sink":       { "record": {...}, "properties": [...] },
  "region":     { "record": {...}, "properties": [...] },
  "utilities":  [ { "record": {...}, "properties": [...] }, ... ],
  "subsystems": [ { "record": {...}, "properties": [...] }, ... ],
  "scenarios": [
    {
      "record": {...},
      "process_conditions": {
        "record":         {...},
        "properties":     [...],
        "configurations": [ { "record": {...}, "properties": [...] }, ... ]
      }
    },
    ...
  ]
}
```

### Screening analysis bundle

```python
bundle = v2.get_screening_analysis_bundle(analysis_id=1)
```

---

## 7. TEA / LCA Reference Data

```python
# Sources, sinks, regions, utilities
df = v2.get_sources(name='Coal')
df = v2.get_sinks()
df = v2.get_regions(code='GB')
df = v2.get_utilities(name='Electricity')

# Properties (GFK-linked to any model)
df = v2.get_properties(domain='TEA', category='params_amb')
df = v2.get_properties(object_id=42)

# Process definitions
df = v2.get_process_conditions(type='tvsa')
df = v2.get_process_configurations(type='dac')
df = v2.get_contactor_configurations()

# Equipment
df = v2.get_equipment(group='Blower')
df = v2.get_equipment_costs(equipment_id=5)
df = v2.get_equipment_designs(key='D1')

# Economic reference data
df = v2.get_region_costs(region='GB', year=2023)
df = v2.get_cost_indices(year=2023)
df = v2.get_ambient_parameters()

# MEA baseline
df = v2.get_mea_baselines()
df = v2.get_mea_kpis(category='CAC')

# Physical constants
df = v2.get_constants(param='R')

# Molecules and elements
df = v2.get_molecules(name='CO2')
df = v2.get_elements(symbol='Fe')

# References / transport
df = v2.get_references(doi='10.1039/xxx')
df = v2.get_transports()
df = v2.get_transport_scenarios()
df = v2.get_subsystems(type='dac')
```

All list endpoints have a matching single-record detail method that accepts an
integer PK, e.g.:

```python
v2.get_source(source_id=1)
v2.get_region(region_id=5)
v2.get_molecule(molecule_id=2)
v2.get_element(element_id=26)
v2.get_reference(ref_id=10)
v2.get_process_condition(condition_id=3)
v2.get_equipment_item(equipment_id=7)
```

---

## 8. Flowsheets

### Fetch a flowsheet

```python
payload = v2.get_flowsheet(name='dac_min')
bundle  = v2.get_flowsheet_bundle(name='dac_min')
```

### Upload flowsheets

```python
import pandas as pd

df = pd.read_json('my_flowsheets.json')

# Append (default — adds a suffix to avoid conflicts)
result = v2.upsert_flowsheets(
    df,
    screening_analysis_name='my_screening_run',
    on_exists='append',
    appendix='_v2',
)

# Overwrite existing records
result = v2.upsert_flowsheets(
    df,
    screening_analysis_name='my_screening_run',
    on_exists='overwrite',
)
```

`screening_analysis_name` must match a screening analysis name that already
exists in the database (see `v2.list_case_studies()` for valid names).

---

## 9. Write Endpoints (Upsert)

| Method | Lookup key |
|--------|-----------|
| `upsert_flowsheets(df, ...)` | scenario + MOF |
| `upsert_output_kpis(df)` | `(scenario, MOF)` integer PKs |
| `upsert_region_costs(df)` | `Name` (unique) |
| `upsert_ambient_parameters(df)` | `Name` (unique) |

All upsert methods accept a `pd.DataFrame` (or `list[dict]`) and return a
summary dict with `created`, `updated` and optionally `errors` keys.

---

## 10. Utility Lookups

These are helper methods that do not map to a single REST endpoint:

| Method | Description |
|--------|-------------|
| `health()` | Check API connectivity |
| `set_return_format('dataframe'\|'json')` | Toggle output format globally |
| `preflight_material_check(name)` | Return `True` if a MOF name exists |

---

## 11. Advanced Filtering

`get_material_property_bundle` and `get_material_bundle` accept an optional
`query` dict that lets you pass per-endpoint filters beyond the convenience
parameters:

```python
bundle = v2.get_material_property_bundle(
    'ABEXEM',
    query={
        # Applied to every science endpoint
        'common': {'limit': 200},

        # Override for isotherms only
        'isotherms': {'molecule': 'CO2'},

        # Override for simulated Zeo++ only
        'zeopp_simulated': {'good_structure': 'true'},
    }
)
```

Supported `query` keys: `materials`, `isotherms`, `zeopp_simulated`,
`zeopp_experimental`, `water_kpis`, `common`.

`common` values are merged into all four science endpoints; endpoint-specific
keys take precedence over `common`.
