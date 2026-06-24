# PrISMa API

Python client for the PrISMa platform APIs.

This package provides:

- legacy v1 wrappers on the main `api` object
- a larger v2 REST client on `api.v2`
- local config-based API-key management

PrISMa is a platform for numerical synthesis and assessment of metal-organic frameworks and related carbon-capture workflows.

## Installation

### From PyPI

```bash
pip install prisma_api
```

### Requirements

- Python 3.10+
- Runtime dependencies are installed automatically from `pyproject.toml`

## Authentication and configuration

The client uses an API key stored in a local config file.

### First-time setup

```python
import prisma_api

api = prisma_api.init()
```

On first use, the package creates a config file and prompts for an API key.

### Upgrades

```python
pip install --upgrade prisma_api
```

### Find the config path

```python
from prisma_api.config import locate_config

print(locate_config())
```

Typical locations:

- macOS/Linux: `~/.config/prisma_api/config.yaml`
- Windows: `%APPDATA%/prisma-api/prisma_api/config.yaml`

### Create or update the config programmatically

```python
from prisma_api.config import create_config_file

create_config_file(api_key="YOUR_API_KEY_HERE")
```

### Environment-variable mode

If you do not want to use the config file:

```bash
export PRISMA_API_KEY="YOUR_API_KEY_HERE"
export PRISMA_API_DEV="False"
```

```python
from prisma_api.prisma_api import prisma_api

api = prisma_api(use_config_file=False)
```

## Quick start

```python
import prisma_api

api = prisma_api.init()

# v2 list endpoints return JSON by default in the main client
materials = api.v2.list_materials(name="ABEX")
print(materials[:2])

# switch list endpoints to pandas DataFrames if preferred
api.set_return_format("dataframe")
materials_df = api.v2.list_materials(name="ABEX")
print(materials_df.head())
```

### Flowsheets

```python
import prisma_api

api = prisma_api.init()

flowsheet = api.v2.get_flowsheet(name="dac_min")
```


## Return formats

All v2 list endpoints support two formats:

- `json`: returns `list[dict]`
- `dataframe`: returns `pandas.DataFrame`

Detail endpoints always return `dict`.

```python
api.set_return_format("json")
records = api.v2.get_molecules()

api.set_return_format("dataframe")
df = api.v2.get_molecules()
```

## Main objects

- `prisma_api.init()`
    Returns the main client object.
- `api`
    Legacy v1 wrappers plus configuration helpers.
- `api.v2`
    `PrismaAPIv2` instance with the v2 REST surface.

## v1 wrappers

The main client exposes these v1 methods:

- `get_mofs(payload={})`
- `get_carbon_isotherms(payload={})`
- `get_carbon_data_nested(payload={}, safe_names=False)`
- `get_materials_data(payload={}, separate_experimental=True)`
- `update_adsorption_singlepoint(df)`
- `update_heat_capacity_all_tidy(df)`
- `update_isotherm_h2(df)`
- `update_mofchecker(df)`
- `update_zeopp_metrics(df)`

Configuration helpers on the main client:

- `set_return_format(fmt)`
- `update_dev_mode(dev)`

Module-level helpers exported from the package:

- `prisma_api.init`
- `prisma_api.PrismaAPIv2`
- `prisma_api.update_dev_mode`
- `prisma_api.update_dev_host_port`
- `prisma_api.locate_config`

## v2 wrapper list

All methods below are available on `api.v2`.

### Health and flowsheets

- `health()`
- `get_flowsheet(name="dac_min")`

### Materials and bundles

- `list_materials(name=None, limit=10000)`
- `get_material(material_id)`
- `get_materials_psdi(name=None, limit=500, offset=0)`
- `get_material_psdi(material_id)`
- `get_material_property_bundle(mof, sim_or_exp=None, good_structure=None, limit=500, offset=0, query=None)`
- `preflight_material_check(name)`

### Case bundles and pack builders

- `get_cases_bundle(name=None, source=None, sink=None, region=None, limit_cases=100, limit_props=2000)`
- `build_case_spec(case_id)`
- `build_scenario_spec(scenario_id)`
- `build_case_pack(case_id, scenario_id=None)`
- `list_case_packs(source=None, sink=None, region=None, study=None, include_scenarios=False, limit=100, offset=0)`

### Catalog and reference data

