# PrISMa API — Python Client Reference (v2)

> **Package:** `prisma_api` v0.3.9  
> **v2 Base URL:** `https://prisma-platform.org/api/v2/`  
> **Authentication:** `X-API-Key` header (set via config file or `PRISMA_API_KEY` env var)

See [API_REFERENCE_V1.md](API_REFERENCE_V1.md) for the v1 (`api.get_materials_data`) reference.

---

## Initialisation

```python
import prisma_api

api = prisma_api.init()          # reads key from ~/.config/prisma_api/config.yaml
api.v2                           # PrismaAPIv2 instance, attached automatically
```

---

## v2 Methods (`api.v2`)

All v2 methods are accessed via the `api.v2` attribute. List endpoints return a
`pd.DataFrame` by default; detail endpoints return a `dict`. Call
`api.v2.set_return_format('json')` to make all list endpoints return
`list[dict]` instead (`'dataframe'` restores the default).

---

### Health

#### `api.v2.health()`

```python
api.v2.health()
# {'status': 'ok', 'version': '2.0.0'}
```

---

### Flowsheets

#### `api.v2.get_flowsheet(name='dac_min')`

Returns the DB-normalised flowsheet payload for the named object.

```python
api.v2.get_flowsheet('dac_min')
```

---

#### `api.v2.get_flowsheet_bundle(name='dac_min')`

Returns the bundled flowsheet payload for the named object.

```python
api.v2.get_flowsheet_bundle('dac_min')
```

---

#### `api.v2.upsert_flowsheets(flowsheets, screening_analysis_name=None, on_exists='append', appendix='_v4')`

Bulk-upserts flowsheet records via `PUT /api/v2/flowsheets/upsert/`.

| Argument | Type | Default | Description |
|---|---|---|---|
| `flowsheets` | `pd.DataFrame \| list[dict]` | — | Records to upload. |
| `screening_analysis_name` | `str \| None` | `None` | Should match one of the nested screening-analysis names returned by `list_case_studies()`. Omitting it is experimentation-only and raises a `UserWarning`. |
| `on_exists` | `str` | `'append'` | `'append'` (adds `appendix` suffix on conflict) or `'overwrite'`. |
| `appendix` | `str` | `'_v4'` | Suffix used only in append mode. |

```python
api.v2.upsert_flowsheets(df, screening_analysis_name='UK_2030_screening')
api.v2.upsert_flowsheets(df, on_exists='overwrite')
```

---

### Catalog

#### `api.v2.list_materials(name=None, limit=10_000)`

Fetches all matching materials, paginating internally (page size 500) so
result sets larger than the server default page size are returned
transparently. Prints a one-line summary (`"N materials loaded from <server>"`).

```python
api.v2.list_materials()
api.v2.list_materials(name='ABEX')     # substring filter
api.v2.list_materials(limit=0)          # no cap — fetch everything
```
```
   id    name                                           cif_url  material_id material_backend        gas_basis
0   1  ABEXEM  https://prisma-platform.org/media/structures/ABEXEM.cif       ABEXEM  tabular_binary_iast  [CO2, N2, H2O]
1   2  FOOFOO  https://prisma-platform.org/media/structures/FOOFOO.cif       FOOFOO  tabular_binary_iast       [CO2, N2]
```

Each record also includes `supports_humid_ternary`, `tags`, `provenance`,
`lifecycle`, `metadata`, and `source_path` (mostly reserved/`None` fields).

---

#### `api.v2.preflight_material_check(name)`

Returns `True` if at least one material matches `name` (substring), `False`
otherwise. Thin wrapper over `list_materials(name=name, limit=1)`.

```python
api.v2.preflight_material_check('ABEXEM')   # True
```

---

#### `api.v2.list_cifs(tag=None)`

Returns a plain `list[str]` of MOF names that have CIF files, optionally
filtered by `tag`.

```python
api.v2.list_cifs()
# ['ABEXEM', 'FOOFOO', ...]
```

---

#### `api.v2.get_cifs(mof, structured=True, pandas=True, save_dir=None)`

Fetch CIF payload(s) for one or more MOF names via `GET /api/v2/cifs/files/`.

