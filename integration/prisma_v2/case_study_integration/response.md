# `prisma_api` — New Functions & Usage Reference

## Access pattern

All v2 methods live on the `api.v2` sub-object, which is instantiated automatically by `prisma_api.init()`.

```python
import prisma_api
api = prisma_api.init()   # reads key from ~/.config/prisma_api/config.yaml
```

---

## 1 · Extended material list fields (`list_materials`)

`GET /api/v2/materials/` now returns nine additional fields on every record alongside the existing `id`, `name`, `cif_url`.

```python
df = api.v2.list_materials()              # DataFrame (default)
# or
api.v2.set_return_format("json")
records = api.v2.list_materials()         # list[dict]
```

| Field | Type | Value |
|---|---|---|
| `material_id` | `str` | Same as `name` — used as slug identifier |
| `material_backend` | `str` | Always `"tabular_binary_iast"` |
| `gas_basis` | `list[str]` | `["CO2","N2","H2O"]` if Water KPI data exist, else `["CO2","N2"]` |
| `supports_humid_ternary` | `None` | Reserved |
| `tags` | `list` | Always `[]` — reserved |
| `provenance` | `str` | Always `"tabular_material"` |
| `lifecycle` | `dict` | `{"object_kind": "catalog", "version": "legacy.v1"}` |
| `metadata` | `dict` | `{"django_candidate_tables": ["MOF","Carbon_Isotherm","Water_KPIs","Carbon_ZeoPP"], "source": "live_db"}` |
| `source_path` | `None` | Reserved |

Filtering and pagination are unchanged:

```python
api.v2.list_materials(name="ABEXEM", limit=50, offset=0)
```

---

## 2 · Preflight check (`preflight_material_check`)

Returns `True` if at least one material matching the name exists. Makes one `GET /api/v2/materials/?name=…&limit=1` call.

```python
exists = api.v2.preflight_material_check("ABEXEM")   # True / False
```

---

## 3 · Property bundle (`get_material_property_bundle`)

Single call that aggregates all four science data types for a given MOF. Returns a plain `dict` regardless of `return_format`.

```python
bundle = api.v2.get_material_property_bundle("ABEXEM")

# bundle keys:
# {
#   "isotherms":          list | DataFrame,
#   "zeopp_simulated":    list | DataFrame,
#   "zeopp_experimental": list | DataFrame,
#   "water_kpis":         list | DataFrame,
# }
```

Optional filters apply consistently across all four sub-queries:

```python
bundle = api.v2.get_material_property_bundle(
    mof="ABEXEM",
    sim_or_exp="sim",
    good_structure=True,
)
```

---

## 4 · Case pack builders (`ImportedCasePack` spec)

Four compound methods that fetch remote Django records and return nested dicts conforming to the `ImportedCasePack` / `CaseSpec` / `ScenarioSpec` JSON contract.

> **Important:** Fields that exist only in the originating YAML pack (`pack_root`, per-component `document` sub-trees, `available_documents`, `import_issues`) are returned as `None` / `[]`. Merge locally scanned document data in after retrieval if needed.

---

### 4.1 `build_case_spec(case_id)` → `CaseSpec` dict

Fetches `GET /api/v2/cases/{case_id}/` and reshapes into a `CaseSpec`.

```python
spec = api.v2.build_case_spec(3372)
# {
#   "case_name":      "UK Coal CCS 2030",
#   "source_name":    "Coal Power Plant",
#   "sink_name":      "North Sea Aquifer",
#   "region":         "GB",
#   "root_case_path": None,
#   "source":    {"component_type": "source",    "name": "Coal Power Plant", "document": None, ...},
#   "sink":      {"component_type": "sink",      "name": "North Sea Aquifer", ...},
#   "transport": {"component_type": "transport", "name": "Pipeline 200km", ...},
#   "utilities": [{"component_type": "utility",  "name": "Steam", ...}],
#   "tea_general":   None,
#   "import_issues": []
# }
```

---

### 4.2 `build_scenario_spec(scenario_id)` → `ScenarioSpec` dict

Fetches `GET /api/v2/scenarios/{scenario_id}/`.

```python
spec = api.v2.build_scenario_spec(830)
# {
#   "scenario_name":       "baseline_2030",
#   "case_name":           "UK Coal CCS 2030",
#   "source_name":         None,
#   "sink_name":           None,
#   "region":              None,
#   "process":             None,   # YAML-compiled — not stored remotely
#   "adsorption_scenario": None,
#   "process_preview":     None,
#   "utilities":           [],
#   "tea_general":         None,
#   "import_issues":       []
# }
```

---

### 4.3 `build_case_pack(case_id, scenario_id=None)` → `ImportedCasePack` dict

Makes 1–2 GET calls and returns the full pack structure.

```python
# Auto-resolve first scenario for the case (2 GETs)
pack = api.v2.build_case_pack(3372)

# Explicit scenario (2 GETs, no list call)
pack = api.v2.build_case_pack(3372, scenario_id=830)

# No scenario resolution (1 GET)
pack = api.v2.build_case_pack(3372, scenario_id=-1)

# Return shape:
# {
#   "pack_root":           None,
#   "case_spec":           { CaseSpec },
#   "scenario_spec":       { ScenarioSpec } | None,
#   "available_documents": [],
#   "import_issues":       []
# }
```

---

### 4.4 `list_case_packs(…)` → `list[ImportedCasePack dict]`

Fetches `GET /api/v2/cases/` with optional filters and returns one pack dict per case.

```python
# Lightweight — scenario_spec is None for every record (1 GET total)
packs = api.v2.list_case_packs(source="coal", region="GB", limit=20)

# With scenarios — attaches first ScenarioSpec per case (N+1 GETs)
# Use only with small result sets
packs = api.v2.list_case_packs(study="UK2030", limit=5, include_scenarios=True)
```

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `source` | `str \| None` | `None` | Source name substring |
| `sink` | `str \| None` | `None` | Sink name substring |
| `region` | `str \| None` | `None` | Exact region ISO code |
| `study` | `str \| None` | `None` | Exact study label |
| `include_scenarios` | `bool` | `False` | Resolves first scenario per case — N+1 requests |
| `limit` | `int` | `100` | Max cases (default lower than other list endpoints) |
| `offset` | `int` | `0` | Pagination offset |

---

## 5 · Return format

All list endpoints respect `set_return_format`. The case pack builders always return `dict` / `list[dict]` regardless of this setting.

```python
api.v2.set_return_format("dataframe")  # pd.DataFrame (default)
api.v2.set_return_format("json")       # list[dict]
```

---

## 6 · CaseComponentSpec shape (reference)

Every `source`, `sink`, `transport`, and `utilities` entry in a `CaseSpec` has this shape:

```python
{
    "component_type":    "source" | "sink" | "transport" | "utility" | "tea_general",
    "name":              str,
    "document":          None,   # populated only from local YAML pack
    "region_use":        None,
    "region_synthesis":  None,
    "region_storage":    None,
    "sink_type":         None,
}
```
