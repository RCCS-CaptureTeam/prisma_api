# %% [markdown]
# # PrISMa API — Full Demo
# 
# This notebook demonstrates every wrapper function in the `prisma_api` client package.
# 
# | Layer | Accessed via |
# |---|---|
# | **v1** | `api.*` |
# | **v2** | `api.v2.*` |
# 
# > **Requires:** a valid API key stored in `~/.config/prisma_api/config.yaml`  
# > Run `prisma_api.init()` — the config wizard runs automatically on first use.

# %% [markdown]
# ## 1 · Setup

# %%
import prisma_api
import pandas as pd

# Initialise — reads API key from config file (~/.config/prisma_api/config.yaml)
api = prisma_api.init()
api.update_dev_mode(True)
api = prisma_api.init()

# Use JSON (list[dict]) return format throughout this notebook
api.set_return_format('json')

print(f"prisma_api version : {prisma_api.__version__}")
print(f"API key loaded     : {'yes' if api.key else 'NO KEY FOUND'}")
print(f"Dev mode           : {api.dev}")
print(f"Return format      : json (list[dict])")

# %% [markdown]
# ## Latest additions

# %%
flowsheet = api.v2.get_flowsheet(name='dac_min')
flowsheet

# %% [markdown]
# ---
# ## 2 · v1 — `get_materials_data`
# 
# Returns all materials with nested fields unpacked, Zeo++ columns coalesced (simulated preferred over experimental), and a `sim_or_exp` flag as the first column.
# 
# `separate_experimental=True` (default) splits the result into two DataFrames.

# %%
result = api.get_materials_data()   # separate_experimental=True by default

sim = result['simulated']
exp = result['experimental']
meta   = result['meta']

print(f"Source host  : {meta['source']}")
print(f"Simulated    : {len(sim)} rows")
print(f"Experimental : {len(exp)} rows")
print(f"Columns      : {list(sim.columns)}")


# %%
sim.head()


# %%
exp

# %%
# Combined — separate_experimental=False
result_combined = api.get_materials_data(separate_experimental=False)
result_combined['data'].head()

# %% [markdown]
# ---
# ## 3 · v2 — Health

# %%
api.v2.health()

# %% [markdown]
# ---
# ## 4 · v2 — Catalog
# 
# ### 4.1 Materials

# %%
# List all materials
materials = api.v2.list_materials()


# %%
# Filter by name substring
api.v2.list_materials(name='AB')

# %%
# Detail for a single material
first_id = int(materials[0]['id'])
api.v2.get_material(first_id)

# %% [markdown]
# ### 4.1b Materials (PSDI — extended crystallographic fields)
# 
# `get_materials_psdi` / `get_material_psdi` return the full set of PSDI fields:
# chemical formulae, SMILES, space group, cell geometry, CIF URL, and (on detail) linker/node chemistry and element composition.

# %%
# List all PSDI materials — includes formula, SMILES, space group, cell geometry
psdi = api.v2.get_materials_psdi()
print(f"{len(psdi)} materials")
print(f"Fields: {list(psdi[0].keys()) if psdi else []}")
psdi[:5]


# %%
# Filter by name substring
api.v2.get_materials_psdi(name='Lewatit_1065_exp')

# %%
# Full detail record — includes linker/node SMILES, PubChem fields, element composition
first_psdi = psdi.iloc[0] if hasattr(psdi, 'iloc') else psdi[0]
psdi_id = int(first_psdi['id'])
api.v2.get_material_psdi(psdi_id)


# %% [markdown]
# ### 4.1c Preflight Check & Property Bundle
# 
# `preflight_material_check(name)` — returns `True` if any material matching the name exists.
# 
# `get_material_property_bundle(mof)` — single call that aggregates isotherms, simulated Zeo++, experimental Zeo++ and water KPIs for a given MOF.

# %%
# Check existence before doing further work
mof_name = materials[0]['name']
exists = api.v2.preflight_material_check(mof_name)
print(f"'{mof_name}' exists: {exists}")