| Argument | Type | Default | Description |
|---|---|---|---|
| `mof` | `str \| list[str]` | — | One MOF name, or a list for batch fetch. |
| `structured` | `bool` | `True` | Return structured JSON instead of raw CIF text. |
| `pandas` | `bool` | `True` | When `structured=True`, convert tabular sections (e.g. `elements`, `atom_site`) to `pd.DataFrame`. |
| `save_dir` | `str \| None` | `None` | Only valid when `structured=False`; downloads and saves the CIF file(s) to this directory. |

```python
api.v2.get_cifs('ABEXEM')                          # structured dict, nested DataFrames
api.v2.get_cifs(['ABEXEM', 'FOOFOO'])              # list of structured dicts
api.v2.get_cifs('ABEXEM', structured=False, save_dir='./downloads/cifs')
# './downloads/cifs/ABEXEM.cif'
```

---

#### `api.v2.get_material(material_id=None, *, name=None, bundle=<all>, sim_or_exp=None, good_structure=None, limit=500, offset=0, include_cif_text=False, cif_timeout=60)`

Return one or more material detail records, optionally bundled with related
isotherms / Zeo++ / water KPIs / CIF metadata.

| Argument | Description |
|---|---|
| `material_id` | Fetch one material by integer PK. |
| `name` | `str` for one material (name-matched), or `list[str]` for many. Exactly one of `material_id`/`name` must be given. |
| `bundle` | Omit for all bundles `['isotherms','zeopp','water_kpis','cif']`; `None` for root-only; or an explicit subset list. |
| `sim_or_exp`, `good_structure`, `limit`, `offset` | Forwarded as filters to the bundled science-data sub-queries. |
| `include_cif_text` | If `True` (with `'cif'` bundle selected), downloads and parses the CIF text into a structured dict. |
| `cif_timeout` | Timeout (seconds) for the CIF text download. |

```python
api.v2.get_material(1)                                       # by id, all bundles
api.v2.get_material(1, bundle=None)                          # root-only
api.v2.get_material(name='ABEXEM')                           # direct name lookup
api.v2.get_material(name=['ABEXEM', 'HKUST'], bundle=None)   # list lookup -> list[dict]
api.v2.get_material(1, bundle=['isotherms'])                 # only isotherms bundle
```
```python
{
    'id': 1,
    'name': 'ABEXEM',
    'cif_url': 'https://prisma-platform.org/media/structures/ABEXEM.cif',
    'isotherms': [...],
    'zeopp': [...],
    'water_kpis': [...],
    'cif': {'url': '...', 'filename': 'ABEXEM.cif'},
}
```

---

#### `api.v2.get_materials_psdi(name=None, limit=500, offset=0)`

