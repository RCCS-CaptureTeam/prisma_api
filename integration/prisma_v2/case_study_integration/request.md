Searched for regex `class ImportedCasePack|class ComponentDocument|class ProcessSpec|class ScientificField` (`**/src/prisma_v2/case_model/models.py`), 4 results

Searched for text `class ImportedCasePack` (`**/src/prisma_v2/**`), 1 result

Read [](file:///Users/pm3006/Documents/GitHub/r2h2/PrISMa-Platform-v2/src/prisma_v2/case_model/models.py)

Here is the complete field/structure specification for `ImportedCasePack` as expected by the API:

---

## `ImportedCasePack` — JSON structure spec

```jsonc
{
  "pack_root": "string",           // filesystem root of the scanned pack directory

  "case_spec": { ... },            // CaseSpec — see below

  "scenario_spec": { ... } | null, // ScenarioSpec — only present when a process set was resolved

  "available_documents": [         // flat inventory of every YAML found in the pack
    {
      "name": "string",            // basename stem (e.g. "high-purity-general")
      "kind": "string",            // inferred family: "source"|"sink"|"process"|"utility"|"tea_general"|"case_root"
      "source_path": "string"      // absolute path on disk
    }
  ],

  "import_issues": [               // warnings/errors from scanning
    {
      "code": "string",
      "severity": "info"|"warning"|"error",
      "message": "string",
      "document_name": "string" | null,
      "requested_path": "string" | null,
      "resolved_path": "string" | null
    }
  ]
}
```

---

## `CaseSpec`

```jsonc
{
  "case_name": "string",           // stem of root YAML, e.g. "DAC_Workington_northernlights_transport"
  "source_name": "string",
  "sink_name": "string",
  "region": "string",              // e.g. "UK2030-SSP2-PkBudg1150"
  "root_case_path": "string",

  "source":    { ... },            // CaseComponentSpec (required)
  "sink":      { ... },            // CaseComponentSpec (required)
  "transport": { ... } | null,
  "utilities": [ { ... } ],        // list[CaseComponentSpec]
  "tea_general": { ... } | null,   // CaseComponentSpec
  "import_issues": [ ... ]
}
```

---

## `CaseComponentSpec`

```jsonc
{
  "component_type": "source"|"sink"|"transport"|"utility"|"tea_general",
  "name": "string",
  "document": { ... },             // ComponentDocument
  "region_use": "string" | null,
  "region_synthesis": "string" | null,
  "region_storage": "string" | null,
  "sink_type": "string" | null
}
```

---

## `ComponentDocument`

```jsonc
{
  "kind": "string",                // inferred document family
  "logical_name": "string",        // best-effort scientific name
  "source_path": "string",

  "sections": {                    // dict[section_name → list[ScientificField]]
    "Process": [
      {
        "name": "string",          // field label from YAML
        "value": <any>,
        "units": "string" | null,
        "reference": "string" | null,
        "description": "string" | null,
        "source_document": "string",
        "section": "string"
      }
    ]
  },

  "scalar_entries": {              // dict[str → any] for non-list YAML keys
    "Region": "UK",
    "Source": "DAC"
  },

  "nested_includes": [             // IncludeResolution records
    {
      "key": "string",             // YAML key that triggered the include
      "reference": {
        "requested_path": "string",
        "basename": "string",
        "role_hint": "string" | null
      },
      "status": "resolved"|"missing",
      "resolved_path": "string" | null,
      "document": { ... } | null   // nested ComponentDocument (recursive)
    }
  ],

  "issues": [ ... ]                // list[ImportIssue]
}
```

---

## `ScenarioSpec` *(only when process set resolved)*

```jsonc
{
  "scenario_name": "string",
  "case_name": "string",
  "source_name": "string",
  "sink_name": "string",
  "region": "string",

  "process": { ... } | null,                         // ProcessSpec
  "adsorption_scenario": { ... } | null,             // ResolvedAdsorptionScenario (process_contracts.py)
  "process_preview": { ... } | null,                 // ProcessCyclePreview (process_contracts.py)

  "utilities": [ { ... } ],                          // list[CaseComponentSpec]
  "tea_general": { ... } | null,
  "import_issues": [ ... ]
}
```

---

## `ProcessSpec` *(inside ScenarioSpec)*

```jsonc
{
  "parameter_set_name": "string",
  "document": { ... },                               // ComponentDocument
  "process_family": "string",                        // e.g. "TVSA", "PSA"
  "backend_key": "equilibrium"|"pyadscycle_numba",
  "fidelity": "screening_equilibrium"|"...",
  "process_fidelity": "string" | null,
  "solver_kernel": "string" | null,
  "cycle_definition": { ... },                       // CycleDefinitionSpec
  "scientific_model": { ... },                       // ProcessScientificModel
  "provisional_flags": ["string"]
}
```

---

## Key design notes for the remote API

| Concern | Detail |
|---------|--------|
| **Serialisation** | `ImportedCasePack.snapshot_payload()` / `.snapshot_json()` already produce the canonical JSON — use those directly |
| **Recursive documents** | `ComponentDocument.nested_includes[].document` is self-referential; depth is bounded by the YAML include tree (typically 1–2 levels) |
| **`sections` vs `scalar_entries`** | Legacy YAML docs store data as `list[{Name, Value, Units}]` → `sections`; modern scalar YAML keys go into `scalar_entries` |
| **`process_preview` / `adsorption_scenario`** | These are large compiled science objects from process_contracts.py; if the remote API only needs to *store and return* the pack, treat them as opaque JSON blobs |
| **All models use `extra="forbid"`** | The remote API must not add undeclared fields; unknown fields in a response will fail `model_validate` |