# %% [markdown]
# Example null response

# %%
print(f"'DOESNOTEXIST123' exists: {api.v2.preflight_material_check('DOESNOTEXIST123')}")


# %%
# Fetch all science data for a MOF in one call
bundle = api.v2.get_material_property_bundle(mof_name)

# %%
bundle

# %% [markdown]
# ### 4.2 Molecules

# %%
molecules = api.v2.get_molecules()
molecules[:5]

# %%
mol_id = int(molecules[0]['id'])
api.v2.get_molecule(mol_id)


# %% [markdown]
# ### 4.3 Elements

# %%
elements = api.v2.get_elements()
print(f"{len(elements)} elements")
elements[:5]


# %%
# Filter by symbol
api.v2.get_elements(symbol='Zn')

# %%
# el_id = int(elements[0]['id'])
# api.v2.get_element(el_id)


# %% [markdown]
# ### 4.4 Regions

# %%
regions = api.v2.get_regions()
regions


# %%
api.v2.get_regions(code='US')

# %%
region_id = int(regions[0]['id'])
api.v2.get_region(region_id)


# %% [markdown]
# ### 4.5 Sources

# %%
sources = api.v2.get_sources()
sources

# %%
# source = api.v2.get_source(name='coal_source')

# %%
src_id = int(sources[0]['id'])
api.v2.get_source(src_id)

# %% [markdown]
# ### 4.6 Sinks

# %%
sinks = api.v2.get_sinks()
sinks


# %%
sink_id = int(sinks[0]['id'])
api.v2.get_sink(sink_id)


# %% [markdown]
# ### 4.7 Transport Scenarios

# %%
transport_scenarios = api.v2.get_transport_scenarios()
transport_scenarios


# %%
ts_id = int(transport_scenarios[0]['id'])
api.v2.get_transport_scenario(ts_id)


# %% [markdown]
# ### 4.7b Transport Modes

# %%
transports = api.v2.get_transports()
print(f"{len(transports)} transport modes")
transports


# %%
if transports:
    tr_id = int(transports[0]['id'])
    api.v2.get_transport(tr_id)


# %% [markdown]
# ### 4.8 Utilities

# %%
utilities = api.v2.get_utilities()
utilities


# %%
util_id = int(utilities[0]['id'])
api.v2.get_utility(util_id)


# %% [markdown]
# ### 4.9 References

# %%
refs = api.v2.get_references()
print(f"{len(refs)} references")
refs[:5]


# %%
ref_id = int(refs[0]['id'])
api.v2.get_reference(ref_id)


# %% [markdown]
# ### 4.10 Subsystems

# %%
subsystems = api.v2.get_subsystems()
print(f"{len(subsystems)} subsystems")
# Filter by type
api.v2.get_subsystems(type='dac')


# %%
if subsystems:
    sub_id = int(subsystems[0]['id'])
    api.v2.get_subsystem(sub_id)


# %% [markdown]
# ### 4.11 Equipment

# %%
try:
    equipment = api.v2.get_equipment()
    display(equipment)
except Exception as e:
    print(f"get_equipment unavailable: {e}")
    equipment = None


# %%
if equipment is not None:
    print(f"{len(equipment)} equipment items")
    # Filter by name substring
    try:
        display(api.v2.get_equipment(name='blower'))
    except Exception as e:
        print(f"Filter unavailable: {e}")

# %%
if equipment is not None:
    eq_id = int(equipment[0]['id'])
    try:
        api.v2.get_equipment_item(eq_id)

    except Exception as e:
        print(f"get_equipment_item unavailable: {e}")

# %%
equipment

# %% [markdown]
# ### 4.12 Properties

# %%
properties = api.v2.get_properties()
print(f"{len(properties)} properties")
# Filter by domain and category
api.v2.get_properties(domain='TEA', category='params_amb')


