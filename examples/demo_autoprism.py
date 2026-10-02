# # PrISMa API v2 Scopes + AutoPrism Demo
# 
# This script demonstrates:
# - `api.v2.get_autoprism_collection(...)`
# - AutoPrism upsert wrappers for batch writes
# 
# It uses the v2 wrappers on the initialized `api` client.

# %%
import prisma_api
import json

# Reads API key from ~/.config/prisma_api/config.yaml unless env vars are set
api = prisma_api.init()



# ============================= DATA UPSERTS =============================
# %%
# #### adsorption_singlepoint (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_adsorption_singlepoint.json", "r") as f:
    sample_adsorption_singlepoint = json.load(f)

# Upsert examples for remaining tables
resp_adsorption = api.v2.upsert_adsorption_singlepoint(sample_adsorption_singlepoint)


# %%
# #### heat_capacity (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_heat_capacity.json", "r") as f:
    sample_heat_capacity = json.load(f)

resp_heat = api.v2.upsert_heat_capacity(sample_heat_capacity)


# %%
# ### isotherm_h2 (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_isotherm_h2.json", "r") as f:
    sample_isotherm_h2 = json.load(f)

resp_h2 = api.v2.upsert_isotherm_h2(sample_isotherm_h2)


# %%
# ### mofchecker (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_mofchecker.json", "r") as f:
    sample_mofchecker = json.load(f)

resp_mofchecker = api.v2.upsert_mofchecker(sample_mofchecker)


# %%
# ### zeopp_metrics (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_zeopp_metrics.json", "r") as f:
    sample_zeopp_metrics = json.load(f)

resp_zeopp = api.v2.upsert_zeopp_metrics(sample_zeopp_metrics)


# %%
# ### All AutoPrism (all tables)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open("../reference_data/autoprism/mock_payload_all_autoprism.json", "r") as f:
    sample_all_autoprism = json.load(f)

# Upsert all autoprism data
result = api.v2.upsert_autoprism_collection(sample_all_autoprism)
result


# %%
# ============================= DATA GATHERING =============================
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
