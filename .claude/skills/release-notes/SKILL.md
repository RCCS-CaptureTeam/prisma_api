---
name: release-notes
description: Write or extend plain-language release notes for the prisma_api Python client, for a minor release series (`/release-notes v0.4.x`) or for one patch tag (`/release-notes v0.4.7`), including a tag that is about to be released (commits since the latest tag plus uncommitted changes). Only genuine GitHub releases (and tags newer than the latest release) get notes; historical tags without a release are skipped and folded into the next release. Keeps one Markdown doc per minor release (docs/release_notes/v0.4.x.md) with an H1 per patch tag, the release edit link under each H1, H3 themed sections grouped by the client's endpoint sets (v2 case studies, flowsheets, AutoPrism, materials & CIFs, adsorption data, TEA/LCA, PSDI, v1 client, setup, …) of up to 5 bullets each, and a GitHub compare link per patch. Only patches missing from the docs are written, including any released since the notes were last updated. Use when asked for release notes, a release summary or a changelog for a version series or an upcoming release.
argument-hint: v0.4.x | v0.4.7
---

# Release notes for a prisma_api minor release series

prisma_api is the Python client for the PrISMa platform REST API. It has two
method sets:

- **v1** (`api.*`, [prisma_api/prisma_api.py](../../../prisma_api/prisma_api.py),
  [API_REFERENCE_V1.md](../../../API_REFERENCE_V1.md)): the original client,
  now largely legacy and being deprecated in favour of v2.
- **v2** (`api.v2.*`, [prisma_api/prisma_api_v2.py](../../../prisma_api/prisma_api_v2.py),
  [API_REFERENCE_V2.md](../../../API_REFERENCE_V2.md)): the current client,
  organised into endpoint sets (flowsheets, catalog, science data, AutoPrism
  tables, TEA/LCA, cases & scenarios, case-study library, bundles, case packs).

Each tag is published to PyPI by `.github/workflows/publish.yml` when its
GitHub release is published, so the notes are read by people who
`pip install prisma_api`: researchers pulling data and contributors uploading
it (e.g. AutoPrism runs). Write for them.

**Argument:** either

- a minor release such as `v0.4.x` (also accepts `v0.4` or `0.4`), or
- a patch tag such as `v0.4.7`. If that tag doesn't exist yet and is newer
  than the latest tag, it is the **upcoming release**, assumed to be about to
  be tagged. Its notes cover the commits since the latest tag **plus the
  uncommitted changes in the working tree**.

If none is given, ask which series or tag, or use the series of the latest
tag (`git tag --sort=-v:refname | head -1`).

**Output:** `docs/release_notes/v<major>.<minor>.x.md`. There is one doc per
minor release. Create it (and the folder) if it doesn't exist.

## 1. Find the missing patches

```bash
python3 .claude/skills/release-notes/releases.py plan <argument>   # e.g. v0.4.x or v0.4.7
```

**Only genuine releases count.** Some older tags never got a GitHub release
(e.g. `v0.2.5`). `plan` reads the published (non-draft) releases from the
GitHub API, so it needs network access. Set `GITHUB_TOKEN` if the API is
rate-limited. A tag counts as a release if either:

- it has a published GitHub release, or
- it is newer than the latest GitHub release. Such tags are assumed to be
  about to become releases. `plan` marks them "no GitHub release yet,
  assumed to become one".

Tags older than the latest release that have no release are **historical**.
They are skipped: they get no heading and no compare link of their own. Their
commits fall into the next release's range, and `plan` lists them under that
release as "includes historical tag(s) without a release".

`plan` lists the releases in the series, the skipped historical tags, and the
newest tag documented in any release-notes doc. A release is **missing** if
either:

- it is in the named series (up to the named tag, if one was given) and has
  no `# vX.Y.Z` heading, or
- it is newer than the newest documented tag, in any series. These are
  releases missed since the notes were last updated, and each is listed with
  the doc it belongs in (`docs/release_notes/v<major>.<minor>.x.md`).

For each missing release, and for the upcoming tag, `plan` prints:

- the release date. This is the tag date, because some GitHub releases were
  published long after the tag. When they differ, the publish date is shown
  too; write the tag date in the notes,
