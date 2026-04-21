"""
PrISMa API v2 client wrappers.

Mirrors the v2 REST surface documented in
integration/prisma-v2/prisma_cloud_apis_v2/api_v2_examples.md

All methods authenticate using the same API key as the v1 client and
return pandas DataFrames (or dicts of DataFrames for detail endpoints
that carry nested data).

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
_BASE_LEGACY = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/v2"


class PrismaAPIv2:
    """
    Thin wrapper around the PrISMa v2 REST endpoints.
    Instantiated automatically as ``api.v2`` by the v1 prisma_api class.
    """

    def __init__(self, key: str, dev: bool = False, dev_host_port: str = ""):
        self._key = key
        self._dev = dev
        self._dev_host_port = dev_host_port

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        if self._dev:
            return f"http://localhost:{self._dev_host_port}/api/v2"
        return _BASE_PROD

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._key,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET request, trying prod then legacy fallback (non-dev only)."""
        urls = (
            [f"http://localhost:{self._dev_host_port}/api/v2{path}"]
            if self._dev
            else [f"{_BASE_PROD}{path}", f"{_BASE_LEGACY}{path}"]
        )
        last_exc: Exception | None = None
        for url in urls:
            try:
                resp = requests.get(url, params=params, headers=self._headers(), timeout=60)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                continue
        raise RuntimeError(f"All v2 endpoints failed for GET {path}: {last_exc}")

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

    @staticmethod
    def _to_df(response: Any, key: str = "results") -> pd.DataFrame:
        """Convert a list-endpoint response envelope to a DataFrame."""
        records = response.get(key, response) if isinstance(response, dict) else response
        return pd.DataFrame(records) if records else pd.DataFrame()

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
        return self._to_df(self._get("/materials/", params))

    def get_material(self, material_id: int) -> dict:
        """
        GET /api/v2/materials/{material_id}/

        Returns a dict with material detail including element composition.
        """
        return self._get(f"/materials/{material_id}/")

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


# ── Module-level helper ───────────────────────────────────────────────────────

def _compact(**kwargs) -> dict:
    """Return kwargs dict with None values removed."""
    return {k: v for k, v in kwargs.items() if v is not None}
