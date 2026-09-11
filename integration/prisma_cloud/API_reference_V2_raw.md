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
- GET, PUT /api/v2/isotherm-h2/
- GET /api/v2/isotherm-h2/{row_id}/
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
  - upsert lookup key: (structure, md5, mixture_id, component, temperature_K, pressure_bar)
- GET /api/v2/heat-capacity/
  - structure, temperature_K, limit, offset
- PUT /api/v2/heat-capacity/
  - accepts object or list
  - upsert lookup key: (structure, temperature_K)
- GET /api/v2/isotherm-h2/
  - structure, isotherm_id, component, temperature_K, pressure_bar, limit, offset
- PUT /api/v2/isotherm-h2/
  - accepts object or list
  - upsert lookup key: (structure, md5, isotherm_id, component, temperature_K, pressure_bar)
- GET /api/v2/mofchecker/
  - structure, md5, is_mof, MOFQ, limit, offset
- PUT /api/v2/mofchecker/
  - accepts object or list
  - upsert lookup key: (structure, md5)
- GET /api/v2/zeopp-metrics/
  - mof, md5, probe, limit, offset
- PUT /api/v2/zeopp-metrics/
  - accepts object or list
  - upsert lookup key: (mof, md5, probe)

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
- 2026-09-09: Added AutoPrism table endpoints (adsorption-singlepoint, heat-capacity, isotherm-h2, mofchecker, zeopp-metrics).
- 2026-09-09: Added authenticated PUT upsert support for AutoPrism table list endpoints.
