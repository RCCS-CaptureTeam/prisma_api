---
name: prisma-dataset
description: Prepare this dataset folder for the PrISMa platform — profile the files, draft or update prisma_manifest.yaml against the platform's live target catalogue, and loop `prisma-dataset validate` and a server dry run until the package is clean. Use when asked to prepare, package, upload or update this dataset for PrISMa, to write or fix the manifest, or after new results were added to the folder (`/prisma-dataset`).
argument-hint: "[what changed, or what to focus on]"
---

# Prepare this folder for PrISMa

The folder belongs to the researchers: never move, rename or edit their files.
The only file you write is `prisma_manifest.yaml` at the folder root. The
format is in [manifest_guide.md](manifest_guide.md); read it first.

`prisma-dataset` comes with the `prisma_api` package. If it is missing, say so
and suggest `pip install prisma_api`. If commands report a missing API key,
suggest `python -c "import prisma_api; prisma_api.init()"`.

Use `--prod` for the platform unless the user says they run a local
development server (`--dev`).

## 1. Learn what the platform can store

```bash
prisma-dataset targets --prod
prisma-dataset targets --prod --json     # the full catalogue, including defaults and allowed keys
```

Base every target name, field name and key on this output, never on memory.
Targets whose fields are "any names you choose" take any columns: use them for
data with no fixed table instead of skipping it.

## 2. Profile the folder (read-only)

Work out the following. For a big folder, sample files rather than reading them all.

- **File families:** files grouped by naming pattern, with their counts, and the columns or keys of each family. For a git repository, also note the recent history: `git log --stat`, and any change notes the authors wrote.
- **The id column** of each family, and how ids are spelled across families: suffixes such as `.cif`, case differences, and names of benchmarks that are not materials.
- **Variants encoded in paths:** cases, conditions, model versions. Each distinct variant becomes a run.
- **Rollups and copies:** which files summarise others (prefer the rollup where it is complete), and which are identical copies (compare hashes).
- **Units:** take them from column headers, READMEs and notebooks. Record only conditions you can source.

## 3. Draft the manifest

Write `prisma_manifest.yaml` with these sections, in this order:

1. `dataset`
2. `material_id`
3. `reference_systems`
4. `parameter_sets`
5. `runs`
6. `sources`

- Map each family to the best target in the catalogue. Map columns to the target's fields; for "any names you choose" targets, pick short snake_case names and give their `units`.
- Use `rows: supplement` for per-material data that should join onto each run's records. Keep `rows: create` on the files that define which materials a run covered.
- Give every file a source. Put deliberate omissions under `target: skip` with a specific reason: plots, notebooks, copies, partial or temporary files.
- Comment judgement calls in the YAML, e.g. `# 2,525 of 8,236 rows; the full file is X`.
- Ask the user which tag (or tags) the records should carry (`dataset.tag`); platform datasets group records by tag. Don't invent one.
- Ask the user before setting `dataset.by_others`. It decides whether the data may appear in the platform's Zenodo publications.

## 4. Check until clean

```bash
prisma-dataset validate . --prod
prisma-dataset pack . --out ../<slug>.zip
prisma-dataset upload ../<slug>.zip --prod          # dry run: writes nothing
```

Fix every error and repeat. Then read the dry-run counts critically:

- Rows per run should match the records in that run's files.
- Unexpected "materials created" usually mean id spellings need `strip_suffixes` or reference-system `aliases`.
- Any deletions should be explained.

## 5. Hand over

Summarise for the user:

- the runs, with their row counts
- the benchmarks
- what was skipped and why
- data problems the authors should check: outliers, files that shrank, partial runs

Never run `upload --apply` unless the user explicitly asks. It writes to the
platform and removes records that are no longer in the package.
