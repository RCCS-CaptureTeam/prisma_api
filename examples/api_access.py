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
from prisma_api.config import update_dev_mode
update_dev_mode(False)
api = prisma_api.init()

# %% [markdown]
# ### Gather MOF data from API

# %%
api.get_mofs()

# %% [markdown]
# ### Gather Carbon Isotherm data from API (using dynamic filtering)

# %%
api.get_carbon_isotherms({'molecule': 'CO2', 'good_structure': False})

# %% [markdown]
# # TESTS
# 
# ### adsorption_singlepoint
# 
# Load sample data for upload

# %%
import pandas as pd

# %%
df = pd.read_csv('../../AutoPrism/results/adsorption_singlepoint.csv')
api.update_adsorption_singlepoint(df)

# %%
df = pd.read_csv('../../AutoPrism/results/heat_capacity_all_tidy.csv')
api.update_heat_capacity_all_tidy(df)

# %%
df = pd.read_csv('../../AutoPrism/results/isotherm_H2.csv')
api.update_isotherm_h2(df)

# %%
df = pd.read_csv('../../AutoPrism/results/mofchecker.csv')
api.update_mofchecker(df)

# %%
df = pd.read_csv('../../AutoPrism/results/zeopp_metrics.csv')
api.update_zeopp_metrics(df)

# %%



