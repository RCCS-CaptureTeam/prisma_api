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
api.update_dev_mode(False)
api = prisma_api.init()

print(f"prisma_api version : {prisma_api.__version__}")
print(f"API key loaded     : {'yes' if api.key else 'NO KEY FOUND'}")
print(f"Dev mode           : {api.dev}")

# %% [markdown]
# ---
# ## 2 · v1 — `get_materials_data`
# 
# Returns all materials with nested fields unpacked, Zeo++ columns coalesced (simulated preferred over experimental), and a `sim_or_exp` flag as the first column.
# 
# `separate_experimental=True` (default) splits the result into two DataFrames.

# %%
result = api.get_materials_data()   # separate_experimental=True by default

df_sim = result['simulated']
df_exp = result['experimental']
meta   = result['meta']

print(f"Source host  : {meta['source']}")
print(f"Simulated    : {len(df_sim)} rows")
print(f"Experimental : {len(df_exp)} rows")
print(f"Columns      : {list(df_sim.columns)}")

# %%
df_sim.head()

# %%
df_exp.head()

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
df_materials = api.v2.list_materials()
print(f"{len(df_materials)} materials")
df_materials.head()

# %%
# Filter by name substring
api.v2.list_materials(name='ABEX')

# %%
# Detail for a single material (replace 1 with a real PK from the list above)
first_id = int(df_materials.iloc[0]['id'])
api.v2.get_material(first_id)

# %% [markdown]
# ### 4.1b Materials (PSDI — extended crystallographic fields)
# 
# `get_materials_psdi` / `get_material_psdi` return the full set of PSDI fields:
# chemical formulae, SMILES, space group, cell geometry, CIF URL, and (on detail) linker/node chemistry and element composition.

# %%
# List all PSDI materials — includes formula, SMILES, space group, cell geometry
df_psdi = api.v2.get_materials_psdi()
print(f"{len(df_psdi)} materials")
print(f"Columns: {list(df_psdi.columns)}")
df_psdi.head()

# %%
# Filter by name substring
api.v2.get_materials_psdi(name='1810_dmp+N398+39_charge')

# %%
# Full detail record — includes linker/node SMILES, PubChem fields, element composition
psdi_id = int(df_psdi.iloc[0]['id'])
api.v2.get_material_psdi(psdi_id)

# %% [markdown]
# ### 4.2 Molecules

# %%
df_molecules = api.v2.get_molecules()
df_molecules

# %%
mol_id = int(df_molecules.iloc[0]['id'])
api.v2.get_molecule(mol_id)

# %% [markdown]
# ### 4.3 Elements

# %%
df_elements = api.v2.get_elements()
print(f"{len(df_elements)} elements")
df_elements.head()

# %%
# Filter by symbol
api.v2.get_elements(symbol='Zn')

# %%
# el_id = int(df_elements.iloc[0]['id'])
# api.v2.get_element(el_id)

# %% [markdown]
# ### 4.4 Regions

# %%
df_regions = api.v2.get_regions()
df_regions

# %%
api.v2.get_regions(code='UK')

# %%
region_id = int(df_regions.iloc[0]['id'])
api.v2.get_region(region_id)

# %% [markdown]
# ### 4.5 Sources

# %%
df_sources = api.v2.get_sources()
df_sources

# %%
src_id = int(df_sources.iloc[0]['id'])
api.v2.get_source(src_id)

# %% [markdown]
# ### 4.6 Sinks

# %%
df_sinks = api.v2.get_sinks()
df_sinks

# %%
sink_id = int(df_sinks.iloc[0]['id'])
api.v2.get_sink(sink_id)

# %% [markdown]
# ### 4.7 Transport Scenarios

# %%
df_transport = api.v2.get_transport_scenarios()
df_transport

# %%
ts_id = int(df_transport.iloc[0]['id'])
api.v2.get_transport_scenario(ts_id)