# %%
if properties:
    prop_id = int(properties[0]['id'])
    api.v2.get_property(prop_id)


# %% [markdown]
# ### 4.13 TEA Equipment

# %%
equipment = api.v2.get_equipment()
print(f"{len(equipment)} TEA equipment items")
# Filter by group
api.v2.get_equipment(group='Blower')


# %%
if equipment:
    eq_id = int(equipment[0]['id'])
    api.v2.get_equipment_item(eq_id)


# %%
api.v2.get_equipment(name="GenericHeatPump")

# %% [markdown]
# ### 4.14 TEA Equipment Costs

# %%
costs = api.v2.get_equipment_costs()
print(f"{len(costs)} TEA equipment cost records")
# Filter by equipment PK
if equipment:
    api.v2.get_equipment_costs(equipment_id=eq_id)


# %%
if costs:
    cost_id = int(costs[0]['id'])
    api.v2.get_equipment_cost(cost_id)


# %% [markdown]
# ### 4.15 TEA Equipment Design Parameters

# %%
designs = api.v2.get_equipment_designs()
print(f"{len(designs)} TEA equipment design parameters")
# Filter by key
api.v2.get_equipment_designs(key='D1')


# %%
if designs:
    design_id = int(designs[0]['id'])
    api.v2.get_equipment_design(design_id)


# %% [markdown]
# ### 4.16 Process Conditions

# %%
process_conditions = api.v2.get_process_conditions()
print(f"{len(process_conditions)} process conditions")
# Filter by type
api.v2.get_process_conditions(type='tvsa')


# %%
if process_conditions:
    pc_id = int(process_conditions[0]['id'])
    api.v2.get_process_condition(pc_id)


# %% [markdown]
# ### 4.17 Process Configurations

# %%
process_configs = api.v2.get_process_configurations()
print(f"{len(process_configs)} process configurations")
# Filter by type
api.v2.get_process_configurations(type='dac')


# %%
if process_configs:
    pconf_id = int(process_configs[0]['id'])
    api.v2.get_process_configuration(pconf_id)


# %% [markdown]
# ### 4.18 Contactor Configurations

# %%
contactor_configs = api.v2.get_contactor_configurations()
print(f"{len(contactor_configs)} contactor configurations")
# Filter by type
api.v2.get_contactor_configurations(type='kiln')


# %%
if contactor_configs:
    cconf_id = int(contactor_configs[0]['id'])
    api.v2.get_contactor_configuration(cconf_id)


# %% [markdown]
# ### 4.19 Cost Indices

# %%
cost_indices = api.v2.get_cost_indices()
print(f"{len(cost_indices)} cost index records")
# Filter by year
api.v2.get_cost_indices(year=2019)


# %%
if cost_indices:
    ci_id = int(cost_indices[0]['id'])
    api.v2.get_cost_index(ci_id)


# %% [markdown]
# ### 4.20 Physical Constants

# %%
constants = api.v2.get_constants()
print(f"{len(constants)} physical constants")
# Retrieve the ideal gas constant by symbol
api.v2.get_constants(param='R')


# %%
if constants:
    const_id = int(constants[0]['id'])
    api.v2.get_constant(const_id)


# %% [markdown]
# ### 4.21 MEA Baseline

# %%
mea = api.v2.get_mea_baselines()
print(f"{len(mea)} MEA baseline records")
# Filter by name
api.v2.get_mea_baselines(name='NGCC')


# %%
if mea:
    mea_id = int(mea[0]['id'])
    api.v2.get_mea_baseline(mea_id)


# %% [markdown]
# ### 4.22 MEA KPIs

# %%
mea_kpis = api.v2.get_mea_kpis()
print(f"{len(mea_kpis)} MEA KPI records")
# Filter by category
api.v2.get_mea_kpis(category='CAC')


# %%
if mea_kpis:
    mea_kpi_id = int(mea_kpis[0]['id'])
    api.v2.get_mea_kpi(mea_kpi_id)


