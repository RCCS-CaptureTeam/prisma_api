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
df_materials = api.v2.get_materials()
print(f"{len(df_materials)} materials")
df_materials.head()

# %%
# Filter by name substring
api.v2.get_materials(name='ABEX')

# %%
# Detail for a single material (replace 1 with a real PK from the list above)
first_id = int(df_materials.iloc[0]['id'])
api.v2.get_material(first_id)

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
el_id = int(df_elements.iloc[0]['id'])
api.v2.get_element(el_id)

# %% [markdown]
# ### 4.4 Regions

# %%
df_regions = api.v2.get_regions()
df_regions

# %%
api.v2.get_regions(code='GB')

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
# ---
# ## 5 · v2 — Science Data
# 
# ### 5.1 Isotherms

# %%
# All isotherms
df_isotherms = api.v2.get_isotherms()
print(f"{len(df_isotherms)} isotherm records")
df_isotherms.head()

# %%
# Filter: simulated CO2 isotherms, good structures only
api.v2.get_isotherms(molecule='CO2', sim_or_exp='sim', good_structure=True)

# %%
# Temperature range + specific MOF
api.v2.get_isotherms(mof='ABEXEM', molecule='CO2', temperature_min=273, temperature_max=350)

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
# ---
# ## 6 · v2 — TEA / LCA Data
# 
# ### 6.1 Cases

# %%
df_cases = api.v2.get_cases()
print(f"{len(df_cases)} cases")
df_cases.head()

# %%
case_id = int(df_cases.iloc[0]['id'])
api.v2.get_case(case_id)

# %% [markdown]
# ### 6.2 Scenarios

# %%
# All scenarios for this case
df_scenarios = api.v2.get_scenarios(case_id=case_id)
df_scenarios

# %%
# TEA scenarios only
df_tea = api.v2.get_scenarios(case_id=case_id, type='TEA')
df_tea

# %%
scenario_id = int(df_scenarios.iloc[0]['id'])
api.v2.get_scenario(scenario_id)

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


