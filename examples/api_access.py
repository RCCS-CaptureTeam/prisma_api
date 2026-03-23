# %%
# # PrISMa_API

# ### Load Library

import prisma_api

# %%
# ### Initialise API class

api = prisma_api.init()

# %%
from prisma_api.config import update_dev_mode
update_dev_mode(True)
api = prisma_api.init()

# %%
# vars(api)

# %%

data = api.get_materials_data()

import pandas as pd

df = pd.DataFrame(data['simulated']['data'])


# %%

data = api.get_carbon_data_nested(safe_names=True)

data['Simulated']['isotherm']


# %%
# ### Gather MOF data from API

api.get_mofs()

# %%
# ### Gather Carbon Isotherm data from API (using dynamic filtering)

api.get_carbon_isotherms({'molecule': 'CO2', 'good_structure': False})

# %%
# # TESTS
# 
# ### adsorption_singlepoint
# 
# Load sample data for upload

import pandas as pd

# %%
df = pd.read_csv('../../AutoPrism/results/adsorption_singlepoint.csv')
api.update_adsorption_singlepoint(df)

# %%
df = pd.read_csv('../../AutoPrism/results/heat_capacity_all_tidy.csv')
df

# %%
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



