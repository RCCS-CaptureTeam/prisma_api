# API Reference V2 (Raw)

This document is the raw, repo-local reference for the Django PrISMa v2 API surface implemented in prisma_cloud/api_v2.py and wired in prisma_cloud/urls.py.

It is intentionally separate from any wrapper-package documentation that may use the API_reference_V2.md filename.

## Scope

- API base path: /api/v2/
- Authentication: required on all endpoints via X-API-Key (API key auth)
- Primary implementation: prisma_cloud/api_v2.py
- URL wiring: prisma_cloud/urls.py

## Shared Behavior

### Error Mapping

- 404: lookup-style failures (LookupError, KeyError, FileNotFoundError)
- 400: invalid client input (ValueError)
- 501: not implemented
- 500: unhandled server errors

### List Envelope

Most list endpoints return:

- count: integer
- results: array

Many also include:

- offset: integer
- limit: integer

### Pagination

Where supported, query params are:

- limit
- offset

Default limit is typically 500 unless endpoint code states otherwise.

### Upsert Endpoints

Endpoints that support PUT return:

- created: integer
- updated: integer
- errors: array (only present if needed)

## Endpoint Index

## Health

- GET /api/v2/health/

## Catalog: Materials and Chemistry

- GET /api/v2/materials/
- GET /api/v2/materials/{material_id}/
- GET /api/v2/materials/{material_id}/bundle/
- GET,POST /api/v2/materials/bundle/
- PUT,POST /api/v2/materials/bundle/upsert/
- GET /api/v2/materials-psdi/
- GET /api/v2/materials-psdi/{material_id}/
- GET /api/v2/cifs/
- GET /api/v2/cifs/files/
- GET /api/v2/molecules/
- GET /api/v2/molecules/{molecule_id}/
- GET /api/v2/elements/
- GET /api/v2/elements/{element_id}/

## Catalog: Geography and Context

- GET /api/v2/regions/
- GET /api/v2/regions/{region_id}/
- GET, PUT /api/v2/region-costs/
- GET /api/v2/region-costs/{rc_id}/
- GET /api/v2/sources/
- GET /api/v2/sources/{source_id}/
- GET /api/v2/sinks/
- GET /api/v2/sinks/{sink_id}/
- GET /api/v2/transport-scenarios/
- GET /api/v2/transport-scenarios/{ts_id}/
- GET /api/v2/utilities/
- GET /api/v2/utilities/{utility_id}/
- GET /api/v2/references/
- GET /api/v2/references/{ref_id}/

## Science Data

- GET /api/v2/isotherms/
- GET /api/v2/water-kpis/
- GET /api/v2/carbon-zeopp/
- GET /api/v2/carbon-zeopp/{zeopp_id}/
- GET /api/v2/carbon-zeopp-experimental/
- GET /api/v2/carbon-zeopp-experimental/{zeopp_id}/

## AutoPrism Tables

- GET, PUT /api/v2/computation-runs/
- GET /api/v2/computation-runs/{run_id}/
- GET, PUT /api/v2/adsorption-singlepoint/
- GET /api/v2/adsorption-singlepoint/{row_id}/
- GET, PUT /api/v2/heat-capacity/
- GET /api/v2/heat-capacity/{row_id}/
- GET, PUT /api/v2/isotherm-h2/ (deprecated alias of adsorption-isotherm, component H2)
- GET /api/v2/isotherm-h2/{row_id}/ (deprecated; adsorption-isotherm ids)
- GET, PUT /api/v2/adsorption-isotherm/
- GET /api/v2/adsorption-isotherm/{row_id}/
- GET, PUT /api/v2/mofchecker/
- GET /api/v2/mofchecker/{row_id}/
- GET, PUT /api/v2/zeopp-metrics/
- GET /api/v2/zeopp-metrics/{row_id}/

## TEA and LCA