# %% [markdown]
# ---
# ## 5 · v2 — Science Data
# 
# ### 5.1 Isotherms

# %%
# All isotherms
isotherms = api.v2.get_isotherm()
print(f"{len(isotherms)} isotherm records")
isotherms[:5]


# %%
# Filter: simulated CO2 isotherms, good structures only
api.v2.get_isotherm(molecule='CO2', sim_or_exp='sim', good_structure=True)

# %%
# Temperature range + specific MOF
api.v2.get_isotherm(mof='ABEXEM', molecule='CO2', temperature_min=273, temperature_max=350)

# %% [markdown]
# ### 5.2 Water KPIs

# %%
water_kpis = api.v2.get_water_kpis()
print(f"{len(water_kpis)} water KPI records")
water_kpis[:5]


# %%
# Filtered: simulated, good structures, specific source
api.v2.get_water_kpis(sim_or_exp='sim', good_structure=True)

# %% [markdown]
# ### 5.3 Carbon ZeoPP — Simulated

# %%
zeopp = api.v2.get_carbon_zeopp()
print(f"{len(zeopp)} simulated Zeo++ records")
# Filter: good structures for a specific MOF
api.v2.get_carbon_zeopp(mof='HKUST', good_structure=True)


# %% [markdown]
# ### 5.4 Carbon ZeoPP — Experimental

# %%
zeopp_exp = api.v2.get_carbon_zeopp_experimental()
print(f"{len(zeopp_exp)} experimental Zeo++ records")
# Filter by MOF name
api.v2.get_carbon_zeopp_experimental(mof='HKUST')


# %% [markdown]
# ---
# ## 6 · v2 — TEA / LCA Data
# 
# ### 6.1 Cases

# %%
cases = api.v2.get_cases()
print(f"{len(cases)} cases")
cases


# %%
case_id = int(cases[0]['id'])
api.v2.get_case(case_id)


# %% [markdown]
# ### 6.1b Case Pack Builders — `ImportedCasePack` spec
# 
# Four compound methods that fetch remote Django records and reshape them into the nested dict structure defined by the `ImportedCasePack` / `CaseSpec` / `ScenarioSpec` spec.
# 
# | Method | Remote calls | Returns |
# |---|---|---|
# | `build_case_spec(case_id)` | `GET /cases/{id}/` | `CaseSpec` dict |
# | `build_scenario_spec(scenario_id)` | `GET /scenarios/{id}/` | `ScenarioSpec` dict |
# | `build_case_pack(case_id, scenario_id=None)` | case + first scenario (1–2 GETs) | full `ImportedCasePack` dict |
# | `list_case_packs(…, include_scenarios=False)` | `GET /cases/` + optional scenario GETs | `list[ImportedCasePack dict]` |
# 
# > **Note:** Fields that live only in the originating YAML pack (`pack_root`, per-component `document` sub-trees, `available_documents`, `import_issues`) are returned as `None` / `[]`. Merge in locally scanned document data after retrieval if needed.

# %%
# build_case_spec — CaseSpec-shaped dict for a single case
case_spec = api.v2.build_case_spec(case_id)

print(f"case_name   : {case_spec['case_name']}")
print(f"source_name : {case_spec['source_name']}")
print(f"sink_name   : {case_spec['sink_name']}")
print(f"region      : {case_spec['region']}")
print(f"transport   : {case_spec['transport']}")
print(f"utilities   : {case_spec['utilities']}")
case_spec

# %%
# build_case_pack — full ImportedCasePack dict
# Omit scenario_id to auto-resolve the first scenario for the case.
# Pass scenario_id=-1 to skip scenario resolution entirely.
pack = api.v2.build_case_pack(case_id)

print("Top-level keys :", list(pack.keys()))
print("pack_root      :", pack['pack_root'])           # None — not stored remotely
print("scenario_spec  :", pack['scenario_spec'] is not None)

