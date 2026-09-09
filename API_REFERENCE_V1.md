# PrISMa API — Python Client Reference (v1)

> **Package:** `prisma_api` v0.3.9  
> **Base URL (production):** `https://prisma-platform.org/api/`  
> **Authentication:** `X-API-Key` header (set via config file or `PRISMA_API_KEY` env var)

See [API_REFERENCE_V2.md](API_REFERENCE_V2.md) for the `api.v2` method reference.

---

## Initialisation

```python
import prisma_api

api = prisma_api.init()          # reads key from ~/.config/prisma_api/config.yaml
api_dev = prisma_api.init(local_dev=True)   # target local/dev backend at init time
api.v2                           # PrismaAPIv2 instance, attached automatically
```

`update_dev_mode()` still exists but is deprecated; prefer selecting dev/prod
target with `init(local_dev=True|False)`.

---

## v1 Methods

### `api.get_materials_data(payload={}, separate_experimental=True)`

Returns processed materials data with nested fields unpacked, zeopp columns
coalesced (simulated preferred over experimental), and a top-level `sim_or_exp`
flag inserted as the first column.

In production mode, the client attempts multiple hosts and uses the first one
that returns non-empty data.

| Argument | Type | Default | Description |
|---|---|---|---|
| `payload` | `dict` | `{}` | Query-parameter payload forwarded to the API. |
| `separate_experimental` | `bool` | `True` | If `True` the return dict contains `simulated` and `experimental` DataFrames split by `sim_or_exp`. If `False` a single `data` DataFrame is returned. |

**Returns:** `dict`

```python
# separate_experimental=True  (default)
result = api.get_materials_data()

result['simulated']      # pd.DataFrame — rows where sim_or_exp == 'sim'
result['experimental']   # pd.DataFrame — rows where sim_or_exp == 'exp'
result['meta']           # {'source': 'prisma-platform.org'}
```

```
# result['simulated'] — example (3 of ~20 columns shown)
   sim_or_exp    name  cif_file                                     Molecule  CO2 Uptake (mol/kg)
0         sim  ABEXEM  https://prisma-platform.org/media/...ABEXEM.cif  CO2              2.45
1         sim  FOOFOO  https://prisma-platform.org/media/...FOOFOO.cif  CO2              1.87
```

```python
# separate_experimental=False  — single combined DataFrame
result = api.get_materials_data(separate_experimental=False)

result['data']   # pd.DataFrame — all rows
result['meta']   # {'source': 'prisma-platform.org'}
```

**Key output columns** (after unpacking and renaming):

| Column | Source |
|---|---|
| `sim_or_exp` | Derived; first column |
| `name` | Material name |
| `cif_file` | Full URL to CIF structure file |
| `Molecule` | `carbon_isotherm__Molecule` |
| `Good Structure` | `carbon_isotherm__good_structure` |
| `CO2 Henry (mol/kg/Pa)` | `carbon_isotherm__Henry_mol_per_kg_Pa` |
| `CO2 Pressure (bar)` | `carbon_isotherm__Pressure_bar` |
| `CO2 Uptake (mol/kg)` | `carbon_isotherm__Uptake_mol_per_kg` |
| `CO2 Heat (kJ/mol)` | `carbon_isotherm__Heat_kJ_per_mol` |
| `CO2 T_ref (K)` | `carbon_isotherm__T_ref_K` |
| `Zeo++ Density_g_per_cm3` | `carbon_zeopp__Density_g_per_cm3` |
| `Zeo++ POAVF` | `carbon_zeopp__POAVF` |
| `Zeo++ Formula` | `carbon_zeopp__Formula` |
| `Zeo++ Cp_J_per_gK` | `carbon_zeopp__Cp_J_per_gK` |
| `Zeo++ DOI` | `carbon_zeopp__DOI` |
| `Zeo++ Binder` | `carbon_zeopp__Binder` |
| `Zeo++ Macroporosity` | `carbon_zeopp__Macroporosity` |
| `Zeo++ Pellet_Density_g_per_cm3` | `carbon_zeopp__Pellet_Density_g_per_cm3` |
| `Zeo++ Round` | `carbon_zeopp__Round` |

---

## API Endpoint

| | URL |
|---|---|
| **Production** | `https://prisma-platform.org/api/` |
| **Dev mode** | `http://localhost:{dev_host_port}/` |

For `get_materials_data`, the `result['meta']['source']` key indicates which
host responded.

---

## Dev Mode

```python
# Preferred: choose target at init time
api = prisma_api.init(local_dev=True)

# Deprecated: persisted config toggle (still available)
api.update_dev_mode(True)

# Or set at init time via env vars
# PRISMA_API_DEV=true PRISMA_API_DEV_HOST_PORT=8000 python script.py
```

In dev mode all requests (v1 and v2) are routed to `http://localhost:{dev_host_port}/`.
