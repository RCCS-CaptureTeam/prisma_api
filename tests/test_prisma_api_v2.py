"""
Unit tests for prisma_api.prisma_api_v2.PrismaAPIv2

All HTTP calls are intercepted with responses (or unittest.mock) so no
live network access is required.  Run with:

    pytest tests/ -v --cov=prisma_api --cov-report=term-missing
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from numbers import Integral
from pathlib import Path

import pandas as pd
import pytest
import requests
import responses as resp_lib
from responses import matchers

from prisma_api.prisma_api_v2 import (
    _BASE_PROD,
    _BUNDLE_SECTIONS,
    PrismaAPIv2,
    _parse_cif_metadata,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

PROD_BASE = _BASE_PROD


@pytest.fixture
def api():
    """Return a PrismaAPIv2 instance pointed at prod (non-dev), DataFrame output."""
    return PrismaAPIv2(key="test-api-key", dev=False, return_format="dataframe")


@pytest.fixture
def dev_api():
    """Return a PrismaAPIv2 instance in dev mode."""
    return PrismaAPIv2(key="dev-key", dev=True, dev_host_port="8000")


def _envelope(results: list, count: int | None = None) -> dict:
    """Build a standard v2 list-envelope response body."""
    return {"count": count if count is not None else len(results),
            "offset": 0, "limit": 500, "results": results}


# ── Helpers: shared assertions ────────────────────────────────────────────────

def assert_df_columns(df, *columns):
    for col in columns:
        assert col in df.columns, f"Expected column '{col}' in DataFrame, got: {list(df.columns)}"


# ── return_format ─────────────────────────────────────────────────────────────

def test_default_return_format_is_json():
    api = PrismaAPIv2(key="k")
    assert api._return_format == "json"


def test_set_return_format_json():
    api = PrismaAPIv2(key="k")
    api.set_return_format("json")
    assert api._return_format == "json"


def test_set_return_format_invalid():
    api = PrismaAPIv2(key="k")
    with pytest.raises(ValueError):
        api.set_return_format("csv")


@resp_lib.activate
def test_json_format_returns_list(api):
    api.set_return_format("json")
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/molecules/",
                 json=_envelope([{"id": 3, "name": "CO2"}]), status=200)
    result = api.get_molecules()
    assert isinstance(result, list)
    assert result[0]["name"] == "CO2"


@resp_lib.activate
def test_json_format_empty_returns_empty_list(api):
    api.set_return_format("json")
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/molecules/",
                 json=_envelope([]), status=200)
    result = api.get_molecules()
    assert result == []


@resp_lib.activate
def test_json_format_restores_to_dataframe(api):
    import pandas as pd
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/molecules/",
                 json=_envelope([{"id": 3, "name": "CO2"}]), status=200)
    api.set_return_format("json")
    api.set_return_format("dataframe")
    result = api.get_molecules()
    assert isinstance(result, pd.DataFrame)


@resp_lib.activate
def test_json_format_cif_url_resolved(api):
    """cif_url relative paths are resolved even in json mode."""
    api.set_return_format("json")
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "MOF1", "cif_url": "/cifs/MOF1.cif"}]),
                 status=200)
    result = api.list_materials()
    assert result[0]["cif_url"] == "https://prisma-platform.org/cifs/MOF1.cif"


# ── _compact ─────────────────────────────────────────────────────────────────

def test_compact_removes_none():
    from prisma_api.prisma_api_v2 import _compact
    result = _compact(a=1, b=None, c="x")
    assert result == {"a": 1, "c": "x"}


def test_compact_keeps_false_and_zero():
    from prisma_api.prisma_api_v2 import _compact
    result = _compact(flag=False, count=0, name=None)
    assert result == {"flag": False, "count": 0}


# ── _to_df ────────────────────────────────────────────────────────────────────

def test_to_df_from_envelope(api):
    data = _envelope([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    df = api._to_df(data)
    assert len(df) == 2
    assert list(df["name"]) == ["A", "B"]


def test_to_df_empty_results(api):
    df = api._to_df(_envelope([]))
    assert df.empty


def test_to_df_plain_list(api):
    df = api._to_df([{"id": 1}])
    assert len(df) == 1


# ── Health ────────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_health_ok(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/health/",
                 json={"status": "ok", "version": "2.0.0"}, status=200)
    result = api.health()
    assert result["status"] == "ok"
    assert result["version"] == "2.0.0"


@resp_lib.activate
def test_health_http_error_raises(api):
    """Non-2xx response should propagate as an exception."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/health/", status=503)
    with pytest.raises(requests.HTTPError):
        api.health()


# ── Dev mode routing ──────────────────────────────────────────────────────────

@resp_lib.activate
def test_dev_mode_uses_localhost(dev_api):
    resp_lib.add(resp_lib.GET, "http://localhost:8000/api/v2/health/",
                 json={"status": "ok", "version": "2.0.0"}, status=200)
    result = dev_api.health()
    assert result["status"] == "ok"
    # Ensure no prod URL was called
    for call in resp_lib.calls:
        assert "localhost" in call.request.url


# ── Materials ─────────────────────────────────────────────────────────────────

_MATERIAL_EXTRA_FIELDS = {
    "material_id": "ABEXEM",
    "material_backend": "tabular_binary_iast",
    "gas_basis": ["CO2", "N2"],
    "supports_humid_ternary": None,
    "tags": [],
    "provenance": "tabular_material",
    "lifecycle": {"object_kind": "catalog", "version": "legacy.v1"},
    "metadata": {
        "django_tables": ["MOF", "Carbon_Isotherm", "Water_KPIs", "Carbon_ZeoPP"],
        "source": "live_db",
    },
    "source_path": None,
}

_NEW_MATERIAL_FIELDS = list(_MATERIAL_EXTRA_FIELDS.keys())


@resp_lib.activate
def test_list_materials_returns_dataframe(api):
    body = _envelope([
        {"id": 1, "name": "ABEXEM", "cif_url": "/media/ABEXEM.cif", **_MATERIAL_EXTRA_FIELDS},
        {"id": 2, "name": "FOOFOO", "cif_url": "/media/FOOFOO.cif",
         **_MATERIAL_EXTRA_FIELDS, "material_id": "FOOFOO"},
    ])
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/", json=body, status=200)
    df = api.list_materials()
    assert len(df) == 2
    assert_df_columns(df, "id", "name", "cif_url", *_NEW_MATERIAL_FIELDS)


@resp_lib.activate
def test_list_materials_new_fields_present(api):
    """All new schema fields returned by the server are surfaced in the response."""
    body = _envelope([{"id": 1, "name": "ABEXEM", "cif_url": "", **_MATERIAL_EXTRA_FIELDS}])
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/", json=body, status=200)
    df = api.list_materials()
    for field in _NEW_MATERIAL_FIELDS:
        assert field in df.columns, f"Expected column '{field}' missing from list_materials response"
    assert df.iloc[0]["material_id"] == "ABEXEM"
    assert df.iloc[0]["material_backend"] == "tabular_binary_iast"
    assert df.iloc[0]["provenance"] == "tabular_material"
    assert df.iloc[0]["lifecycle"] == {"object_kind": "catalog", "version": "legacy.v1"}
    assert df.iloc[0]["tags"] == []


@resp_lib.activate
def test_list_materials_name_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "ABEXEM", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "ABEXEM", "cif_url": "", **_MATERIAL_EXTRA_FIELDS}]), status=200)
    df = api.list_materials(name="ABEXEM")
    assert df.iloc[0]["name"] == "ABEXEM"


@resp_lib.activate
def test_get_material_detail(api):
    detail = {"id": 1, "name": "ABEXEM", "cif_url": "/media/ABEXEM.cif",
              "elements": [{"symbol": "C", "mass_fraction": 0.45}]}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/1/", json=detail, status=200)
    result = api.get_material(1, bundle=None)
    assert result["name"] == "ABEXEM"
    assert len(result["elements"]) == 1


@resp_lib.activate
def test_get_material_default_bundle_from_id(api):
    detail = {"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "elements": []}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/1/", json=detail, status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 json=_envelope([{"id": 10, "mof": "HKUST"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/",
                 json=_envelope([{"id": 20, "mof": "HKUST"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp-experimental/",
                 json=_envelope([{"id": 21, "mof": "HKUST"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/water-kpis/",
                 json=_envelope([{"id": 30, "mof": "HKUST", "Molecule": 1}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials-psdi/1/",
                 json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "cif_filename": "HKUST.cif"},
                 status=200)

    result = api.get_material(1)
    assert "isotherms" in result
    assert "zeopp" in result
    assert "water_kpis" in result
    assert "cif" in result
    assert result["zeopp"][0]["_zeopp_source"] in {"simulated", "experimental"}


@resp_lib.activate
def test_get_material_by_name_string_root_only(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "HKUST", "limit": "50"})],
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/1/",
                 json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "elements": []}, status=200)

    result = api.get_material(name="HKUST", bundle=None)
    assert result["id"] == 1
    assert result["name"] == "HKUST"


@resp_lib.activate
def test_get_material_by_name_list(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "HKUST", "limit": "50"})],
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "ABEXEM", "limit": "50"})],
                 json=_envelope([{"id": 2, "name": "ABEXEM"}]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/1/",
                 json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "elements": []}, status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/2/",
                 json={"id": 2, "name": "ABEXEM", "cif_url": "/media/ABEXEM.cif", "elements": []}, status=200)

    result = api.get_material(name=["HKUST", "ABEXEM"], bundle=None)
    assert isinstance(result, list)
    assert [r["name"] for r in result] == ["HKUST", "ABEXEM"]


@resp_lib.activate
def test_list_materials_empty(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/", json=_envelope([]), status=200)
    df = api.list_materials()
    assert df.empty


# ── Materials PSDI ────────────────────────────────────────────────────────────

_PSDI_RECORD = {
    "id": 1, "name": "ABEXEM",
    "cif_url": "https://prisma-platform.org/media/structures/ABEXEM.cif",
    "cif_filename": "ABEXEM.cif",
    "formula_descriptive": "C12H8N2O4Zn",
    "formula_hill": "C12H8N2O4Zn",
    "formula_reduced": "C12H8N2O4Zn",
    "formula_anonymous": "A12B8C2D4E",
    "formula": "C12H8N2O4Zn",
    "formula_calculated": "C12H8N2O4Zn",
    "chemical_name": "Zinc 1,4-benzenedicarboxylate",
    "periodic_dimensions": 3,
    "smiles": "[Zn]",
    "spacegroup_hm": "P 21/c",
    "spacegroup_hall": "-P 2ybc",
    "spacegroup_number": 14,
    "cell_volume": 1024.5,
    "cell_lengths": [10.2, 10.2, 10.2],
    "cell_angles": [90.0, 90.0, 90.0],
    "cell_ratios": [1.0, 1.0, 1.0],
    "unit_cell": None,
}


@resp_lib.activate
def test_get_materials_psdi_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials-psdi/",
                 json=_envelope([_PSDI_RECORD]), status=200)
    df = api.get_materials_psdi()
    assert len(df) == 1
    for col in ("name", "cif_url", "formula_hill", "smiles", "spacegroup_hm",
                "cell_volume", "spacegroup_number"):
        assert col in df.columns, f"Expected column '{col}'"


@resp_lib.activate
def test_get_materials_psdi_name_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials-psdi/",
                 match=[matchers.query_param_matcher({"name": "ABEX", "limit": "500", "offset": "0"})],
                 json=_envelope([_PSDI_RECORD]), status=200)
    df = api.get_materials_psdi(name="ABEX")
    assert df.iloc[0]["name"] == "ABEXEM"


@resp_lib.activate
def test_get_material_psdi_detail(api):
    detail = {**_PSDI_RECORD,
              "smiles_linker": "c1ccc(cc1)C(=O)O",
              "formula_linker": "C8H6O4",
              "smiles_linker_PubChem": "c1ccc(cc1)C(=O)O",
              "formula_linker_PubChem": "C8H6O4",
              "count_dict_PubChem": {"C8H6O4": 2},
              "smiles_node": "[Zn]",
              "formula_node": "Zn",
              "elements": [{"symbol": "C", "mass_fraction": 0.45},
                           {"symbol": "Zn", "mass_fraction": 0.20}]}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials-psdi/1/",
                 json=detail, status=200)
    result = api.get_material_psdi(1)
    assert result["name"] == "ABEXEM"
    assert result["smiles_linker"] == "c1ccc(cc1)C(=O)O"
    assert len(result["elements"]) == 2


@resp_lib.activate
def test_get_materials_psdi_empty(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials-psdi/",
                 json=_envelope([]), status=200)
    df = api.get_materials_psdi()
    assert df.empty


# ── Molecules ─────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_molecules_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/molecules/",
                 json=_envelope([{"id": 3, "name": "CO2"}, {"id": 4, "name": "N2"}]),
                 status=200)
    df = api.get_molecules()
    assert len(df) == 2
    assert "CO2" in df["name"].values


@resp_lib.activate
def test_get_molecule_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/molecules/3/",
                 json={"id": 3, "name": "CO2"}, status=200)
    result = api.get_molecule(3)
    assert result["name"] == "CO2"


# ── Elements ──────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_elements_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/elements/",
                 json=_envelope([{"id": 6, "symbol": "C", "name": "Carbon",
                                  "atomic_number": 6, "atomic_weight": 12.011}]),
                 status=200)
    df = api.get_elements()
    assert_df_columns(df, "symbol", "atomic_number")


@resp_lib.activate
def test_get_elements_symbol_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/elements/",
                 match=[matchers.query_param_matcher({"symbol": "Fe", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 26, "symbol": "Fe", "name": "Iron",
                                  "atomic_number": 26, "atomic_weight": 55.845}]),
                 status=200)
    df = api.get_elements(symbol="Fe")
    assert df.iloc[0]["symbol"] == "Fe"


@resp_lib.activate
def test_get_element_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/elements/26/",
                 json={"id": 26, "symbol": "Fe", "name": "Iron",
                       "atomic_number": 26, "atomic_weight": 55.845},
                 status=200)
    result = api.get_element(26)
    assert result["symbol"] == "Fe"


# ── Regions ───────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_regions_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/regions/",
                 json=_envelope([{"id": 1, "name": "United Kingdom", "code": "GB"}]),
                 status=200)
    df = api.get_regions()
    assert_df_columns(df, "id", "name", "code")


@resp_lib.activate
def test_get_regions_code_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/regions/",
                 match=[matchers.query_param_matcher({"code": "GB", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "United Kingdom", "code": "GB"}]),
                 status=200)
    df = api.get_regions(code="GB")
    assert df.iloc[0]["code"] == "GB"


@resp_lib.activate
def test_get_region_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/regions/1/",
                 json={"id": 1, "name": "United Kingdom", "code": "GB"}, status=200)
    result = api.get_region(1)
    assert result["code"] == "GB"


# ── Sources / Sinks / Transport / Utilities / References ─────────────────────

@pytest.mark.parametrize("method,path,fixture", [
    ("get_sources",    "/sources/",    [{"id": 1, "name": "Coal Plant", "short_name": "CP"}]),
    ("get_scopes",     "/scopes/",     [{"id": 7, "name": "Point Source"}]),
    ("get_sinks",      "/sinks/",      [{"id": 2, "name": "North Sea"}]),
    ("get_transport_scenarios", "/transport-scenarios/", [{"id": 3, "name": "Pipeline 200km"}]),
    ("get_utilities",  "/utilities/",  [{"id": 4, "name": "Steam"}]),
    ("get_references", "/references/", [{"id": 5, "Name": "IPCC AR6", "Doi": "10.1/x"}]),
])
@resp_lib.activate
def test_catalog_list_endpoints_return_dataframe(api, method, path, fixture):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}",
                 json=_envelope(fixture), status=200)
    df = getattr(api, method)()
    assert len(df) == 1


@pytest.mark.parametrize("method,path,record", [
    ("get_source",             "/sources/1/",            {"id": 1, "name": "Coal Plant"}),
    ("get_scope",              "/scopes/7/",             {"id": 7, "name": "Point Source"}),
    ("get_sink",               "/sinks/2/",              {"id": 2, "name": "North Sea"}),
    ("get_transport_scenario", "/transport-scenarios/3/",{"id": 3, "name": "Pipeline"}),
    ("get_utility",            "/utilities/4/",          {"id": 4, "name": "Steam"}),
    ("get_reference",          "/references/5/",         {"id": 5, "Name": "IPCC"}),
])
@resp_lib.activate
def test_catalog_detail_endpoints_return_dict(api, method, path, record):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}", json=record, status=200)
    pk = record["id"]
    result = getattr(api, method)(pk)
    assert result["id"] == pk


# ── Transport Modes ───────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_transports_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/transports/",
                 json=_envelope([{"id": 1, "name": "Ship"}]), status=200)
    df = api.get_transports()
    assert len(df) == 1


@resp_lib.activate
def test_get_transports_name_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/transports/",
                 match=[matchers.query_param_matcher({"name": "ship", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "Ship"}]), status=200)
    api.get_transports(name="ship")


