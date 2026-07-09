# %%
import json
from pathlib import Path
import prisma_api

# %% [markdown]
# ### Initialise using config file API key

# %%
# api = prisma_api.init()
api = prisma_api.init(local_dev=True)

# %% [markdown]
# ### Load mock payload from workspace file

# %%
payload_path = Path("reference_data/prisma_v2/dac_min_2026_07_08.json")
with payload_path.open("r", encoding="utf-8") as f:
    flowsheet_payload = json.load(f)

# %%
flowsheet_payload

# %% [markdown]
# Wrapper expects a list of flowsheet objects

# %%
result = api.v2.upsert_flowsheets(
    [flowsheet_payload],
    screening_analysis_name='dac_min_with_contract',
    appendix="_v2026-07-08_test",
)

# %% [markdown]
# # Get flowsheet from server

# %% [markdown]
# flowsheet = api.v2.get_flowsheet_bundle(name='dac_min')

