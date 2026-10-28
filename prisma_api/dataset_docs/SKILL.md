---
name: prisma-dataset
description: Build or update prisma_manifest.yaml for the files ticked in this folder's PrISMa folder tree, check it with the platform's dry run, and send the data, in one command such as `/prisma-dataset my-dataset --tag "My tag" --prod` (the dataset page shows it above the folder tree). Use when asked to prepare, package, send or update this dataset for PrISMa, to write or fix the manifest, or after new results were added to the folder.
argument-hint: '<dataset-slug> --tag "<tag>" [--dev | --prod]'
---

# Build the manifest and send this folder to PrISMa

Arguments: `$ARGUMENTS`

The dataset page on the platform gives these arguments, in the command above its
**View folder tree**:

- the dataset slug (first);
- the tag the records go under (`--tag "..."`; there may be more than one);
- the server: `--prod` for the platform, `--dev` for a local development server.

If the slug or the tag is missing, ask the user to copy the command from the
dataset page; don't invent either. With no server flag, use `--prod`. Below,
`<server>`, `<slug>` and `<tag>` stand for these arguments; use them in every
command.

The folder belongs to the researchers: never move, rename or edit their files.
The only file you write is `prisma_manifest.yaml` at the folder root. The
format is in [manifest_guide.md](manifest_guide.md); read it first.

`prisma-dataset` comes with the `prisma_api` package. If it is missing, say so
and suggest `pip install prisma_api`. If commands report a missing API key,
suggest `python -c "import prisma_api; prisma_api.init()"` (with
`local_dev=True` inside `init(...)` for `--dev`).

## 1. Find the files to send

```bash
prisma-dataset ticked . <server> --dataset <slug>
prisma-dataset ticked . <server> --dataset <slug> --json    # the same, for reading
```

This lists the files the user ticked "in dataset" in the platform's folder tree,
with the dataset's title and tags. Only these files are sent, so the manifest
must cover every one of them; files that are not ticked need no source.

- **No tree yet:** the user first sends the folder structure with the dataset page's **Add un-managed dataset** command (`prisma-dataset tree . <server> --dataset <slug> --tag "<tag>"`), then ticks files in **View folder tree**. Give them that, and stop.
- **Nothing ticked:** ask them to tick the files to send on the dataset page, and stop.
- **"Newer than the tree":** these files are not sent. If the user wants them, they resend the tree (`prisma-dataset tree . <server>`) and tick them. Mention them in the hand-over.
- **"[by others]":** the user marked these files as data by others. Give their sources `by_others: true`.

## 2. Learn what the platform can store

```bash
prisma-dataset targets <server>
prisma-dataset targets <server> --json     # the full catalogue, including defaults and allowed keys
```

Base every target name, field name and key on this output, never on memory.
Targets whose fields are "any names you choose" take any columns: use them for
data with no fixed table instead of skipping it.

## 3. Profile the ticked files (read-only)

Work out the following. For many files, sample rather than reading them all.

- **File families:** files grouped by naming pattern, with their counts, and the columns or keys of each family. For a git repository, also note the recent history: `git log --stat`, and any change notes the authors wrote.
- **The id column** of each family, and how ids are spelled across families: suffixes such as `.cif`, case differences, and names of benchmarks that are not materials.
- **Variants encoded in paths:** cases, conditions, model versions. Each distinct variant becomes a run.
- **Rollups and copies:** which files summarise others (prefer the rollup where it is complete), and which are identical copies (compare hashes).
- **Units:** take them from column headers, READMEs and notebooks. Record only conditions you can source.

## 4. Build or update the manifest

If `prisma_manifest.yaml` exists, update it. Keep the authors' sources, runs,
comments and decisions. Add sources for ticked files that no source reads, and
fix what is out of date. Leave sources whose files are all unticked in place;
they are simply not sent. Otherwise write a new one with these sections, in
this order:

1. `dataset`
2. `material_id`
3. `reference_systems`
4. `parameter_sets`
5. `runs`
6. `sources`

The `dataset` section:

- `slug`: the `<slug>` argument.
- `tag`: the `<tag>` argument (a list if there are several).
- `name`: the dataset's title from step 1.
- `by_others`: keep the manifest's value. In a new manifest write `by_others: false  # our own data` and point it out in the hand-over. It decides whether the data may appear in the platform's Zenodo publications.

If an existing manifest names another slug or tag, replace it with the
argument and tell the user. The exception is a slug the step 1 output lists
under `lineage` (an older version of the same dataset); that one may stay.

For the other sections:

- Map each family to the best target in the catalogue. Map columns to the target's fields; for "any names you choose" targets, pick short snake_case names and give their `units`.
- Use `rows: supplement` for per-material data that should join onto each run's records. Keep `rows: create` on the files that define which materials a run covered.
- Give every ticked file a source. Put ticked files that hold nothing to ingest (plots, notebooks, copies, partial or temporary files) under `target: skip` with a specific reason.
- Comment judgement calls in the YAML, e.g. `# 2,525 of 8,236 rows; the full file is X`.

## 5. Check until clean

```bash
prisma-dataset validate . <server>
prisma-dataset send . <server> --json        # pack the ticked files and dry run: writes nothing
```

Fix every error and repeat. Then read the dry-run counts critically:

- Rows per run should match the records in that run's files.
- Unexpected "materials created" usually mean id spellings need `strip_suffixes` or reference-system `aliases`.
- Any deletions should be explained.

A refusal about the dataset or the tag (no such dataset, deprecated, tag in use
elsewhere) is not a manifest problem: tell the user what the platform said and
stop.

## 6. Confirm, then send

Summarise for the user:

- the runs, with their row counts
- the benchmarks
- what was skipped and why
- the dataset version the upload will make (`version` in the dry run)
- `by_others`, if you set it
- files that are newer than the tree, or ticked but missing
- data problems the authors should check: outliers, files that shrank, partial runs

Then ask once: "Send this to the platform (`<server>`)?" Only on a clear yes, run:

```bash
prisma-dataset send . <server> --apply
```

Report the version it made and the dataset page link.

Never run `send --apply` or `upload --apply` without that yes. It writes to the
platform and removes records that are no longer in the package.

## Later updates

Run the same command again after new results arrive. The manifest is updated
the same way, and a send that changes records makes a minor version.

If files were added or removed, the user resends the tree first
(`prisma-dataset tree . <server>`) and ticks the new files. Once data has been
sent, a changed file list makes a new major version, `<slug>-v2` tagged
`"<tag> v2"`. The tree command prints the new command to use.