# %% [markdown]
# ### 4.7b Transport Modes

# %%
df_transports = api.v2.get_transports()
print(f"{len(df_transports)} transport modes")
df_transports

# %%
if not df_transports.empty:
    tr_id = int(df_transports.iloc[0]['id'])
    api.v2.get_transport(tr_id)

# %% [markdown]
# ### 4.8 Utilities

# %%
df_utilities = api.v2.get_utilities()
df_utilities

# %%
util_id = int(df_utilities.iloc[0]['id'])
api.v2.get_utility(util_id)

# %% [markdown]
# ### 4.9 References

# %%
df_refs = api.v2.get_references()
print(f"{len(df_refs)} references")
df_refs.head()

# %%
ref_id = int(df_refs.iloc[0]['id'])
api.v2.get_reference(ref_id)

# %% [markdown]
# ### 4.10 Subsystems

# %%
df_subsystems = api.v2.get_subsystems()
print(f"{len(df_subsystems)} subsystems")
# Filter by type
api.v2.get_subsystems(type='dac')

# %%
if not df_subsystems.empty:
    sub_id = int(df_subsystems.iloc[0]['id'])
    api.v2.get_subsystem(sub_id)

# %% [markdown]
# ### 4.11 Equipment

# %%
df_equipment = api.v2.get_equipment()
print(f"{len(df_equipment)} equipment items")
# Filter by name
api.v2.get_equipment(name='blower')

# %%
if not df_equipment.empty:
    eq_id = int(df_equipment.iloc[0]['id'])
    api.v2.get_equipment_item(eq_id)

# %% [markdown]
# ### 4.12 Properties

# %%
df_properties = api.v2.get_properties()
print(f"{len(df_properties)} properties")
# Filter by domain and category
api.v2.get_properties(domain='TEA', category='params_amb')

# %%
if not df_properties.empty:
    prop_id = int(df_properties.iloc[0]['id'])
    api.v2.get_property(prop_id)

# %% [markdown]
# ### 4.13 TEA Equipment

# %%
df_tea_equipment = api.v2.get_tea_equipment()
print(f"{len(df_tea_equipment)} TEA equipment items")
# Filter by group
api.v2.get_tea_equipment(group='Blower')

# %%
if not df_tea_equipment.empty:
    tea_eq_id = int(df_tea_equipment.iloc[0]['id'])
    api.v2.get_tea_equipment_item(tea_eq_id)

# %% [markdown]
# ### 4.14 TEA Equipment Costs

# %%
df_tea_costs = api.v2.get_tea_equipment_costs()
print(f"{len(df_tea_costs)} TEA equipment cost records")
# Filter by equipment PK
if not df_tea_equipment.empty:
    api.v2.get_tea_equipment_costs(equipment_id=tea_eq_id)

# %%
if not df_tea_costs.empty:
    tea_cost_id = int(df_tea_costs.iloc[0]['id'])
    api.v2.get_tea_equipment_cost(tea_cost_id)

# %% [markdown]
# ### 4.15 TEA Equipment Design Parameters

# %%
df_tea_designs = api.v2.get_tea_equipment_designs()
print(f"{len(df_tea_designs)} TEA equipment design parameters")
# Filter by key
api.v2.get_tea_equipment_designs(key='D1')

# %%
if not df_tea_designs.empty:
    tea_design_id = int(df_tea_designs.iloc[0]['id'])
    api.v2.get_tea_equipment_design(tea_design_id)

# %% [markdown]
# ### 4.16 Process Conditions

# %%
df_process_conditions = api.v2.get_process_conditions()
print(f"{len(df_process_conditions)} process conditions")
# Filter by type
api.v2.get_process_conditions(type='tvsa')

# %%
if not df_process_conditions.empty:
    pc_id = int(df_process_conditions.iloc[0]['id'])
    api.v2.get_process_condition(pc_id)

