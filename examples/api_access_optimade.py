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

# %%
# from prisma_api.config import update_api_key
# update_api_key('your-api-key-here')

# api.update_dev_mode(False)  # Set to True to use local development server, False to use production server
# api = prisma_api.init()
# vars(api)

# %%
data = api.get_materials_data(separate_experimental=True)

# %%
data['meta']['source']

# %%
data['simulated'].sim_or_exp.value_counts()

# %%
data['experimental'].sim_or_exp.value_counts()

# %%
data['simulated']

# %%
data['simulated'][data['simulated']['cif_file'].isna()]

# %%
data['simulated'][data['simulated']['cif_file'].notna()]


# %%



