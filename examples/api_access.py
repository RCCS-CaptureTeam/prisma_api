# %% [markdown]
# # PrISMa_API

# %% [markdown]
# ### Load Library

# %%
import prisma_api

# %% [markdown]
# ### Initialise API class

# %%
api = prisma_api.init()

# %% [markdown]
# ### Gather MOF data from API

# %%
api.get_mofs()

# %% [markdown]
# ### Gather Carbon Isotherm data from API (using dynamic filtering)

# %%
api.get_carbon_isotherms({'molecule': 'CO2', 'good_structure': False, 'simulated': True})

# %% [markdown]
# ### Load sample data for upload

# %%
import pandas as pd
df = pd.read_csv('../../AutoPrism/results/adsorption_singlepoint.csv')

# %% [markdown]
# ### Upload to DB via API

# %%
api.update_adsorption_singlepoint(df)