# %% [markdown]
# ### 4.17 Process Configurations

# %%
df_process_configs = api.v2.get_process_configurations()
print(f"{len(df_process_configs)} process configurations")
# Filter by type
api.v2.get_process_configurations(type='dac')

# %%
if not df_process_configs.empty:
    pconf_id = int(df_process_configs.iloc[0]['id'])
    api.v2.get_process_configuration(pconf_id)

# %% [markdown]
# ### 4.18 Contactor Configurations

# %%
df_contactor_configs = api.v2.get_contactor_configurations()
print(f"{len(df_contactor_configs)} contactor configurations")
# Filter by type
api.v2.get_contactor_configurations(type='kiln')

# %%
if not df_contactor_configs.empty:
    cconf_id = int(df_contactor_configs.iloc[0]['id'])
    api.v2.get_contactor_configuration(cconf_id)

# %% [markdown]
# ### 4.19 Cost Indices

# %%
df_cost_indices = api.v2.get_cost_indices()
print(f"{len(df_cost_indices)} cost index records")
# Filter by year
api.v2.get_cost_indices(year=2019)

# %%
if not df_cost_indices.empty:
    ci_id = int(df_cost_indices.iloc[0]['id'])
    api.v2.get_cost_index(ci_id)

# %% [markdown]
# ### 4.20 Physical Constants

# %%
df_constants = api.v2.get_constants()
print(f"{len(df_constants)} physical constants")
# Retrieve the ideal gas constant by symbol
api.v2.get_constants(param='R')

# %%
if not df_constants.empty:
    const_id = int(df_constants.iloc[0]['id'])
    api.v2.get_constant(const_id)

# %% [markdown]
# ### 4.21 MEA Baseline

# %%
df_mea = api.v2.get_mea_baselines()
print(f"{len(df_mea)} MEA baseline records")
# Filter by name
api.v2.get_mea_baselines(name='NGCC')

# %%
if not df_mea.empty:
    mea_id = int(df_mea.iloc[0]['id'])
    api.v2.get_mea_baseline(mea_id)

# %% [markdown]
# ### 4.22 MEA KPIs

# %%
df_mea_kpis = api.v2.get_mea_kpis()
print(f"{len(df_mea_kpis)} MEA KPI records")
# Filter by category
api.v2.get_mea_kpis(category='CAC')

# %%
if not df_mea_kpis.empty:
    mea_kpi_id = int(df_mea_kpis.iloc[0]['id'])
    api.v2.get_mea_kpi(mea_kpi_id)

# %% [markdown]
# ---
# ## 5 · v2 — Science Data
# 
# ### 5.1 Isotherms

# %%
# All isotherms
df_isotherms = api.v2.get_isotherm()
print(f"{len(df_isotherms)} isotherm records")
df_isotherms.head()

# %%
# Filter: simulated CO2 isotherms, good structures only
api.v2.get_isotherm(molecule='CO2', sim_or_exp='sim', good_structure=True)

# %%
# Temperature range + specific MOF
api.v2.get_isotherm(mof='ABEXEM', molecule='CO2', temperature_min=273, temperature_max=350)

# %% [markdown]
# ### 5.2 Water KPIs

# %%
df_water = api.v2.get_water_kpis()
print(f"{len(df_water)} water KPI records")
df_water.head()

# %%
# Filtered: simulated, good structures, specific source
api.v2.get_water_kpis(sim_or_exp='sim', good_structure=True)

# %% [markdown]
# ### 5.3 Carbon ZeoPP — Simulated

# %%
df_zeopp = api.v2.get_carbon_zeopp()
print(f"{len(df_zeopp)} simulated Zeo++ records")
# Filter: good structures for a specific MOF
api.v2.get_carbon_zeopp(mof='HKUST', good_structure=True)

# %% [markdown]
# ### 5.4 Carbon ZeoPP — Experimental

