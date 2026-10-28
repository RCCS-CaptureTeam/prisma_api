# Bringing a dataset folder to PrISMa

You have a folder of results (CSV, JSON, YAML), organised your own way. You want them on the PrISMa platform without reorganising anything.

You add one file to the folder, `prisma_manifest.yaml`, which says what each file is and where its data goes. `prisma-dataset` then checks the folder, packs it into one zip, and sends it. The platform checks the whole package before it writes anything.

## 1. Setup (once)

```bash
pip install prisma_api
python -c "import prisma_api; prisma_api.init()"     # asks for your API key (on your platform profile page)
```

## 2. See what the platform can store

```bash
prisma-dataset targets --prod
```

This lists the **targets**, the places data can go. Each target has a kind:

| Kind | What a record is | Needs |
|---|---|---|
| `rows` | one per material (or benchmark), e.g. features | an id column |
| `run_rows` | one per material per **run** (a case or variant of your model), e.g. results | an id column, and a run binding (`run` or `runs_where`) |
| `parameters` | model inputs shared by runs (defaults, prices, indices) | a parameter set and a layout |
| `skip` | nothing: files you deliberately leave out | a `reason` |

Some targets have fixed fields; `targets` prints them with their types and units. Others say **"any names you choose"**: for those you name your columns yourself and give their units. Use these for data the platform has no table for yet.

To work offline, save the list and pass it to `validate`/`pack` later: `prisma-dataset targets --prod --save targets.json`.

## 3. Write the manifest

Put `prisma_manifest.yaml` at the top of your folder. A small example:

```yaml
_schema: prisma.dataset.ingest.v1

dataset:
  slug: co2-screening-2026          # letters, digits, - and _; identifies your dataset
  name: CO2 screening of 1,200 MOFs
  tag: CO2 Screening 2026           # tags everything the package writes; a name or a list of names
  by_others: false                  # true: keep this data out of the platform's Zenodo publications

material_id:
  strip_suffixes: [".cif"]          # "ABC.cif" in a file means material "ABC"
  on_missing: create                # unknown materials: create | skip | error

reference_systems:                  # benchmarks that are not materials
  - {name: Zeolite-13X, kind: adsorbent, aliases: [13X, zeolite_13x]}

runs:                               # one per case / variant your results belong to
  - {key: co2-298K, name: "CO2 at 298 K", conditions: {temperature_K: 298}}
  - {key: co2-313K, name: "CO2 at 313 K", conditions: {temperature_K: 313}}

sources:
  - id: screening
    path: results/{T}K/summary.csv            # {T} captures 298 / 313 ...
    target: run_results                       # a target from 'prisma-dataset targets'
    run: co2-{T}K                             # ... and picks the run
    id_column: structure
    columns:                                  # your column -> stored name
      "CO2 uptake (mmol/g)": co2_uptake
      "Selectivity CO2/N2": selectivity
    units: {co2_uptake: mmol/g}
    ignore_columns: [notes]

  - id: figures
    path: figures/**
    target: skip
    reason: Plots made from the results above.
```

### Sources

Each source matches files with a `path` pattern and sends them to one `target`.

| Key | Meaning |
|---|---|
| `path` | Pattern relative to the folder. `{name}` captures part of a path segment; `*` matches within a segment; `**/` matches any number of folders. |
| `exclude` | A list of patterns to leave out of `path`. |
| `id_column` | The column (or JSON key) naming the material or benchmark. Without it, the platform's default applies (see `targets --json`, under `defaults`). |
| `columns` | Your column name → the target's field name (or your chosen name). |
| `match_field_names: true` | Columns already named like the target's fields map themselves. |
| `json_columns` | Columns holding lists or dicts. JSON and Python-style `{'a': 1}` both work. |
| `ignore_columns` | Columns that are not data (copies, notes, file paths). |
| `units` | For "any names you choose" targets: the units of each name. |
| `run` | A run key, which may use the captured `{names}`, e.g. `case{case}-{variant}`. |
| `runs_where` | Binds the file to every run whose fields match, e.g. `{case: "Case_{case}"}`, when one file serves several runs. |
| `rows: supplement` | Only adds fields to records another source created for the same run. Use it for per-material data you want joined onto each run's results. |
| `by_others` | Overrides `dataset.by_others` for this source's files. |
| `on_bad_value: null` | Store unreadable values as empty instead of failing. |

**Every file needs a home.** Each file in the folder should match a source; deliberate omissions go under `target: skip` with a reason. Every column of a file you read must be mapped or ignored. This means a new column, or a new file, is always noticed instead of silently dropped.