- `get_molecules(name=None, limit=500, offset=0)`
- `get_molecule(molecule_id)`
- `get_elements(symbol=None, name=None, limit=500, offset=0)`
- `get_element(element_id)`
- `get_regions(code=None, name=None, limit=500, offset=0)`
- `get_region(region_id)`
- `get_sources(name=None, limit=500, offset=0)`
- `get_source(source_id)`
- `get_sinks(name=None, limit=500, offset=0)`
- `get_sink(sink_id)`
- `get_transport_scenarios(name=None, limit=500, offset=0)`
- `get_transport_scenario(ts_id)`
- `get_utilities(name=None, limit=500, offset=0)`
- `get_utility(utility_id)`
- `get_references(name=None, doi=None, limit=500, offset=0)`
- `get_reference(ref_id)`
- `get_transports(name=None, limit=500, offset=0)`
- `get_transport(transport_id)`
- `get_subsystems(name=None, type=None, limit=500, offset=0)`
- `get_subsystem(subsystem_id)`
- `get_properties(name=None, domain=None, category=None, object_id=None, limit=500, offset=0)`
- `get_property(property_id)`
- `get_equipment(name=None, group=None, limit=500, offset=0)`
- `get_equipment_item(equipment_id)`
- `get_equipment_costs(equipment_id=None, limit=500, offset=0)`
- `get_equipment_cost(cost_id)`
- `get_equipment_designs(equipment_id=None, key=None, limit=500, offset=0)`
- `get_equipment_design(design_id)`
- `get_process_conditions(name=None, type=None, limit=500, offset=0)`
- `get_process_condition(condition_id)`
- `get_process_configurations(name=None, type=None, limit=500, offset=0)`
- `get_process_configuration(config_id)`
- `get_contactor_configurations(name=None, type=None, limit=500, offset=0)`
- `get_contactor_configuration(config_id)`
- `get_cost_indices(year=None, limit=500, offset=0)`
- `get_cost_index(index_id)`
- `get_constants(param=None, limit=500, offset=0)`
- `get_constant(constant_id)`
- `get_mea_baselines(name=None, limit=500, offset=0)`
- `get_mea_baseline(mea_id)`
- `get_mea_kpis(name=None, category=None, limit=500, offset=0)`
- `get_mea_kpi(kpi_id)`

### Science data

- `get_isotherm(mof=None, molecule=None, temperature_min=None, temperature_max=None, sim_or_exp=None, good_structure=None, limit=500, offset=0)`
- `get_water_kpis(mof=None, molecule=None, source=None, sim_or_exp=None, good_structure=None, limit=500, offset=0)`
- `get_carbon_zeopp(mof=None, good_structure=None, limit=500, offset=0)`
- `get_carbon_zeopp_item(item_id)`
- `get_carbon_zeopp_experimental(mof=None, limit=500, offset=0)`
- `get_carbon_zeopp_experimental_item(item_id)`

### TEA, LCA, cases, and scenarios

- `get_output_kpis(scenario_id=None, mof=None, good_structure=None, limit=500, offset=0)`
- `get_output_kpi(kpi_id)`
- `upsert_output_kpis(df)`
- `get_region_costs(region=None, name=None, year=None, limit=500, offset=0)`
- `get_region_cost(rc_id)`
- `upsert_region_costs(df)`
- `get_ambient_parameters(name=None, limit=500, offset=0)`
- `get_ambient_parameter(ap_id)`
- `upsert_ambient_parameters(df)`
- `get_cases(source=None, sink=None, region=None, study=None, limit=500, offset=0)`
- `get_case(case_id)`
- `get_scenarios(case_id=None, name=None, type=None, limit=500, offset=0)`
- `get_scenario(scenario_id)`
- `get_screening_summaries(scenario_id=None, limit=500, offset=0)`
- `get_screening_summary(summary_id)`

## Examples

### Materials

```python
import prisma_api

api = prisma_api.init()

materials = api.v2.list_materials(name="ABEX")
first = materials[0]
detail = api.v2.get_material(first["id"])
```

### PSDI detail

```python
psdi = api.v2.get_materials_psdi(name="Lewatit")
first_psdi = psdi[0]
record = api.v2.get_material_psdi(first_psdi["id"])
```

### Flowsheet retrieval

```python
flowsheet = api.v2.get_flowsheet(name="dac_min")
print(flowsheet["template_id"])
```

### Advanced property-bundle query

`get_material_property_bundle` supports a generic query dictionary for more complex endpoint-specific filtering.

Supported keys are:

- `common`
- `materials`
- `isotherms`
- `zeopp_simulated`
- `zeopp_experimental`
- `water_kpis`

Merge precedence is:

- defaults
- `common`
- endpoint-specific filters

```python
bundle = api.v2.get_material_property_bundle(
        "HKUST",
        good_structure=True,
        query={
                "common": {"limit": 50},
                "materials": {"limit": 20},
                "isotherms": {
                        "molecule": "CO2",
                        "temperature_min": 273,
                        "temperature_max": 350,
                },
                "water_kpis": {"source": "DAC"},
        },
)

print(bundle.keys())
```

### Cases and scenarios

```python
cases = api.v2.get_cases(region="GB", limit=10)
case_id = cases[0]["id"]

case_detail = api.v2.get_case(case_id)
scenario_list = api.v2.get_scenarios(case_id=case_id)
case_pack = api.v2.build_case_pack(case_id)
```

## Testing

Run the test suite with:

```bash
pytest tests/ -v --cov=prisma_api --cov-report=term-missing
```

## Additional documentation

- [API_REFERENCE.md](API_REFERENCE.md)
- [DEVELOPMENT_SUMMARY.md](DEVELOPMENT_SUMMARY.md)
- [User Guide.md](User%20Guide.md)

## Notes

- Production v2 base URL: `https://prisma-platform.org/api/v2`
- Authentication header: `X-API-Key`
- Local development routing is controlled through config and `api.update_dev_mode(True)`