Returns a `pd.DataFrame` of PSDI (extended crystallographic) material records.

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str \| None` | Filter by name substring (case-insensitive) |
| `limit` | `int` | Max records per page (default 500) |
| `offset` | `int` | Pagination offset (default 0) |

Columns returned: `id`, `name`, `cif_url`, `cif_filename`, `formula_descriptive`, `formula_hill`, `formula_reduced`, `formula_anonymous`, `formula`, `formula_calculated`, `chemical_name`, `periodic_dimensions`, `smiles`, `spacegroup_hm`, `spacegroup_hall`, `spacegroup_number`, `cell_volume`, `cell_lengths`, `cell_angles`, `cell_ratios`, `unit_cell`

```python
df = api.v2.get_materials_psdi()
df = api.v2.get_materials_psdi(name='ABEX')
```

---

#### `api.v2.get_material_psdi(material_id)`

Returns a `dict` with the full PSDI detail record for a single material, including all list fields plus linker/node chemistry and element composition.

Extra fields over `get_materials_psdi`: `smiles_linker`, `formula_linker`, `smiles_linker_PubChem`, `formula_linker_PubChem`, `count_dict_PubChem`, `smiles_node`, `formula_node`, `elements` (list of dicts with `symbol`, `atomic_number`, `mass_fraction`)

```python
api.v2.get_material_psdi(1)
```

---

#### `api.v2.get_molecules(name=None, limit=500, offset=0)` / `api.v2.get_molecule(molecule_id)`

```python
api.v2.get_molecules()
api.v2.get_molecule(1)
# {'id': 1, 'name': 'CO2'}
```

---

#### `api.v2.get_elements(symbol=None, name=None, limit=500, offset=0)` / `api.v2.get_element(element_id)`

```python
api.v2.get_elements(symbol='Fe')
api.v2.get_element(26)
# {'id': 26, 'symbol': 'Fe', 'name': 'Iron', 'atomic_number': 26, 'atomic_weight': 55.845}
```

---

#### `api.v2.get_regions(code=None, name=None, limit=500, offset=0)` / `api.v2.get_region(region_id)`

```python
api.v2.get_regions(code='GB')
api.v2.get_region(1)
# {'id': 1, 'name': 'United Kingdom', 'code': 'GB'}
```

---

#### `api.v2.get_sources(name=None, limit=500, offset=0)` / `api.v2.get_source(source_id)`

```python
api.v2.get_sources()
api.v2.get_source(1)
# {'id': 1, 'name': 'Coal Plant', 'short_name': 'CP'}
```

---

#### `api.v2.get_scopes(name=None, limit=500, offset=0)` / `api.v2.get_scope(scope_id)`

```python
api.v2.get_scopes()
api.v2.get_scopes(name='point')
api.v2.get_scope(7)
# {'id': 7, 'name': 'Point Source'}
```

---

#### `api.v2.get_sinks(name=None, limit=500, offset=0)` / `api.v2.get_sink(sink_id)`

```python
api.v2.get_sinks()
api.v2.get_sink(1)
# {'id': 1, 'name': 'North Sea'}
```

---

#### `api.v2.get_transport_scenarios(name=None, limit=500, offset=0)` / `api.v2.get_transport_scenario(ts_id)`

```python
api.v2.get_transport_scenarios()
api.v2.get_transport_scenario(1)
# {'id': 1, 'name': 'Pipeline 200km'}
```

---

#### `api.v2.get_transports(name=None, limit=500, offset=0)` / `api.v2.get_transport(transport_id)`

Transport mode/leg records (distinct from `get_transport_scenarios`).

```python
api.v2.get_transports()
api.v2.get_transport(1)
```

---

#### `api.v2.get_utilities(name=None, limit=500, offset=0)` / `api.v2.get_utility(utility_id)`

```python
api.v2.get_utilities()
api.v2.get_utility(1)
# {'id': 1, 'name': 'Steam'}
```

---

#### `api.v2.get_references(name=None, doi=None, limit=500, offset=0)` / `api.v2.get_reference(ref_id)`

```python
api.v2.get_references(doi='10.1017/9781009157896')
api.v2.get_reference(1)
# {'id': 1, 'Name': 'IPCC AR6', 'Doi': '10.1017/9781009157896'}
```

---

#### `api.v2.get_subsystems(name=None, type=None, limit=500, offset=0)` / `api.v2.get_subsystem(subsystem_id)`

```python
api.v2.get_subsystems(type='dac')
api.v2.get_subsystem(1)
```

---

#### `api.v2.get_properties(name=None, domain=None, category=None, object_id=None, limit=500, offset=0)` / `api.v2.get_property(property_id)`

Generic key/value property records linked to any model object via a Django
`GenericForeignKey` (`object_id`).

```python
api.v2.get_properties(domain='TEA', category='params_amb')
api.v2.get_property(1)
```

---

#### `api.v2.get_equipment(name=None, group=None, limit=500, offset=0)` / `api.v2.get_equipment_item(equipment_id)`

```python
api.v2.get_equipment(group='Blower')
api.v2.get_equipment_item(1)
```

---

#### `api.v2.get_equipment_costs(equipment_id=None, limit=500, offset=0)` / `api.v2.get_equipment_cost(cost_id)`

```python
api.v2.get_equipment_costs(equipment_id=1)
api.v2.get_equipment_cost(1)
```

---

#### `api.v2.get_equipment_designs(equipment_id=None, key=None, limit=500, offset=0)` / `api.v2.get_equipment_design(design_id)`

```python
api.v2.get_equipment_designs(equipment_id=1, key='D1')
api.v2.get_equipment_design(1)
```

---

#### `api.v2.get_process_conditions(name=None, type=None, limit=500, offset=0)` / `api.v2.get_process_condition(condition_id)`

```python
api.v2.get_process_conditions(type='tvsa')
api.v2.get_process_condition(1)
```

---

#### `api.v2.get_process_configurations(name=None, type=None, limit=500, offset=0)` / `api.v2.get_process_configuration(config_id)`

```python
api.v2.get_process_configurations(type='dac')
api.v2.get_process_configuration(1)
```

---

#### `api.v2.get_contactor_configurations(name=None, type=None, limit=500, offset=0)` / `api.v2.get_contactor_configuration(config_id)`

```python
api.v2.get_contactor_configurations(type='kiln')
api.v2.get_contactor_configuration(1)
```

---

#### `api.v2.get_cost_indices(year=None, limit=500, offset=0)` / `api.v2.get_cost_index(index_id)`

```python
api.v2.get_cost_indices(year=2030)
api.v2.get_cost_index(1)
```

---

#### `api.v2.get_constants(param=None, limit=500, offset=0)` / `api.v2.get_constant(constant_id)`

```python
api.v2.get_constants(param='R')
api.v2.get_constant(1)
```

---

#### `api.v2.get_mea_baselines(name=None, limit=500, offset=0)` / `api.v2.get_mea_baseline(mea_id)`

```python
api.v2.get_mea_baselines()
api.v2.get_mea_baseline(1)
```

---

#### `api.v2.get_mea_kpis(name=None, category=None, limit=500, offset=0)` / `api.v2.get_mea_kpi(kpi_id)`

```python
api.v2.get_mea_kpis(category='CAC')
api.v2.get_mea_kpi(1)
```

---

### Science Data

#### `api.v2.get_isotherm(mof=None, molecule=None, temperature_min=None, temperature_max=None, sim_or_exp=None, good_structure=None, limit=500, offset=0)`

> Renamed from `get_isotherms` (plural) — the singular `get_isotherm` is the
> current method name.

```python
api.v2.get_isotherm()                                        # all records
api.v2.get_isotherm(mof='ABEXEM', molecule='CO2')           # by MOF + molecule
api.v2.get_isotherm(sim_or_exp='sim', good_structure=True)  # simulated, good structures only
api.v2.get_isotherm(temperature_min=273, temperature_max=350)
```
```
   id     mof molecule  T_ref_K sim_or_exp  good_structure  Henry_mol_per_kg_Pa  Uptake_mol_per_kg  Heat_kJ_per_mol
