"""
Unit tests for prisma_api.prisma_api_v2.PrismaAPIv2

All HTTP calls are intercepted with responses (or unittest.mock) so no
live network access is required.  Run with:

    pytest tests/ -v --cov=prisma_api --cov-report=term-missing
"""

from __future__ import annotations

import json
import pytest
import responses as resp_lib
from responses import matchers

from prisma_api.prisma_api_v2 import PrismaAPIv2, _BASE_PROD

# ── Fixtures ──────────────────────────────────────────────────────────────────

PROD_BASE = _BASE_PROD


@pytest.fixture
def api():
    """Return a PrismaAPIv2 instance pointed at prod (non-dev)."""
    return PrismaAPIv2(key="test-api-key", dev=False)


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
    with pytest.raises(Exception):
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

@resp_lib.activate
def test_get_materials_returns_dataframe(api):
    body = _envelope([
        {"id": 1, "name": "ABEXEM", "cif_url": "/media/ABEXEM.cif"},
        {"id": 2, "name": "FOOFOO", "cif_url": "/media/FOOFOO.cif"},
    ])
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/", json=body, status=200)
    df = api.get_materials()
    assert len(df) == 2
    assert_df_columns(df, "id", "name", "cif_url")


@resp_lib.activate
def test_get_materials_name_filter_passed_as_param(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/",
                 match=[matchers.query_param_matcher({"name": "ABEXEM", "limit": "500", "offset": "0"})],
                 json=_envelope([{"id": 1, "name": "ABEXEM", "cif_url": ""}]), status=200)
    df = api.get_materials(name="ABEXEM")
    assert df.iloc[0]["name"] == "ABEXEM"


@resp_lib.activate
def test_get_material_detail(api):
    detail = {"id": 1, "name": "ABEXEM", "cif_url": "/media/ABEXEM.cif",
              "elements": [{"symbol": "C", "mass_fraction": 0.45}]}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/1/", json=detail, status=200)
    result = api.get_material(1)
    assert result["name"] == "ABEXEM"
    assert len(result["elements"]) == 1


@resp_lib.activate
def test_get_materials_empty(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/materials/", json=_envelope([]), status=200)
    df = api.get_materials()
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


# ── Equipment ─────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_equipment_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment/",
                 json=_envelope([{"id": 1, "name": "Blower"}]), status=200)
    df = api.get_equipment()
    assert len(df) == 1


@resp_lib.activate
def test_get_equipment_item_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/equipment/1/",
                 json={"id": 1, "name": "Blower"}, status=200)
    assert api.get_equipment_item(1)["name"] == "Blower"


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


# ── TEA Equipment ─────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_tea_equipment_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment/",
                 json=_envelope([{"id": 1, "name": "Blower A", "group": "Blower"}]),
                 status=200)
    df = api.get_tea_equipment()
    assert_df_columns(df, "name", "group")


@resp_lib.activate
def test_get_tea_equipment_group_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment/",
                 match=[matchers.query_param_matcher(
                     {"group": "Blower", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_tea_equipment(group="Blower")


@resp_lib.activate
def test_get_tea_equipment_item_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment/1/",
                 json={"id": 1, "name": "Blower A", "group": "Blower"}, status=200)
    assert api.get_tea_equipment_item(1)["group"] == "Blower"


# ── TEA Equipment Costs ───────────────────────────────────────────────────────

@resp_lib.activate
def test_get_tea_equipment_costs_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-costs/",
                 json=_envelope([{"id": 1, "equipment_id": 1, "cost": 5000.0}]),
                 status=200)
    df = api.get_tea_equipment_costs()
    assert_df_columns(df, "equipment_id", "cost")


@resp_lib.activate
def test_get_tea_equipment_costs_equipment_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-costs/",
                 match=[matchers.query_param_matcher(
                     {"equipment_id": "1", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_tea_equipment_costs(equipment_id=1)


@resp_lib.activate
def test_get_tea_equipment_cost_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-costs/1/",
                 json={"id": 1, "equipment_id": 1, "cost": 5000.0}, status=200)
    assert api.get_tea_equipment_cost(1)["cost"] == 5000.0


# ── TEA Equipment Designs ─────────────────────────────────────────────────────

@resp_lib.activate
def test_get_tea_equipment_designs_returns_dataframe(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-designs/",
                 json=_envelope([{"id": 1, "equipment_id": 1, "key": "D1", "value": 1.5}]),
                 status=200)
    df = api.get_tea_equipment_designs()
    assert_df_columns(df, "equipment_id", "key")


@resp_lib.activate
def test_get_tea_equipment_designs_key_filter(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-designs/",
                 match=[matchers.query_param_matcher(
                     {"key": "D1", "limit": "500", "offset": "0"})],
                 json=_envelope([]), status=200)
    api.get_tea_equipment_designs(key="D1")


@resp_lib.activate
def test_get_tea_equipment_design_detail(api):
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/tea-equipment-designs/1/",
                 json={"id": 1, "key": "D1", "value": 1.5}, status=200)
    assert api.get_tea_equipment_design(1)["key"] == "D1"


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

@pytest.mark.parametrize("method,path,fixture", [
    ("get_sources",    "/sources/",    [{"id": 1, "name": "Coal Plant", "short_name": "CP"}]),
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


# ── Isotherms ─────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_isotherms_returns_dataframe(api):
    records = [
        {"id": 1, "mof": "ABEXEM", "molecule": "CO2", "T_ref_K": 298.0,
         "sim_or_exp": "sim", "good_structure": True},
        {"id": 2, "mof": "FOOFOO", "molecule": "N2",  "T_ref_K": 303.0,
         "sim_or_exp": "exp", "good_structure": False},
    ]
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 json=_envelope(records), status=200)
    df = api.get_isotherms()
    assert len(df) == 2
    assert_df_columns(df, "id", "mof", "molecule", "T_ref_K", "sim_or_exp", "good_structure")


@resp_lib.activate
def test_get_isotherms_all_filters_passed(api):
    expected_params = {
        "mof": "ABEXEM", "molecule": "CO2",
        "temperature_min": "273.0", "temperature_max": "350.0",
        "sim_or_exp": "sim", "good_structure": "true",
        "limit": "100", "offset": "0",
    }
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_params)],
                 json=_envelope([]), status=200)
    df = api.get_isotherms(
        mof="ABEXEM", molecule="CO2",
        temperature_min=273.0, temperature_max=350.0,
        sim_or_exp="sim", good_structure=True,
        limit=100, offset=0,
    )
    assert df.empty  # matched correctly → empty result is fine


@resp_lib.activate
def test_get_isotherms_good_structure_false(api):
    expected_params = {"good_structure": "false", "limit": "500", "offset": "0"}
    resp_lib.add(resp_lib.GET, f"{PROD_BASE}/isotherms/",
                 match=[matchers.query_param_matcher(expected_params)],
                 json=_envelope([]), status=200)
    api.get_isotherms(good_structure=False)


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