### Runs, benchmarks and parameter sets

- **`runs`**: `key` (letters, digits, `-`, `_`), `name`, optional `case`, `conditions` (any key: value pairs, e.g. temperature, cycles, pressure), `description`, and `parameter_set`.
- **`reference_systems`**: benchmarks that are not catalogue materials (a compressed-gas tank, a reference adsorbent). `kind` is one of the values listed by `targets --json` (`reference_system_kinds`). `aliases` lists every other spelling your files use.
- **`parameter_sets`**: `key`, `name`, `description`. Parameter sources then give:
  - `parameter_set`
  - `category`
  - `layout`, one of:
    - `mapping`: a flat YAML `name: value  # units`
    - `records`: a list of Name/Value/Units/Reference/Description, under `records_key`
    - `table`: a CSV with a `key_column` such as Year

## 4. Choose the files on the platform

```bash
prisma-dataset tree . --prod --dataset <slug> --tag "<tag>"   # the first time: the dataset page gives this command
prisma-dataset tree . --prod                                  # later: refresh the dataset's tree, keeping its ticks
```

This sends only the folder structure: each file's path and size. No file contents, zip or manifest are sent. The dataset must already exist on the platform; create it on the web portal first if it doesn't. A tag already used by another dataset is refused, since its records would show in both.

The listing always leaves out `.git` and cache folders and anything named `*.claude`, `*.venv` or `*.DS_Store` (folders or files), even if `.gitignore` doesn't list them, and whatever the folder's `.gitignore` files match. No other ignore file counts.

The command prints a link to the dataset's page. There, **View folder tree** opens the folder, with two checkboxes per file:

- **In dataset:** only ticked files are packed and sent. Every file starts unticked.
- **By others:** the data is not yours to republish, so it stays out of the platform's Zenodo publications.

Ticks save as you click.

## 5. Build the manifest and send, with Claude Code

The folder tree on the platform shows a command for Claude Code above it. In your folder:

```bash
prisma-dataset install-skill .      # once
claude                              # then paste the command, e.g.:
/prisma-dataset co2-screening-2026 --tag "CO2 Screening 2026" --prod
```

Claude lists the ticked files (`prisma-dataset ticked . --prod --dataset <slug>`) and writes or updates `prisma_manifest.yaml` for them, using that slug and tag. It then checks the manifest with the platform's dry run until it is clean, summarises what would be written, and sends the data once you say yes.

## 6. Check, pack, send by hand

```bash
prisma-dataset send . --prod --package <id>
```

`send` validates and packs the ticked files, asks the platform for a dry run, prints the report and asks before writing (`--apply` writes without asking). It does the steps below in one go:

```bash
prisma-dataset validate . --prod                   # local check of the ticked files against the platform's targets
prisma-dataset pack . --prod --out ../my_dataset.zip   # only the ticked files; write the zip next to the folder
prisma-dataset upload ../my_dataset.zip --prod     # DRY RUN: the platform checks everything, writes nothing
```

`pack` uses the dataset's latest tree. To choose another tree, use `--package <id>`; to ignore the ticks and pack every file the manifest reads, use `--all-files`. The zip records which tree it came from, so the upload joins that tree on the platform.

When files change, send the tree again with `prisma-dataset tree . --prod --package <id>`. Your ticks are kept, and new files start unticked.

The dry run's report lists every problem at once, then the records it *would* create, update or delete per table and per run. Fix and repeat until it says `OK` and the counts look right.

**Tags.** The platform tags every record the package writes with the names in `dataset.tag`: the materials, your runs, benchmarks and parameter sets. Platform datasets and searches group records by these tags. You can add more names when packing or sending, without editing the manifest: `--tag "Name"` on `pack` (written into the zip) or on `upload` (this upload only). Both are repeatable.

`pack` adds your folder's git commit to the package (if it is a git repository) and checksums every file it packs. It also lists the whole folder, so platform staff can see what was left out and why.

Writing is `upload ... --apply`. It is all or nothing: one error and nothing is written.

Re-sending a newer version of the same dataset updates it:
- Records that changed are updated.
- Records missing from the new package are removed from the runs.

**Versions.** If an upload changes records, the dataset goes up a minor version (1.0 → 1.1); an upload that changes nothing leaves the version as it is. If you resend the tree with files added or removed after data was sent, the platform makes a new major version, `<slug>-v2` at 2.0 and tagged `"<tag> v2"`, and later uploads go to it. The manifest may keep the original slug. Each version records what its upload changed. `prisma-dataset versions <slug> --prod` lists them; the dry run reports the version an upload would make.

Ask the platform team before your first `--apply`.