0   1  ABEXEM      CO2    298.0        sim            True             1.23e-05               2.45            35.0
1   2  FOOFOO      CO2    303.0        exp           False             4.10e-06               1.12            28.4
```

---

#### `api.v2.get_water_kpis(mof=None, molecule=None, source=None, sim_or_exp=None, good_structure=None, limit=500, offset=0)`

```python
api.v2.get_water_kpis()
api.v2.get_water_kpis(mof='ABEXEM', source='Coal Plant')
api.v2.get_water_kpis(sim_or_exp='sim', good_structure=True)
```
```
   id     mof molecule        source sim_or_exp  good_structure  water_uptake_kg_per_tCO2
0  10  ABEXEM      H2O    Coal Plant        sim            True                      4.12
1  11  FOOFOO      H2O  Natural Gas          exp           True                      5.78
```

Integer FK columns `MOF` / `Molecule` are stripped automatically — use the
human-readable `mof` / `molecule` string columns instead.

---

#### `api.v2.get_carbon_zeopp(mof=None, good_structure=None, limit=500, offset=0)` / `api.v2.get_carbon_zeopp_item(item_id)`

Simulated Zeo++ geometric characterisation data.

```python
api.v2.get_carbon_zeopp(mof='ABEXEM', good_structure=True)
api.v2.get_carbon_zeopp_item(1)
```

---

#### `api.v2.get_carbon_zeopp_experimental(mof=None, limit=500, offset=0)` / `api.v2.get_carbon_zeopp_experimental_item(item_id)`

Experimental Zeo++ geometric characterisation data.

```python
api.v2.get_carbon_zeopp_experimental(mof='ABEXEM')
api.v2.get_carbon_zeopp_experimental_item(1)
```

---

### TEA / LCA Data

#### `api.v2.get_output_kpis(scenario_id=None, mof=None, good_structure=None, limit=500, offset=0)`

```python
api.v2.get_output_kpis()
api.v2.get_output_kpis(scenario_id=830)
api.v2.get_output_kpis(mof='ABEXEM', good_structure=True)
```
```
    id  scenario_id mof_name  purity  recovery  CAPEX_M_USD  LCOC_USD_per_tCO2