- GET, PUT /api/v2/output-kpis/
- GET /api/v2/output-kpis/{kpi_id}/
- GET, PUT /api/v2/ambient-parameters/
- GET /api/v2/ambient-parameters/{ap_id}/
- GET /api/v2/cost-indices/
- GET /api/v2/cost-indices/{ci_id}/
- GET /api/v2/constants/
- GET /api/v2/constants/{const_id}/
- GET /api/v2/mea/
- GET /api/v2/mea/{mea_id}/
- GET /api/v2/mea-kpis/
- GET /api/v2/mea-kpis/{kpi_id}/
- GET /api/v2/screening-summaries/
- GET /api/v2/screening-summaries/{summary_id}/

## Cases, Scenarios, and Scope

- GET /api/v2/case-studies/
- GET /api/v2/cases/
- GET /api/v2/cases/{case_id}/
- GET /api/v2/scenarios/
- GET /api/v2/scenarios/{scenario_id}/
- GET /api/v2/scopes/
- GET /api/v2/scopes/{scope_id}/
- GET /api/v2/screening-analyses/{analysis_id}/bundle/

## Process and Flowsheets

- GET /api/v2/subsystems/
- GET /api/v2/subsystems/{subsystem_id}/
- GET /api/v2/properties/
- GET /api/v2/properties/{property_id}/
- GET /api/v2/equipment/
- GET /api/v2/equipment/{equip_id}/
- GET /api/v2/equipment-costs/
- GET /api/v2/equipment-costs/{cost_id}/
- GET /api/v2/equipment-designs/
- GET /api/v2/equipment-designs/{design_id}/
- GET /api/v2/process-conditions/
- GET /api/v2/process-conditions/{cond_id}/
- GET /api/v2/process-configurations/
- GET /api/v2/process-configurations/{config_id}/
- GET /api/v2/contactor-configurations/
- GET /api/v2/contactor-configurations/{config_id}/
- PUT /api/v2/flowsheets/upsert/
- GET /api/v2/flowsheets/{template_id}/
- GET /api/v2/flowsheets/{template_id}/bundle/
- GET /api/v2/transports/
- GET /api/v2/transports/{transport_id}/

## Sync Utilities

- GET /api/v2/table-timestamps/

## Query Parameters by Endpoint

Below are the key filters exposed in api_v2.py docstrings and implementation.

### Materials

- GET /api/v2/materials/
  - name, limit, offset
- GET /api/v2/materials-psdi/
  - name, limit, offset
- GET /api/v2/materials/{material_id}/bundle/
  - sections, exclude, include_cif_content
- GET,POST /api/v2/materials/bundle/
  - ids, names, match, sections, exclude, include_cif_content, output
- PUT,POST /api/v2/materials/bundle/upsert/
  - create_materials

### CIFs

- GET /api/v2/cifs/
  - mof, tag, primary, limit, offset
- GET /api/v2/cifs/files/
  - ids, zip_name

### Core Catalog

- GET /api/v2/molecules/
  - name, limit, offset
- GET /api/v2/elements/
  - symbol, name, limit, offset
- GET /api/v2/regions/
  - code, name, limit, offset
- GET /api/v2/region-costs/
  - region, name, year, limit, offset
- GET /api/v2/sources/
  - name, limit, offset
- GET /api/v2/sinks/
  - name, limit, offset
- GET /api/v2/transport-scenarios/
  - name, limit, offset
- GET /api/v2/utilities/
  - name, utility_type, limit, offset
- GET /api/v2/references/
  - name, doi, year, limit, offset

### Science Data

- GET /api/v2/isotherms/
  - mof, molecule, sim_or_exp, good_structure, limit, offset
- GET /api/v2/water-kpis/
  - mof, molecule, source, sim_or_exp, good_structure, limit, offset
- GET /api/v2/carbon-zeopp/
  - mof, good_structure, limit, offset
- GET /api/v2/carbon-zeopp-experimental/
  - mof, round, limit, offset

### AutoPrism Tables

- GET /api/v2/computation-runs/
  - workflow_id, step, status, limit, offset
- PUT /api/v2/computation-runs/
  - accepts object or list
  - upsert lookup key: (id)
