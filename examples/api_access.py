# %% [markdown]
# Load Library

# %%
import prisma_api

# %% [markdown]
# Initialise API class

# %%
api = prisma_api.init()

# %% [markdown]
# Gather MOF data from API

# %%
api.get_mofs()

# %% [markdown]
# Gather Carbon Isotherm data from API

# %%
import importlib
importlib.reload(prisma_api)
api = prisma_api.init()

data = api.get_carbon_isotherms({'molecule': 'CO2', 'good_structure': True, 'simulated': True})
data


