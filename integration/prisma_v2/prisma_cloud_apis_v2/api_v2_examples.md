# PrISMa Cloud — REST API v2: Example Calls

Base URL: `https://<host>/api/v2/`

All endpoints require the header:

```
X-API-Key: <your-api-key>
```

Responses use the envelope `{"count": N, "offset": N, "limit": N, "results": [...]}` for list
endpoints and a flat JSON object for detail endpoints.

---

## Authentication

```bash
# All curl examples below assume this variable is set:
export KEY="your-api-key-here"
export HOST="https://prisma-cloud.example.com"
```

---

## Health

### `GET /api/v2/health/`

```bash
curl -H "X-API-Key: $KEY" "$HOST/api/v2/health/"
```

```json
{"status": "ok", "version": "2.0.0"}
```

---

## Catalog

### Materials (MOFs)

#### List materials

```bash
# All materials (default limit 500)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/materials/"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/materials/?name=ABEXEM"

# Paginate
curl -H "X-API-Key: $KEY" "$HOST/api/v2/materials/?limit=50&offset=100"
```

```json
{
  "count": 4639,
  "offset": 0,
  "limit": 50,
  "results": [
    {"id": 231325, "name": "ABEXEM", "cif_url": "/media_private/cifs/ABEXEM.cif"},
    ...
  ]
}
```

#### Get material detail (with element composition)

```bash
curl -H "X-API-Key: $KEY" "$HOST/api/v2/materials/231325/"
```

```json
{
  "id": 231325,
  "name": "ABEXEM",
  "cif_url": "/media_private/cifs/ABEXEM.cif",
  "elements": [
    {"symbol": "C", "name": "Carbon", "mass_fraction": 0.4512},
    {"symbol": "N", "name": "Nitrogen", "mass_fraction": 0.1834}
  ]
}
```

---

### Molecules

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/molecules/"

# Filter by name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/molecules/?name=CO2"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/molecules/3/"
```

```json
{"id": 3, "name": "CO2"}
```

---

### Elements

```bash
# List all elements (ordered by atomic number)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/elements/"

# Filter by symbol (exact, case-insensitive)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/elements/?symbol=Fe"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/elements/?name=carbon"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/elements/6/"
```

```json
{"id": 6, "symbol": "C", "name": "Carbon", "atomic_number": 6, "atomic_weight": 12.011}
```

---

### Regions

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/regions/"

# Filter by ISO code
curl -H "X-API-Key: $KEY" "$HOST/api/v2/regions/?code=GB"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/regions/?name=Europe"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/regions/1304/"
```

```json
{"id": 1304, "name": "United Kingdom", "code": "GB"}
```

---

### Sources

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sources/"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sources/?name=power"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sources/1257/"
```

```json
{"id": 1257, "name": "Coal Power Plant", "short_name": "CPP", ...}
```

---

### Sinks

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sinks/"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sinks/?name=storage"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/sinks/42/"
```

---

### Transport Scenarios

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/transport-scenarios/"

# Filter by name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/transport-scenarios/?name=pipeline"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/transport-scenarios/7/"
```

---

### Utilities

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/utilities/"

# Filter by name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/utilities/?name=steam"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/utilities/12/"
```

---

### References

```bash
# List
curl -H "X-API-Key: $KEY" "$HOST/api/v2/references/"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/references/?name=IPCC"

# Filter by DOI (exact, case-insensitive)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/references/?doi=10.1038/s41586-019-1666-5"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/references/88/"
```

---

## Science Data

### Isotherms

```bash
# All isotherms (limit 500 default)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/"

# Filter by MOF name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?mof=ABEXEM"

# Filter by molecule
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?molecule=CO2"

# Temperature range [K]
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?temperature_min=290&temperature_max=320"

# Simulation vs experimental data
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?sim_or_exp=sim"
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?sim_or_exp=exp"

# Only good structures
curl -H "X-API-Key: $KEY" "$HOST/api/v2/isotherms/?good_structure=true"

# Combined filters + pagination
curl -H "X-API-Key: $KEY" \
  "$HOST/api/v2/isotherms/?mof=ABEXEM&molecule=CO2&sim_or_exp=sim&limit=20"
```