0  100          830   ABEXEM    0.96      0.88        42.10              58.30
1  101          830   FOOFOO    0.91      0.79        38.50              64.10
```

---

#### `api.v2.get_output_kpi(kpi_id)`

```python
api.v2.get_output_kpi(100)
```
```python
{
    'id': 100,
    'scenario_id': 830,
    'mof_name': 'ABEXEM',
    'purity': 0.96,
    'recovery': 0.88,
    'CAPEX_M_USD': 42.10,
    'LCOC_USD_per_tCO2': 58.30,
    'good_structure': True,
}
```

---

#### `api.v2.upsert_output_kpis(df)`

Bulk-creates or updates output KPI records. Lookup key: `(scenario, MOF)` integer PKs.

```python
import pandas as pd

df = pd.DataFrame([
    {'scenario': 830, 'MOF': 1, 'purity': 0.96, 'recovery': 0.88},
    {'scenario': 830, 'MOF': 2, 'purity': 0.91, 'recovery': 0.79},
])
api.v2.upsert_output_kpis(df)
# {'created': 2, 'updated': 0}
```

On partial failure (HTTP 207):
```python
# {'created': 1, 'updated': 0, 'errors': [{'item': {...}, 'errors': {'scenario': ['Invalid pk']}}]}
```

---

#### `api.v2.get_region_costs(region=None, name=None, year=None, limit=500, offset=0)`

```python
api.v2.get_region_costs()
api.v2.get_region_costs(region='GB', year=2030)
api.v2.get_region_costs(name='electricity')
```
```
   id                   Name region  Units   Value  Year
0  55  GB_electricity_2030      GB  £/kWh    0.18  2030
1  56      GB_gas_2030          GB  £/GJ    4.50  2030
```

---

#### `api.v2.get_region_cost(rc_id)`

```python
api.v2.get_region_cost(55)
# {'id': 55, 'Name': 'GB_electricity_2030', 'region': 'GB', 'Units': '£/kWh', 'Value': 0.18, 'Year': 2030}
```

---

#### `api.v2.upsert_region_costs(df)`

Bulk-creates or updates region cost records. Lookup key: `Name` (unique).

```python
df = pd.DataFrame([
    {'Name': 'GB_electricity_2030', 'region': 'GB', 'Units': '£/kWh', 'Value': 0.20, 'Year': 2030},
])
api.v2.upsert_region_costs(df)
# {'created': 0, 'updated': 1}
```

---

#### `api.v2.get_ambient_parameters(name=None, limit=500, offset=0)`

```python
api.v2.get_ambient_parameters()
```
```
   id          Name Units
0   1  ambient_T_K      K
1   2  ambient_P_Pa    Pa
2   3  ambient_RH      %
```

---

#### `api.v2.get_ambient_parameter(ap_id)`

```python
api.v2.get_ambient_parameter(1)
# {'id': 1, 'Name': 'ambient_T_K', 'Units': 'K'}
```

---

#### `api.v2.upsert_ambient_parameters(df)`

Bulk-creates or updates ambient parameter records. Lookup key: `Name` (unique).

```python
df = pd.DataFrame([
    {'Name': 'ambient_T_K', 'Units': 'K', 'Value': 288.15},
])
api.v2.upsert_ambient_parameters(df)
# {'created': 0, 'updated': 1}
```

---

### Cases & Scenarios

#### `api.v2.get_cases(source=None, sink=None, region=None, study=None, limit=500, offset=0)`

```python
api.v2.get_cases()
api.v2.get_cases(source='Coal Plant', region='GB')
```
```
     id                  name       source        sink region transport_scenario utilities