- GET /api/v2/adsorption-singlepoint/
  - structure, md5, mixture_id, component, limit, offset
- PUT /api/v2/adsorption-singlepoint/
  - accepts object or list
  - upsert lookup key: (structure, md5, mixture, config, component, temperature_K, pressure_bar)
- GET /api/v2/heat-capacity/
  - structure, temperature_K, temperature_C, limit, offset
- PUT /api/v2/heat-capacity/
  - accepts object or list
  - upsert lookup key: (structure, md5, temperature_K); structure required to match
- GET /api/v2/isotherm-h2/ (deprecated)
  - structure, md5, isotherm_id, temperature_K, pressure_bar, limit, offset
  - returns the component-H2 rows of adsorption_isotherm
- PUT /api/v2/isotherm-h2/ (deprecated)
  - accepts object or list; writes adsorption_isotherm
  - component defaults to H2; any other gas is rejected
  - upsert lookup key: as adsorption-isotherm
- GET /api/v2/adsorption-isotherm/
  - structure, md5, isotherm_id, component (exact), temperature_K, pressure_bar, limit, offset
- PUT /api/v2/adsorption-isotherm/
  - accepts object or list; isotherms for every gas, H2 included
  - component required
  - upsert lookup key: (structure, md5, isotherm_id, config, component, temperature_K, pressure_bar)
- GET /api/v2/mofchecker/
  - structure, md5, is_mof, MOFQ, limit, offset
- PUT /api/v2/mofchecker/
  - accepts object or list
  - upsert lookup key: (structure, md5)
- GET /api/v2/zeopp-metrics/
  - mof, md5, probe, limit, offset
- PUT /api/v2/zeopp-metrics/
  - accepts object or list
  - upsert lookup key: (mof, md5, probe, scale)

AutoPrism GET name filters (`structure`, or `mof` on zeopp-metrics) are
case-insensitive substring matches by default, so `structure=LAGNAK` also
returns `LAGNAK_clean`. Add `match=exact` for an exact (case-insensitive)
match; any other `match` value is a 400.

AutoPrism upsert rules (all six tables above except computation-runs):

- One row per configuration: a new `config`, zeo++ `scale` or CIF `md5`
  adds a row rather than replacing the earlier result.
- Key fields absent from a row are not used for matching; if more than one
  stored row then matches, the row is rejected as ambiguous.
- `structure` matches a MOF pk or an exact name (`LAGNAK` and `LAGNAK_clean`
  are different MOFs); an unknown name creates a MOF.
- `mixture` / `config` accept `{"id": ...}`, or without an id
  `{"mixture_id": ...}` / `{"config_hash": ...}` and the flat
  `mixture_id` / `config_hash` fields: matched by value, or created with an
  id derived from the value.
- Response: `created`, `updated`, plus `errors`, `unknown_fields`
  (`{field: row_count}` for payload keys not stored; `meta_provenance` is
  always accepted) and `new_structures` (MOF names created) when non-empty.
- Status: 200 all rows stored, 207 partial success, 400 no row stored. The
  400 rule applies to every v2 upsert endpoint.
- mofchecker rows carry the formal-charge checks
  (`positive_charge_from_linkers`, `negative_charge_from_linkers`,
  `linker_formal_charge`, `implied_metal_oxidation_sum`,
  `implied_metal_oxidation_per_metal`, `formal_charge_plausible`,
  `formal_charge_reason`, `has_high_charges`, `cif_net_atom_site_charge`,
  `cif_charge_neutral`).

### TEA and LCA

- GET /api/v2/output-kpis/
  - scenario_id, mof, good_structure, limit, offset
- PUT /api/v2/output-kpis/
  - accepts object or list
- GET /api/v2/ambient-parameters/
  - name, limit, offset
- PUT /api/v2/ambient-parameters/
  - accepts object or list
- GET /api/v2/cost-indices/
  - year, limit, offset
- GET /api/v2/constants/
  - param, limit, offset
- GET /api/v2/mea/
  - name, limit, offset
- GET /api/v2/mea-kpis/
  - name, category, limit, offset