- the release edit URL (`https://github.com/RCCS-CaptureTeam/prisma_api/releases/edit/<tag>`),
- the compare URL (previous **release** → this release, skipping historical
  tags, e.g. `v0.2.4...v0.2.6`; the first patch compares against the last
  release of the previous minor, e.g. `v0.3.10...v0.4.0`),
- the commits in that range. Under each commit it prints the **areas** it
  touched (`v1`, `v2`, `config`, `package`, `docs`, `examples`,
  `integration`, `tests`, `ci`, `packaging`, `agent`, `other`) and any public
  client methods it added (`new: api.v2.upsert_autoprism_cifs`) or removed
  (`removed: api.update_isotherm_h2`). Use these as hints for themes.

For the **upcoming** tag, the range is latest tag → `HEAD`, the date is
today's, and the compare URL works once the tag is pushed. It also lists
every uncommitted path (`git status --porcelain`: modified, staged and
untracked) with the same area/method summary. Read those changes with
`git diff HEAD -- <path>`, or open the untracked files, and describe them
alongside the commits. These are read-only git commands; never stage,
commit or tag anything.

If nothing is missing and there is no upcoming tag, say so and stop. Don't
rewrite sections that already exist unless the user asks.

## 2. Understand each missing patch

- Read the commit subjects first. When a subject is vague, or the patch is
  small and needs more detail, use `git show --stat <sha>` (and the diff when
  needed) to see what changed for users.
- The diff to `API_REFERENCE_V1.md` / `API_REFERENCE_V2.md` is usually the
  quickest way to see what a user-facing change looks like (new signatures,
  parameters, return shapes, deprecations).
- Watch for changes users must act on: renamed or removed methods, changed
  defaults, deprecations (`DeprecationWarning`), new exceptions or warnings
  (`PrismaUpsertError`, `PrismaRowErrorWarning`, …), and new config or env
  vars. These always get a bullet.
- Ignore pure housekeeping: version bumps, merges, typo fixes, tests-only,
  dev cross-check scripts in `tests/`, and agent/skill files. Mention
  examples, notebooks, docs or CI only when they matter to someone using the
  package (e.g. a new demo notebook, a rewritten API reference).
- For large ranges (more than about 40 commits), you can hand them out to
  subagents in parallel, one patch each, and have each return draft bullets
  grouped by theme.

## 3. Write the sections

Put each patch under an H1 heading, with the release edit link on its own
line directly below it. Themes are H3. Each section ends with the changelog
block. Keep sections **newest first**.

```markdown
# v0.4.5

https://github.com/RCCS-CaptureTeam/prisma_api/releases/edit/v0.4.5

_Released 2026-10-06_

### AutoPrism

- CIF files from AutoPrism runs can now be uploaded directly, and collection uploads send their CIFs along automatically (`api.v2.upsert_autoprism_cifs`)
- AutoPrism lookups can match names exactly instead of partially (`match="exact"`)

### Adsorption & property data

- Hydrogen isotherms now live in the general adsorption isotherm table, so one method reads and writes all isotherm data (`api.v2.get_adsorption_isotherm`, `upsert_adsorption_isotherm`)
- Deprecated: the separate hydrogen isotherm methods still work but now warn; switch to the adsorption isotherm methods (`api.v2.*_isotherm_h2*`)

## Changelog

- https://github.com/RCCS-CaptureTeam/prisma_api/compare/v0.4.4...v0.4.5
```

**Themes.** Choose them from what changed. Use only the themes that apply to
that patch, in this order. The v2 themes follow the endpoint sets in
`API_REFERENCE_V2.md`:

| Theme (H3) | What belongs there |
|---|---|
| Case studies & scenarios | `get_cases`, `get_scenarios`, `list_case_studies`, screening summaries/analysis bundles, case-study library sync (`*case_study_library*`), case packs (`build_case_spec`, `build_case_pack`, `list_case_packs`), `get_cases_bundle` |
| Flowsheets | `get_flowsheet`, `get_flowsheet_bundle`, `upsert_flowsheets` |
| AutoPrism | `upsert_autoprism_collection`, `get_autoprism_collection`, `upsert_autoprism_cifs`, AutoPrism provenance (`meta_provenance`, `repo_dir`) and row-rejection handling |
| Materials & structures | `list_materials`, `get_material`, `preflight_material_check`, CIFs (`list_cifs`, `get_cifs`), material bundles (`get_material_bundle(s)`, `upsert_material_bundles`, `get_material_property_bundle`) |
| Adsorption & property data | isotherms (`get_isotherm`, `*adsorption_isotherm*`, `*isotherm_h2*`), single-point adsorption, heat capacity, water KPIs, zeo++ metrics, mofchecker, computation runs, carbon zeo++ tables |
| TEA / LCA data | output KPIs, region costs, ambient parameters, equipment (costs, designs), process/contactor configurations, cost indices, constants, MEA baselines/KPIs |
| Reference catalog | molecules, elements, regions, sources, sinks, scopes, transports, transport scenarios, utilities, references, subsystems, properties |
| PSDI | `get_materials_psdi`, `get_material_psdi` and other PSDI-facing endpoints |
| v1 client | anything under `api.*` (not `api.v2`): `get_materials_data`, `get_carbon_*`, `update_*` uploads, and their deprecations |
| Setup & configuration | `init()`, `config.yaml` / env-var fallback, dev vs production targets, `return_format`, timeouts, pagination, exceptions and warnings exported from `prisma_api` |
| Docs & examples | API references, README, user guide, demo scripts and notebooks in `examples/` (only when users would benefit) |
| Packaging | Python/dependency requirements, PyPI publishing, install changes (only items users would notice) |

You may add a new theme if a patch clearly needs one (e.g. a new endpoint set
in `API_REFERENCE_V2.md`). Keep theme names consistent across the whole doc.
A change that adds an upload method to an existing data table belongs with
that table's theme, not with AutoPrism, unless it is AutoPrism-specific.

**Bullets.**

- At most **5 per theme**. Merge related commits into one bullet rather than
  listing each commit.
- Say what users can now do or what got better, in plain words, not how it
  was built.
- End with the relevant method names in brackets, in backticks, e.g.
  `` (`api.v2.get_material_bundles`) ``. Use the full `api.` / `api.v2.`
  prefix for the first method in a bullet so v1 and v2 are never confused.
  Keep the bracket short: at most about three names, or a pattern such as
  `` `api.v2.upsert_*` ``.
- Flag breaking changes and deprecations clearly at the start of the bullet,
  e.g. "**Breaking:** …" or "Deprecated: …", and say what to use instead.
- Each bullet is one line, with no full stop at the end.
- Don't include commit hashes, author names or internal ticket jargon.

If a patch has only housekeeping commits, write one theme
`### Maintenance` with a single bullet such as "Version bump and internal
tidy-up, with no user-facing changes".

**Changelog block.** Every patch section ends with exactly:

```markdown
## Changelog

- https://github.com/RCCS-CaptureTeam/prisma_api/compare/<prev>...<tag>
```

Use the compare URL from the `plan` output exactly as printed. It runs from
the previous genuine release, never from a historical tag. The very first
release (`v0.2.0`) has nothing before it, so it has no changelog block.

**New doc.** Start it with one HTML comment line (no title heading, because
versions are the H1s):

```markdown
<!-- Release notes for prisma_api v0.4.x: one section per patch, newest first. Maintained by the release-notes skill. -->
```

## 4. Insert and validate

Add each new section to its series doc. Position doesn't matter, because the
check step sorts them. Then run the check that `plan` printed for each doc
touched, for example:

```bash
python3 .claude/skills/release-notes/releases.py check v0.4.x
python3 .claude/skills/release-notes/releases.py check v0.4.7   # the doc holding the upcoming tag
```

Check the doc holding the upcoming release with the tag itself. Otherwise its
heading fails as "no such git tag".

This reorders the H1 sections newest-first and adds the release edit link
under any H1 that lacks one. It reports a `PROBLEM:` for any of the
following: an edit link for the wrong tag, a wrong or missing changelog URL,
more than 5 bullets in a theme, a heading that isn't a real tag, or a heading
for a historical tag with no release. For a historical tag, remove its section
and fold its changes into the next release. Fix every problem and re-run until
it is clean.

## 5. Report

Tell the user which patches were added and the doc paths. Say which sections
were missed releases, and, for an upcoming release, that its notes include
uncommitted changes and should be re-checked if more changes land before
tagging. The notes can be pasted into the GitHub release body via the edit
link. Don't commit, tag or publish a release unless asked.