# Inspect the nested CaseSpec
cs = pack['case_spec']
print(f"\nCaseSpec:")
print(f"  case_name  : {cs['case_name']}")
print(f"  source     : {cs['source']['name'] if cs['source'] else None}")
print(f"  sink       : {cs['sink']['name'] if cs['sink'] else None}")
print(f"  transport  : {cs['transport']['name'] if cs['transport'] else None}")

# Inspect the nested ScenarioSpec (if resolved)
ss = pack['scenario_spec']
if ss:
    print(f"\nScenarioSpec:")
    print(f"  scenario_name : {ss['scenario_name']}")
    print(f"  process       : {ss['process']}")          # None — YAML-only

# %%
# build_case_pack with an explicit scenario_id
# Useful when you already know which scenario you want, avoids a list call.
if pack['scenario_spec']:
    explicit_sid = pack['scenario_spec']['scenario_name']   # for display only
    print(f"Re-fetching with explicit scenario — scenario_name: {explicit_sid}")

# Pass scenario_id=-1 to suppress scenario resolution
pack_no_scenario = api.v2.build_case_pack(case_id, scenario_id=-1)
print(f"\nWith scenario_id=-1 → scenario_spec: {pack_no_scenario['scenario_spec']}")

# %%
# list_case_packs — returns list[ImportedCasePack dict] for matching cases
# Default: scenario_spec=None per record (lightweight, no N+1 requests)
packs = api.v2.list_case_packs(limit=5)
print(f"{len(packs)} packs returned")
for p in packs:
    cs = p['case_spec']
    print(f"  {cs['case_name']:50s}  scenario_spec={'resolved' if p['scenario_spec'] else 'null'}")

print()
# include_scenarios=True — attaches ScenarioSpec for each case (one extra GET per case)
# Use with small result sets only
packs_with_scenarios = api.v2.list_case_packs(limit=2, include_scenarios=True)
for p in packs_with_scenarios:
    ss = p['scenario_spec']
    print(f"  {p['case_spec']['case_name']:50s}  → {ss['scenario_name'] if ss else 'no scenario'}")

# %% [markdown]
# ### 6.2 Scenarios

# %%
# All scenarios for this case
import copy

for case in cases:
    case_id = case['id']
    try:
        scenarios = api.v2.get_scenarios(case_id=case_id)
        if scenarios:
            print("-" * 40)
            print(f"Scenarios for case {case_id} ({case['name']}):")
            for scen in scenarios:
                print(f"  - {scen['name']} (type: {scen['type']})")
            scenarios_success = copy.deepcopy(scenarios)
            case_id_success = copy.deepcopy(case_id)
    except Exception as e:
        print(f"Error retrieving scenarios for case {case_id}: {e}")


# %%
# Identify first case with scenarios
if 'case_id_success' in locals():
    print(f"First case with scenarios: {case_id_success}")
    scenarios_success


# %%
# TEA scenarios only
scenarios = api.v2.get_scenarios(case_id=case_id_success, type='TEA')
scenarios


# %%
scenario_id = int(scenarios_success[0]['id'])
api.v2.get_scenario(scenario_id)


# %% [markdown]
# ### 6.2b Screening Summaries

# %%
summaries = api.v2.get_screening_summaries(scenario_id=scenario_id)
print(f"{len(summaries)} screening summary records for scenario {scenario_id}")
summaries[:5]


# %% [markdown]
# ### 6.3 Output KPIs

# %%
kpis = api.v2.get_output_kpis(scenario_id=scenario_id)
print(f"{len(kpis)} KPI records for scenario {scenario_id}")
kpis[:5]


# %%
# Good structures only
api.v2.get_output_kpis(scenario_id=scenario_id, good_structure=True)[:5]


# %%
# Detail for a single KPI record
if kpis:
    kpi_id = int(kpis[0]['id'])
    api.v2.get_output_kpi(kpi_id)


