"""
PrISMa API v2 client wrappers.

Mirrors the v2 REST surface documented in
integration/prisma-v2/prisma_cloud_apis_v2/api_v2_examples.md

All methods authenticate using the same API key as the v1 client.
List endpoints return pandas DataFrames by default; set
``return_format='json'`` for raw list-of-dicts output instead.

Usage:
    import prisma_api
    api = prisma_api.init()        # standard v1 init
    api.v2.get_isotherms(mof='ABEXEM', molecule='CO2')
"""

from __future__ import annotations

import pandas as pd
import requests
from typing import Any


_BASE_PROD = "https://prisma-platform.org/api/v2"


class PrismaAPIv2:
    """
    Thin wrapper around the PrISMa v2 REST endpoints.
    Instantiated automatically as ``api.v2`` by the v1 prisma_api class.
    """

    def __init__(self, key: str, dev: bool = False, dev_host_port: str = "",
                 return_format: str = "json"):
        self._key = key
        self._dev = dev
        self._dev_host_port = dev_host_port
        self._return_format = return_format  # 'dataframe' | 'json'

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        if self._dev:
            return f"http://localhost:{self._dev_host_port}/api/v2"
        return _BASE_PROD

    def set_return_format(self, fmt: str) -> None:
        """
        Set the output format for all list endpoints.

        Args:
            fmt: ``'dataframe'`` (default) — return ``pd.DataFrame``.
                 ``'json'``      — return a plain ``list[dict]``.
        """
        if fmt not in ("dataframe", "json"):
            raise ValueError("return_format must be 'dataframe' or 'json'")
        self._return_format = fmt

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._key,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET request to the v2 API."""
        url = (
            f"http://localhost:{self._dev_host_port}/api/v2{path}"
            if self._dev
            else f"{_BASE_PROD}{path}"
        )
        resp = requests.get(url, params=params, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: list) -> dict:
        """PUT (upsert) request."""
        url = (
            f"http://localhost:{self._dev_host_port}/api/v2{path}"
            if self._dev
            else f"{_BASE_PROD}{path}"
        )
        resp = requests.put(url, json=data, headers=self._headers(), timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _to_df(self, response: Any, key: str = "results") -> "pd.DataFrame | list":
        """Convert a list-endpoint response envelope to a DataFrame or list of dicts."""
        records = response.get(key, response) if isinstance(response, dict) else response
        records = records or []
        if self._return_format == "json":
            return records
        return pd.DataFrame(records) if records else pd.DataFrame()

    def _resolve_cif_url_df(self, data: "pd.DataFrame | list") -> "pd.DataFrame | list":
        """Prepend the base URL to any relative cif_url values in a DataFrame or list of dicts."""
        base = self._base_url().rstrip("/").rsplit("/api/v2", 1)[0]
        if isinstance(data, pd.DataFrame):
            if "cif_url" not in data.columns:
                return data
            data = data.copy()
            data["cif_url"] = data["cif_url"].apply(
                lambda v: f"{base}{v}" if isinstance(v, str) and v.startswith("/") else v
            )
            return data
        # list of dicts
        return [
            {**r, "cif_url": f"{base}{r['cif_url']}"}
            if isinstance(r.get("cif_url"), str) and r["cif_url"].startswith("/")
            else r
            for r in data
        ]

    def _resolve_cif_url_dict(self, d: dict) -> dict:
        """Prepend the base URL to a relative cif_url value in a detail dict."""
        if isinstance(d.get("cif_url"), str) and d["cif_url"].startswith("/"):
            base = self._base_url().rstrip("/").rsplit("/api/v2", 1)[0]
            d = {**d, "cif_url": f"{base}{d['cif_url']}"}
        return d

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """GET /api/v2/health/ — returns status dict."""
        return self._get("/health/")

    # ── Catalog ───────────────────────────────────────────────────────────────

    def get_materials(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/materials/

        Args:
            name:   Case-insensitive substring filter on material name.
            limit:  Max records to return (default 500).
            offset: Pagination offset.

        Returns:
            DataFrame with one row per material.
        """
        params = _compact(name=name, limit=limit, offset=offset)
        return self._resolve_cif_url_df(self._to_df(self._get("/materials/", params)))

    def get_material(self, material_id: int) -> dict:
        """
        GET /api/v2/materials/{material_id}/

        Returns a dict with material detail including element composition.
        """
        return self._resolve_cif_url_dict(self._get(f"/materials/{material_id}/"))

    def get_materials_psdi(self, name: str | None = None,
                           limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/materials-psdi/

        Extended material list including full crystallographic and PSDI fields:
        chemical formulae, SMILES, space group, cell geometry, CIF URL/filename.

        Args:
            name:   Case-insensitive substring filter on material name.
            limit:  Max records to return (default 500).
            offset: Pagination offset.

        Returns:
            DataFrame with one row per material.
        """
        params = _compact(name=name, limit=limit, offset=offset)
        return self._resolve_cif_url_df(self._to_df(self._get("/materials-psdi/", params)))

    def get_material_psdi(self, material_id: int) -> dict:
        """
        GET /api/v2/materials-psdi/{material_id}/

        Full extended MOF record: all crystallographic fields, CIF URL/filename,
        linker/node chemistry (SMILES, formulae, PubChem pipeline outputs),
        and element composition.

        Args:
            material_id: Integer PK of the material.

        Returns:
            dict with all PSDI fields plus nested 'elements' list.
        """
        return self._resolve_cif_url_dict(self._get(f"/materials-psdi/{material_id}/"))

    def get_molecules(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/molecules/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/molecules/", params))

    def get_molecule(self, molecule_id: int) -> dict:
        """GET /api/v2/molecules/{molecule_id}/"""
        return self._get(f"/molecules/{molecule_id}/")

    def get_elements(self, symbol: str | None = None, name: str | None = None,
                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/elements/

        Args:
            symbol: Exact symbol filter (case-insensitive), e.g. 'Fe'.
            name:   Substring filter on element name.
        """
        params = _compact(symbol=symbol, name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/elements/", params))

    def get_element(self, element_id: int) -> dict:
        """GET /api/v2/elements/{element_id}/"""
        return self._get(f"/elements/{element_id}/")

    def get_regions(self, code: str | None = None, name: str | None = None,
                    limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/regions/

        Args:
            code: Exact ISO code filter (case-insensitive), e.g. 'GB'.
            name: Substring filter on region name.
        """
        params = _compact(code=code, name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/regions/", params))

    def get_region(self, region_id: int) -> dict:
        """GET /api/v2/regions/{region_id}/"""
        return self._get(f"/regions/{region_id}/")

    def get_sources(self, name: str | None = None,
                    limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/sources/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/sources/", params))

    def get_source(self, source_id: int) -> dict:
        """GET /api/v2/sources/{source_id}/"""
        return self._get(f"/sources/{source_id}/")

    def get_sinks(self, name: str | None = None,
                  limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/sinks/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/sinks/", params))

    def get_sink(self, sink_id: int) -> dict:
        """GET /api/v2/sinks/{sink_id}/"""
        return self._get(f"/sinks/{sink_id}/")

    def get_transport_scenarios(self, name: str | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/transport-scenarios/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/transport-scenarios/", params))

    def get_transport_scenario(self, ts_id: int) -> dict:
        """GET /api/v2/transport-scenarios/{ts_id}/"""
        return self._get(f"/transport-scenarios/{ts_id}/")

    def get_utilities(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/utilities/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/utilities/", params))

    def get_utility(self, utility_id: int) -> dict:
        """GET /api/v2/utilities/{utility_id}/"""
        return self._get(f"/utilities/{utility_id}/")

    def get_references(self, name: str | None = None, doi: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/references/

        Args:
            name: Substring filter on reference name.
            doi:  Exact DOI filter (case-insensitive).
        """
        params = _compact(name=name, doi=doi, limit=limit, offset=offset)
        return self._to_df(self._get("/references/", params))

    def get_reference(self, ref_id: int) -> dict:
        """GET /api/v2/references/{ref_id}/"""
        return self._get(f"/references/{ref_id}/")

    def get_transports(self, name: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/transports/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/transports/", params))

    def get_transport(self, transport_id: int) -> dict:
        """GET /api/v2/transports/{transport_id}/"""
        return self._get(f"/transports/{transport_id}/")

    def get_subsystems(self, name: str | None = None, type: str | None = None,
                       limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/subsystems/

        Args:
            name: Substring filter on subsystem name.
            type: Exact type filter (e.g. 'dac').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/subsystems/", params))

    def get_subsystem(self, subsystem_id: int) -> dict:
        """GET /api/v2/subsystems/{subsystem_id}/"""
        return self._get(f"/subsystems/{subsystem_id}/")

    def get_equipment(self, name: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/equipment/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/equipment/", params))

    def get_equipment_item(self, equipment_id: int) -> dict:
        """GET /api/v2/equipment/{equipment_id}/"""
        return self._get(f"/equipment/{equipment_id}/")

    def get_properties(self,
                       name: str | None = None,
                       domain: str | None = None,
                       category: str | None = None,
                       object_id: int | None = None,
                       limit: int = 500,
                       offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/properties/

        Args:
            name:      Substring filter on property name.
            domain:    Domain filter (e.g. 'TEA').
            category:  Category filter (e.g. 'params_amb').
            object_id: Exact object PK filter.
        """
        params = _compact(name=name, domain=domain, category=category,
                          object_id=object_id, limit=limit, offset=offset)
        return self._to_df(self._get("/properties/", params))

    def get_property(self, property_id: int) -> dict:
        """GET /api/v2/properties/{property_id}/"""
        return self._get(f"/properties/{property_id}/")

    def get_tea_equipment(self, name: str | None = None, group: str | None = None,
                          limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/tea-equipment/

        Args:
            name:  Substring filter on TEA equipment name.
            group: Exact group filter (e.g. 'Blower').
        """
        params = _compact(name=name, group=group, limit=limit, offset=offset)
        return self._to_df(self._get("/tea-equipment/", params))

    def get_tea_equipment_item(self, tea_equipment_id: int) -> dict:
        """GET /api/v2/tea-equipment/{tea_equipment_id}/"""
        return self._get(f"/tea-equipment/{tea_equipment_id}/")

    def get_tea_equipment_costs(self, equipment_id: int | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/tea-equipment-costs/

        Args:
            equipment_id: Exact TEA equipment PK filter.
        """
        params = _compact(equipment_id=equipment_id, limit=limit, offset=offset)
        return self._to_df(self._get("/tea-equipment-costs/", params))

    def get_tea_equipment_cost(self, cost_id: int) -> dict:
        """GET /api/v2/tea-equipment-costs/{cost_id}/"""
        return self._get(f"/tea-equipment-costs/{cost_id}/")

    def get_tea_equipment_designs(self, equipment_id: int | None = None,
                                  key: str | None = None,
                                  limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/tea-equipment-designs/

        Args:
            equipment_id: Exact TEA equipment PK filter.
            key:          Exact design parameter key filter (e.g. 'D1').
        """
        params = _compact(equipment_id=equipment_id, key=key,
                          limit=limit, offset=offset)
        return self._to_df(self._get("/tea-equipment-designs/", params))

    def get_tea_equipment_design(self, design_id: int) -> dict:
        """GET /api/v2/tea-equipment-designs/{design_id}/"""
        return self._get(f"/tea-equipment-designs/{design_id}/")

    def get_process_conditions(self, name: str | None = None,
                               type: str | None = None,
                               limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/process-conditions/

        Args:
            name: Substring filter on process condition name.
            type: Exact type filter (e.g. 'tvsa').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/process-conditions/", params))

    def get_process_condition(self, condition_id: int) -> dict:
        """GET /api/v2/process-conditions/{condition_id}/"""
        return self._get(f"/process-conditions/{condition_id}/")

    def get_process_configurations(self, name: str | None = None,
                                   type: str | None = None,
                                   limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/process-configurations/

        Args:
            name: Substring filter on process configuration name.
            type: Exact type filter (e.g. 'dac').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/process-configurations/", params))

    def get_process_configuration(self, config_id: int) -> dict:
        """GET /api/v2/process-configurations/{config_id}/"""
        return self._get(f"/process-configurations/{config_id}/")

    def get_contactor_configurations(self, name: str | None = None,
                                     type: str | None = None,
                                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/contactor-configurations/

        Args:
            name: Substring filter on contactor configuration name.
            type: Exact type filter (e.g. 'kiln').
        """
        params = _compact(name=name, type=type, limit=limit, offset=offset)
        return self._to_df(self._get("/contactor-configurations/", params))

    def get_contactor_configuration(self, config_id: int) -> dict:
        """GET /api/v2/contactor-configurations/{config_id}/"""
        return self._get(f"/contactor-configurations/{config_id}/")

    def get_cost_indices(self, year: int | None = None,
                         limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/cost-indices/

        Args:
            year: Exact year filter.
        """
        params = _compact(year=year, limit=limit, offset=offset)
        return self._to_df(self._get("/cost-indices/", params))

    def get_cost_index(self, index_id: int) -> dict:
        """GET /api/v2/cost-indices/{index_id}/"""
        return self._get(f"/cost-indices/{index_id}/")

    def get_constants(self, param: str | None = None,
                      limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/constants/

        Args:
            param: Exact parameter symbol filter (e.g. 'R').
        """
        params = _compact(param=param, limit=limit, offset=offset)
        return self._to_df(self._get("/constants/", params))

    def get_constant(self, constant_id: int) -> dict:
        """GET /api/v2/constants/{constant_id}/"""
        return self._get(f"/constants/{constant_id}/")

    def get_mea_baselines(self, name: str | None = None,
                          limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/mea/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/mea/", params))

    def get_mea_baseline(self, mea_id: int) -> dict:
        """GET /api/v2/mea/{mea_id}/"""
        return self._get(f"/mea/{mea_id}/")

    def get_mea_kpis(self, name: str | None = None, category: str | None = None,
                     limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/mea-kpis/

        Args:
            name:     Substring filter on KPI name.
            category: Exact category filter (e.g. 'CAC').
        """
        params = _compact(name=name, category=category, limit=limit, offset=offset)
        return self._to_df(self._get("/mea-kpis/", params))

    def get_mea_kpi(self, kpi_id: int) -> dict:
        """GET /api/v2/mea-kpis/{kpi_id}/"""
        return self._get(f"/mea-kpis/{kpi_id}/")

    # ── Science data ──────────────────────────────────────────────────────────

    def get_isotherms(self,
                      mof: str | None = None,
                      molecule: str | None = None,
                      temperature_min: float | None = None,
                      temperature_max: float | None = None,
                      sim_or_exp: str | None = None,
                      good_structure: bool | None = None,
                      limit: int = 500,
                      offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/isotherms/

        Args:
            mof:             MOF name substring filter.
            molecule:        Molecule name substring filter.
            temperature_min: Lower bound on T_ref_K [K].
            temperature_max: Upper bound on T_ref_K [K].
            sim_or_exp:      'sim' or 'exp'.
            good_structure:  Filter to good/bad structures.
            limit:           Max records (default 500).
            offset:          Pagination offset.

        Returns:
            DataFrame with one row per isotherm record.
        """
        params = _compact(
            mof=mof, molecule=molecule,
            temperature_min=temperature_min, temperature_max=temperature_max,
            sim_or_exp=sim_or_exp,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/isotherms/", params))

    def get_water_kpis(self,
                       mof: str | None = None,
                       molecule: str | None = None,
                       source: str | None = None,
                       sim_or_exp: str | None = None,
                       good_structure: bool | None = None,
                       limit: int = 500,
                       offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/water-kpis/

        Args:
            mof:            MOF name substring filter.
            molecule:       Molecule name substring filter.
            source:         Source name substring filter.
            sim_or_exp:     'sim' or 'exp'.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            mof=mof, molecule=molecule, source=source,
            sim_or_exp=sim_or_exp,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/water-kpis/", params))

    def get_carbon_zeopp(self,
                         mof: str | None = None,
                         good_structure: bool | None = None,
                         limit: int = 500,
                         offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/carbon-zeopp/

        Simulated Zeo++ geometric characterisation data.

        Args:
            mof:            MOF name substring filter.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            mof=mof,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/carbon-zeopp/", params))

    def get_carbon_zeopp_item(self, item_id: int) -> dict:
        """GET /api/v2/carbon-zeopp/{item_id}/"""
        return self._get(f"/carbon-zeopp/{item_id}/")

    def get_carbon_zeopp_experimental(self,
                                      mof: str | None = None,
                                      limit: int = 500,
                                      offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/carbon-zeopp-experimental/

        Experimental Zeo++ geometric characterisation data.

        Args:
            mof: MOF name substring filter.
        """
        params = _compact(mof=mof, limit=limit, offset=offset)
        return self._to_df(self._get("/carbon-zeopp-experimental/", params))

    def get_carbon_zeopp_experimental_item(self, item_id: int) -> dict:
        """GET /api/v2/carbon-zeopp-experimental/{item_id}/"""
        return self._get(f"/carbon-zeopp-experimental/{item_id}/")

    # ── TEA / LCA data ────────────────────────────────────────────────────────

    def get_output_kpis(self,
                        scenario_id: int | None = None,
                        mof: str | None = None,
                        good_structure: bool | None = None,
                        limit: int = 500,
                        offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/output-kpis/

        Args:
            scenario_id:    Exact scenario PK filter.
            mof:            MOF name substring filter.
            good_structure: Filter to good/bad structures.
        """
        params = _compact(
            scenario_id=scenario_id, mof=mof,
            good_structure=None if good_structure is None else str(good_structure).lower(),
            limit=limit, offset=offset,
        )
        return self._to_df(self._get("/output-kpis/", params))

    def get_output_kpi(self, kpi_id: int) -> dict:
        """GET /api/v2/output-kpis/{kpi_id}/"""
        return self._get(f"/output-kpis/{kpi_id}/")

    def upsert_output_kpis(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/output-kpis/

        Bulk upsert. Lookup key: (scenario, MOF) integer PKs.

        Args:
            df: DataFrame with columns matching the OutputKpi write schema.

        Returns:
            dict with keys 'created', 'updated', and optionally 'errors'.
        """
        return self._put("/output-kpis/", df.to_dict(orient="records"))

    def get_region_costs(self,
                         region: str | None = None,
                         name: str | None = None,
                         year: int | None = None,
                         limit: int = 500,
                         offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/region-costs/

        Args:
            region: Exact region ISO code filter.
            name:   Substring filter on cost name.
            year:   Exact year filter.
        """
        params = _compact(region=region, name=name, year=year, limit=limit, offset=offset)
        return self._to_df(self._get("/region-costs/", params))

    def get_region_cost(self, rc_id: int) -> dict:
        """GET /api/v2/region-costs/{rc_id}/"""
        return self._get(f"/region-costs/{rc_id}/")

    def upsert_region_costs(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/region-costs/  Lookup key: Name (unique).

        Args:
            df: DataFrame with columns matching the RegionCost write schema.
        """
        return self._put("/region-costs/", df.to_dict(orient="records"))

    def get_ambient_parameters(self, name: str | None = None,
                               limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """GET /api/v2/ambient-parameters/"""
        params = _compact(name=name, limit=limit, offset=offset)
        return self._to_df(self._get("/ambient-parameters/", params))

    def get_ambient_parameter(self, ap_id: int) -> dict:
        """GET /api/v2/ambient-parameters/{ap_id}/"""
        return self._get(f"/ambient-parameters/{ap_id}/")

    def upsert_ambient_parameters(self, df: pd.DataFrame) -> dict:
        """
        PUT /api/v2/ambient-parameters/  Lookup key: Name (unique).

        Args:
            df: DataFrame with columns matching the AmbientParameter write schema.
        """
        return self._put("/ambient-parameters/", df.to_dict(orient="records"))

    # ── Cases & Scenarios ─────────────────────────────────────────────────────

    def get_cases(self,
                  source: str | None = None,
                  sink: str | None = None,
                  region: str | None = None,
                  study: str | None = None,
                  limit: int = 500,
                  offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/cases/

        Args:
            source: Source name substring filter.
            sink:   Sink name substring filter.
            region: Exact region ISO code filter.
            study:  Exact study label filter.
        """
        params = _compact(source=source, sink=sink, region=region,
                          study=study, limit=limit, offset=offset)
        return self._to_df(self._get("/cases/", params))

    def get_case(self, case_id: int) -> dict:
        """GET /api/v2/cases/{case_id}/"""
        return self._get(f"/cases/{case_id}/")

    def get_scenarios(self,
                      case_id: int | None = None,
                      name: str | None = None,
                      type: str | None = None,
                      limit: int = 500,
                      offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/scenarios/

        Args:
            case_id: Exact case PK filter.
            name:    Substring filter on name or print_name.
            type:    Exact scenario type filter (e.g. 'TEA').
        """
        params = _compact(case_id=case_id, name=name, type=type,
                          limit=limit, offset=offset)
        return self._to_df(self._get("/scenarios/", params))

    def get_scenario(self, scenario_id: int) -> dict:
        """GET /api/v2/scenarios/{scenario_id}/"""
        return self._get(f"/scenarios/{scenario_id}/")

    def get_screening_summaries(self, scenario_id: int | None = None,
                                limit: int = 500, offset: int = 0) -> pd.DataFrame:
        """
        GET /api/v2/screening-summaries/

        Args:
            scenario_id: Exact scenario PK filter.
        """
        params = _compact(scenario_id=scenario_id, limit=limit, offset=offset)
        return self._to_df(self._get("/screening-summaries/", params))

    def get_screening_summary(self, summary_id: int) -> dict:
        """GET /api/v2/screening-summaries/{summary_id}/"""
        return self._get(f"/screening-summaries/{summary_id}/")


# ── Module-level helper ───────────────────────────────────────────────────────

def _compact(**kwargs) -> dict:
    """Return kwargs dict with None values removed."""
    return {k: v for k, v in kwargs.items() if v is not None}