@resp_lib.activate
def test_get_transport_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/transports/1/",
                 json={"id": 1, "name": "Ship"}, status=200)
    assert api.get_transport(1)["name"] == "Ship"


# ── Subsystems ────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_subsystems_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/subsystems/",
                 json=_envelope([{"id": 1, "name": "Capture", "type": "dac"}]), status=200)
    df = api.get_subsystems()
    assert_df_columns(df, "id", "name", "type")


@resp_lib.activate
def test_get_subsystems_type_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/subsystems/",
                 match=[matchers.query_param_matcher({"type": "dac", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "Capture", "type": "dac"}]), status=200)
    api.get_subsystems(type="dac")


@resp_lib.activate
def test_get_subsystem_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/subsystems/1/",
                 json={"id": 1, "name": "Capture", "type": "dac"}, status=200)
    assert api.get_subsystem(1)["type"] == "dac"


# ── Properties ────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_properties_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/properties/",
                 json=_envelope([{"id": 1, "name": "pressure", "domain": "TEA",
                                  "category": "params_amb"}]), status=200)
    df = api.get_properties()
    assert_df_columns(df, "name", "domain", "category")


@resp_lib.activate
def test_get_properties_filters(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/properties/",
                 match=[matchers.query_param_matcher(
                     {"domain": "TEA", "category": "params_amb", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_properties(domain="TEA", category="params_amb")


@resp_lib.activate
def test_get_property_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/properties/1/",
                 json={"id": 1, "name": "pressure"}, status=200)
    assert api.get_property(1)["name"] == "pressure"


# ── Equipment ─────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_equipment_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment/",
                 json=_envelope([{"id": 1, "name": "Blower A", "group": "Blower"}]),
                 status=200)
    df = api.get_equipment()
    assert_df_columns(df, "name", "group")


@resp_lib.activate
def test_get_equipment_group_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment/",
                 match=[matchers.query_param_matcher(
                     {"group": "Blower", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_equipment(group="Blower")


@resp_lib.activate
def test_get_equipment_item_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment/1/",
                 json={"id": 1, "name": "Blower A", "group": "Blower"}, status=200)
    assert api.get_equipment_item(1)["group"] == "Blower"


# ── Equipment Costs ───────────────────────────────────────────────────────

@resp_lib.activate
def test_get_equipment_costs_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-costs/",
                 json=_envelope([{"id": 1, "equipment_id": 1, "cost": 5000.0}]),
                 status=200)
    df = api.get_equipment_costs()
    assert_df_columns(df, "equipment_id", "cost")


@resp_lib.activate
def test_get_equipment_costs_equipment_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-costs/",
                 match=[matchers.query_param_matcher(
                     {"equipment_id": "1", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_equipment_costs(equipment_id=1)


@resp_lib.activate
def test_get_equipment_cost_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-costs/1/",
                 json={"id": 1, "equipment_id": 1, "cost": 5000.0}, status=200)
    assert api.get_equipment_cost(1)["cost"] == 5000.0


# ── Equipment Designs ─────────────────────────────────────────────────────

@resp_lib.activate
def test_get_equipment_designs_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-designs/",
                 json=_envelope([{"id": 1, "equipment_id": 1, "key": "D1", "value": 1.5}]),
                 status=200)
    df = api.get_equipment_designs()
    assert_df_columns(df, "equipment_id", "key")


@resp_lib.activate
def test_get_equipment_designs_key_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-designs/",
                 match=[matchers.query_param_matcher(
                     {"key": "D1", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_equipment_designs(key="D1")


@resp_lib.activate
def test_get_equipment_design_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment-designs/1/",
                 json={"id": 1, "key": "D1", "value": 1.5}, status=200)
    assert api.get_equipment_design(1)["key"] == "D1"


# ── Process Conditions ────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_process_conditions_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/process-conditions/",
                 json=_envelope([{"id": 1, "name": "TVSA01", "type": "tvsa"}]),
                 status=200)
    df = api.get_process_conditions()
    assert_df_columns(df, "name", "type")


@resp_lib.activate
def test_get_process_conditions_type_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/process-conditions/",
                 match=[matchers.query_param_matcher(
                     {"type": "tvsa", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_process_conditions(type="tvsa")


@resp_lib.activate
def test_get_process_condition_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/process-conditions/1/",
                 json={"id": 1, "name": "TVSA01", "type": "tvsa"}, status=200)
    assert api.get_process_condition(1)["type"] == "tvsa"


# ── Process Configurations ────────────────────────────────────────────────────

@resp_lib.activate
def test_get_process_configurations_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/process-configurations/",
                 json=_envelope([{"id": 1, "name": "dac_std", "type": "dac"}]),
                 status=200)
    df = api.get_process_configurations()
    assert_df_columns(df, "name", "type")


@resp_lib.activate
def test_get_process_configuration_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/process-configurations/1/",
                 json={"id": 1, "name": "dac_std", "type": "dac"}, status=200)
    assert api.get_process_configuration(1)["type"] == "dac"


# ── Contactor Configurations ──────────────────────────────────────────────────

@resp_lib.activate
def test_get_contactor_configurations_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/contactor-configurations/",
                 json=_envelope([{"id": 1, "name": "kiln_std", "type": "kiln"}]),
                 status=200)
    df = api.get_contactor_configurations()
    assert_df_columns(df, "name", "type")


@resp_lib.activate
def test_get_contactor_configuration_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/contactor-configurations/1/",
                 json={"id": 1, "name": "kiln_std", "type": "kiln"}, status=200)
    assert api.get_contactor_configuration(1)["type"] == "kiln"


# ── Cost Indices ──────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_cost_indices_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cost-indices/",
                 json=_envelope([{"id": 1, "year": 2019, "index": 607.5}]),
                 status=200)
    df = api.get_cost_indices()
    assert_df_columns(df, "year", "index")


@resp_lib.activate
def test_get_cost_indices_year_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cost-indices/",
                 match=[matchers.query_param_matcher(
                     {"year": "2019", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_cost_indices(year=2019)


@resp_lib.activate
def test_get_cost_index_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cost-indices/1/",
                 json={"id": 1, "year": 2019, "index": 607.5}, status=200)
    assert api.get_cost_index(1)["year"] == 2019


# ── Physical Constants ────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_constants_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/constants/",
                 json=_envelope([{"id": 1, "param": "R", "value": 8.314, "units": "J/mol/K"}]),
                 status=200)
    df = api.get_constants()
    assert_df_columns(df, "param", "value")


@resp_lib.activate
def test_get_constants_param_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/constants/",
                 match=[matchers.query_param_matcher(
                     {"param": "R", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "param": "R", "value": 8.314}]),
                 status=200)
    df = api.get_constants(param="R")
    assert df.iloc[0]["param"] == "R"


@resp_lib.activate
def test_get_constant_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/constants/1/",
                 json={"id": 1, "param": "R", "value": 8.314}, status=200)
    assert api.get_constant(1)["param"] == "R"


# ── MEA Baseline ──────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_mea_baselines_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea/",
                 json=_envelope([{"id": 1, "name": "NGCC"}]), status=200)
    df = api.get_mea_baselines()
    assert_df_columns(df, "id", "name")


@resp_lib.activate
def test_get_mea_baselines_name_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea/",
                 match=[matchers.query_param_matcher(
                     {"name": "NGCC", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "NGCC"}]), status=200)
    api.get_mea_baselines(name="NGCC")


@resp_lib.activate
def test_get_mea_baseline_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea/1/",
                 json={"id": 1, "name": "NGCC"}, status=200)
    assert api.get_mea_baseline(1)["name"] == "NGCC"


# ── MEA KPIs ──────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_mea_kpis_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea-kpis/",
                 json=_envelope([{"id": 1, "name": "CAPEX", "category": "CAC"}]),
                 status=200)
    df = api.get_mea_kpis()
    assert_df_columns(df, "name", "category")


@resp_lib.activate
def test_get_mea_kpis_category_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea-kpis/",
                 match=[matchers.query_param_matcher(
                     {"category": "CAC", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_mea_kpis(category="CAC")


@resp_lib.activate
def test_get_mea_kpi_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/mea-kpis/1/",
                 json={"id": 1, "name": "CAPEX", "category": "CAC"}, status=200)
    assert api.get_mea_kpi(1)["category"] == "CAC"

# ── Isotherms ─────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_isotherm_returns_dataframe(api):
    records = [
        {"id": 1, "mof": "ABEXEM", "molecule": "CO2", "T_ref_K": 298.0,
         "sim_or_exp": "sim", "good_structure": True},
        {"id": 2, "mof": "FOOFOO", "molecule": "N2",  "T_ref_K": 303.0,
         "sim_or_exp": "exp", "good_structure": False},
    ]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 json=_envelope(records), status=200)
    df = api.get_isotherm()
    assert len(df) == 2
    assert_df_columns(df, "id", "mof", "molecule", "T_ref_K", "sim_or_exp", "good_structure")


# ── Scopes ───────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_scopes_name_filter(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/scopes/",
        match=[matchers.query_param_matcher({"name": "point", "limit": "500", "offset": "0"})],
        json=_envelope([{"id": 7, "name": "Point Source"}]),
        status=200,
    )
    df = api.get_scopes(name="point")
    assert df.iloc[0]["name"] == "Point Source"


@resp_lib.activate
def test_get_scopes_coerces_types(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/scopes/",
        json=_envelope([
            {
                "id": "7",
                "name": "Point Source",
                "active": "true",
                "capture_efficiency": "0.935",
                "created_at": "2026-07-01T12:34:56Z",
                "tags": "[\"pilot\", \"uk\"]",
            }
        ]),
        status=200,
    )

    df = api.get_scopes()
    row = df.iloc[0]

    assert isinstance(row["id"], Integral)
    assert isinstance(row["name"], str)
    assert pd.api.types.is_bool_dtype(df["active"])
    assert isinstance(row["capture_efficiency"], float)
    assert pd.api.types.is_datetime64_any_dtype(df["created_at"])
    assert isinstance(row["tags"], list)


@resp_lib.activate
def test_get_scope_detail_coerces_types(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/scopes/7/",
        json={
            "id": "7",
            "name": "Point Source",
            "active": "false",
            "capture_efficiency": "1.05",
            "created_at": "2026-07-01T12:34:56Z",
            "tags": "[\"a\", \"b\"]",
        },
        status=200,
    )

    scope = api.get_scope(7)

    assert isinstance(scope["id"], int)
    assert isinstance(scope["name"], str)
    assert isinstance(scope["active"], bool)
    assert isinstance(scope["capture_efficiency"], float)
    assert isinstance(scope["created_at"], datetime)
    assert isinstance(scope["tags"], list)


@resp_lib.activate
def test_get_isotherm_all_filters_passed(api):
    expected_params = {
        "mof": "ABEXEM", "molecule": "CO2",
        "temperature_min": "273.0", "temperature_max": "350.0",
        "sim_or_exp": "sim", "good_structure": "true",
        "limit": "100", "offset": "0",
    }
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_params)],
                 json=_envelope([]), status=200)
    df = api.get_isotherm(
        mof="ABEXEM", molecule="CO2",
        temperature_min=273.0, temperature_max=350.0,
        sim_or_exp="sim", good_structure=True,
        limit=100, offset=0,
    )
    assert df.empty  # matched correctly → empty result is fine


@resp_lib.activate
def test_get_isotherm_good_structure_false(api):
    expected_params = {"good_structure": "false", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_params)],
                 json=_envelope([]), status=200)
    api.get_isotherm(good_structure=False)


# ── get_material_property_bundle ─────────────────────────────────────────────

@resp_lib.activate
def test_get_material_property_bundle_returns_dict(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)
    for path in ("/isotherms/", "/carbon-zeopp/",
                 "/carbon-zeopp-experimental/", "/water-kpis/"):
        resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}",
                     json=_envelope([{"id": 1, "mof": "HKUST"}]), status=200)
    bundle = api.get_material_property_bundle("HKUST")
    assert set(bundle.keys()) == {
        "isotherms", "zeopp_simulated", "zeopp_experimental", "water_kpis"
    }


@resp_lib.activate
def test_get_material_property_bundle_accepts_name_keyword(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)
    for path in ("/isotherms/", "/carbon-zeopp/",
                 "/carbon-zeopp-experimental/", "/water-kpis/"):
        resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}",
                     json=_envelope([{"id": 1, "mof": "HKUST"}]), status=200)

    bundle = api.get_material_property_bundle(name="HKUST")
    assert set(bundle.keys()) == {
        "isotherms", "zeopp_simulated", "zeopp_experimental", "water_kpis"
    }


@resp_lib.activate
def test_get_material_property_bundle_filters_forwarded(api):
    """sim_or_exp and good_structure must be forwarded to isotherms and water KPIs."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)
    expected_iso = {"mof": "HKUST", "sim_or_exp": "sim",
                    "good_structure": "true", "limit": "500", "offset": "0"}
    expected_w   = {"mof": "HKUST", "sim_or_exp": "sim",
                    "good_structure": "true", "limit": "500", "offset": "0"}
    expected_z   = {"mof": "HKUST", "good_structure": "true",
                    "limit": "500", "offset": "0"}
    expected_ze  = {"mof": "HKUST", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_iso)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/",
                 match=[matchers.query_param_matcher(expected_z)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp-experimental/",
                 match=[matchers.query_param_matcher(expected_ze)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/water-kpis/",
                 match=[matchers.query_param_matcher(expected_w)],
                 json=_envelope([]), status=200)
    api.get_material_property_bundle("HKUST", sim_or_exp="sim", good_structure=True)


@resp_lib.activate
def test_get_material_property_bundle_supports_query_dict(api):
    """Advanced query dict filters are merged and forwarded per endpoint."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "HKUST", "limit": "20"})],
                 json=_envelope([{"id": 1, "name": "HKUST"}]), status=200)

    expected_iso = {
        "mof": "HKUST",
        "limit": "10",
        "offset": "0",
        "good_structure": "true",
        "molecule": "CO2",
        "temperature_min": "273",
    }
    expected_z = {
        "mof": "HKUST",
        "limit": "10",
        "offset": "0",
        "good_structure": "true",
    }
    expected_ze = {
        "mof": "HKUST",
        "limit": "10",
        "offset": "0",
    }
    expected_w = {
        "mof": "HKUST",
        "limit": "10",
        "offset": "0",
        "good_structure": "true",
        "source": "Coal",
    }

    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_iso)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/",
                 match=[matchers.query_param_matcher(expected_z)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp-experimental/",
                 match=[matchers.query_param_matcher(expected_ze)],
                 json=_envelope([]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/water-kpis/",
                 match=[matchers.query_param_matcher(expected_w)],
                 json=_envelope([]), status=200)

    api.get_material_property_bundle(
        "HKUST",
        good_structure=True,
        query={
            "common": {"limit": 10},
            "materials": {"limit": 20},
            "isotherms": {"molecule": "CO2", "temperature_min": 273},
            "water_kpis": {"source": "Coal"},
        },
    )


@resp_lib.activate
def test_get_material_bundle_includes_text(api, monkeypatch):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials/",
        match=[matchers.query_param_matcher({"name": "HKUST", "limit": "50"})],
        json=_envelope([{"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials/1/",
        json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif"},
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials-psdi/1/",
        json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "cif_filename": "HKUST.cif"},
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        "https://prisma-platform.org/media/HKUST.cif",
        body="data_test\n_cell_length_a 10.0",
        status=200,
        content_type="text/plain",
    )

    expected_bundle = {
        "isotherms": [],
        "zeopp_simulated": [],
        "zeopp_experimental": [],
        "water_kpis": [],
    }

    def _fake_bundle(*args, **kwargs):
        return expected_bundle

    monkeypatch.setattr(api, "get_material_property_bundle", _fake_bundle)

    result = api.get_material_bundle("HKUST", include_cif=True, include_cif_text=True)

    assert result["material"]["id"] == 1
    assert result["material_psdi"]["cif_filename"] == "HKUST.cif"
    assert result["property_bundle"] == expected_bundle
    assert result["cif"]["url"] == "https://prisma-platform.org/media/HKUST.cif"
    assert isinstance(result["cif"]["text"], dict)
    assert result["cif"]["text"]["line_count"] == 2
    assert result["cif"]["text"]["fields"]["_cell_length_a"] == "10.0"
    assert "data_test" in result["cif"]["text"]["raw"]


@resp_lib.activate
def test_get_material_bundle_raises_on_ambiguous_name(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials/",
        match=[matchers.query_param_matcher({"name": "HK", "limit": "50"})],
        json=_envelope([
            {"id": 1, "name": "HKUST"},
            {"id": 2, "name": "HK-MOF-2"},
        ]),
        status=200,
    )

    with pytest.raises(ValueError, match="matched 2 materials"):
        api.get_material_bundle("HK")


@resp_lib.activate
def test_get_material_bundle_can_skip_cif(api, monkeypatch):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials/",
        match=[matchers.query_param_matcher({"name": "HKUST", "limit": "50"})],
        json=_envelope([{"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials/1/",
        json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif"},
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/materials-psdi/1/",
        json={"id": 1, "name": "HKUST", "cif_url": "/media/HKUST.cif", "cif_filename": "HKUST.cif"},
        status=200,
    )

    expected_bundle = {
        "isotherms": [],
        "zeopp_simulated": [],
        "zeopp_experimental": [],
        "water_kpis": [],
    }

    def _fake_bundle(*args, **kwargs):
        return expected_bundle

    monkeypatch.setattr(api, "get_material_property_bundle", _fake_bundle)

    result = api.get_material_bundle(
        "HKUST",
        include_cif=False,
        include_cif_text=True,
    )

    assert result["property_bundle"] == expected_bundle
    assert result["cif"] is None


# ── preflight_material_check ──────────────────────────────────────────────────

@resp_lib.activate
def test_preflight_material_check_true(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "HKUST", "cif_url": ""}]), status=200)
    assert api.preflight_material_check("HKUST") is True


@resp_lib.activate
def test_preflight_material_check_false(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([]), status=200)
    assert api.preflight_material_check("DOESNOTEXIST") is False


@resp_lib.activate
def test_preflight_material_check_json_format():
    """Works correctly when return_format is 'json'."""
    api_json = PrismaAPIv2(key="k", return_format="json")
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 json=_envelope([{"id": 1, "name": "HKUST", "cif_url": ""}]), status=200)
    assert api_json.preflight_material_check("HKUST") is True