0  3372  UK Coal CCS 2030    Coal Plant   North Sea     GB     Pipeline 200km     Steam
1  3373  UK NGCC CCS 2030    Natural Gas  North Sea     GB     Pipeline 200km     Steam
```

---

#### `api.v2.get_case(case_id)`

```python
api.v2.get_case(3372)
```
```python
{
    'id': 3372,
    'name': 'UK Coal CCS 2030',
    'source': 'Coal Plant',
    'sink': 'North Sea',
    'region': 'GB',
    'transport_scenario': 'Pipeline 200km',
    'utilities': 'Steam',
}
```

---

#### `api.v2.list_case_studies(name=None, limit=500, offset=0)`

```python
api.v2.list_case_studies()
api.v2.list_case_studies(name='UK Coal')
```

---

#### `api.v2.get_scenarios(case_id=None, name=None, type=None, limit=500, offset=0)`

```python
api.v2.get_scenarios()
api.v2.get_scenarios(case_id=3372)
api.v2.get_scenarios(case_id=3372, type='TEA')
```
```
    id             name          print_name  type  case_study_id
0  830  baseline_2030   Baseline 2030         TEA           3372
1  831  highcost_2030   High Cost 2030        TEA           3372
2  832  baseline_2030   Baseline 2030         LCA           3372
```

---

#### `api.v2.get_scenario(scenario_id)`

```python
api.v2.get_scenario(830)
```
```python
{
    'id': 830,
    'name': 'baseline_2030',
    'print_name': 'Baseline 2030',
    'type': 'TEA',
    'case_study_id': 3372,
}
```

---

#### `api.v2.get_screening_analysis_bundle(analysis_id)`

```python
api.v2.get_screening_analysis_bundle(1)
```

---

#### `api.v2.get_screening_summaries(scenario_id=None, limit=500, offset=0)` / `api.v2.get_screening_summary(summary_id)`

```python
api.v2.get_screening_summaries(scenario_id=830)
api.v2.get_screening_summary(1)
```

---

### Bundled / Aggregate Queries

These helper methods make several internal calls to assemble a single
structured payload, and print a one-line summary of what was fetched.

#### `api.v2.get_material_property_bundle(mof=None, sim_or_exp=None, good_structure=None, limit=500, offset=0, query=None, name=None)`

Fetches all science data for one MOF in a single call: isotherms, simulated
Zeo++, experimental Zeo++, and water KPIs, with consistent filters applied
across all four sub-queries. `name` is an alias for `mof`.

```python
api.v2.get_material_property_bundle('ABEXEM')
api.v2.get_material_property_bundle('ABEXEM', sim_or_exp='sim', good_structure=True)

