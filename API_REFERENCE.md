# PrISMa API — Python Client Reference

> **Package:** `prisma_api` v0.2.8  
> **Base URL (production):** `https://prisma-platform.org/api/`  
> **v2 Base URL:** `https://prisma-platform.org/api/v2/`  
> **Authentication:** `X-API-Key` header (set via config file or `PRISMA_API_KEY` env var)

---

## Initialisation

```python
import prisma_api

api = prisma_api.init()          # reads key from ~/.config/prisma_api/config.yaml
api.v2                           # PrismaAPIv2 instance, attached automatically
```

---

## v1 Methods

### `api.get_materials_data(payload={}, separate_experimental=True)`

Returns processed materials data with nested fields unpacked, zeopp columns
coalesced (simulated preferred over experimental), and a top-level `sim_or_exp`
flag inserted as the first column.

| Argument | Type | Default | Description |
|---|---|---|---|
| `payload` | `dict` | `{}` | Query-parameter payload forwarded to the API. |
| `separate_experimental` | `bool` | `True` | If `True` the return dict contains `simulated` and `experimental` DataFrames split by `sim_or_exp`. If `False` a single `data` DataFrame is returned. |

**Returns:** `dict`

```python
# separate_experimental=True  (default)
result = api.get_materials_data()

result['simulated']      # pd.DataFrame — rows where sim_or_exp == 'sim'
result['experimental']   # pd.DataFrame — rows where sim_or_exp == 'exp'
result['meta']           # {'source': 'prisma-platform.org'}
```

```
# result['simulated'] — example (3 of ~20 columns shown)
   sim_or_exp    name  cif_file                                     Molecule  CO2 Uptake (mol/kg)
0         sim  ABEXEM  https://prisma-platform.org/media/...ABEXEM.cif  CO2              2.45
1         sim  FOOFOO  https://prisma-platform.org/media/...FOOFOO.cif  CO2              1.87
```

```python
# separate_experimental=False  — single combined DataFrame
result = api.get_materials_data(separate_experimental=False)

result['data']   # pd.DataFrame — all rows
result['meta']   # {'source': 'prisma-platform.org'}
```

**Key output columns** (after unpacking and renaming):

| Column | Source |
|---|---|
| `sim_or_exp` | Derived; first column |
| `name` | Material name |
| `cif_file` | Full URL to CIF structure file |
| `Molecule` | `carbon_isotherm__Molecule` |
| `Good Structure` | `carbon_isotherm__good_structure` |
| `CO2 Henry (mol/kg/Pa)` | `carbon_isotherm__Henry_mol_per_kg_Pa` |
| `CO2 Pressure (bar)` | `carbon_isotherm__Pressure_bar` |
| `CO2 Uptake (mol/kg)` | `carbon_isotherm__Uptake_mol_per_kg` |
| `CO2 Heat (kJ/mol)` | `carbon_isotherm__Heat_kJ_per_mol` |
| `CO2 T_ref (K)` | `carbon_isotherm__T_ref_K` |
| `Zeo++ Density_g_per_cm3` | `carbon_zeopp__Density_g_per_cm3` |
| `Zeo++ POAVF` | `carbon_zeopp__POAVF` |
| `Zeo++ Formula` | `carbon_zeopp__Formula` |
| `Zeo++ Cp_J_per_gK` | `carbon_zeopp__Cp_J_per_gK` |
| `Zeo++ DOI` | `carbon_zeopp__DOI` |

---

## v2 Methods (`api.v2`)

All v2 methods are accessed via the `api.v2` attribute.  List endpoints return a
`pd.DataFrame`; detail endpoints return a `dict`.

---

### Health

#### `api.v2.health()`

```python
api.v2.health()
# {'status': 'ok', 'version': '2.0.0'}
```

---

### Catalog

#### `api.v2.get_materials(name=None, limit=500, offset=0)`

```python
api.v2.get_materials()
```
```
   id    name                                           cif_url
0   1  ABEXEM  https://prisma-platform.org/media/structures/ABEXEM.cif
1   2  FOOFOO  https://prisma-platform.org/media/structures/FOOFOO.cif
```

```python
api.v2.get_materials(name='ABEX')   # substring filter
```

---

#### `api.v2.get_material(material_id)`

```python
api.v2.get_material(1)
```
```python
{
    'id': 1,
    'name': 'ABEXEM',
    'cif_url': 'https://prisma-platform.org/media/structures/ABEXEM.cif',
    'elements': [
        {'symbol': 'C',  'atomic_number': 6,  'mass_fraction': 0.452},
        {'symbol': 'H',  'atomic_number': 1,  'mass_fraction': 0.031},
        {'symbol': 'N',  'atomic_number': 7,  'mass_fraction': 0.118},
        {'symbol': 'O',  'atomic_number': 8,  'mass_fraction': 0.204},
        {'symbol': 'Zn', 'atomic_number': 30, 'mass_fraction': 0.195},
    ]
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

#### `api.v2.get_molecules(name=None, limit=500, offset=0)`

```python
api.v2.get_molecules()
```
```
   id  name