```json
{
  "count": 14,
  "results": [
    {
      "id": 9001,
      "mof": "ABEXEM",
      "molecule": "CO2",
      "T_ref_K": 298.0,
      "sim_or_exp": "sim",
      "good_structure": true,
      ...
    }
  ]
}
```

---

### Water KPIs

```bash
# All water KPIs
curl -H "X-API-Key: $KEY" "$HOST/api/v2/water-kpis/"

# Filter by MOF
curl -H "X-API-Key: $KEY" "$HOST/api/v2/water-kpis/?mof=ABEXEM"

# Filter by molecule and source
curl -H "X-API-Key: $KEY" "$HOST/api/v2/water-kpis/?molecule=H2O&source=Coal"

# Sim/exp split
curl -H "X-API-Key: $KEY" "$HOST/api/v2/water-kpis/?sim_or_exp=exp"

# Good structures only
curl -H "X-API-Key: $KEY" "$HOST/api/v2/water-kpis/?good_structure=true"
```

---

## TEA / LCA Data

### Output KPIs

#### List / filter

```bash
# All output KPIs
curl -H "X-API-Key: $KEY" "$HOST/api/v2/output-kpis/"

# Filter by scenario
curl -H "X-API-Key: $KEY" "$HOST/api/v2/output-kpis/?scenario_id=830"

# Filter by MOF name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/output-kpis/?mof=ABEXEM"

# Good structures only + scenario
curl -H "X-API-Key: $KEY" \
  "$HOST/api/v2/output-kpis/?scenario_id=830&good_structure=true&limit=100"
```

#### Get single record

```bash
curl -H "X-API-Key: $KEY" "$HOST/api/v2/output-kpis/110803/"
```

```json
{
  "id": 110803,
  "scenario_id": 830,
  "mof_name": "ABEXEM",
  "purity": 0.96,
  "recovery": 0.88,
  ...
}
```

#### Upsert (bulk write)

Lookup key: `(scenario, MOF)` integer PKs.

```bash
curl -X PUT \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '[
    {"scenario": 830, "MOF": 231325, "purity": 0.96, "recovery": 0.88},
    {"scenario": 830, "MOF": 231326, "purity": 0.91, "recovery": 0.79}
  ]' \
  "$HOST/api/v2/output-kpis/"
```

```json
{"created": 1, "updated": 1}
```

If any record fails validation, a `207 Multi-Status` is returned and the `errors` key lists the failures:

```json
{"created": 1, "updated": 0, "errors": [{"item": {...}, "errors": {...}}]}
```

---

### Region Costs

```bash
# List all
curl -H "X-API-Key: $KEY" "$HOST/api/v2/region-costs/"

# Filter by region code
curl -H "X-API-Key: $KEY" "$HOST/api/v2/region-costs/?region=GB"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/region-costs/?name=electricity"

# Filter by year
curl -H "X-API-Key: $KEY" "$HOST/api/v2/region-costs/?year=2030"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/region-costs/55/"
```

#### Upsert

Lookup key: `Name` (unique).

```bash
curl -X PUT \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "Name": "GB_electricity_2030",
      "Region": 1304,
      "Year": 2030,
      "Value": 0.18,
      "Unit": "£/kWh"
    }
  ]' \
  "$HOST/api/v2/region-costs/"
```

```json
{"created": 0, "updated": 1}
```

---

### Ambient Parameters

```bash
# List all
curl -H "X-API-Key: $KEY" "$HOST/api/v2/ambient-parameters/"

# Filter by name substring
curl -H "X-API-Key: $KEY" "$HOST/api/v2/ambient-parameters/?name=temperature"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/ambient-parameters/3/"
```

#### Upsert

Lookup key: `Name` (unique).

```bash
curl -X PUT \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '[{"Name": "ambient_temperature_K", "Value": 298.15}]' \
  "$HOST/api/v2/ambient-parameters/"
```

```json
{"created": 0, "updated": 1}
```

---

## Cases & Scenarios

### Cases

