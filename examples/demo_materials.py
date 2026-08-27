# %%
import pandas
import prisma_api
api = prisma_api.init(local_dev=True)

# %%
mat = api.v2.get_material_property_bundle(name="CALF20")

# %%
cifs = api.v2.list_cifs(tag='MOFevaluator')

# %%
len(cifs)

# %%
paths = api.v2.get_cifs(["CALF20", "ABEXEM"], save_dir="downloads/cifs")

# %%
cifs