- GET /api/v2/screening-summaries/
  - scenario_id, limit, offset

### Cases, Scenarios, Scope

- GET /api/v2/case-studies/
  - name
- GET /api/v2/cases/
  - source, sink, region, study, limit, offset
- GET /api/v2/scenarios/
  - case_id, name, type, limit, offset
- GET /api/v2/scopes/
  - analysis_id, case_study_id, name, limit, offset
- GET /api/v2/screening-analyses/{analysis_id}/bundle/
  - no query params

### Process and Flowsheets

- GET /api/v2/subsystems/
  - name, subsystem_type, limit, offset
- GET /api/v2/properties/
  - content_type, object_id, name, category, domain, limit, offset
- GET /api/v2/equipment/
  - name, group, limit, offset
- GET /api/v2/equipment-costs/
  - equipment, limit, offset
- GET /api/v2/equipment-designs/
  - equipment, key, limit, offset
- GET /api/v2/process-conditions/
  - name, conditions_type, limit, offset
- GET /api/v2/process-configurations/
  - name, process_type, limit, offset
- GET /api/v2/contactor-configurations/
  - name, contactor_type, limit, offset
- GET /api/v2/transports/
  - name, limit, offset
- PUT /api/v2/flowsheets/upsert/
  - accepts object or list

## Material Bundle Payload Notes

One call returning every per-material record the dataset page draws on, so a
client does not have to fan out across the per-table endpoints.

`GET /api/v2/materials/{material_id}/bundle/` returns `_schema`,
`sections`, `material` (the extended materials-psdi representation),
`counts`, and one key per section:

- cifs
- isotherms
- water_kpis
- carbon_zeopp
- carbon_zeopp_experimental
- adsorption_singlepoint
- heat_capacity
- isotherm_h2 (deprecated: the H2 rows of adsorption_isotherm, repeated)
- adsorption_isotherm (all gases)
- mofchecker
- zeopp_metrics
- mof_h2 (single object or null, not a list)
- h2_results

Sections can be narrowed with `sections=` or trimmed with `exclude=`; an
unknown name is a 400. `include_cif_content=true` adds a `content` key with
the raw CIF text to each row in `cifs` (off by default, since it dominates the
response size).

`GET,POST /api/v2/materials/bundle/` is the bulk form, selected by `ids=`
and/or `names=` (repeated or comma-separated; `match=contains` switches names
from exact to substring). It returns `count`, `missing` (requested ids/names
that matched nothing), `sections`, and `results` — a list of the same bundle
objects. A request matching more than 200 materials is rejected with a 400
rather than silently truncated.

`output=zip` returns the same data as a downloadable archive: one
`<material name>.json` per material plus a `manifest.json` listing ids, names,
filenames and per-section counts. The switch is spelled `output` rather than
`format` because DRF reserves `?format=` for content negotiation; the POST
body accepts either key.

Sections are fetched one query per table for the whole material set, so the
query count is flat (~15) whether the request covers one material or 200.

## Material Bundle Upsert Notes

`PUT,POST /api/v2/materials/bundle/upsert/` is the write counterpart of the
bundle read routes. It accepts one bundle object or a list of them in the same
shape the read route returns, so a bundle can be fetched, edited and posted
back unchanged.

Writable sections: `material`, `cifs`, `isotherms`, `water_kpis`,
`carbon_zeopp`, `carbon_zeopp_experimental`, `zeopp_metrics`, `mof_h2`,
`h2_results`.

Read-only here: `adsorption_singlepoint`, `heat_capacity`, `isotherm_h2`,
`adsorption_isotherm`, `mofchecker`. These have dedicated PUT endpoints whose nested
run/result/config payloads the bundle does not reproduce; sending them returns
an error naming the endpoint to use instead.

Row matching, in order:

1. an `id` on the row updates that row — and must belong to the bundle's
   material, otherwise the whole bundle is rejected;
2. otherwise the section's natural key is matched;
3. otherwise a row is created.