```bash
# List all cases
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/"

# Filter by source name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/?source=power"

# Filter by sink name
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/?sink=storage"

# Filter by region code
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/?region=GB"

# Filter by study label (exact, case-insensitive)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/?study=UK2030"

# Paginate
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/?limit=20&offset=40"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/cases/3372/"
```

```json
{
  "id": 3372,
  "name": "UK Coal CCS 2030",
  "source": "Coal Power Plant",
  "sink": "North Sea Aquifer",
  "region": "GB",
  "transport_scenario": "Pipeline 200km",
  ...
}
```

---

### Scenarios

```bash
# List all scenarios
curl -H "X-API-Key: $KEY" "$HOST/api/v2/scenarios/"

# Filter scenarios belonging to a case
curl -H "X-API-Key: $KEY" "$HOST/api/v2/scenarios/?case_id=3372"

# Filter by name substring (matches name or print_name)
curl -H "X-API-Key: $KEY" "$HOST/api/v2/scenarios/?name=baseline"

# Filter by scenario type
curl -H "X-API-Key: $KEY" "$HOST/api/v2/scenarios/?type=TEA"

# Detail
curl -H "X-API-Key: $KEY" "$HOST/api/v2/scenarios/830/"
```

```json
{
  "id": 830,
  "name": "baseline_2030",
  "print_name": "Baseline 2030",
  "type": "TEA",
  "case_study_id": 3372
}
```

---

## Error Responses

| Situation | Status | Body |
|---|---|---|
| Unknown ID | `404 Not Found` | `{"detail": "Material '9999' not found."}` |
| Bad query param type | `400 Bad Request` | `{"detail": "scenario_id must be an integer, got 'abc'"}` |
| Invalid enum value | `400 Bad Request` | `{"detail": "sim_or_exp must be 'sim' or 'exp'"}` |
| Missing / invalid API key | `403 Forbidden` | `{"detail": "Authentication credentials were not provided."}` |
| Upsert partial failure | `207 Multi-Status` | `{"created": N, "updated": N, "errors": [...]}` |

---

## Query-String Parameter Reference

| Endpoint | Parameter | Type | Notes |
|---|---|---|---|
| All list endpoints | `limit` | int | Default 500 |
| All list endpoints | `offset` | int | Default 0 |
| `/materials/` | `name` | string | Case-insensitive substring |
| `/molecules/` | `name` | string | Case-insensitive substring |
| `/elements/` | `symbol` | string | Exact, case-insensitive |
| `/elements/` | `name` | string | Substring |
| `/regions/` | `code` | string | Exact, case-insensitive |
| `/regions/` | `name` | string | Substring |
| `/sources/` `/sinks/` `/transport-scenarios/` `/utilities/` | `name` | string | Substring |
| `/references/` | `name` | string | Substring |
| `/references/` | `doi` | string | Exact, case-insensitive |
| `/isotherms/` | `mof` | string | MOF name substring |
| `/isotherms/` | `molecule` | string | Molecule name substring |
| `/isotherms/` | `temperature_min` | float | Lower bound on T\_ref\_K [K] |
| `/isotherms/` | `temperature_max` | float | Upper bound on T\_ref\_K [K] |
| `/isotherms/` `/water-kpis/` | `sim_or_exp` | `sim` \| `exp` | Data origin |
| `/isotherms/` `/water-kpis/` `/output-kpis/` | `good_structure` | `true`\|`false` | |
| `/water-kpis/` | `source` | string | Source name substring |
| `/output-kpis/` | `scenario_id` | int | Exact scenario PK |
| `/output-kpis/` | `mof` | string | MOF name substring |
| `/region-costs/` | `region` | string | Region code, exact |
| `/region-costs/` | `name` | string | Substring |
| `/region-costs/` | `year` | int | Exact year |
| `/ambient-parameters/` | `name` | string | Substring |
| `/cases/` | `source` | string | Source name substring |
| `/cases/` | `sink` | string | Sink name substring |
| `/cases/` | `region` | string | Region code, exact |
| `/cases/` | `study` | string | Study label, exact |
| `/scenarios/` | `case_id` | int | Exact case PK |
| `/scenarios/` | `name` | string | Substring (name or print\_name) |
| `/scenarios/` | `type` | string | Exact, case-insensitive |
