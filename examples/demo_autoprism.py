# %% [markdown]
# # PrISMa API v2 Scopes + AutoPrism Demo
# 
# This notebook demonstrates:
# - `api.v2.get_autoprism_collection(...)`
# - AutoPrism upsert wrappers for batch writes
# 
# It uses the v2 wrappers on the initialized `api` client.

# %%
import prisma_api
import json

# Reads API key from ~/.config/prisma_api/config.yaml unless env vars are set
api = prisma_api.init(local_dev=True)

# %% [markdown]
# ## Mock payloads + direct upsert workflow for all six AutoPrism tables

# %% [markdown]
# #### adsorption_singlepoint (only)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_adsorption_singlepoint.json", "r") as f:
    sample_adsorption_singlepoint = json.load(f)

# %%
# Upsert examples for remaining tables
resp_adsorption = api.v2.upsert_adsorption_singlepoint(sample_adsorption_singlepoint)

# %% [markdown]
# #### heat_capacity (only)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_heat_capacity.json", "r") as f:
    sample_heat_capacity = json.load(f)

# %%
resp_heat = api.v2.upsert_heat_capacity(sample_heat_capacity)

# %% [markdown]
# ### isotherm_h2 (only)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_isotherm_h2.json", "r") as f:
    sample_isotherm_h2 = json.load(f)

# %%
resp_h2 = api.v2.upsert_isotherm_h2(sample_isotherm_h2)

# %% [markdown]
# ### mofchecker (only)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_mofchecker.json", "r") as f:
    sample_mofchecker = json.load(f)

# %%
resp_mofchecker = api.v2.upsert_mofchecker(sample_mofchecker)


# %% [markdown]
# ### zeopp_metrics (only)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_zeopp_metrics.json", "r") as f:
    sample_zeopp_metrics = json.load(f)

# %%
resp_zeopp = api.v2.upsert_zeopp_metrics(sample_zeopp_metrics)

# %% [markdown]
# ### All AutoPrism (all tables)

# %%
# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_all_autoprism.json", "r") as f:
    sample_all_autoprism = json.load(f)

# %%
# Upsert all autoprism data
result = api.v2.upsert_autoprism_collection(sample_all_autoprism)
result

# %% [markdown]
# ## Validate

# %%
# AutoPrism collection wrapper: includes computation runs + 5 table pulls
autoprism = api.v2.get_autoprism_collection(
    workflow_id='wf-demo',
    step='adsorption',
    status='done',
    mof='ABEXEM',
    component='H2',
    limit=20,
    offset=0,
 )

row_keys = [
    'computation_runs',
    'adsorption_singlepoints',
    'heat_capacities',
    'isotherm_H2s',
    'mofchecker',
    'zeopp_metrics',
]

{name: len(autoprism.get(name, [])) for name in row_keys}