# %% [markdown]
# #### Upsert Output KPIs
# 
# `upsert_output_kpis(df)` bulk-creates or updates records. Lookup key: `(scenario, MOF)` integer PKs.
# 
# > ⚠️ **Caution:** the cell below is commented out by default to avoid accidental writes. Uncomment and adjust the DataFrame before running.

# %%
# upsert_df = pd.DataFrame([
#     {'scenario': scenario_id, 'MOF': <mof_pk>, 'purity': 0.96, 'recovery': 0.88},
# ])
# api.v2.upsert_output_kpis(upsert_df)
# => {'created': 1, 'updated': 0}
print("Upsert cell — uncomment and fill in values to run.")

# %% [markdown]
# ### 6.4 Region Costs

# %%
costs = api.v2.get_region_costs()
print(f"{len(costs)} region cost records")
costs[:5]


# %%
# Filter by region and year
api.v2.get_region_costs(region='GB', year=2030)

# %%
if costs:
    rc_id = int(costs[0]['id'])
    api.v2.get_region_cost(rc_id)


# %%
# Upsert region costs (commented out — fill in values before running)
# upsert_rc = pd.DataFrame([
#     {'Name': 'GB_electricity_2030', 'region': 'GB', 'Units': '£/kWh', 'Value': 0.20, 'Year': 2030},
# ])
# api.v2.upsert_region_costs(upsert_rc)
# => {'created': 0, 'updated': 1}
print("Upsert cell — uncomment and fill in values to run.")

# %% [markdown]
# ### 6.5 Ambient Parameters

# %%
ambient = api.v2.get_ambient_parameters()
ambient


# %%
if ambient:
    ap_id = int(ambient[0]['id'])
    api.v2.get_ambient_parameter(ap_id)


# %%
# Upsert ambient parameters (commented out — fill in values before running)
# upsert_ap = pd.DataFrame([
#     {'Name': 'ambient_T_K', 'Units': 'K', 'Value': 288.15},
# ])
# api.v2.upsert_ambient_parameters(upsert_ap)
# => {'created': 0, 'updated': 1}
print("Upsert cell — uncomment and fill in values to run.")

# %% [markdown]
# ---
# ## 7 · Pagination
# 
# All list endpoints accept `limit` and `offset` for pagination.

# %%
page1 = api.v2.get_output_kpis(scenario_id=scenario_id, limit=50, offset=0)
page2 = api.v2.get_output_kpis(scenario_id=scenario_id, limit=50, offset=50)

print(f"Page 1: {len(page1)} records")
print(f"Page 2: {len(page2)} records")

all_kpis = page1 + page2
print(f"Combined: {len(all_kpis)} records")


# %% [markdown]
# ---
# ## 8 · Dev Mode
# 
# Switch between production and a local development server.

# %%
# Enable dev mode — routes all requests to localhost
# api.update_dev_mode(True)

# Disable dev mode — routes to production
# api.update_dev_mode(False)

# Re-initialise after toggling
# api = prisma_api.init()
# print(f"Dev mode: {api.dev}")
print("Dev mode cells — uncomment to use.")

# %% [markdown]
# ---
# ## 9 · Return Format
# 
# All list endpoints support two output formats, switchable at any time:
# 
# | Format | Method call | Output type |
# |---|---|---|
# | `'json'` | `api.set_return_format('json')` | `list[dict]` *(default in this notebook)* |
# | `'dataframe'` | `api.set_return_format('dataframe')` | `pd.DataFrame` |
# 
# Detail endpoints (single-record lookups) always return a `dict` regardless of this setting.

# %%
# Switch to DataFrames
api.set_return_format('dataframe')

molecules_df = api.v2.get_molecules()
print(type(molecules_df))    # <class 'pandas.core.frame.DataFrame'>
molecules_df

# %%
# Switch back to JSON (list of dicts)
api.set_return_format('json')

molecules_json = api.v2.get_molecules()
print(type(molecules_json))   # <class 'list'>
print(molecules_json[:3])


