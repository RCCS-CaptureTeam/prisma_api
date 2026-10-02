# # PrISMa API v2 Scopes + AutoPrism Demo
# 
# This script demonstrates:
# - `api.v2.get_autoprism_collection(...)`
# - AutoPrism upsert wrappers for batch writes
# 
# It uses the v2 wrappers on the initialized `api` client.
#
# TARGET: `prisma_api.init()` / `init(local_dev=False)` targets PRODUCTION
# (prisma-platform.org). This demo writes mock data, so it uses
# `init(local_dev=True)` (local dev server). Only switch to production for
# real uploads.

# %%
import prisma_api
import json

# API key: ~/.config/prisma_api/config.yaml, or PRISMA_API_* env vars if
# there is no config file. init() prints the base URL it connected to.
api = prisma_api.init(local_dev=True)

MOCK_DIR = "../reference_data/autoprism/01"



# ============================= DATA UPSERTS =============================
# %%
# #### adsorption_singlepoint (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_adsorption_singlepoint.json", "r") as f:
    sample_adsorption_singlepoint = json.load(f)

# Upsert examples for remaining tables
resp_adsorption = api.v2.upsert_adsorption_singlepoint(sample_adsorption_singlepoint)


# %%
# #### heat_capacity (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_heat_capacity.json", "r") as f:
    sample_heat_capacity = json.load(f)

resp_heat = api.v2.upsert_heat_capacity(sample_heat_capacity)


# %%
# ### isotherm_h2 (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_isotherm_h2.json", "r") as f:
    sample_isotherm_h2 = json.load(f)

resp_h2 = api.v2.upsert_isotherm_h2(sample_isotherm_h2)


# %%
# ### mofchecker (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_mofchecker.json", "r") as f:
    sample_mofchecker = json.load(f)

resp_mofchecker = api.v2.upsert_mofchecker(sample_mofchecker)


# %%
# ### zeopp_metrics (only)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_zeopp_metrics.json", "r") as f:
    sample_zeopp_metrics = json.load(f)

resp_zeopp = api.v2.upsert_zeopp_metrics(sample_zeopp_metrics)


# %%
# ### All AutoPrism (all tables)

# Load mock payload from json, assume the python session generates this data (and doesn't simply read it from a file)
with open(f"{MOCK_DIR}/mock_payload_all_autoprism.json", "r") as f:
    sample_all_autoprism = json.load(f)

# Upsert all autoprism data. Rows the server rejects (HTTP 207) mark the
# section "error"/"partial"; raise_on_error=True turns that into an exception.
result = api.v2.upsert_autoprism_collection(sample_all_autoprism)
print(result["overall_status"], json.dumps(result["totals"]))


# %%
# ============================= DATA GATHERING =============================
# AutoPrism collection wrapper: includes computation runs + 5 table pulls
autoprism = api.v2.get_autoprism_collection(
    mof='ASEJOZ',
    limit=20,
    offset=0,
)
