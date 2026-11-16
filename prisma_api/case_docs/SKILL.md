---
name: prisma-case
description: Publish a local case study (a process-graph JSON such as PrISMa-Platform-v2's cases/<name>/<name>.json, with optional <name>.study.yaml settings) to the PrISMa platform's case study builder, and keep the local case and the online build in step — status, push a draft, publish the v2 study, pull online edits, or fork when both changed. Use when asked to publish, upload, sync, check, pull or fork a case study on the PrISMa platform / prisma_cloud, or when `prisma-case status` reports a case ahead or behind.
argument-hint: '<case.json> [status|push|publish|pull|fork] [--dev | --prod]'
---

# Publish a case study to PrISMa and keep it in step

Arguments: `$ARGUMENTS`

- the case file (a `prisma_v2.flowsheet.process_graph.v6` JSON; first argument);
- the action: `status` (default), `push` (draft only), `publish`, `pull` or `fork`;
- the server: `--prod` (prisma-platform.org) or `--dev` (local server). With no flag, ask which one —
  never default to production for a write.

Everything goes through the `prisma-case` command of the installed `prisma_api` package. Never call the
HTTP API by hand, never print or copy the API key (it lives in prisma_api's `config.yaml`), and never edit
`<name>.cloud.json` (the link file `prisma-case` keeps). If a call fails with 401/403, the user's key is
missing, revoked, or not in the platform's case-study-builder team: tell them, don't retry.

## 1. Look before writing

```
prisma-case status <case.json> <server> --json
```

`state` is one of: `unlinked` (not online yet), `in_sync`, `local_ahead`, `online_ahead`, `diverged`
(both changed), `missing` (the linked build was deleted). `actions` lists what applies; `build` holds the
online status, `design_hash`, and `urls.edit` (the canvas page) when linked.

## 2. Study settings

The graph carries the flowsheet; the study settings the builder page adds go in `<name>.study.yaml` next
to the case (create it if the user gives settings; keys outside this list are refused):

```yaml
name: DAC min UK            # study name (unique on the platform); default: the graph's label/template_id
desc: Which sorbents capture most?
locs: ["United Kingdom (UK-B)"]   # from `prisma-case catalogue <server> --json` -> options.locations
time: "2030"                # present | 2030 | 2050
scen: SSP2-PkBudg500        # only with a future time
tea: {hours: "8500", life: "25", discount: "8", build: "2", year: "2024", currency: EUR}
lca: {fu: "1 t CO₂ stored", method: ""}
kpis:                       # '<node_id>.<output>'; outputs per node type in the catalogue
  - {key: co2-contactor.co2_captured_kg_per_h, label: CO₂ captured, role: rank, fmt: "3"}
samp:                       # per node_id: mat one|set|all, n, isos, cycles, par {param: fixed|opt|s3|s5|s10}
  co2-sorbent-material: {mat: set, n: "20", isos: [Langmuir]}
systems:                    # optional alternatives, each its own canvas
  - {name: Heat pump 2, graph: dac_min_alt.json}
```

TEA hours/lifetime, the LCA functional unit and region are read from the graph's plant/tea/lca nodes when
the file does not set them. Before writing, show the user what the server would make:
`prisma-case publish <case.json> <server> --dry-run --json` reports the sync state, the study settings as
the builder reads them, the nodes, `fixes` (block publishing) and `warns`, and writes nothing.

## 3. Act on the state

| state | do |
|---|---|
| unlinked / missing | `prisma-case push` (draft) or `prisma-case publish` (draft + v2 study) |
| local_ahead, draft | `push` or `publish` |
| local_ahead, published | `fork` (a published build never changes): new draft '<name> rN', link moves to it |
| online_ahead | `pull` (writes the case JSON and study file; show the user `git diff` afterwards) |
| diverged | **ask the user**: `fork` (keep both), `pull` (discard local edits), or `overwrite` (draft only) |
| in_sync | nothing; `publish` if the draft should go live |

Writes ask for confirmation in a terminal. From this session pass the user's decision explicitly:
`--yes` once they agreed, and `--on-conflict fork|pull|overwrite` for the conflict cases. Exit code 2
means a decision is still needed: report the message and ask; don't pick for them. Always use `--json`
and report the `edit_url` / `study_url` the command prints.

## 4. Other commands

- `prisma-case list <server> [--case-id <template_id>]` — builds online.
- `prisma-case link <case.json> <build_id> <server>` — attach a case to a build drawn on the page.
- `prisma-case unlink <case.json> <server>`.
- `prisma-case catalogue <server> --json` — node types, model paths, outputs, locations, templates.

Pull refuses builds with nodes that have no platform model yet (`placeholders`): the local runner cannot run
them. Tell the user which nodes; pass `--allow-placeholders` only if they ask.