# %%
df_zeopp_exp = api.v2.get_carbon_zeopp_experimental()
print(f"{len(df_zeopp_exp)} experimental Zeo++ records")
# Filter by MOF name
api.v2.get_carbon_zeopp_experimental(mof='HKUST')

# %% [markdown]
# ---
# ## 6 · v2 — TEA / LCA Data
# 
# ### 6.1 Cases

# %%
df_cases = api.v2.get_cases()
print(f"{len(df_cases)} cases")
df_cases

# %%
case_id = int(df_cases.iloc[0]['id'])
api.v2.get_case(case_id)

# %% [markdown]
# ### 6.2 Scenarios

# %%
# All scenarios for this case
import copy


for case in df_cases.itertuples():
    case_id = case.id
    try:
        df_scenarios = api.v2.get_scenarios(case_id=case_id)
        if not df_scenarios.empty:
            # print nice tree
            print("-" * 40)
            print(f"Scenarios for case {case_id} ({case.name}):")
            for scen in df_scenarios.itertuples():
                print(f"  - {scen.name} (type: {scen.type})")
            df_scenarios_success = copy.deepcopy(df_scenarios)
            case_id_success = copy.deepcopy(case_id)
    except Exception as e:
        print(f"Error retrieving scenarios for case {case_id}: {e}")

# %%
# Identify first case with scenarios
if 'case_id_success' in locals():
    print(f"First case with scenarios: {case_id_success}")
    df_scenarios_success

# %%
# TEA scenarios only
df_tea = api.v2.get_scenarios(case_id=case_id_success, type='TEA')
df_tea

# %%
scenario_id = int(df_scenarios_success.iloc[0]['id'])
api.v2.get_scenario(scenario_id)

# %% [markdown]
# ### 6.2b Screening Summaries

# %%
df_summaries = api.v2.get_screening_summaries(scenario_id=scenario_id)
print(f"{len(df_summaries)} screening summary records for scenario {scenario_id}")
df_summaries.head()

# %% [markdown]
# ### 6.3 Output KPIs

# %%
df_kpis = api.v2.get_output_kpis(scenario_id=scenario_id)
print(f"{len(df_kpis)} KPI records for scenario {scenario_id}")
df_kpis.head()

# %%
# Good structures only
api.v2.get_output_kpis(scenario_id=scenario_id, good_structure=True).head()

# %%
# Detail for a single KPI record
if not df_kpis.empty:
    kpi_id = int(df_kpis.iloc[0]['id'])
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
df_costs = api.v2.get_region_costs()
print(f"{len(df_costs)} region cost records")
df_costs.head()

# %%
# Filter by region and year
api.v2.get_region_costs(region='GB', year=2030)

# %%
if not df_costs.empty:
    rc_id = int(df_costs.iloc[0]['id'])
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
df_ambient = api.v2.get_ambient_parameters()
df_ambient

# %%
if not df_ambient.empty:
    ap_id = int(df_ambient.iloc[0]['id'])
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

print(f"Page 1: {len(page1)} rows")
print(f"Page 2: {len(page2)} rows")

all_kpis = pd.concat([page1, page2], ignore_index=True)
print(f"Combined: {len(all_kpis)} rows")

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
# | `'json'` | `api.set_return_format('json')` | `list[dict]` (default) |
# | `'dataframe'` | `api.set_return_format('dataframe')` | `pd.DataFrame` |
# 
# Detail endpoints (single-record lookups) always return a `dict` regardless of this setting.

# %%
# Switch to raw JSON (list of dicts)
api.set_return_format('json')

molecules_json = api.v2.get_molecules()
print(type(molecules_json))   # <class 'list'>
print(molecules_json[:2])

# %%
# Switch back to DataFrames (default)
api.set_return_format('dataframe')

molecules_df = api.v2.get_molecules()
print(type(molecules_df))    # <class 'pandas.core.frame.DataFrame'>
molecules_df


