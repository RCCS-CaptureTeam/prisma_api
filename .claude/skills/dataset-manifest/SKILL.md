---
name: dataset-manifest
description: Draft, fix or update the prisma_manifest.yaml for a third-party academic dataset (a folder or git repo of CSV/JSON/YAML results from another team) so it can be packed and uploaded to the PrISMa platform as one zip (server ingest pipeline 15). Profiles the folder, maps files to target tables (mof_h2, h2_results, run_inputs, parameters, skip), declares runs, benchmarks and parameter sets, then loops `prisma-dataset validate` and a server dry run until clean. Use when asked to onboard, ingest, package or re-ingest a dataset, to write or update a dataset manifest, or after the authors push new data (`/dataset-manifest ../Hydrogen_v2`).
argument-hint: <dataset folder> [manifest path]
---

# Dataset manifest for a third-party package

Expect ad-hoc academic practice in the folder:

- units embedded in column headers
- the same benchmark spelled three ways
- result variants encoded only in folder names
- byte-identical copies, `_v2` / `old/` / `.bak` files
- rows that a filename says should be there but are not

The manifest absorbs all of this. Never edit the authors' files.

The reference for every key is
[reference_data/prisma_cloud/dataset_manifest_brief.md](../../../reference_data/prisma_cloud/dataset_manifest_brief.md).
Read it first. The worked example is
[integration/datasets/hydrogen_v2/prisma_manifest.yaml](../../../integration/datasets/hydrogen_v2/prisma_manifest.yaml).

Keep manifests for other teams' repositories in `integration/datasets/<name>/prisma_manifest.yaml`, not in their repository.

## 1. Profile the folder (read-only)

Delegate broad sweeps to an Explore agent when the folder has more than a few hundred files. Establish the following:

- **File families.** Group files by naming pattern, with counts per directory. For each family, record its columns or keys and its row counts.
- **The material id column** and its spellings: suffixes such as `.cif`/`_clean`, case changes, and benchmark names.
- **Variants encoded in paths:** case, cycles, lanes, tank volume. Each distinct variant becomes a run.
- **Which files are rollups of others.** Prefer the rollup, but use the per-record JSON where a rollup is missing or partial.
- **Duplicates.** Hash-compare suspected copies.
- **Units.** Take them from headers, notebooks (`SYSTEM_*` constants) and READMEs. Record conditions you can source; never invent them.
- **Recent changes.** `git log` / `git diff --stat <last-ingested-commit>..HEAD`. If a `DATA_CHANGES_*.md` exists, read it and reflect each point in the manifest.

## 2. Draft the manifest

Write the sections in this order:

1. `dataset`
2. `material_id`
3. `reference_systems` (every non-material benchmark, with all its spellings as aliases)
4. `parameter_sets`
5. `case_studies`
6. `runs` (one per case × variant)
7. `sources`

**Prefer existing targets.** Only use `run_inputs` when a run used inputs that differ from the material's own record (e.g. other pressures).

**Bind files to runs.** Use `run:` templates where paths name the variant, and `runs_where:` where one file serves every run of a case.

**Choose `rows:` for each source.**

- Use `rows: supplement` for files that describe the material rather than the run, such as sizing joined onto the run's cost rows.
- Leave `rows: create` on the file that defines which materials a run covered.

**Give every file a source.**

- Put deliberate omissions under `target: skip` with a specific `reason`: derived plot data, notebooks, subsets, partial or temporary files, and data with no existing home (mark the last as *Deferred*).
- Comment on judgement calls in YAML comments, e.g. "cut to 2,525 rows at 20f2d35; using X instead".

## 3. Validate, pack, dry run

From the prisma_api repo root:

```bash
.venv/bin/python -m prisma_api.dataset_package validate <folder> --manifest <manifest>
.venv/bin/python -m prisma_api.dataset_package pack <folder> --manifest <manifest> --out <scratchpad>/pkg.zip
# Server dry run, against the local dev DB (applies and rolls back):
(cd ../prisma_cloud && .venv/bin/python manage.py ingest_dataset <scratchpad>/pkg.zip --report <scratchpad>/report.json)
```

Iterate until there are no errors. Then read the warnings and the per-run counts critically:

- A run with far fewer or more rows than its source folder has records means a binding or `rows:` mistake.
- `supplement_rows_without_base` should match known coverage gaps.
- `materials_created` should be expected.
- `H2_Results legacy_deleted` should only cover cases the package replaces.

## 4. Hand over

Summarise for the user:

- the runs and their row counts
- the benchmarks
- what was skipped and why
- the checks the data needs from its authors (outliers, suspicious row-count changes, partial runs)

Do not apply the package. `--apply`, `prisma-dataset upload --apply` and `dry_run=false` write to a database and mirror-delete rows. Run them only when the user explicitly asks, and say which server they target.