Natural keys: isotherms `(MOF, Molecule, sim_or_exp, T_ref_K)`; water_kpis
`(MOF, Molecule, source, sim_or_exp, mof_ref)`; carbon_zeopp and
carbon_zeopp_experimental `(MOF, Molecule, mof_ref, Round)`; zeopp_metrics
`(mof, md5, probe, scale)`; h2_results `(mof_h2, case_study_h2)`. CIFs have no natural
key and match on the stored file name instead. `mof_h2` is the single row
behind `MOF.mof_h2`, so it needs no key.

Rows are never deleted — this is upsert only. Removing a row needs the admin
or a per-table endpoint.

FK fields accept the name strings a read bundle carries (`molecule`, `source`)
or raw pks. Names must already exist; an unknown one is an error rather than a
silent create. `tags` accept names or ids (the read bundle emits both shapes
depending on section) and must already exist. Tag names match exactly first,
then case-insensitively (`AutoPrism` finds `autoprism`); a name matching
several tags that differ only in case is an error.

CIF file content arrives two ways:

- inline — `"content": "data_...\n..."` on the CIF row, which is exactly what
  `GET ...?include_cif_content=true` returns;
- upload — `multipart/form-data` with the JSON document in a `bundle` form
  field and `"file": "<part name>"` on the CIF row.

The two are mutually exclusive on one row. CIF storage is keyed by file
name, so re-sending the same file name updates the existing row and replaces
its file, **unless** that stored file is also used by another CIF row or by
another material's `MOF.cif_file`. Then different content is rejected
("refusing to overwrite") and the bundle rolls back; identical content is
accepted unchanged. Upload a different file under a distinct name, e.g.
`{name}__{source}_{checksum}.cif`. A material with no primary CIF
(`MOF.cif_file` empty, e.g. one created by this upload) adopts the uploaded
file as its primary CIF; an existing primary CIF is never replaced.

`create_materials=false` makes an unknown material an error instead of
creating it.

Each bundle is applied in its own transaction: one bad row rolls that material
back entirely and leaves the other bundles in the request untouched. The
response carries `_schema`, `materials`, `created`/`updated` counts per
section, `results`, and `errors` when any bundle failed — HTTP 200, or 207
when at least one bundle failed.

## Scope Payload Notes

The standalone Scope endpoints use a dedicated serializer and expose:

- id
- name
- description
- screening_analysis_id
- screening_analysis_name
- case_study_id
- case_study_name
- created_by
- created_at
- updated_at
- scope

The screening analysis bundle endpoint also embeds linked Scope rows under:

- analysis.scopes

## Compatibility Notes

- Legacy v1 endpoints under /api/ remain in urls.py and are separate from this reference.
- This file is meant as a source-of-truth inventory for the raw Django API shape in this repository.

## Change Log

- 2026-09-09: Added standalone Scope endpoints to the v2 route inventory.
- 2026-09-21: Added the material bundle endpoints (single and bulk, with zip download).
- 2026-09-21: Added the material bundle upsert endpoint, including CIF file upload.
- 2026-09-09: Added AutoPrism table endpoints (adsorption-singlepoint, heat-capacity, isotherm-h2, mofchecker, zeopp-metrics).
- 2026-09-09: Added authenticated PUT upsert support for AutoPrism table list endpoints.
- Unreleased: `match=exact` on the AutoPrism GET `structure` / `mof` filters (AutoPrism closeout C2).
- Unreleased: bundle upsert refuses to overwrite a stored CIF file shared with other records; materials without a primary CIF adopt the uploaded one; tag names resolve case-insensitively.
- 2026-10-02 (0.6.16): AutoPrism client feedback: added adsorption-isotherm (all gases) and its bundle section, with isotherm-h2 (endpoint, bundle section and v1 update_isotherm_h2) now an alias over it and isotherm_H2 frozen (rows copied by migration 0055); mofchecker formal-charge columns; heat_capacity md5; one-row-per-configuration upsert keys (config, scale, md5) with ambiguity errors; value-based mixture/config matching; `unknown_fields` / `new_structures` in upsert responses; 400 when an upsert stores no rows.