# Endpoint-specific overrides via `query`
api.v2.get_material_property_bundle(
    'ABEXEM',
    query={'common': {'limit': 100}, 'isotherms': {'molecule': 'CO2'}},
)
```
```python
{
    'isotherms': ...,            # DataFrame/list
    'zeopp_simulated': ...,
    'zeopp_experimental': ...,
    'water_kpis': ...,           # 'MOF'/'Molecule' PK columns stripped
}
```

Raises `ValueError` if `mof` matches more than one material (use a more
specific name).

---

#### `api.v2.get_material_bundle(mof, sim_or_exp=None, good_structure=None, limit=500, offset=0, query=None, include_cif=False, include_cif_text=False, cif_timeout=60)`

Fetches material detail, PSDI detail, and the full science property bundle
for one MOF in a single call.

```python
api.v2.get_material_bundle('ABEXEM')
api.v2.get_material_bundle('ABEXEM', include_cif=True, include_cif_text=True)
```
```python
{
    'material': {...},           # get_material(..., bundle=None)
    'material_psdi': {...},      # get_material_psdi(...)
    'property_bundle': {...},    # get_material_property_bundle(...)
    'cif': {'url': ..., 'filename': ..., 'text': {...}} | None,
}
```

Raises `ValueError` if `mof` resolves to zero or multiple materials.

---

#### `api.v2.get_cases_bundle(name=None, source=None, sink=None, region=None, limit_cases=100, limit_props=2000)`

Aggregates all related data for one or more `CaseStudy` records, walking the
full relationship graph (source/sink/region/utilities/subsystems, each with
their linked `Property` records, plus scenarios → process conditions →
process configurations). Returns `list[dict]`, one entry per matched case,
and prints a one-line summary per case.

```python
api.v2.get_cases_bundle(source='Coal Plant', region='GB')
```
```python
[
    {
        'case': {...},
        'source': {'record': {...}, 'properties': [...]},
        'sink': {'record': {...}, 'properties': [...]},
        'region': {'record': {...}, 'properties': [...]},
        'utilities': [{'record': {...}, 'properties': [...]}, ...],
        'subsystems': [{'record': {...}, 'properties': [...]}, ...],
        'scenarios': [
            {
                'record': {...},
                'process_conditions': {
                    'record': {...},
                    'properties': [...],
                    'configurations': [{'record': {...}, 'properties': [...]}, ...],
                } | None,
            },
            ...
        ],
    },
    ...
]
```

---

### Case-Pack Builders (`ImportedCasePack` spec)

These helpers reshape live DB records into the nested `CaseSpec` /
`ScenarioSpec` / `ImportedCasePack` schema used for import/export tooling.
Fields that only exist in the originating YAML pack (e.g. `document`,
`root_case_path`, `available_documents`) are not stored server-side and are
returned as `None` / `[]`.

#### `api.v2.build_case_spec(case_id)`

```python
api.v2.build_case_spec(3372)
```
```python
{
    'case_name': 'UK Coal CCS 2030',
    'source_name': 'Coal Plant',
    'sink_name': 'North Sea',
    'region': 'GB',
    'root_case_path': None,
    'source': {'component_type': 'source', 'name': 'Coal Plant', 'document': None, ...},
    'sink': {...},
    'transport': {...} | None,
    'utilities': [{...}, ...],
    'tea_general': None,
    'import_issues': [],
}
```

---

#### `api.v2.build_scenario_spec(scenario_id)`

```python
api.v2.build_scenario_spec(830)
```
```python
{
    'scenario_name': 'baseline_2030',
    'case_name': 'UK Coal CCS 2030',
    'source_name': None,
    'sink_name': None,
    'region': None,
    'process': None,
    'adsorption_scenario': None,
    'process_preview': None,
    'utilities': [],
    'tea_general': None,
    'import_issues': [],
}
```

---

#### `api.v2.build_case_pack(case_id, scenario_id=None)`

Assembles an `ImportedCasePack`-shaped dict for a single case. When
`scenario_id` is omitted, the first scenario found for the case is used (if
any); pass `scenario_id=-1` to force `scenario_spec: None`.

```python
api.v2.build_case_pack(3372)                 # auto-resolves first scenario
api.v2.build_case_pack(3372, scenario_id=830)
api.v2.build_case_pack(3372, scenario_id=-1)  # scenario_spec always None
```
```python
{
    'pack_root': None,
    'case_spec': {...},
    'scenario_spec': {...} | None,
    'available_documents': [],
    'import_issues': [],
}
```

---

#### `api.v2.list_case_packs(source=None, sink=None, region=None, study=None, include_scenarios=False, limit=100, offset=0)`

Returns `list[dict]` of `ImportedCasePack`-shaped records for every matching
case. `scenario_spec` is `None` for every record unless
`include_scenarios=True` (adds one extra request per case — use with small
result sets).

```python
api.v2.list_case_packs(region='GB')
api.v2.list_case_packs(region='GB', include_scenarios=True, limit=20)
```

---

## Pagination

All list endpoints accept `limit` and `offset` parameters for pagination:

```python
# First page
df1 = api.v2.get_output_kpis(scenario_id=830, limit=100, offset=0)

# Second page
df2 = api.v2.get_output_kpis(scenario_id=830, limit=100, offset=100)
```

---

## API Endpoint

All v2 methods route to:

| | URL |
|---|---|
| **Production** | `https://prisma-platform.org/api/v2/` |
| **Dev mode** | `http://localhost:{dev_host_port}/api/v2/` |

---

## Dev Mode

```python
# Enable dev mode (writes to config.yaml)
api.update_dev_mode(True)

# Or set at init time via env vars
# PRISMA_API_DEV=true PRISMA_API_DEV_HOST_PORT=8000 python script.py
```

In dev mode all requests (v1 and v2) are routed to `http://localhost:{dev_host_port}/`.