# ── Water KPIs ────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_water_kpis_returns_dataframe(api):
    records = [{"id": 10, "mof": "ABEXEM", "molecule": "H2O",
                "source": "Coal", "sim_or_exp": "sim", "good_structure": True}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/water-kpis/",
                 json=_envelope(records), status=200)
    df = api.get_water_kpis()
    assert len(df) == 1
    assert_df_columns(df, "mof", "molecule", "sim_or_exp")


@resp_lib.activate
def test_get_water_kpis_filters_passed(api):
    expected = {"mof": "MOF1", "source": "Coal", "sim_or_exp": "exp",
                "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/water-kpis/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.get_water_kpis(mof="MOF1", source="Coal", sim_or_exp="exp")


# ── Carbon ZeoPP ─────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_carbon_zeopp_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/",
                 json=_envelope([{"id": 1, "mof": "HKUST", "pld": 3.6,
                                  "good_structure": True}]), status=200)
    df = api.get_carbon_zeopp()
    assert_df_columns(df, "mof", "good_structure")


@resp_lib.activate
def test_get_carbon_zeopp_filters(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/",
                 match=[matchers.query_param_matcher(
                     {"mof": "HKUST", "good_structure": "true",
                      "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_carbon_zeopp(mof="HKUST", good_structure=True)


@resp_lib.activate
def test_get_carbon_zeopp_item_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp/1/",
                 json={"id": 1, "mof": "HKUST", "pld": 3.6}, status=200)
    assert api.get_carbon_zeopp_item(1)["mof"] == "HKUST"


@resp_lib.activate
def test_get_carbon_zeopp_experimental_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp-experimental/",
                 json=_envelope([{"id": 1, "mof": "HKUST", "pld": 3.4}]),
                 status=200)
    df = api.get_carbon_zeopp_experimental()
    assert_df_columns(df, "mof")


@resp_lib.activate
def test_get_carbon_zeopp_experimental_item_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/carbon-zeopp-experimental/1/",
                 json={"id": 1, "mof": "HKUST", "pld": 3.4}, status=200)
    assert api.get_carbon_zeopp_experimental_item(1)["mof"] == "HKUST"


# ── AutoPrism Tables ─────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_autoprism_collection_returns_all_records(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/computation-runs/",
        match=[matchers.query_param_matcher({
            "workflow_id": "wf-1",
            "step": "adsorption",
            "status": "done",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 99, "workflow_id": "wf-1", "step": "adsorption", "status": "done"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/adsorption-singlepoint/",
        match=[matchers.query_param_matcher({
            "structure": "ABEXEM",
            "md5": "abc123",
            "mixture_id": "mix-1",
            "component": "CO2",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 1, "structure": "ABEXEM"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/heat-capacity/",
        match=[matchers.query_param_matcher({
            "structure": "ABEXEM",
            "temperature_K": "298.0",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 2, "structure": "ABEXEM", "temperature_K": 298.0}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/isotherm-h2/",
        match=[matchers.query_param_matcher({
            "structure": "ABEXEM",
            "isotherm_id": "iso-1",
            "component": "CO2",
            "temperature_K": "298.0",
            "pressure_bar": "1.0",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 3, "structure": "ABEXEM", "isotherm_id": "iso-1"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/adsorption-isotherm/",
        match=[matchers.query_param_matcher({
            "structure": "ABEXEM",
            "isotherm_id": "iso-1",
            "component": "CO2",
            "temperature_K": "298.0",
            "pressure_bar": "1.0",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 6, "structure": "ABEXEM", "component": "CO2"}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/mofchecker/",
        match=[matchers.query_param_matcher({
            "structure": "ABEXEM",
            "md5": "abc123",
            "is_mof": "true",
            "MOFQ": "yes",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 4, "structure": "ABEXEM", "is_mof": True}]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/zeopp-metrics/",
        match=[matchers.query_param_matcher({
            "mof": "ABEXEM",
            "md5": "abc123",
            "probe": "N2",
            "limit": "50",
            "offset": "0",
        })],
        json=_envelope([{"id": 5, "mof": "ABEXEM", "probe": "N2"}]),
        status=200,
    )

    bundle = api.get_autoprism_collection(
        workflow_id="wf-1",
        step="adsorption",
        status="done",
        structure="ABEXEM",
        mof="ABEXEM",
        md5="abc123",
        mixture_id="mix-1",
        component="CO2",
        isotherm_id="iso-1",
        temperature_K=298.0,
        pressure_bar=1.0,
        probe="N2",
        is_mof=True,
        MOFQ="yes",
        limit=50,
        offset=0,
    )

    assert set(bundle.keys()) == {
        "computation_runs",
        "adsorption_singlepoints",
        "heat_capacities",
        "isotherm_H2s",
        "adsorption_isotherms",
        "mofchecker",
        "zeopp_metrics",
        "meta_provenance",
    }
    assert len(bundle["computation_runs"]) == 1
    assert len(bundle["adsorption_singlepoints"]) == 1
    assert len(bundle["heat_capacities"]) == 1
    assert len(bundle["isotherm_H2s"]) == 1
    assert len(bundle["adsorption_isotherms"]) == 1
    assert len(bundle["mofchecker"]) == 1
    assert len(bundle["zeopp_metrics"]) == 1


@resp_lib.activate
def test_get_autoprism_collection_uses_mof_as_structure_fallback(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/computation-runs/",
        match=[matchers.query_param_matcher({"limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/adsorption-singlepoint/",
        match=[matchers.query_param_matcher({"structure": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/heat-capacity/",
        match=[matchers.query_param_matcher({"structure": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/isotherm-h2/",
        match=[matchers.query_param_matcher({"structure": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/adsorption-isotherm/",
        match=[matchers.query_param_matcher({"structure": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/mofchecker/",
        match=[matchers.query_param_matcher({"structure": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/zeopp-metrics/",
        match=[matchers.query_param_matcher({"mof": "HKUST", "limit": "500", "offset": "0"})],
        json=_envelope([]),
        status=200,
    )

    api.get_autoprism_collection(mof="HKUST")


@resp_lib.activate
def test_get_computation_runs_filters(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/computation-runs/",
        match=[matchers.query_param_matcher({
            "workflow_id": "wf-1",
            "step": "zeopp",
            "status": "running",
            "limit": "25",
            "offset": "5",
        })],
        json=_envelope([{"id": 1, "workflow_id": "wf-1", "step": "zeopp", "status": "running"}]),
        status=200,
    )
    df = api.get_computation_runs(workflow_id="wf-1", step="zeopp", status="running", limit=25, offset=5)
    assert_df_columns(df, "id", "workflow_id", "step", "status")


@resp_lib.activate
def test_get_computation_run_detail(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/computation-runs/7/",
        json={"id": 7, "workflow_id": "wf-7", "step": "mofchecker", "status": "done"},
        status=200,
    )
    result = api.get_computation_run(7)
    assert result["id"] == 7
    assert result["status"] == "done"


@resp_lib.activate
def test_upsert_computation_runs_accepts_single_dict_and_new_fields(api):
    payload = {
        "id": 7,
        "workflow_id": "wf-7",
        "step": "adsorption",
        "status": "done",
        "new_field_from_server": "kept",
    }
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/computation-runs/",
        match=[matchers.json_params_matcher([payload])],
        json={"created": 0, "updated": 1},
        status=200,
    )
    result = api.upsert_computation_runs(payload)
    assert result["updated"] == 1


@resp_lib.activate
def test_autoprism_detail_endpoints(api):
    detail_endpoints = [
        ("/adsorption-singlepoint/1/", "get_adsorption_singlepoint_item", {"id": 1, "structure": "ABEXEM"}),
        ("/heat-capacity/2/", "get_heat_capacity_item", {"id": 2, "structure": "ABEXEM"}),
        ("/isotherm-h2/3/", "get_isotherm_h2_item", {"id": 3, "structure": "ABEXEM"}),
        ("/adsorption-isotherm/6/", "get_adsorption_isotherm_item", {"id": 6, "structure": "ABEXEM"}),
        ("/mofchecker/4/", "get_mofchecker_item", {"id": 4, "structure": "ABEXEM"}),
        ("/zeopp-metrics/5/", "get_zeopp_metrics_item", {"id": 5, "mof": "ABEXEM"}),
    ]

    for path, _, body in detail_endpoints:
        resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}", json=body, status=200)

    assert api.get_adsorption_singlepoint_item(1)["id"] == 1
    assert api.get_heat_capacity_item(2)["id"] == 2
    with pytest.warns(DeprecationWarning):
        assert api.get_isotherm_h2_item(3)["id"] == 3
    assert api.get_adsorption_isotherm_item(6)["id"] == 6
    assert api.get_mofchecker_item(4)["id"] == 4
    assert api.get_zeopp_metrics_item(5)["id"] == 5


@resp_lib.activate
def test_upsert_autoprism_tables_accept_dataframes_and_pass_all_fields(api, monkeypatch):
    fake_meta = {
        "source_repo": "AutoPrism",
        "source_repo_semantic_version": "0.1.0",
        "source_repo_tag": "0.1.0",
        "source_commit_hash": "724b0306f6b21f953fba21e424cdda230525862f",
    }
    fake_repo_url = "https://github.com/AutoPrism/AutoPrism"
    monkeypatch.setattr(api, "_autoprism_meta_provenance", lambda repo_dir=None: fake_meta)
    monkeypatch.setattr(api, "_autoprism_source_repo_url", lambda repo_dir=None: fake_repo_url)

    adsorption_df = pd.DataFrame([
        {
            "structure": "ABEXEM",
            "md5": "a1",
            "mixture_id": "mix-1",
            "component": "CO2",
            "temperature_K": 298.0,
            "pressure_bar": 1.0,
            "new_extra_field": "pass-through",
        }
    ])
    heat_capacity_df = pd.DataFrame([
        {"structure": "ABEXEM", "temperature_K": 298.0, "Cp": 123.4, "new_extra_field": "pass-through"}
    ])
    isotherm_h2_df = pd.DataFrame([
        {
            "structure": "ABEXEM",
            "md5": "a1",
            "isotherm_id": "iso-1",
            "component": "H2",
            "temperature_K": 298.0,
            "pressure_bar": 1.0,
            "uptake": 2.1,
            "new_extra_field": "pass-through",
        }
    ])
    mofchecker_df = pd.DataFrame([
        {"structure": "ABEXEM", "md5": "a1", "is_mof": True, "MOFQ": "yes", "new_extra_field": "pass-through"}
    ])
    zeopp_df = pd.DataFrame([
        {"mof": "ABEXEM", "md5": "a1", "probe": "N2", "pld": 3.4, "new_extra_field": "pass-through"}
    ])

    adsorption_expected = [{
        **adsorption_df.to_dict(orient="records")[0],
        "meta_provenance": {**fake_meta, "source_repo_url": fake_repo_url},
    }]
    heat_capacity_expected = [{
        **heat_capacity_df.to_dict(orient="records")[0],
        "meta_provenance": {**fake_meta, "source_repo_url": fake_repo_url},
    }]
    isotherm_h2_expected = [{
        **isotherm_h2_df.to_dict(orient="records")[0],
        "meta_provenance": {**fake_meta, "source_repo_url": fake_repo_url},
    }]
    mofchecker_expected = [{
        **mofchecker_df.to_dict(orient="records")[0],
        "meta_provenance": {**fake_meta, "source_repo_url": fake_repo_url},
    }]
    zeopp_expected = [{
        **zeopp_df.to_dict(orient="records")[0],
        "meta_provenance": {**fake_meta, "source_repo_url": fake_repo_url},
    }]

    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/adsorption-singlepoint/",
        match=[matchers.json_params_matcher(adsorption_expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/heat-capacity/",
        match=[matchers.json_params_matcher(heat_capacity_expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/isotherm-h2/",
        match=[matchers.json_params_matcher(isotherm_h2_expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/mofchecker/",
        match=[matchers.json_params_matcher(mofchecker_expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/zeopp-metrics/",
        match=[matchers.json_params_matcher(zeopp_expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )

    assert api.upsert_adsorption_singlepoint(adsorption_df)["created"] == 1
    assert api.upsert_heat_capacity(heat_capacity_df)["created"] == 1
    with pytest.warns(DeprecationWarning):
        assert api.upsert_isotherm_h2(isotherm_h2_df)["created"] == 1
    assert api.upsert_mofchecker(mofchecker_df)["created"] == 1
    assert api.upsert_zeopp_metrics(zeopp_df)["created"] == 1


@resp_lib.activate
def test_upsert_zeopp_metrics_accepts_wrapped_payload_and_overwrites_meta(api, monkeypatch):
    fake_meta = {
        "source_repo": "AutoPrism",
        "source_repo_semantic_version": "0.1.0",
        "source_repo_tag": "0.1.0",
        "source_commit_hash": "724b0306f6b21f953fba21e424cdda230525862f",
    }
    monkeypatch.setattr(api, "_autoprism_meta_provenance", lambda repo_dir=None: fake_meta)
    monkeypatch.setattr(api, "_autoprism_source_repo_url", lambda repo_dir=None: None)

    payload = {
        "zeopp_metrics": [
            {
                "mof": "UiO-66",
                "md5": "aaaaaaaa",
                "probe": "N2",
                "Di": 6.4,
                "meta_provenance": {
                    "source_repo": "stale",
                    "source_repo_semantic_version": "stale",
                    "source_repo_tag": "stale",
                    "source_commit_hash": "stale",
                },
            }
        ],
        "meta_provenance": {
            "source_repo": "top-level-stale",
            "source_repo_semantic_version": "top-level-stale",
            "source_repo_tag": "top-level-stale",
            "source_commit_hash": "top-level-stale",
        },
    }

    expected = [{
        "mof": "UiO-66",
        "md5": "aaaaaaaa",
        "probe": "N2",
        "Di": 6.4,
        "meta_provenance": {**fake_meta, "source_repo_url": None},
    }]

    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/zeopp-metrics/",
        match=[matchers.json_params_matcher(expected)],
        json={"created": 1, "updated": 0},
        status=200,
    )

    result = api.upsert_zeopp_metrics(payload)
    assert result["created"] == 1


def test_upsert_autoprism_collection_dispatches_sections(api, monkeypatch):
    calls = {}

    def _fake(name, result):
        def _method(payload, **kwargs):
            calls[name] = kwargs
            return result
        return _method

    monkeypatch.setattr(api, "upsert_computation_runs", _fake("computation_runs", {"created": 1, "updated": 0}))
    monkeypatch.setattr(api, "upsert_adsorption_singlepoint", _fake("adsorption", {"created": 2, "updated": 0}))
    monkeypatch.setattr(api, "upsert_heat_capacity", _fake("heat", {"created": 0, "updated": 3}))
    monkeypatch.setattr(api, "upsert_isotherm_h2", _fake("h2", {"created": 4, "updated": 1}))
    monkeypatch.setattr(api, "upsert_adsorption_isotherm", _fake("iso", {"created": 7, "updated": 0}))
    monkeypatch.setattr(api, "upsert_mofchecker", _fake("mofchecker", {"created": 5, "updated": 0}))
    monkeypatch.setattr(api, "upsert_zeopp_metrics", _fake("zeopp", {"created": 6, "updated": 2}))

    top_level_meta = {"source_repo": "AutoPrism", "source_commit_hash": "abc123"}
    payload = {
        "computation_runs": [{"id": "run-1"}],
        "adsorption_singlepoints": [{"id": 1}],
        "heat_capacities": [{"id": 2}],
        "isotherm_H2s": [{"id": 3}],
        "adsorption_isotherms": [{"id": 6}],
        "mofchecker": [{"id": 4}],
        "zeopp_metrics": [{"id": 5}],
        "meta_provenance": top_level_meta,
    }

    with pytest.warns(DeprecationWarning, match="isotherm_H2s"):
        result = api.upsert_autoprism_collection(payload)

    assert result["overall_status"] == "ok"
    assert result["totals"]["created"] == 25
    assert result["totals"]["updated"] == 6
    assert result["totals"]["failed_sections"] == 0
    assert result["sections"]["zeopp_metrics"]["status"] == "ok"
    assert result["sections"]["mofchecker"]["status"] == "ok"
    assert result["sections"]["adsorption_isotherms"]["status"] == "ok"
    # Top-level meta_provenance is passed down to every AutoPrism table.
    for name in ("adsorption", "heat", "h2", "iso", "mofchecker", "zeopp"):
        assert calls[name]["meta_provenance"] == top_level_meta
    assert "meta_provenance" not in calls["computation_runs"]


def test_upsert_autoprism_collection_argument_meta_overrides_payload(api, monkeypatch):
    seen = {}

    def _capture(payload, **kwargs):
        seen.update(kwargs)
        return {"created": 1, "updated": 0}

    monkeypatch.setattr(api, "upsert_zeopp_metrics", _capture)
    override = {"source_repo": "explicit"}
    api.upsert_autoprism_collection(
        {"zeopp_metrics": [{"id": 5}], "meta_provenance": {"source_repo": "payload"}},
        meta_provenance=override,
    )
    assert seen["meta_provenance"] == override


def test_upsert_autoprism_collection_reports_skips_and_errors(api, monkeypatch):
    monkeypatch.setattr(api, "upsert_computation_runs", lambda payload, **kw: {"created": 1, "updated": 0})
    monkeypatch.setattr(api, "_resolve_meta_provenance", lambda meta=None, repo_dir=None: meta or {})

    def _raise_error(payload, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api, "upsert_zeopp_metrics", _raise_error)

    payload = {
        "computation_runs": [{"id": "run-1"}],
        "zeopp_metrics": [{"id": 5}],
    }

    result = api.upsert_autoprism_collection(payload)

    assert result["overall_status"] == "partial_failure"
    assert result["totals"]["created"] == 1
    assert result["totals"]["updated"] == 0
    assert result["totals"]["failed_sections"] == 1
    assert result["sections"]["computation_runs"]["status"] == "ok"
    assert result["sections"]["adsorption_singlepoints"]["status"] == "skipped"
    assert result["sections"]["zeopp_metrics"]["status"] == "error"

    with pytest.raises(RuntimeError, match="zeopp_metrics: boom"):
        api.upsert_autoprism_collection(payload, raise_on_error=True)


@resp_lib.activate
def test_upsert_explicit_meta_provenance_used_as_is(api, monkeypatch):
    def _no_git(*args, **kwargs):
        raise AssertionError("git provenance must not be derived when meta_provenance is given")

    monkeypatch.setattr(api, "_autoprism_meta_provenance", _no_git)
    meta = {"source_repo": "AutoPrism", "source_commit_hash": "abc123"}
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/isotherm-h2/",
        match=[matchers.json_params_matcher([{"structure": "X", "meta_provenance": meta}])],
        json={"created": 1, "updated": 0},
    )
    with pytest.warns(DeprecationWarning):
        assert api.upsert_isotherm_h2({"structure": "X"}, meta_provenance=meta)["created"] == 1


def _init_git_repo(path, remote):
    import subprocess
    run = lambda *a: subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (path / "pyproject.toml").write_text('[project]\nname = "caller"\nversion = "9.8.7"\n')
    run("add", ".")
    run("commit", "-q", "-m", "init")
    run("tag", "v9.8.7")
    run("remote", "add", "origin", remote)


def test_meta_provenance_describes_caller_repo_not_prisma_api(api, tmp_path, monkeypatch):
    repo = tmp_path / "caller_repo"
    repo.mkdir()
    _init_git_repo(repo, "https://x-access-token:SECRET@github.com/org/caller_repo.git")
    monkeypatch.chdir(repo)

    meta = api._resolve_meta_provenance()

    assert meta["source_repo"] == "caller_repo"
    assert meta["source_repo_semantic_version"] == "9.8.7"
    assert meta["source_repo_tag"] == "v9.8.7"
    assert meta["source_commit_hash"] and len(meta["source_commit_hash"]) == 40
    assert meta["source_repo_url"] == "https://github.com/org/caller_repo.git"
    assert "SECRET" not in json.dumps(meta)

    # repo_dir= takes precedence over the working directory.
    monkeypatch.chdir(tmp_path)
    assert api._resolve_meta_provenance(repo_dir=repo)["source_repo"] == "caller_repo"


@pytest.mark.parametrize("url, expected", [
    ("https://x-access-token:tok@github.com/o/r.git", "https://github.com/o/r.git"),
    ("https://user@github.com/o/r", "https://github.com/o/r"),
    ("https://github.com/o/r", "https://github.com/o/r"),
    ("git@github.com:o/r.git", "git@github.com:o/r.git"),
])
def test_strip_url_credentials(url, expected):
    from prisma_api.prisma_api_v2 import _strip_url_credentials
    assert _strip_url_credentials(url) == expected


def test_payload_to_records_is_strict_json_safe(api):
    import numpy as np
    df = pd.DataFrame({
        "structure": ["A", "B", None],
        "value": [1.0, np.nan, np.inf],
        "count": pd.array([1, None, 3], dtype="Int64"),
        "when": [pd.Timestamp("2026-01-01"), pd.NaT, pd.Timestamp("2026-01-02")],
        "flag": [np.bool_(True), np.bool_(False), np.bool_(True)],
    })
    records = api._payload_to_records(df)
    json.dumps(records, allow_nan=False)
    assert records[1]["value"] is None
    assert records[2]["value"] is None
    assert records[1]["count"] is None
    assert records[1]["when"] is None
    assert records[0]["flag"] is True

    nested = api._payload_to_records([{"a": float("nan"), "b": {"c": np.float64("-inf"), "d": [np.int64(2)]}}])
    json.dumps(nested, allow_nan=False)
    assert nested == [{"a": None, "b": {"c": None, "d": [2]}}]


@resp_lib.activate
def test_put_body_has_no_nan_and_honours_timeout(api, monkeypatch):
    import numpy as np
    captured = {}
    real_put = requests.put

    def _spy(url, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return real_put(url, **kwargs)

    monkeypatch.setattr(requests, "put", _spy)
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/region-costs/", json={"created": 1})
    api.upload_timeout = 999
    api.upsert_region_costs(pd.DataFrame({"region": ["UK"], "cost": [np.nan]}))

    body = resp_lib.calls[0].request.body
    json.loads(body, parse_constant=lambda c: pytest.fail(f"non-JSON constant {c}"))
    assert captured["timeout"] == 999


def test_get_autoprism_collection_allows_empty_payloads(api, monkeypatch):
    monkeypatch.setattr(api, "get_computation_runs", lambda **kwargs: None)
    monkeypatch.setattr(api, "get_adsorption_singlepoint", lambda **kwargs: None)
    monkeypatch.setattr(api, "get_heat_capacity", lambda **kwargs: {"results": []})
    monkeypatch.setattr(api, "get_isotherm_h2", lambda **kwargs: 0)
    monkeypatch.setattr(api, "get_adsorption_isotherm", lambda **kwargs: None)
    monkeypatch.setattr(api, "get_mofchecker", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_zeopp_metrics", lambda **kwargs: pd.DataFrame())

    collection = api.get_autoprism_collection(mof="ABEXEM")

    assert set(collection.keys()) == {
        "computation_runs",
        "adsorption_singlepoints",
        "heat_capacities",
        "isotherm_H2s",
        "adsorption_isotherms",
        "mofchecker",
        "zeopp_metrics",
        "meta_provenance",
    }
    assert len(collection["computation_runs"]) == 0
    assert len(collection["adsorption_singlepoints"]) == 0
    assert len(collection["heat_capacities"]) == 0
    assert len(collection["isotherm_H2s"]) == 0
    assert len(collection["adsorption_isotherms"]) == 0
    assert len(collection["mofchecker"]) == 0
    assert len(collection["zeopp_metrics"]) == 0


def test_get_autoprism_collection_tolerates_endpoint_http_error(api, monkeypatch):
    import requests

    def _raise_http_error(**kwargs):
        raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr(api, "get_computation_runs", _raise_http_error)
    monkeypatch.setattr(api, "get_adsorption_singlepoint", lambda **kwargs: [{"id": 1}])
    monkeypatch.setattr(api, "get_heat_capacity", lambda **kwargs: [{"id": 2}])
    monkeypatch.setattr(api, "get_isotherm_h2", lambda **kwargs: [{"id": 3}])
    monkeypatch.setattr(api, "get_adsorption_isotherm", _raise_http_error)
    monkeypatch.setattr(api, "get_mofchecker", lambda **kwargs: [{"id": 4}])
    monkeypatch.setattr(api, "get_zeopp_metrics", lambda **kwargs: [{"id": 5}])

    collection = api.get_autoprism_collection(mof="ABEXEM")

    assert len(collection["computation_runs"]) == 0
    assert len(collection["adsorption_singlepoints"]) == 1
    assert len(collection["heat_capacities"]) == 1
    assert len(collection["isotherm_H2s"]) == 1
    assert len(collection["adsorption_isotherms"]) == 0
    assert len(collection["mofchecker"]) == 1
    assert len(collection["zeopp_metrics"]) == 1


def test_get_autoprism_collection_includes_mofchecker_payload_shape(api, monkeypatch):
    monkeypatch.setattr(api, "get_computation_runs", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_adsorption_singlepoint", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_heat_capacity", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_isotherm_h2", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_adsorption_isotherm", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_zeopp_metrics", lambda **kwargs: [])
    monkeypatch.setattr(
        api,
        "get_mofchecker",
        lambda **kwargs: [{"id": 4, "structure": {"name": "ABEXEM"}, "is_mof": True}],
    )

    collection = api.get_autoprism_collection(mof="ABEXEM")

    assert "mofchecker" in collection
    assert "meta_provenance" in collection
    assert isinstance(collection["mofchecker"], list)
    assert len(collection["mofchecker"]) == 1

    meta = collection["meta_provenance"]
    assert set(meta.keys()) >= {
        "source_repo",
        "source_repo_url",
        "source_repo_semantic_version",
        "source_repo_tag",
        "source_commit_hash",
    }


def test_get_autoprism_collection_includes_zeopp_payload_shape(api, monkeypatch):
    monkeypatch.setattr(api, "get_computation_runs", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_adsorption_singlepoint", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_heat_capacity", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_isotherm_h2", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_adsorption_isotherm", lambda **kwargs: [])
    monkeypatch.setattr(api, "get_mofchecker", lambda **kwargs: [])
    monkeypatch.setattr(
        api,
        "get_zeopp_metrics",
        lambda **kwargs: [{"id": 5, "mof": "UiO-66", "probe": "N2"}],
    )

    collection = api.get_autoprism_collection(mof="UiO-66")

    assert "zeopp_metrics" in collection
    assert "meta_provenance" in collection
    assert isinstance(collection["zeopp_metrics"], list)
    assert len(collection["zeopp_metrics"]) == 1

    meta = collection["meta_provenance"]
    assert set(meta.keys()) >= {
        "source_repo",
        "source_repo_url",
        "source_repo_semantic_version",
        "source_repo_tag",
        "source_commit_hash",
    }


# ── Output KPIs ───────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_output_kpis_returns_dataframe(api):
    records = [{"id": 100, "scenario_id": 830, "mof_name": "ABEXEM",
                "purity": 0.96, "recovery": 0.88, "good_structure": True}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/output-kpis/",
                 json=_envelope(records), status=200)
    df = api.get_output_kpis()
    assert len(df) == 1
    assert_df_columns(df, "scenario_id", "mof_name", "purity", "recovery")


@resp_lib.activate
def test_get_output_kpis_scenario_filter(api):
    expected = {"scenario_id": "830", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/output-kpis/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.get_output_kpis(scenario_id=830)


@resp_lib.activate
def test_get_output_kpi_detail(api):
    detail = {"id": 100, "scenario_id": 830, "mof_name": "ABEXEM",
              "purity": 0.96, "recovery": 0.88}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/output-kpis/100/",
                 json=detail, status=200)
    result = api.get_output_kpi(100)
    assert result["purity"] == 0.96


@resp_lib.activate
def test_upsert_output_kpis(api):
    import pandas as pd
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/output-kpis/",
                 json={"created": 1, "updated": 0}, status=200)
    df = pd.DataFrame([{"scenario": 830, "MOF": 1, "purity": 0.91}])
    result = api.upsert_output_kpis(df)
    assert result["created"] == 1


@resp_lib.activate
def test_upsert_output_kpis_partial_failure_207(api):
    import pandas as pd
    body = {"created": 1, "updated": 0,
            "errors": [{"item": {"scenario": 999}, "errors": {"scenario": ["Invalid pk"]}}]}
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/output-kpis/",
                 json=body, status=207)
    df = pd.DataFrame([{"scenario": 999, "MOF": 1, "purity": 0.91}])
    result = api.upsert_output_kpis(df)
    assert "errors" in result
    assert len(result["errors"]) == 1


# ── Region Costs ──────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_region_costs_returns_dataframe(api):
    records = [{"id": 55, "Name": "GB_electricity_2030", "region": "GB",
                "Units": "£/kWh", "Value": 0.18, "Year": 2030}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/region-costs/",
                 json=_envelope(records), status=200)
    df = api.get_region_costs()
    assert_df_columns(df, "Name", "Value", "Year")


@resp_lib.activate
def test_get_region_costs_filters(api):
    expected = {"region": "GB", "year": "2030", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/region-costs/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.get_region_costs(region="GB", year=2030)


@resp_lib.activate
def test_get_region_cost_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/region-costs/55/",
                 json={"id": 55, "Name": "GB_elec", "Value": 0.18, "Year": 2030},
                 status=200)
    result = api.get_region_cost(55)
    assert result["Value"] == 0.18


@resp_lib.activate
def test_upsert_region_costs(api):
    import pandas as pd
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/region-costs/",
                 json={"created": 0, "updated": 1}, status=200)
    df = pd.DataFrame([{"Name": "GB_electricity_2030", "Value": 0.20, "Year": 2030}])
    result = api.upsert_region_costs(df)
    assert result["updated"] == 1


# ── Ambient Parameters ────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_ambient_parameters_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/ambient-parameters/",
                 json=_envelope([{"id": 3, "Name": "ambient_T_K", "Units": "K"}]),
                 status=200)
    df = api.get_ambient_parameters()
    assert_df_columns(df, "Name", "Units")


@resp_lib.activate
def test_get_ambient_parameter_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/ambient-parameters/3/",
                 json={"id": 3, "Name": "ambient_T_K", "Units": "K"}, status=200)
    result = api.get_ambient_parameter(3)
    assert result["Name"] == "ambient_T_K"


@resp_lib.activate
def test_upsert_ambient_parameters(api):
    import pandas as pd
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/ambient-parameters/",
                 json={"created": 0, "updated": 1}, status=200)
    df = pd.DataFrame([{"Name": "ambient_T_K", "Units": "K"}])
    result = api.upsert_ambient_parameters(df)
    assert result["updated"] == 1


# ── Cases & Scenarios ─────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_cases_returns_dataframe(api):
    records = [{"id": 3372, "name": "UK Coal CCS 2030", "source": "Coal Plant",
                "sink": "North Sea", "region": "GB",
                "transport_scenario": "Pipeline 200km", "utilities": "Steam"}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/",
                 json=_envelope(records), status=200)
    df = api.get_cases()
    assert_df_columns(df, "id", "name", "source", "sink", "region")


@resp_lib.activate
def test_get_cases_filters_passed(api):
    expected = {"source": "Coal", "region": "GB", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.get_cases(source="Coal", region="GB")


@resp_lib.activate
def test_get_case_detail(api):
    detail = {"id": 3372, "name": "UK Coal CCS 2030", "source": "Coal Plant",
              "sink": "North Sea", "region": "GB"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/", json=detail, status=200)
    result = api.get_case(3372)
    assert result["name"] == "UK Coal CCS 2030"


@resp_lib.activate
def test_list_case_studies_returns_dataframe(api):
    records = [{"id": 1, "name": "Alpha 2030"}, {"id": 2, "name": "Beta 2040"}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/case-studies/",
                 json=_envelope(records), status=200)
    df = api.list_case_studies()
    assert_df_columns(df, "id", "name")


@resp_lib.activate
def test_list_case_studies_name_filter_passed(api):
    expected = {"name": "Alpha", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/case-studies/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.list_case_studies(name="Alpha")


@resp_lib.activate
def test_get_scenarios_returns_dataframe(api):
    records = [{"id": 830, "name": "baseline_2030", "print_name": "Baseline 2030",
                "type": "TEA", "case_study_id": 3372}]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 json=_envelope(records), status=200)
    df = api.get_scenarios()
    assert_df_columns(df, "id", "name", "type")


@resp_lib.activate
def test_get_scenarios_filters_passed(api):
    expected = {"case_id": "3372", "type": "TEA", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 match=[matchers.query_param_matcher(expected)],
                 json=_envelope([]), status=200)
    api.get_scenarios(case_id=3372, type="TEA")


@resp_lib.activate
def test_get_scenario_detail(api):
    detail = {"id": 830, "name": "baseline_2030", "print_name": "Baseline 2030",
              "type": "TEA", "case_study_id": 3372}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/830/", json=detail, status=200)
    result = api.get_scenario(830)
    assert result["type"] == "TEA"


@resp_lib.activate
def test_get_screening_analysis_bundle_detail(api):
    bundle = {"analysis_id": 123, "case_study": {"name": "Alpha 2030"}, "results": []}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/screening-analyses/123/bundle/",
                 json=bundle, status=200)
    result = api.get_screening_analysis_bundle(123)
    assert result["analysis_id"] == 123


# ── ImportedCasePack builders ─────────────────────────────────────────────────

_CASE_DETAIL = {
    "id": 3372, "name": "UK Coal CCS 2030", "study": "UK2030",
    "source": "Coal Power Plant", "sink": "North Sea Aquifer",
    "transport_scenario": "Pipeline 200km", "region": "GB",
    "utilities": "Steam", "duration": 25,
}
_SCENARIO_DETAIL = {
    "id": 830, "name": "baseline_2030", "print_name": "Baseline 2030",
    "type": "TEA", "case_study_id": 3372, "case_study_name": "UK Coal CCS 2030",
}


@resp_lib.activate
def test_build_case_spec_shape(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/", json=_CASE_DETAIL, status=200)
    spec = api.build_case_spec(3372)
    assert spec["case_name"]   == "UK Coal CCS 2030"
    assert spec["source_name"] == "Coal Power Plant"
    assert spec["sink_name"]   == "North Sea Aquifer"
    assert spec["region"]      == "GB"
    assert spec["root_case_path"] is None
    assert spec["source"]["component_type"] == "source"
    assert spec["sink"]["component_type"]   == "sink"
    assert spec["transport"]["component_type"] == "transport"
    assert spec["transport"]["name"] == "Pipeline 200km"
    assert isinstance(spec["utilities"], list)
    assert spec["utilities"][0]["component_type"] == "utility"
    assert spec["tea_general"] is None
    assert spec["import_issues"] == []


@resp_lib.activate
def test_build_case_spec_no_transport(api):
    case = {**_CASE_DETAIL, "transport_scenario": None}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/", json=case, status=200)
    spec = api.build_case_spec(3372)
    assert spec["transport"] is None


@resp_lib.activate
def test_build_scenario_spec_shape(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/830/", json=_SCENARIO_DETAIL, status=200)
    spec = api.build_scenario_spec(830)
    assert spec["scenario_name"] == "baseline_2030"
    assert spec["case_name"]     == "UK Coal CCS 2030"
    assert spec["process"]             is None
    assert spec["adsorption_scenario"] is None
    assert spec["process_preview"]     is None
    assert spec["utilities"]           == []
    assert spec["import_issues"]       == []


@resp_lib.activate
def test_build_case_pack_full(api):
    """build_case_pack fetches case + first scenario and assembles ImportedCasePack."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/",    json=_CASE_DETAIL,     status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 json={"count": 1, "results": [_SCENARIO_DETAIL]}, status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/830/", json=_SCENARIO_DETAIL, status=200)
    pack = api.build_case_pack(3372)
    # Top-level keys match ImportedCasePack spec
    assert set(pack.keys()) == {"pack_root", "case_spec", "scenario_spec",
                                 "available_documents", "import_issues"}
    assert pack["pack_root"]           is None
    assert pack["available_documents"] == []
    assert pack["import_issues"]       == []
    # Nested CaseSpec
    assert pack["case_spec"]["case_name"]   == "UK Coal CCS 2030"
    assert pack["case_spec"]["source"]["component_type"] == "source"
    # Nested ScenarioSpec
    assert pack["scenario_spec"]["scenario_name"] == "baseline_2030"
    assert pack["scenario_spec"]["process"] is None


@resp_lib.activate
def test_build_case_pack_no_scenario_resolved(api):
    """When no scenarios exist, scenario_spec is None."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/", json=_CASE_DETAIL, status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 json={"count": 0, "results": []}, status=200)
    pack = api.build_case_pack(3372)
    assert pack["scenario_spec"] is None


@resp_lib.activate
def test_build_case_pack_suppress_scenario(api):
    """scenario_id=-1 skips scenario resolution entirely."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/", json=_CASE_DETAIL, status=200)
    pack = api.build_case_pack(3372, scenario_id=-1)
    assert pack["scenario_spec"] is None


@resp_lib.activate
def test_build_case_pack_explicit_scenario(api):
    """Explicit scenario_id is fetched directly without listing."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/3372/",    json=_CASE_DETAIL,     status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/830/", json=_SCENARIO_DETAIL, status=200)
    pack = api.build_case_pack(3372, scenario_id=830)
    assert pack["scenario_spec"]["scenario_name"] == "baseline_2030"


@resp_lib.activate
def test_list_case_packs_returns_list_of_dicts(api):
    """list_case_packs returns a list of ImportedCasePack dicts."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/",
                 json={"count": 2, "results": [
                     {**_CASE_DETAIL, "id": 1, "name": "Case A"},
                     {**_CASE_DETAIL, "id": 2, "name": "Case B"},
                 ]}, status=200)
    packs = api.list_case_packs()
    assert isinstance(packs, list)
    assert len(packs) == 2
    for pack in packs:
        assert set(pack.keys()) == {"pack_root", "case_spec", "scenario_spec",
                                     "available_documents", "import_issues"}
        assert pack["scenario_spec"] is None   # include_scenarios=False by default


@resp_lib.activate
def test_list_case_packs_include_scenarios(api):
    """include_scenarios=True attaches ScenarioSpec for each case."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/",
                 json={"count": 1, "results": [{**_CASE_DETAIL, "id": 3372}]},
                 status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 json={"count": 1, "results": [_SCENARIO_DETAIL]}, status=200)
    packs = api.list_case_packs(include_scenarios=True)
    assert packs[0]["scenario_spec"]["scenario_name"] == "baseline_2030"


@resp_lib.activate
def test_list_case_packs_no_scenarios_available(api):
    """Case with no scenarios yields scenario_spec=None even with include_scenarios=True."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/cases/",
                 json={"count": 1, "results": [{**_CASE_DETAIL, "id": 3372}]},
                 status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/scenarios/",
                 json={"count": 0, "results": []}, status=200)
    packs = api.list_case_packs(include_scenarios=True)
    assert packs[0]["scenario_spec"] is None


# ── Screening Summaries ──────────────────────────────────────────────────────

@resp_lib.activate
def test_get_screening_summaries_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/screening-summaries/",
                 json=_envelope([{"id": 1, "scenario_id": 830, "mof": "ABEXEM",
                                  "rank": 1}]), status=200)
    df = api.get_screening_summaries()
    assert_df_columns(df, "scenario_id", "mof")


@resp_lib.activate
def test_get_screening_summaries_scenario_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/screening-summaries/",
                 match=[matchers.query_param_matcher(
                     {"scenario_id": "830", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_screening_summaries(scenario_id=830)


@resp_lib.activate
def test_get_screening_summary_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/screening-summaries/1/",
                 json={"id": 1, "scenario_id": 830, "mof": "ABEXEM"},
                 status=200)
    assert api.get_screening_summary(1)["mof"] == "ABEXEM"


# ── PUT sends correct JSON body ───────────────────────────────────────────────

@resp_lib.activate
def test_put_sends_json_body(api):
    """Verify that upsert methods serialise DataFrame rows as JSON list."""
    import pandas as pd

    captured = []

    def request_callback(request):
        captured.append(json.loads(request.body))
        return (200, {}, json.dumps({"created": 1, "updated": 0}))

    resp_lib.add_callback(resp_lib.PUT, f"{PROD_BASE}/output-kpis/", request_callback,
                          content_type="application/json")

    df = pd.DataFrame([{"scenario": 1, "MOF": 2, "purity": 0.9}])
    api.upsert_output_kpis(df)

    assert captured[0] == [{"scenario": 1, "MOF": 2, "purity": 0.9}]


# ── Authentication header ─────────────────────────────────────────────────────

@resp_lib.activate
def test_api_key_header_sent(api):
    """Every request must include X-API-Key."""
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/health/",
                 json={"status": "ok", "version": "2.0.0"}, status=200)
    api.health()
    assert resp_lib.calls[0].request.headers["X-API-Key"] == "test-api-key"


# ── Flowsheets ────────────────────────────────────────────────────────────────

_UPSERT_FLOWSHEET_FIXTURE = "reference_data/prisma_v2/dac_min_2026-07-01.json"
_SKIP_UPSERT_FLOWSHEET_IN_CI = pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Upsert flowsheet fixture tests are disabled in CI",
)


def _load_upsert_flowsheet_payload() -> list[dict]:
    with open(_UPSERT_FLOWSHEET_FIXTURE, "r", encoding="utf-8") as f:
        return [json.load(f)]

@resp_lib.activate
@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Offline development fixture test is disabled in CI",
)
def test_get_flowsheet_matches_reference_fixture(api):
    fixture_path = "reference_data/01-prisma-v2--flowsheets/dac_min_db.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/flowsheets/dac_min/",
                 json=expected, status=200)
    result = api.get_flowsheet()
    assert result == expected


@resp_lib.activate
def test_get_flowsheet_uses_dev_mode_base_url(dev_api):
    resp_lib.add(resp_lib.GET, f"{dev_api._base_url()}/flowsheets/dac_min/",
                 json={"template_id": "dac_min"}, status=200)
    result = dev_api.get_flowsheet()
    assert result["template_id"] == "dac_min"


@resp_lib.activate
def test_get_flowsheet_custom_name_routes_path(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/flowsheets/custom_case/",
                 json={"template_id": "custom_case"}, status=200)
    result = api.get_flowsheet(name="custom_case")
    assert result["template_id"] == "custom_case"


@resp_lib.activate
def test_get_flowsheet_bundle_returns_dict(api):
    expected = {"template_id": "dac_min", "bundle": {"nodes": [], "edges": []}}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/flowsheets/dac_min/bundle/",
                 json=expected, status=200)
    result = api.get_flowsheet_bundle()
    assert result == expected


@resp_lib.activate
def test_get_flowsheet_bundle_uses_dev_mode_base_url(dev_api):
    resp_lib.add(resp_lib.GET, f"{dev_api._base_url()}/flowsheets/dac_min/bundle/",
                 json={"template_id": "dac_min"}, status=200)
    result = dev_api.get_flowsheet_bundle()
    assert result["template_id"] == "dac_min"


@resp_lib.activate
def test_get_flowsheet_bundle_custom_name_routes_path(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/flowsheets/custom_case/bundle/",
                 json={"template_id": "custom_case"}, status=200)
    result = api.get_flowsheet_bundle(name="custom_case")
    assert result["template_id"] == "custom_case"


@resp_lib.activate
@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_default_append_mode(api):
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/flowsheets/upsert/?on_exists=append&appendix=_v4&screening_analysis_name=screening_case",
        json={"created": 1, "updated": 0},
        status=200,
    )
    payload = _load_upsert_flowsheet_payload()
    result = api.upsert_flowsheets(payload, screening_analysis_name="screening_case")
    assert result["created"] == 1


@resp_lib.activate
@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_overwrite_mode(api):
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/flowsheets/upsert/?on_exists=overwrite&screening_analysis_name=screening_case",
        json={"created": 0, "updated": 1},
        status=200,
    )
    payload = _load_upsert_flowsheet_payload()
    result = api.upsert_flowsheets(
        payload,
        screening_analysis_name="screening_case",
        on_exists="overwrite",
    )
    assert result["updated"] == 1


@resp_lib.activate
@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_uses_dev_mode_base_url(dev_api):
    resp_lib.add(
        resp_lib.PUT,
        "http://localhost:8000/api/v2/flowsheets/upsert/?on_exists=append&appendix=_dev&screening_analysis_name=screening_dev",
        json={"created": 1, "updated": 0},
        status=200,
    )
    payload = _load_upsert_flowsheet_payload()
    result = dev_api.upsert_flowsheets(
        payload,
        screening_analysis_name="screening_dev",
        appendix="_dev",
    )
    assert result["created"] == 1


@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_rejects_invalid_on_exists(api):
    payload = _load_upsert_flowsheet_payload()
    with pytest.raises(ValueError):
        api.upsert_flowsheets(
            payload,
            screening_analysis_name="screening_case",
            on_exists="replace",
        )


@resp_lib.activate
@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_allows_missing_screening_analysis_name_with_warning(api):
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/flowsheets/upsert/?on_exists=append&appendix=_v4",
        json={"created": 1, "updated": 0},
        status=200,
    )
    payload = _load_upsert_flowsheet_payload()
    with pytest.warns(UserWarning, match="for experimentation only"):
        result = api.upsert_flowsheets(payload)
    assert result["created"] == 1


@resp_lib.activate
@_SKIP_UPSERT_FLOWSHEET_IN_CI
def test_upsert_flowsheets_blank_screening_analysis_name_warns_and_omits_query_param(api):
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/flowsheets/upsert/?on_exists=overwrite",
        json={"created": 0, "updated": 1},
        status=200,
    )
    payload = _load_upsert_flowsheet_payload()
    with pytest.warns(UserWarning, match="list_case_studies"):
        result = api.upsert_flowsheets(payload, screening_analysis_name="   ", on_exists="overwrite")
    assert result["updated"] == 1


# ── Material bundles (server-side bundle endpoints) ───────────────────────────

_BUNDLE_FIXTURE = "reference_data/prisma_cloud/example_payloads/material_bundle_Zeolite_13X.json"
_SKIP_NO_BUNDLE_FIXTURE = pytest.mark.skipif(
    not os.path.exists(_BUNDLE_FIXTURE),
    reason=f"Local fixture {_BUNDLE_FIXTURE} not available",
)


def _load_bundle_fixture() -> dict:
    with open(_BUNDLE_FIXTURE, "r", encoding="utf-8") as f:
        return json.load(f)


def _bundle_envelope(results: list, missing: list | None = None) -> dict:
    return {"_schema": "prisma_v2.material.bundle.v1",
            "count": len(results),
            "missing": missing or [],
            "sections": list(_BUNDLE_SECTIONS),
            "results": results}


@resp_lib.activate
@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Offline development fixture test is disabled in CI",
)
@_SKIP_NO_BUNDLE_FIXTURE
def test_get_material_bundles_single_name_returns_bundle_fixture(api):
    fixture = _load_bundle_fixture()
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([fixture]), status=200,
                 match=[matchers.query_param_matcher(
                     {"names": "Zeolite_13X", "match": "exact"})])
    result = api.get_material_bundles("Zeolite_13X")
    assert result == fixture
    assert result["material"]["id"] == 84368
    assert result["sections"] == list(_BUNDLE_SECTIONS)
    # mof_h2 is a single object or None, never a list
    assert not isinstance(result["mof_h2"], list)


@resp_lib.activate
def test_get_material_bundles_single_id_uses_detail_route(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/84368/bundle/",
                 json={"_schema": "prisma_v2.material.bundle.v1",
                       "material": {"id": 84368, "name": "Zeolite_13X"},
                       "sections": list(_BUNDLE_SECTIONS),
                       "counts": {"cifs": 2}},
                 status=200)
    result = api.get_material_bundles(84368)
    assert result["material"]["name"] == "Zeolite_13X"
    assert result["counts"]["cifs"] == 2


@resp_lib.activate
def test_get_material_bundles_list_returns_envelope_with_missing(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope(
                     [{"material": {"id": 84368, "name": "Zeolite_13X"}}],
                     missing=["NoSuchMaterial"]),
                 status=200)
    result = api.get_material_bundles(["Zeolite_13X", "NoSuchMaterial"])
    assert result["count"] == 1
    assert result["missing"] == ["NoSuchMaterial"]
    assert result["sections"] == list(_BUNDLE_SECTIONS)
    assert result["results"][0]["material"]["name"] == "Zeolite_13X"


@resp_lib.activate
def test_get_material_bundles_sends_section_filters(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"id": 1, "name": "M"}}]),
                 status=200,
                 match=[matchers.query_param_matcher(
                     {"names": "M", "match": "contains",
                      "sections": "cifs,isotherms", "exclude": "water_kpis",
                      "include_cif_content": "true"})])
    api.get_material_bundles(["M"], sections=["cifs", "isotherms"],
                             exclude="water_kpis", include_cif_content=True,
                             match="contains")


@resp_lib.activate
def test_get_material_bundles_never_sends_format_param(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"id": 1, "name": "M"}}]),
                 status=200)
    api.get_material_bundles(["M"])
    assert "format=" not in resp_lib.calls[0].request.url


@resp_lib.activate
def test_get_material_bundles_batches_over_the_cap(api):
    names = [f"M{i}" for i in range(250)]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope(
                     [{"material": {"name": n}} for n in names[:200]]), status=200)
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope(
                     [{"material": {"name": n}} for n in names[200:]],
                     missing=["M249"]), status=200)
    result = api.get_material_bundles(names)
    assert len(resp_lib.calls) == 2
    assert result["count"] == 250
    assert result["missing"] == ["M249"]


@resp_lib.activate
def test_get_material_bundles_bulk_404_folds_into_missing(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json={"detail": "No materials matched."}, status=404)
    result = api.get_material_bundles(["NoSuchMaterial"])
    assert result["count"] == 0
    assert result["missing"] == ["NoSuchMaterial"]


@resp_lib.activate
def test_get_material_bundles_single_name_no_match_raises(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([], missing=["NoSuchMaterial"]), status=200)
    with pytest.raises(ValueError, match="No material matched"):
        api.get_material_bundles("NoSuchMaterial")


@resp_lib.activate
def test_get_material_bundles_single_name_multiple_matches_raises(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"name": "Zeolite_13X"}},
                                        {"material": {"name": "Zeolite_5A"}}]),
                 status=200)
    with pytest.raises(ValueError, match="matched 2 materials"):
        api.get_material_bundles("Zeolite", match="contains")


@resp_lib.activate
def test_get_material_bundles_http_error_is_passed_through(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json={"detail": "Invalid API key."}, status=403)
    with pytest.raises(requests.HTTPError):
        api.get_material_bundles(["Zeolite_13X"])


@resp_lib.activate
def test_get_material_bundles_uses_post_body_when_requested(api):
    resp_lib.add(resp_lib.POST, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"name": "Zeolite_13X"}}]),
                 status=200,
                 match=[matchers.json_params_matcher(
                     {"names": ["Zeolite_13X"], "match": "exact"})])
    result = api.get_material_bundles(["Zeolite_13X"], use_post=True)
    assert result["count"] == 1


@resp_lib.activate
def test_get_material_bundles_zip_writes_file(api, tmp_path):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 body=b"PK\x03\x04zipbytes", status=200,
                 content_type="application/zip",
                 headers={"Content-Disposition": 'attachment; filename="bundles.zip"'},
                 match=[matchers.query_param_matcher(
                     {"names": "Zeolite_13X", "match": "exact", "output": "zip"})])
    path = api.get_material_bundles(["Zeolite_13X"], output="zip", save_path=tmp_path)
    assert path == tmp_path / "bundles.zip"
    assert path.read_bytes() == b"PK\x03\x04zipbytes"


@resp_lib.activate
def test_get_material_bundles_zip_explicit_filename(api, tmp_path):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 body=b"PK\x03\x04", status=200, content_type="application/zip")
    target = tmp_path / "nested" / "my_bundles.zip"
    path = api.get_material_bundles(["Zeolite_13X"], output="zip", save_path=target)
    assert path == target and path.exists()


def test_get_material_bundles_zip_over_cap_raises(api):
    with pytest.raises(ValueError, match="capped at 200"):
        api.get_material_bundles([f"M{i}" for i in range(201)], output="zip")


def test_get_material_bundles_requires_names_or_ids(api):
    with pytest.raises(ValueError, match="at least one material"):
        api.get_material_bundles()


def test_get_material_bundles_rejects_unknown_section(api):
    with pytest.raises(ValueError, match="Unknown section name"):
        api.get_material_bundles("Zeolite_13X", sections=["cifs", "not_a_section"])


def test_get_material_bundles_rejects_bad_match_and_output(api):
    with pytest.raises(ValueError, match="match must be"):
        api.get_material_bundles("Zeolite_13X", match="fuzzy")
    with pytest.raises(ValueError, match="output must be"):
        api.get_material_bundles("Zeolite_13X", output="csv")


def test_get_material_bundles_rejects_non_integer_id(api):
    with pytest.raises(ValueError, match="must be integers"):
        api.get_material_bundles(ids=["not-an-id"])


@resp_lib.activate
def test_get_material_bundles_post_body_uses_real_booleans(api):
    resp_lib.add(resp_lib.POST, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"name": "Zeolite_13X"}}]),
                 status=200,
                 match=[matchers.json_params_matcher(
                     {"include_cif_content": True,
                      "names": ["Zeolite_13X"], "match": "exact"})])
    api.get_material_bundles(["Zeolite_13X"], include_cif_content=True, use_post=True)


@resp_lib.activate
def test_get_material_bundles_id_list_uses_bulk_route(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 json=_bundle_envelope([{"material": {"id": 84368, "name": "Zeolite_13X"}}]),
                 status=200,
                 match=[matchers.query_param_matcher({"ids": "84368"})])
    result = api.get_material_bundles(ids=[84368])
    assert result["results"][0]["material"]["id"] == 84368


@resp_lib.activate
def test_get_material_bundles_zip_by_id(api, tmp_path):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/bundle/",
                 body=b"PK\x03\x04", status=200, content_type="application/zip",
                 match=[matchers.query_param_matcher({"ids": "84368", "output": "zip"})])
    path = api.get_material_bundles(ids=[84368], output="zip", save_path=tmp_path)
    assert path == tmp_path / "material_bundles.zip"


# ── Material bundle upsert ────────────────────────────────────────────────────

_CIF_FIXTURE = "reference_data/prisma_cloud/example_payloads/Zeolite_13X.cif"
_SKIP_NO_CIF_FIXTURE = pytest.mark.skipif(
    not os.path.exists(_CIF_FIXTURE),
    reason=f"Local fixture {_CIF_FIXTURE} not available",
)
_UPSERT_URL = f"{PROD_BASE}/materials/bundle/upsert/"


_SAMPLE_CIF = """data_Zeolite_13X

_cell_length_a    25.077
_cell_length_b    25.077
_cell_length_c    25.077
_cell_angle_alpha 90
_cell_angle_beta  90
_cell_angle_gamma 90
_cell_volume      15769.8

_symmetry_cell_setting          cubic
_symmetry_space_group_name_Hall 'P 1'
_symmetry_space_group_name_H-M  'P 1'
_symmetry_Int_Tables_number     1

loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
O1Al     O      0.001400     0.747600     0.891300
O2Al     O      0.108700     0.498600     0.752400
Si       Si     0.124300     0.535300     0.804500
Al       Al     0.036000     0.625400     0.805300
Na       Na     0.200000     0.200000     0.200000
"""


@pytest.fixture
def cif_file(tmp_path) -> Path:
    """A small on-disk CIF, so CIF tests do not depend on reference_data."""
    path = tmp_path / "Zeolite_13X.cif"
    path.write_text(_SAMPLE_CIF, encoding="utf-8")
    return path


def _upsert_report(updated: dict | None = None, created: dict | None = None) -> dict:
    return {"_schema": "prisma_v2.material.bundle.upsert.v1",
            "materials": 1,
            "created": created or {},
            "updated": updated or {},
            "results": [{"material": {"id": 84368, "name": "Zeolite_13X",
                                      "created": False},
                         "created": created or {}, "updated": updated or {}}]}


def _minimal_bundle(name: str = "Zeolite_13X") -> dict:
    return {"material": {"name": name},
            "isotherms": [{"molecule": "CO2", "T_ref_K": 283.15, "sim_or_exp": "sim"}]}


def _multipart_fields(request) -> dict[str, bytes]:
    """Split a multipart request body into {part name: raw value}."""
    body = request.body if isinstance(request.body, bytes) else request.body.encode()
    boundary = request.headers["Content-Type"].split("boundary=")[1].encode()
    fields = {}
    for chunk in body.split(b"--" + boundary):
        if b'name="' not in chunk:
            continue
        head, _, value = chunk.partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = value[:-2] if value.endswith(b"\r\n") else value
    return fields


@resp_lib.activate
@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Offline development fixture test is disabled in CI",
)
@_SKIP_NO_BUNDLE_FIXTURE
def test_upsert_material_bundles_round_trips_read_fixture(api):
    fixture = _load_bundle_fixture()
    resp_lib.add(resp_lib.PUT, _UPSERT_URL,
                 json=_upsert_report(updated={"cifs": 1, "isotherms": 2,
                                              "water_kpis": 2, "carbon_zeopp": 1,
                                              "carbon_zeopp_experimental": 1}),
                 status=200,
                 match=[matchers.query_param_matcher({"create_materials": "true"})])
    result = api.upsert_material_bundles(fixture)
    # The read document is forwarded unchanged — computed keys and all.
    sent = json.loads(resp_lib.calls[0].request.body)
    assert sent == fixture
    assert result["updated"]["isotherms"] == 2
    assert result["created"] == {}


@resp_lib.activate
def test_upsert_material_bundles_list_sends_list_body(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles([_minimal_bundle("A"), _minimal_bundle("B")])
    sent = json.loads(resp_lib.calls[0].request.body)
    assert isinstance(sent, list) and len(sent) == 2
    assert [b["material"]["name"] for b in sent] == ["A", "B"]


@resp_lib.activate
def test_upsert_material_bundles_create_materials_false(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200,
                 match=[matchers.query_param_matcher({"create_materials": "false"})])
    api.upsert_material_bundles(_minimal_bundle(), create_materials=False)


@resp_lib.activate
@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Offline development fixture test is disabled in CI",
)
@_SKIP_NO_BUNDLE_FIXTURE
def test_upsert_material_bundles_strip_ids_for_another_database(api):
    fixture = _load_bundle_fixture()
    resp_lib.add(resp_lib.PUT, _UPSERT_URL,
                 json=_upsert_report(created={"isotherms": 2}), status=200)
    api.upsert_material_bundles(
        fixture, strip_ids=True,
        tag_names={2: "MOFevaluator", 1: "PrISMa V1"})
    sent = json.loads(resp_lib.calls[0].request.body)
    assert "id" not in sent["material"]
    assert sent["material"]["name"] == "Zeolite_13X"
    for section in ("cifs", "isotherms", "water_kpis", "carbon_zeopp"):
        assert all("id" not in row for row in sent[section])
    # Tag ids are database-local and must travel as names
    assert sent["water_kpis"][0]["tags"] == ["MOFevaluator", "PrISMa V1"]
    # The caller's document is untouched
    assert fixture["material"]["id"] == 84368
    assert fixture["water_kpis"][0]["tags"] == [2, 1]


def test_upsert_material_bundles_strip_ids_rejects_untranslated_tags(api):
    bundle = {"material": {"name": "Zeolite_13X"},
              "water_kpis": [{"molecule": "H2O", "tags": [2, 1]}]}
    with pytest.raises(ValueError, match="tag ids"):
        api.upsert_material_bundles(bundle, strip_ids=True)


@resp_lib.activate
def test_upsert_material_bundles_keeps_tag_names_untouched(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Z"},
              "water_kpis": [{"molecule": "H2O", "tags": ["MOFevaluator"]}]}
    api.upsert_material_bundles(bundle, strip_ids=True)
    sent = json.loads(resp_lib.calls[0].request.body)
    assert sent["water_kpis"][0]["tags"] == ["MOFevaluator"]


@resp_lib.activate
def test_upsert_material_bundles_uploads_cif_as_multipart(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL,
                 json=_upsert_report(updated={"cifs": 1}), status=200)
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"id": 18710, "filename": "cifs/Zeolite_13X.cif",
                        "primary": True}]}
    api.upsert_material_bundles(bundle, cif_files=cif_file)

    request = resp_lib.calls[0].request
    assert request.method == "POST"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    fields = _multipart_fields(request)
    sent = json.loads(fields["bundle"])
    row = sent["cifs"][0]
    # The existing metadata row is matched by file name and points at the part
    assert len(sent["cifs"]) == 1
    assert row["file"] == "cif_0_0"
    assert row["id"] == 18710
    assert "content" not in row
    with open(cif_file, "rb") as f:
        assert fields["cif_0_0"] == f.read()


@resp_lib.activate
def test_upsert_material_bundles_cif_without_matching_row_is_appended(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles({"material": {"name": "Zeolite_13X"}},
                                cif_files=cif_file)
    sent = json.loads(_multipart_fields(resp_lib.calls[0].request)["bundle"])
    row = sent["cifs"][0]
    assert len(sent["cifs"]) == 1
    assert row["primary"] is True and row["file"] == "cif_0_0"
    # the appended row describes the file it carries
    assert row["chemical_formula"] == "Al1Na1O2Si1"
    assert row["cell_length_a"] == 25.077


@resp_lib.activate
def test_upsert_material_bundles_inline_cif_content(api, cif_file):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles({"material": {"name": "Zeolite_13X"}},
                                cif_files=cif_file, inline_cifs=True)
    request = resp_lib.calls[0].request
    assert request.headers["Content-Type"] == "application/json"
    row = json.loads(request.body)["cifs"][0]
    with open(cif_file, "r", encoding="utf-8") as f:
        assert row["content"] == f.read()
    assert row["filename"] == "cifs/Zeolite_13X.cif"
    assert "file" not in row


@resp_lib.activate
def test_upsert_material_bundles_cif_mapping_by_material_name(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles(
        [_minimal_bundle("Other"), _minimal_bundle("Zeolite_13X")],
        cif_files={"Zeolite_13X": cif_file})
    fields = _multipart_fields(resp_lib.calls[0].request)
    sent = json.loads(fields["bundle"])
    assert "cifs" not in sent[0]
    assert sent[1]["cifs"][0]["file"] == "cif_1_0"
    assert "cif_1_0" in fields


def test_upsert_material_bundles_cif_mapping_unknown_name(api, cif_file):
    with pytest.raises(ValueError, match="matches no bundle"):
        api.upsert_material_bundles(_minimal_bundle("Zeolite_13X"),
                                    cif_files={"Nope": cif_file})


def test_upsert_material_bundles_cif_path_needs_mapping_for_many_bundles(api, cif_file):
    with pytest.raises(ValueError, match="mapping"):
        api.upsert_material_bundles([_minimal_bundle("A"), _minimal_bundle("B")],
                                    cif_files=cif_file)


def test_upsert_material_bundles_missing_cif_file(api):
    with pytest.raises(FileNotFoundError):
        api.upsert_material_bundles(_minimal_bundle(), cif_files="no_such.cif")


def test_upsert_material_bundles_rejects_populated_readonly_section(api):
    bundle = {**_minimal_bundle(), "mofchecker": [{"structure": "Zeolite_13X"}]}
    with pytest.raises(ValueError, match="upsert_mofchecker"):
        api.upsert_material_bundles(bundle)


@resp_lib.activate
def test_upsert_material_bundles_allows_empty_readonly_section(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles({**_minimal_bundle(), "mofchecker": [],
                                 "heat_capacity": []})
    assert json.loads(resp_lib.calls[0].request.body)["mofchecker"] == []


def test_upsert_material_bundles_rejects_unknown_section(api):
    with pytest.raises(ValueError, match="Unknown key"):
        api.upsert_material_bundles({**_minimal_bundle(), "isoterms": []})


def test_upsert_material_bundles_requires_material(api):
    with pytest.raises(ValueError, match="needs a 'material'"):
        api.upsert_material_bundles({"isotherms": []})
    with pytest.raises(ValueError, match="needs a 'material'"):
        api.upsert_material_bundles({"material": {"formula": "Al86"}})


def test_upsert_material_bundles_rejects_bad_input(api):
    with pytest.raises(TypeError, match="bundle dict"):
        api.upsert_material_bundles("Zeolite_13X")
    with pytest.raises(ValueError, match="No bundles"):
        api.upsert_material_bundles([])
    with pytest.raises(ValueError, match="method must be"):
        api.upsert_material_bundles(_minimal_bundle(), method="patch")


@resp_lib.activate
def test_upsert_material_bundles_warns_on_partial_success(api):
    body = {"_schema": "prisma_v2.material.bundle.upsert.v1",
            "materials": 2,
            "created": {"isotherms": 1}, "updated": {},
            "results": [{"material": {"id": 1, "name": "A", "created": True},
                         "created": {"isotherms": 1}, "updated": {}}],
            "errors": [{"index": 1, "material": "B",
                        "error": "Unknown Molecule 'X'"}]}
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=body, status=207)
    with pytest.warns(UserWarning, match="Retry only those indices"):
        result = api.upsert_material_bundles([_minimal_bundle("A"),
                                              _minimal_bundle("B")])
    assert result["errors"][0]["index"] == 1
    assert result["results"][0]["material"]["name"] == "A"


@resp_lib.activate
def test_upsert_material_bundles_http_error_is_passed_through(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL,
                 json={"detail": "Invalid API key."}, status=403)
    with pytest.raises(requests.HTTPError):
        api.upsert_material_bundles(_minimal_bundle())


@resp_lib.activate
def test_upsert_material_bundles_method_override(api):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles(_minimal_bundle(), method="post")
    assert resp_lib.calls[0].request.method == "POST"


@resp_lib.activate
def test_upsert_material_bundles_sends_api_key_with_multipart(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles(_minimal_bundle(), cif_files=cif_file)
    assert resp_lib.calls[0].request.headers["X-API-Key"] == "test-api-key"


@resp_lib.activate
def test_upsert_material_bundles_uses_dev_mode_base_url(dev_api):
    resp_lib.add(resp_lib.PUT, f"{dev_api._base_url()}/materials/bundle/upsert/",
                 json=_upsert_report(), status=200)
    assert dev_api.upsert_material_bundles(_minimal_bundle())["materials"] == 1


def test_upsert_material_bundles_rejects_non_dict_bundle_in_list(api):
    with pytest.raises(TypeError, match=r"bundles\[1\] must be a dict"):
        api.upsert_material_bundles([_minimal_bundle(), "Zeolite_13X"])


def test_upsert_material_bundles_strip_ids_needs_a_name(api):
    with pytest.raises(ValueError, match="needs a 'name' once ids are stripped"):
        api.upsert_material_bundles({"material": {"id": 84368}}, strip_ids=True)


@resp_lib.activate
def test_upsert_material_bundles_strip_ids_covers_mof_h2_object(api):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Z"},
              "mof_h2": {"id": 99, "mof": "Z", "capacity": 1.2},
              "h2_results": [{"id": 7, "case_study_h2": "base"}]}
    api.upsert_material_bundles(bundle, strip_ids=True)
    sent = json.loads(resp_lib.calls[0].request.body)
    assert sent["mof_h2"] == {"mof": "Z", "capacity": 1.2}
    assert sent["h2_results"] == [{"case_study_h2": "base"}]


@resp_lib.activate
def test_upsert_material_bundles_accepts_several_cif_paths(api, tmp_path, cif_file):
    second = tmp_path / "Zeolite_13X_alt.cif"
    second.write_text("data_Zeolite_13X_alt\n", encoding="utf-8")
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles({"material": {"name": "Zeolite_13X"}},
                                cif_files=[cif_file, second])
    fields = _multipart_fields(resp_lib.calls[0].request)
    rows = json.loads(fields["bundle"])["cifs"]
    assert [r["file"] for r in rows] == ["cif_0_0", "cif_0_1"]
    # Only the first CIF a material gets is marked primary
    assert [r["primary"] for r in rows] == [True, False]
    assert fields["cif_0_1"] == b"data_Zeolite_13X_alt\n"


def test_upsert_material_bundles_rejects_cif_row_with_content_and_file(api, cif_file):
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"filename": "cifs/Zeolite_13X.cif",
                        "content": "data_Zeolite_13X", "file": "part"}]}
    with pytest.raises(ValueError, match="mutually exclusive"):
        api.upsert_material_bundles(bundle, cif_files=cif_file)


def test_upsert_material_bundles_rejects_non_list_cifs(api, cif_file):
    with pytest.raises(ValueError, match=r"\['cifs'\] must be a list"):
        api.upsert_material_bundles({"material": {"name": "Z"}, "cifs": {}},
                                    cif_files=cif_file)


# ── CIF metadata derivation ───────────────────────────────────────────────────

@pytest.mark.skipif(
    os.getenv("CI", "").lower() == "true",
    reason="Offline development fixture test is disabled in CI",
)
@_SKIP_NO_CIF_FIXTURE
def test_parse_cif_metadata_reproduces_stored_row():
    """The client derives exactly what the stored cifs row carries."""
    with open(_CIF_FIXTURE, "r", encoding="utf-8") as f:
        derived = _parse_cif_metadata(f.read())
    stored = _load_bundle_fixture()["cifs"][0]
    for column, value in derived.items():
        assert stored[column] == value, f"{column}: {value!r} != {stored[column]!r}"
    # Everything structural is covered; only identity/provenance is left to the server
    assert {k for k, v in stored.items() if v not in (None, "", [])} - set(derived) == {
        "id", "mof", "tags", "primary", "filename", "file_url", "uploaded_at"}


def test_parse_cif_metadata_fields(cif_file):
    derived = _parse_cif_metadata(cif_file.read_text(encoding="utf-8"))
    assert derived == {
        "cell_length_a": 25.077, "cell_length_b": 25.077, "cell_length_c": 25.077,
        "cell_angle_alpha": 90.0, "cell_angle_beta": 90.0, "cell_angle_gamma": 90.0,
        "cell_volume": 15769.8,
        "symmetry_cell_setting": "cubic",
        "symmetry_space_group_name_Hall": "P 1",
        "symmetry_space_group_name_H_M": "P 1",
        "symmetry_Int_Tables_number": 1,
        # legacy _symmetry_* names also fill the modern space group columns
        "space_group_name_Hall": "P 1",
        "space_group_name_H_M_alt": "P 1",
        # counted from the atom loop, alphabetically, with explicit counts
        "chemical_formula_descriptive": "Al1 Na1 O2 Si1",
        "chemical_formula": "Al1Na1O2Si1",
        "chemical_formula_sum": "Al1Na1O2Si1",
    }


def test_parse_cif_metadata_uses_type_symbol_not_site_label():
    # 'O2Al' is a site label for an oxygen, not an aluminium
    text = ("loop_\n_atom_site_label\n_atom_site_type_symbol\n"
            "O2Al O\nO1Si O\nAL1 Al\n")
    assert _parse_cif_metadata(text)["chemical_formula"] == "Al1O2"


def test_parse_cif_metadata_handles_quirks():
    text = ("data_x\n"
            "_cell_length_a 25.077(3)\n"        # uncertainty
            "_cell_volume ?\n"                  # unknown
            "_chemical_name_common .\n"         # inapplicable
            "_chemical_formula_sum 'Al2 O3'\n"  # explicit tag wins
            "_symmetry_Int_Tables_number 1\n"
            "loop_\n_atom_site_type_symbol\nO2-\nO2-\nAl3+\n")
    derived = _parse_cif_metadata(text)
    assert derived["cell_length_a"] == 25.077
    assert "cell_volume" not in derived and "chemical_name_common" not in derived
    assert derived["chemical_formula_sum"] == "Al2 O3"
    assert derived["chemical_formula"] == "Al1O2"   # still counted from the loop


def test_parse_cif_metadata_ignores_text_blocks():
    text = ("data_x\n_audit_note\n;\n_cell_length_a 99\n;\n_cell_length_a 25.077\n")
    assert _parse_cif_metadata(text)["cell_length_a"] == 25.077


@resp_lib.activate
def test_upsert_material_bundles_derives_metadata_over_stale_row(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"id": 18710, "filename": "cifs/Zeolite_13X.cif",
                        "chemical_formula": "Stale99", "cell_length_a": 1.0,
                        "tags": ["MOFevaluator"]}]}
    api.upsert_material_bundles(bundle, cif_files=cif_file)
    row = json.loads(_multipart_fields(resp_lib.calls[0].request)["bundle"])["cifs"][0]
    assert row["chemical_formula"] == "Al1Na1O2Si1"
    assert row["cell_length_a"] == 25.077
    # identity and curated fields are untouched
    assert row["id"] == 18710 and row["tags"] == ["MOFevaluator"]


@resp_lib.activate
def test_upsert_material_bundles_derive_fill_keeps_set_values(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"filename": "cifs/Zeolite_13X.cif",
                        "chemical_formula": "KeepMe", "cell_volume": None}]}
    api.upsert_material_bundles(bundle, cif_files=cif_file,
                                derive_cif_metadata="fill")
    row = json.loads(_multipart_fields(resp_lib.calls[0].request)["bundle"])["cifs"][0]
    assert row["chemical_formula"] == "KeepMe"      # already set, left alone
    assert row["cell_volume"] == 15769.8            # was None, filled
    assert row["cell_length_a"] == 25.077           # absent, filled


@resp_lib.activate
def test_upsert_material_bundles_derive_disabled(api, cif_file):
    resp_lib.add(resp_lib.POST, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"filename": "cifs/Zeolite_13X.cif", "chemical_formula": "Stale99"}]}
    api.upsert_material_bundles(bundle, cif_files=cif_file, derive_cif_metadata=False)
    row = json.loads(_multipart_fields(resp_lib.calls[0].request)["bundle"])["cifs"][0]
    assert row == {"filename": "cifs/Zeolite_13X.cif", "chemical_formula": "Stale99",
                   "file": "cif_0_0"}


@resp_lib.activate
def test_upsert_material_bundles_derives_from_inline_content(api):
    """A bundle read with include_cif_content=true carries its own structure."""
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    bundle = {"material": {"name": "Zeolite_13X"},
              "cifs": [{"filename": "cifs/Zeolite_13X.cif", "content": _SAMPLE_CIF}]}
    api.upsert_material_bundles(bundle)
    row = json.loads(resp_lib.calls[0].request.body)["cifs"][0]
    assert row["chemical_formula"] == "Al1Na1O2Si1"
    assert row["symmetry_cell_setting"] == "cubic"


@resp_lib.activate
def test_upsert_material_bundles_inline_cifs_derive_once(api, cif_file):
    resp_lib.add(resp_lib.PUT, _UPSERT_URL, json=_upsert_report(), status=200)
    api.upsert_material_bundles({"material": {"name": "Zeolite_13X"}},
                                cif_files=cif_file, inline_cifs=True)
    row = json.loads(resp_lib.calls[0].request.body)["cifs"][0]
    assert row["content"] == _SAMPLE_CIF
    assert row["chemical_formula"] == "Al1Na1O2Si1"


def test_upsert_material_bundles_rejects_bad_derive_mode(api):
    with pytest.raises(ValueError, match="derive_cif_metadata must be"):
        api.upsert_material_bundles(_minimal_bundle(), derive_cif_metadata="yes")


# ── AutoPrism: HTTP 207 row errors and nested id checks ───────────────────────

_ROW_ERROR_BODY = {
    "created": 0,
    "updated": 0,
    "errors": [{"item": {"md5": "a1"}, "errors": {"mixture": ["id is required when mixture is an object"]}}],
}


@pytest.fixture
def no_git_meta(api, monkeypatch):
    monkeypatch.setattr(api, "_resolve_meta_provenance", lambda meta=None, repo_dir=None: meta or {})
    return api


@resp_lib.activate
def test_table_upsert_warns_on_207_row_errors(no_git_meta):
    from prisma_api import PrismaRowErrorWarning
    api = no_git_meta
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/adsorption-singlepoint/", json=_ROW_ERROR_BODY, status=207)

    with pytest.warns(PrismaRowErrorWarning, match="rejected 1 row"):
        result = api.upsert_adsorption_singlepoint({"md5": "a1"})
    assert result["errors"] == _ROW_ERROR_BODY["errors"]


@resp_lib.activate
def test_table_upsert_raise_on_error_207(no_git_meta):
    from prisma_api import PrismaUpsertError
    api = no_git_meta
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/adsorption-singlepoint/", json=_ROW_ERROR_BODY, status=207)

    with pytest.raises(PrismaUpsertError, match="id is required") as info:
        api.upsert_adsorption_singlepoint({"md5": "a1"}, raise_on_error=True)
    assert info.value.result == _ROW_ERROR_BODY


@resp_lib.activate
def test_computation_runs_upsert_raise_on_error_207(api):
    from prisma_api import PrismaUpsertError
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/computation-runs/", json=_ROW_ERROR_BODY, status=207)
    with pytest.raises(PrismaUpsertError):
        api.upsert_computation_runs({"id": "r1"}, raise_on_error=True)


@resp_lib.activate
def test_collection_marks_207_sections_failed(no_git_meta):
    import warnings as _warnings

    from prisma_api import PrismaRowErrorWarning, PrismaUpsertError
    api = no_git_meta
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/adsorption-singlepoint/", json=_ROW_ERROR_BODY, status=207)
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/",
                 json={"created": 2, "updated": 0, "errors": _ROW_ERROR_BODY["errors"] * 2}, status=207)
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/zeopp-metrics/", json={"created": 1, "updated": 0})
    payload = {
        "adsorption_singlepoints": [{"md5": "a1"}],
        "heat_capacities": [{"md5": "a1"}, {"md5": "a2"}, {"md5": "a3"}, {"md5": "a4"}],
        "zeopp_metrics": [{"md5": "a1"}],
    }

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = api.upsert_autoprism_collection(payload)
    row_warnings = [w for w in caught if issubclass(w.category, PrismaRowErrorWarning)]
    assert len(row_warnings) == 1  # one summary, not one per section

    assert result["overall_status"] == "partial_failure"
    assert result["totals"] == {"created": 3, "updated": 0, "rejected": 3, "failed_sections": 2,
                                "new_structures": []}
    assert result["sections"]["adsorption_singlepoints"]["status"] == "error"
    assert result["sections"]["adsorption_singlepoints"]["rejected"] == 1
    assert result["sections"]["heat_capacities"]["status"] == "partial"
    assert len(result["sections"]["heat_capacities"]["errors"]) == 2
    assert result["sections"]["zeopp_metrics"]["status"] == "ok"

    with pytest.raises(PrismaUpsertError, match="adsorption_singlepoints: no rows stored; 1 row") as info:
        api.upsert_autoprism_collection(payload, raise_on_error=True)
    assert info.value.result["totals"]["rejected"] == 3


@pytest.mark.parametrize("row, missing", [
    ({"mixture": {}}, "mixture"),
    ({"config": {"config_hash": ""}}, "config"),
    ({"result": {}}, "result"),
    ({"run": {"step": "x", "workflow": {"id": "w"}}}, "run"),
    ({"run": {"id": "r", "workflow": {}}}, "run.workflow"),
])
def test_check_ids_rejects_nested_objects_without_id(no_git_meta, row, missing):
    with pytest.raises(ValueError, match=f"row 0: {missing}"):
        no_git_meta.upsert_adsorption_singlepoint({"structure": {"name": "X"}, **row})


@resp_lib.activate
def test_check_ids_allows_structure_by_name_and_can_be_disabled(no_git_meta):
    api = no_git_meta
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/", json={"created": 1, "updated": 0})
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/mofchecker/", json={"created": 1, "updated": 0})
    api.upsert_heat_capacity({"structure": {"name": "X"}, "run": {"id": "r", "workflow": {"id": "w"}}})
    api.upsert_mofchecker({"run": {"step": "no-id"}}, check_ids=False)
    assert len(resp_lib.calls) == 2


_MOCK_DIR = Path(__file__).resolve().parents[1] / "reference_data" / "autoprism" / "01"


@pytest.mark.skipif(not _MOCK_DIR.exists(), reason="AutoPrism mock payloads not present")
def test_autoprism_mock_payloads_pass_id_check():
    from prisma_api.prisma_api_v2 import _check_nested_ids
    payload = json.loads((_MOCK_DIR / "mock_payload_all_autoprism.json").read_text())
    for section in ("adsorption_singlepoints", "heat_capacities", "adsorption_isotherms",
                    "mofchecker", "zeopp_metrics"):
        _check_nested_ids(payload.get(section, []), section)


# ── prisma_cloud 0.6.16: 400 bodies, match-by-value, adsorption_isotherm, notices ──

_NO_ROWS_BODY = {
    "created": 0,
    "updated": 0,
    "errors": [{"item": {"md5": "a1"}, "errors": {"structure": ["ambiguous"]}}],
}


@resp_lib.activate
def test_put_returns_400_upsert_body(api):
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/", json=_NO_ROWS_BODY, status=400)
    assert api._put("/heat-capacity/", [{}], upsert_body_on_400=True) == _NO_ROWS_BODY

    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/mofchecker/", json={"detail": "bad"}, status=400)
    with pytest.raises(requests.HTTPError):
        api._put("/mofchecker/", [{}], upsert_body_on_400=True)


@resp_lib.activate
def test_put_400_raises_for_callers_that_do_not_report_row_errors(api):
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/region-costs/", json=_NO_ROWS_BODY, status=400)
    with pytest.raises(requests.HTTPError):
        api.upsert_region_costs(pd.DataFrame({"region": ["UK"]}))


@resp_lib.activate
def test_table_upsert_warns_no_rows_stored_on_400(no_git_meta):
    from prisma_api import PrismaRowErrorWarning
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/", json=_NO_ROWS_BODY, status=400)
    with pytest.warns(PrismaRowErrorWarning, match="no rows stored; server rejected 1 row"):
        result = no_git_meta.upsert_heat_capacity({"md5": "a1"})
    assert result == _NO_ROWS_BODY


@resp_lib.activate
def test_table_upsert_raise_on_error_400(no_git_meta):
    from prisma_api import PrismaUpsertError
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/", json=_NO_ROWS_BODY, status=400)
    with pytest.raises(PrismaUpsertError, match="no rows stored") as info:
        no_git_meta.upsert_heat_capacity({"md5": "a1"}, raise_on_error=True)
    assert info.value.result == _NO_ROWS_BODY


@resp_lib.activate
def test_collection_marks_400_section_error(no_git_meta):
    import warnings as _warnings

    from prisma_api import PrismaUpsertError
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/mofchecker/", json=_NO_ROWS_BODY, status=400)
    payload = {"mofchecker": [{"md5": "a1"}]}

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        result = no_git_meta.upsert_autoprism_collection(payload)
    assert result["sections"]["mofchecker"]["status"] == "error"
    assert result["sections"]["mofchecker"]["rejected"] == 1
    assert result["overall_status"] == "partial_failure"

    with pytest.raises(PrismaUpsertError, match="mofchecker: no rows stored"):
        no_git_meta.upsert_autoprism_collection(payload, raise_on_error=True)


def test_check_ids_allows_mixture_and_config_by_value():
    from prisma_api.prisma_api_v2 import _check_nested_ids
    _check_nested_ids([
        {"mixture": {"mixture_id": "m1"}, "config": {"config_hash": "abc"}},
        {"mixture": {}, "mixture_id": "m1", "config": {}, "config_hash": "abc"},  # flat fields
    ], "adsorption_singlepoints")
    for row in ({"mixture": {}}, {"config": {}}):
        with pytest.raises(ValueError, match="mixture_id"):
            _check_nested_ids([row], "adsorption_singlepoints")
    with pytest.raises(ValueError, match="row 0: run"):
        _check_nested_ids([{"run": {"step": "x"}}], "adsorption_singlepoints")


@resp_lib.activate
def test_upsert_adsorption_isotherm_puts_and_unwraps(no_git_meta):
    rows = [{"structure": {"name": "X"}, "component": "CO2", "pressure_bar": 1.0}]
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/adsorption-isotherm/",
        match=[matchers.json_params_matcher([{**rows[0], "meta_provenance": {}}])],
        json={"created": 1, "updated": 0},
    )
    assert no_git_meta.upsert_adsorption_isotherm({"adsorption_isotherms": rows})["created"] == 1


@resp_lib.activate
def test_get_adsorption_isotherm_component_filter(api):
    resp_lib.add(
        resp_lib.GET,
        f"{PROD_BASE}/adsorption-isotherm/",
        match=[matchers.query_param_matcher({"component": "CO2", "limit": "500", "offset": "0"})],
        json=_envelope([{"id": 1, "component": "CO2"}]),
    )
    df = api.get_adsorption_isotherm(component="CO2")
    assert df.iloc[0]["component"] == "CO2"


def test_collection_splits_mixed_isotherms_by_gas(api, monkeypatch):
    sent = {}
    monkeypatch.setattr(api, "_resolve_meta_provenance", lambda meta=None, repo_dir=None: {})

    def _capture(name):
        def _method(payload, **kwargs):
            sent[name] = payload
            return {"created": len(payload), "updated": 0}
        return _method

    monkeypatch.setattr(api, "upsert_isotherm_h2", _capture("h2"))
    monkeypatch.setattr(api, "upsert_adsorption_isotherm", _capture("other"))
    result = api.upsert_autoprism_collection({
        "isotherms": [{"component": "H2"}, {"component": "CO2"}, {"component": "H2O"}],
        "adsorption_isotherms": [{"component": "N2", "isotherm_id": "existing"}],
    })
    assert "h2" not in sent
    assert [r["component"] for r in sent["other"]] == ["N2", "H2", "CO2", "H2O"]
    assert result["sections"]["isotherm_H2s"]["status"] == "skipped"
    assert result["totals"]["created"] == 4


def test_collection_isotherm_h2s_key_is_deprecated_and_gets_component(api, monkeypatch):
    sent = {}
    monkeypatch.setattr(api, "_resolve_meta_provenance", lambda meta=None, repo_dir=None: {})

    def _capture(payload, **kwargs):
        sent["h2"] = payload
        return {"created": len(payload), "updated": 0}

    monkeypatch.setattr(api, "upsert_isotherm_h2", _capture)
    with pytest.warns(DeprecationWarning, match="isotherm_H2s collection key is deprecated"):
        api.upsert_autoprism_collection({"isotherm_H2s": [{"isotherm_id": "a"},
                                                          {"component": "H2", "isotherm_id": "b"}]})
    assert [r["component"] for r in sent["h2"]] == ["H2", "H2"]


def test_bundle_sections_include_adsorption_isotherm():
    from prisma_api.prisma_api_v2 import _BUNDLE_READONLY_SECTIONS
    assert _BUNDLE_SECTIONS.index("adsorption_isotherm") == _BUNDLE_SECTIONS.index("isotherm_h2") + 1
    assert _BUNDLE_READONLY_SECTIONS["adsorption_isotherm"] == "upsert_adsorption_isotherm"


@resp_lib.activate
def test_upsert_warns_unknown_fields(no_git_meta):
    from prisma_api import PrismaUnknownFieldsWarning
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/zeopp-metrics/",
                 json={"created": 1, "updated": 0, "unknown_fields": {"foo": 1}})
    with pytest.warns(PrismaUnknownFieldsWarning, match="/zeopp-metrics/.*foo"):
        no_git_meta.upsert_zeopp_metrics({"mof": "X", "foo": 1})


@resp_lib.activate
def test_upsert_warns_new_structures(no_git_meta):
    import warnings as _warnings

    from prisma_api import PrismaNewStructureWarning
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/",
                 json={"created": 1, "updated": 0, "new_structures": ["NEWMOF"]})
    with pytest.warns(PrismaNewStructureWarning, match="NEWMOF"):
        no_git_meta.upsert_heat_capacity({"structure": {"name": "NEWMOF"}})
    # raise_on_error does not apply to notices.
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        no_git_meta.upsert_heat_capacity({"structure": {"name": "NEWMOF"}}, raise_on_error=True)


@resp_lib.activate
def test_collection_summarises_unknown_fields_and_new_structures(no_git_meta):
    import warnings as _warnings

    from prisma_api import PrismaNewStructureWarning, PrismaUnknownFieldsWarning
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/",
                 json={"created": 1, "updated": 0, "new_structures": ["B", "A"]})
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/mofchecker/",
                 json={"created": 1, "updated": 0, "new_structures": ["A"],
                       "unknown_fields": {"structure.source_db": 1}})

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = no_git_meta.upsert_autoprism_collection({
            "heat_capacities": [{"md5": "a"}], "mofchecker": [{"md5": "a"}],
        })

    assert result["overall_status"] == "ok"
    assert result["totals"]["new_structures"] == ["A", "B"]
    assert result["sections"]["heat_capacities"]["new_structures"] == ["B", "A"]
    assert result["sections"]["mofchecker"]["unknown_fields"] == {"structure.source_db": 1}
    kinds = [w.category for w in caught]
    assert kinds.count(PrismaNewStructureWarning) == 1
    assert kinds.count(PrismaUnknownFieldsWarning) == 1


# ── 0.4.5: H2 via adsorption_isotherm, exact-match filter, AutoPrism CIFs ──────

@resp_lib.activate
def test_upsert_isotherm_h2_warns_deprecated(no_git_meta):
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/isotherm-h2/", json={"created": 1, "updated": 0})
    with pytest.warns(DeprecationWarning, match="use upsert_adsorption_isotherm with component='H2'"):
        no_git_meta.upsert_isotherm_h2({"structure": "X", "component": "H2"})
    assert resp_lib.calls[0].request.url == f"{PROD_BASE}/isotherm-h2/"


@resp_lib.activate
def test_get_isotherm_h2_warns_deprecated(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherm-h2/", json=_envelope([{"id": 1, "component": "H2"}]))
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherm-h2/1/", json={"id": 1})
    with pytest.warns(DeprecationWarning, match=r"get_adsorption_isotherm\(component='H2'\)"):
        api.get_isotherm_h2(structure="X")
    with pytest.warns(DeprecationWarning, match="get_adsorption_isotherm_item"):
        api.get_isotherm_h2_item(1)
    assert all("/isotherm-h2/" in call.request.url for call in resp_lib.calls)


@resp_lib.activate
def test_upsert_adsorption_isotherm_accepts_h2(no_git_meta):
    import warnings as _warnings
    row = {"structure": {"name": "X"}, "component": "H2", "temperature_K": 77.0, "pressure_bar": 1.0}
    resp_lib.add(
        resp_lib.PUT,
        f"{PROD_BASE}/adsorption-isotherm/",
        match=[matchers.json_params_matcher([{**row, "meta_provenance": {}}])],
        json={"created": 1, "updated": 0},
    )
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        assert no_git_meta.upsert_adsorption_isotherm([row])["created"] == 1


def _fake_collection_getters(api, monkeypatch, seen):
    monkeypatch.setattr(api, "_resolve_meta_provenance", lambda meta=None, repo_dir=None: {})
    rows = {
        "get_computation_runs": [],
        "get_adsorption_singlepoint": [],
        "get_heat_capacity": [],
        "get_isotherm_h2": [{"id": 1, "component": "H2"}],
        "get_adsorption_isotherm": [{"id": 1, "component": "H2"}, {"id": 2, "component": "CO2"}],
        "get_mofchecker": [],
        "get_zeopp_metrics": [],
    }
    for name, records in rows.items():
        def _getter(_name=name, _records=records, **kwargs):
            seen[_name] = kwargs
            return _records
        monkeypatch.setattr(api, name, _getter)


def test_get_autoprism_collection_h2_subset_and_include_flag(api, monkeypatch, capsys):
    seen = {}
    _fake_collection_getters(api, monkeypatch, seen)

    collection = api.get_autoprism_collection(structure="X")
    assert [r["id"] for r in collection["isotherm_H2s"]] == [1]
    # adsorption_isotherms already holds the H2 rows; isotherm_H2s is a subset.
    assert [r["component"] for r in collection["adsorption_isotherms"]] == ["H2", "CO2"]
    assert "isotherm_H2s (H2 subset, deprecated)" in capsys.readouterr().out
    assert "subset" in PrismaAPIv2.get_autoprism_collection.__doc__

    seen.clear()
    collection = api.get_autoprism_collection(structure="X", include_deprecated_h2=False)
    assert "isotherm_H2s" not in collection
    assert "get_isotherm_h2" not in seen
    assert "isotherm_H2s" not in capsys.readouterr().out


@pytest.mark.parametrize("method, path, name_param", [
    ("get_adsorption_singlepoint", "/adsorption-singlepoint/", "structure"),
    ("get_heat_capacity", "/heat-capacity/", "structure"),
    ("get_isotherm_h2", "/isotherm-h2/", "structure"),
    ("get_adsorption_isotherm", "/adsorption-isotherm/", "structure"),
    ("get_mofchecker", "/mofchecker/", "structure"),
    ("get_zeopp_metrics", "/zeopp-metrics/", "mof"),
])
@resp_lib.activate
def test_getters_send_match_only_when_given(api, method, path, name_param):
    import warnings as _warnings
    base = {name_param: "LAGNAK", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}",
                 match=[matchers.query_param_matcher({**base, "match": "exact"})], json=_envelope([]))
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}{path}",
                 match=[matchers.query_param_matcher(base)], json=_envelope([]))
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        getattr(api, method)(**{name_param: "LAGNAK", "match": "exact"})
        getattr(api, method)(**{name_param: "LAGNAK"})
        with pytest.raises(ValueError, match="match must be"):
            getattr(api, method)(**{name_param: "LAGNAK", "match": "fuzzy"})
    assert len(resp_lib.calls) == 2


def test_get_autoprism_collection_forwards_match(api, monkeypatch):
    seen = {}
    _fake_collection_getters(api, monkeypatch, seen)
    api.get_autoprism_collection(structure="LAGNAK", mof="LAGNAK", match="exact")
    named = [name for name in seen if name != "get_computation_runs"]
    assert len(named) == 6
    assert all(seen[name]["match"] == "exact" for name in named)
    assert "match" not in seen["get_computation_runs"]


def test_get_autoprism_collection_rejects_invalid_match_before_requests(api, monkeypatch):
    seen = {}
    _fake_collection_getters(api, monkeypatch, seen)
    with pytest.raises(ValueError, match="match must be"):
        api.get_autoprism_collection(structure="X", match="EXACT")
    assert seen == {}


_CIF_TEXT = "data_LAGNAK\n_cell_length_a 10.0\n_cell_length_b 11.0\n_cell_length_c 12.0\n"
_BUNDLE_UPSERT = f"{PROD_BASE}/materials/bundle/upsert/"


def _cif_md5(text: str = _CIF_TEXT) -> str:
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _bundle_ok(names, created=True):
    return {"materials": len(names), "created": {"cifs": len(names)}, "updated": {},
            "results": [{"material": {"id": i, "name": n, "created": created},
                         "created": {"cifs": 1}, "updated": {}} for i, n in enumerate(names)]}


@resp_lib.activate
def test_upsert_autoprism_cifs_names_files_by_md5(api):
    import warnings as _warnings
    resp_lib.add(resp_lib.PUT, _BUNDLE_UPSERT, json=_bundle_ok(["LAGNAK"], created=False))
    md5 = _cif_md5()
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        result = api.upsert_autoprism_cifs([{"structure": "LAGNAK", "content": _CIF_TEXT, "md5": md5}],
                                           tags=["autoprism"])
    assert result == {"created": 1, "updated": 0, "materials_created": [], "errors": []}

    request = resp_lib.calls[0].request
    assert "create_materials=true" in request.url
    body = json.loads(request.body)
    assert body[0]["material"] == {"name": "LAGNAK"}
    row = body[0]["cifs"][0]
    assert row["filename"] == f"LAGNAK__autoprism_{md5[:12]}.cif"
    assert row["filename"] != "LAGNAK.cif"
    assert row["content"] == _CIF_TEXT
    assert row["tags"] == ["autoprism"]


def test_upsert_autoprism_cifs_rejects_md5_mismatch(api):
    with pytest.raises(ValueError, match="does not match the content"):
        api.upsert_autoprism_cifs([{"structure": "LAGNAK", "content": _CIF_TEXT, "md5": "0" * 32}])


def test_upsert_autoprism_cifs_rejects_long_paths(api):
    with pytest.raises(ValueError, match="CIF.file limit"):
        api.upsert_autoprism_cifs([{"structure": "X" * 70, "content": _CIF_TEXT}])


@resp_lib.activate
def test_upsert_autoprism_cifs_batches(api):
    def _reply(request):
        names = [b["material"]["name"] for b in json.loads(request.body)]
        return 200, {}, json.dumps(_bundle_ok(names, created=False))

    resp_lib.add_callback(resp_lib.PUT, _BUNDLE_UPSERT, callback=_reply)
    items = [{"structure": f"MOF{i}", "content": _CIF_TEXT + f"# {i}\n"} for i in range(120)]
    result = api.upsert_autoprism_cifs(items, batch_size=50)
    assert [len(json.loads(c.request.body)) for c in resp_lib.calls] == [50, 50, 20]
    assert result["created"] == 120


@resp_lib.activate
def test_upsert_autoprism_cifs_reports_materials_created(api):
    from prisma_api import PrismaNewStructureWarning
    resp_lib.add(resp_lib.PUT, _BUNDLE_UPSERT, json=_bundle_ok(["NEWMOF"]))
    with pytest.warns(PrismaNewStructureWarning, match="NEWMOF"):
        result = api.upsert_autoprism_cifs([{"structure": "NEWMOF", "content": _CIF_TEXT}])
    assert result["materials_created"] == ["NEWMOF"]


@resp_lib.activate
def test_upsert_autoprism_cifs_207_all_failed_is_failure(api):
    import warnings as _warnings

    from prisma_api import PrismaRowErrorWarning, PrismaUpsertError
    body = {"materials": 1, "created": {}, "updated": {}, "results": [],
            "errors": [{"index": 0, "material": "LAGNAK", "error": "Unknown tag 'AutoPrism'"}]}
    resp_lib.add(resp_lib.PUT, _BUNDLE_UPSERT, json=body, status=207)
    items = [{"structure": "LAGNAK", "content": _CIF_TEXT}]

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = api.upsert_autoprism_cifs(items)
    assert [w.category for w in caught] == [PrismaRowErrorWarning]
    assert "no rows stored" in str(caught[0].message)
    assert result["created"] == 0 and len(result["errors"]) == 1

    with pytest.raises(PrismaUpsertError, match="Unknown tag"):
        api.upsert_autoprism_cifs(items, raise_on_error=True)


@resp_lib.activate
def test_collection_uploads_cifs_first(no_git_meta):
    import warnings as _warnings

    from prisma_api import PrismaNewStructureWarning
    resp_lib.add(resp_lib.PUT, _BUNDLE_UPSERT, json=_bundle_ok(["NEWMOF"]))
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/computation-runs/", json={"created": 1, "updated": 0})
    resp_lib.add(resp_lib.PUT, f"{PROD_BASE}/heat-capacity/", json={"created": 2, "updated": 0})

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        result = no_git_meta.upsert_autoprism_collection({
            "heat_capacities": [{"md5": "a"}, {"md5": "b"}],
            "computation_runs": [{"id": "r"}],
            "cifs": [{"structure": "NEWMOF", "content": _CIF_TEXT}],
        }, cif_tags=["autoprism"])

    paths = [c.request.url.split("/api/v2")[1].split("?")[0] for c in resp_lib.calls]
    assert paths == ["/materials/bundle/upsert/", "/computation-runs/", "/heat-capacity/"]
    assert json.loads(resp_lib.calls[0].request.body)[0]["cifs"][0]["tags"] == ["autoprism"]
    assert result["sections"]["cifs"]["status"] == "ok"
    assert result["sections"]["cifs"]["created"] == 1
    assert result["sections"]["cifs"]["new_structures"] == ["NEWMOF"]
    assert result["totals"]["created"] == 4
    assert result["totals"]["new_structures"] == ["NEWMOF"]
    assert [w.category for w in caught].count(PrismaNewStructureWarning) == 1