0   1   CO2
1   2    N2
2   3   H2O
3   4   CH4
```

---

#### `api.v2.get_molecule(molecule_id)`

```python
api.v2.get_molecule(1)
# {'id': 1, 'name': 'CO2'}
```

---

#### `api.v2.get_elements(symbol=None, name=None, limit=500, offset=0)`

```python
api.v2.get_elements()
```
```
   id symbol      name  atomic_number  atomic_weight
0   1      H  Hydrogen              1          1.008
1   6      C    Carbon              6         12.011
2   7      N  Nitrogen              7         14.007
```

```python
api.v2.get_elements(symbol='Fe')
```

---

#### `api.v2.get_element(element_id)`

```python
api.v2.get_element(26)
# {'id': 26, 'symbol': 'Fe', 'name': 'Iron', 'atomic_number': 26, 'atomic_weight': 55.845}
```

---

#### `api.v2.get_regions(code=None, name=None, limit=500, offset=0)`

```python
api.v2.get_regions()
```
```
   id             name code
0   1   United Kingdom   GB
1   2          Germany   DE
2   3           Norway   NO
```

```python
api.v2.get_regions(code='GB')
```

---

#### `api.v2.get_region(region_id)`

```python
api.v2.get_region(1)
# {'id': 1, 'name': 'United Kingdom', 'code': 'GB'}
```

---

#### `api.v2.get_sources(name=None, limit=500, offset=0)`

```python
api.v2.get_sources()
```
```
   id            name short_name
0   1      Coal Plant         CP
1   2  Natural Gas CC       NGCC
2   3    Cement Plant        CEM
```

---

#### `api.v2.get_source(source_id)`

```python
api.v2.get_source(1)
# {'id': 1, 'name': 'Coal Plant', 'short_name': 'CP'}
```

---

#### `api.v2.get_sinks(name=None, limit=500, offset=0)`

```python
api.v2.get_sinks()
```
```
   id          name
0   1      North Sea
1   2  Depleted Well
```

---

#### `api.v2.get_sink(sink_id)`

```python
api.v2.get_sink(1)
# {'id': 1, 'name': 'North Sea'}
```

---

#### `api.v2.get_transport_scenarios(name=None, limit=500, offset=0)`

```python
api.v2.get_transport_scenarios()
```
```
   id             name
0   1   Pipeline 200km
1   2   Pipeline 500km
2   3   Ship 1000km
```

---

#### `api.v2.get_transport_scenario(ts_id)`

```python
api.v2.get_transport_scenario(1)
# {'id': 1, 'name': 'Pipeline 200km'}
```

---

#### `api.v2.get_utilities(name=None, limit=500, offset=0)`

```python
api.v2.get_utilities()
```
```
   id   name
0   1  Steam
1   2  Power
```

---

#### `api.v2.get_utility(utility_id)`

```python
api.v2.get_utility(1)
# {'id': 1, 'name': 'Steam'}
```

---

#### `api.v2.get_references(name=None, doi=None, limit=500, offset=0)`

```python
api.v2.get_references()
```
```
   id              Name                   Doi
0   1          IPCC AR6     10.1017/9781009157896
1   2  NETL Cost Manual  10.2172/1893822
```

```python
api.v2.get_references(doi='10.1017/9781009157896')
```

---

#### `api.v2.get_reference(ref_id)`

```python
api.v2.get_reference(1)
# {'id': 1, 'Name': 'IPCC AR6', 'Doi': '10.1017/9781009157896'}
```

---

### Science Data

#### `api.v2.get_isotherms(mof=None, molecule=None, temperature_min=None, temperature_max=None, sim_or_exp=None, good_structure=None, limit=500, offset=0)`

```python
api.v2.get_isotherms()                                        # all records
api.v2.get_isotherms(mof='ABEXEM', molecule='CO2')           # by MOF + molecule
api.v2.get_isotherms(sim_or_exp='sim', good_structure=True)  # simulated, good structures only
api.v2.get_isotherms(temperature_min=273, temperature_max=350)
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

For v1 `get_materials_data` the `result['meta']['source']` key indicates which
host responded.

---

## Dev Mode

```python
# Enable dev mode (writes to config.yaml)
api.update_dev_mode(True)

# Or set at init time via env vars
# PRISMA_API_DEV=true PRISMA_API_DEV_HOST_PORT=8000 python script.py
```

In dev mode all requests are routed to `http://localhost:{dev_host_port}/`.
