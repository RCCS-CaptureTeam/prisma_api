# PrISMa API — User Guide

A quick-start guide for installing the `prisma_api` package and accessing
material data through the **PSDI endpoint**.

---

## 1. Installation

### From PyPI

```bash
pip install prisma_api
```

### From source (this repository)

```bash
git clone https://github.com/RCCS-CaptureTeam/prisma_api.git
cd prisma_api
pip install .
```

**Requirements:** Python ≥ 3.10, plus `numpy`, `pandas`, `pyyaml`,
`platformdirs`, and `requests` (installed automatically).

---

## 2. Configuration

The package authenticates using an API key stored in a local config file.
On first use, run the one-time setup:

```python
import prisma_api

# Interactive prompt — enter your PrISMa API key when asked
api = prisma_api.prisma_api()
```

The key is saved to a platform-specific config file and reused automatically
on every subsequent import:

| Platform | Config file location |
|----------|----------------------|
| macOS / Linux | `~/.config/prisma_api/config.yaml` |
| Windows | `%APPDATA%\prisma-api\prisma_api\config.yaml` |

To find the exact path on your system:

```python
from prisma_api.config import locate_config
print(locate_config())
```

To set or update the key programmatically (skips the interactive prompt):

```python
from prisma_api.config import create_config_file
create_config_file(api_key="YOUR_API_KEY_HERE")
```

---

## 3. Initialisation

```python
import prisma_api

api = prisma_api.prisma_api()   # reads key from config.yaml automatically
```

All PSDI (and other v2) endpoints are accessed via the `api.v2` sub-object.

---

## 4. PSDI Endpoint

The **PSDI** (Physical Sciences Data Infrastructure) endpoint exposes
extended crystallographic and chemical metadata for every material in the
PrISMa database.

### 4.1 List materials — `get_materials_psdi`

Returns a `pandas.DataFrame` with one row per material.

```python
# All materials (up to default limit of 500)
df = api.v2.get_materials_psdi()

# Filter by name substring (case-insensitive)
df = api.v2.get_materials_psdi(name="ABEX")

# Pagination
df = api.v2.get_materials_psdi(limit=100, offset=200)
```

**Columns returned:**

| Column | Description |
|--------|-------------|
| `id` | Integer primary key |
| `name` | Material name (slug identifier) |
| `cif_url` | URL to the CIF structure file |
| `cif_filename` | CIF filename |
| `formula_descriptive` | Human-readable chemical formula |
| `formula_hill` | Hill-notation formula |
| `formula_reduced` | Reduced formula |
| `formula_anonymous` | Anonymous formula |
| `formula` | Primary formula field |
| `formula_calculated` | Calculated formula |
| `chemical_name` | IUPAC / common chemical name |
| `periodic_dimensions` | Number of periodic dimensions |
| `smiles` | SMILES string |
| `spacegroup_hm` | Space group (Hermann–Mauguin) |
| `spacegroup_hall` | Space group (Hall notation) |
| `spacegroup_number` | Space group number |
| `cell_volume` | Unit cell volume (Å³) |
| `cell_lengths` | Unit cell lengths a, b, c (Å) |
| `cell_angles` | Unit cell angles α, β, γ (°) |
| `cell_ratios` | Cell length ratios |
| `unit_cell` | Full unit cell parameter dict |

**Example — inspect the first few results:**

```python
df = api.v2.get_materials_psdi(name="ABEX")
print(df[["name", "formula_hill", "spacegroup_hm", "cell_volume"]].head())
```

```
     name     formula_hill spacegroup_hm  cell_volume
0  ABEXEM   C48 H24 N6 O9 Zn3        P-1       2134.5
1  ABEXIQ  C48 H24 N6 O9 Co3        P-1       2109.3
```

---

### 4.2 Single material detail — `get_material_psdi`

Returns a `dict` with the full extended record for one material, including
all list-endpoint fields **plus** linker/node chemistry and elemental
composition.

```python
# Look up by integer PK (obtain the id from get_materials_psdi)
record = api.v2.get_material_psdi(1)
```

**Additional fields over the list endpoint:**

| Field | Description |
|-------|-------------|
| `smiles_linker` | SMILES of organic linker |
| `formula_linker` | Formula of organic linker |
| `smiles_linker_PubChem` | Canonical SMILES (PubChem pipeline) |
| `formula_linker_PubChem` | Formula from PubChem pipeline |
| `count_dict_PubChem` | Atom-count dict from PubChem |
| `smiles_node` | SMILES of inorganic node |
| `formula_node` | Formula of inorganic node |
| `elements` | List of `{symbol, atomic_number, mass_fraction}` dicts |

**Example:**

```python
record = api.v2.get_material_psdi(1)

print(record["name"])            # 'ABEXEM'
print(record["formula_hill"])    # 'C48 H24 N6 O9 Zn3'
print(record["smiles_linker"])   # 'OC(=O)c1cncc(C(=O)O)c1'

for el in record["elements"]:
    print(el["symbol"], el["mass_fraction"])
# Zn  0.2451
# C   0.3601
# ...
```

---

### 4.3 Retrieve all materials (pagination helper)

The default `limit` is 500. To retrieve the full catalogue, increment
`offset` until fewer records than `limit` are returned:

```python
import pandas as pd

all_rows = []
limit, offset = 500, 0

while True:
    batch = api.v2.get_materials_psdi(limit=limit, offset=offset)
    all_rows.append(batch)
    if len(batch) < limit:
        break
    offset += limit

df_all = pd.concat(all_rows, ignore_index=True)
print(f"{len(df_all)} materials retrieved")
```

---

### 4.4 Return format

By default all list endpoints return a `pandas.DataFrame`. To get plain
Python `list[dict]` instead:

```python
api.set_return_format("json")
records = api.v2.get_materials_psdi(name="ABEX")   # list[dict]

api.set_return_format("dataframe")                  # revert to default
```

---

## 5. Further reading

- Full v2 API reference: [`API_REFERENCE.md`](API_REFERENCE.md)
- All available endpoints: `dir(api.v2)`
- PrISMa platform: <https://prisma-platform.org>
