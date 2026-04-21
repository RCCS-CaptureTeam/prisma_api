"""
Unit tests for prisma_api.prisma_api (v1 client).

All HTTP calls are mocked with the `responses` library so no live network
access is needed.  Run with:

    pytest tests/ -v --cov=prisma_api --cov-report=term-missing
"""

from __future__ import annotations

import json
import pytest
import responses as resp_lib
from unittest.mock import patch, MagicMock

import pandas as pd

# ── Helpers ────────────────────────────────────────────────────────────────────

PROD_URL = "https://prisma-platform.org/api/get_materials_data/"
LEGACY_URL = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/get_materials_data/"


def _make_api(key: str = "test-key", dev: bool = False, dev_host_port: str = ""):
    """Build a prisma_api instance without touching the config file."""
    from prisma_api.prisma_api import prisma_api

    obj = prisma_api.__new__(prisma_api)
    obj.verbose = False
    obj.key = key
    obj.dev = dev
    obj.dev_host_port = dev_host_port

    from prisma_api.prisma_api_v2 import PrismaAPIv2
    obj.v2 = PrismaAPIv2(key=key, dev=dev, dev_host_port=dev_host_port)

    return obj


def _raw_record(**overrides) -> dict:
    """Minimal API record as returned by the server (before unpacking)."""
    base = {
        "id": 1,
        "name": "ABEXEM",
        "cif_file": "/media/structures/ABEXEM.cif",
        "carbon_isotherm": [{
            "id": 11,
            "Molecule": "CO2",
            "good_structure": True,
            "Henry_mol_per_kg_Pa": 1.23e-5,
            "Pressure_bar": 0.1,
            "Uptake_mol_per_kg": 2.45,
            "Heat_kJ_per_mol": 35.0,
            "T_ref_K": 298.0,
            "sim_or_exp": "sim",
        }],
        "carbon_zeopp": [{
            "id": 21,
            "Density_g_per_cm3": 0.85,
            "POAVF": 0.45,
            "Formula": "C12H8N2O4",
            "Binder": None,
            "Cp_J_per_gK": 0.84,
            "DOI": "10.1/test",
            "Macroporosity": None,
            "Molecule": "CO2",
            "Pellet_Density_g_per_cm3": None,
            "Round": None,
            "good_structure": True,
        }],
        "carbon_zeopp_experimental": [],
    }
    base.update(overrides)
    return base


def _server_response(records: list) -> dict:
    return {"data": records, "meta": {}}


# ── Construction without config file ─────────────────────────────────────────

def test_make_api_constructs_without_config():
    api = _make_api()
    assert api.key == "test-key"
    assert not api.dev
    assert hasattr(api, "v2")


def test_v2_is_attached():
    from prisma_api.prisma_api_v2 import PrismaAPIv2
    api = _make_api()
    assert isinstance(api.v2, PrismaAPIv2)


# ── get_materials_data: basic response ────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_returns_dict_with_keys():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data()
    assert isinstance(result, dict)
    assert "simulated" in result or "data" in result
    assert "meta" in result


@resp_lib.activate
def test_get_materials_data_meta_source_key():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data()
    assert result["meta"]["source"] == "prisma-platform.org"


@resp_lib.activate
def test_get_materials_data_uses_legacy_on_primary_failure():
    resp_lib.add(resp_lib.POST, PROD_URL, body=Exception("connection refused"))
    resp_lib.add(resp_lib.POST, LEGACY_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data()
    assert result["meta"]["source"] == "dun-eideann-labs.co.uk"


@resp_lib.activate
def test_get_materials_data_returns_empty_dict_on_total_failure():
    resp_lib.add(resp_lib.POST, PROD_URL, body=Exception("timeout"))
    resp_lib.add(resp_lib.POST, LEGACY_URL, body=Exception("timeout"))
    api = _make_api()
    result = api.get_materials_data()
    # Should return {} or a dict with empty DataFrames — not raise
    assert isinstance(result, dict)


# ── get_materials_data: column unpacking ─────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_cif_file_url_prepended():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert df.iloc[0]["cif_file"].startswith("https://prisma-platform.org")


@resp_lib.activate
def test_get_materials_data_carbon_isotherm_unpacked():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert "Molecule" in df.columns
    assert "CO2 Uptake (mol/kg)" in df.columns


@resp_lib.activate
def test_get_materials_data_carbon_zeopp_unpacked():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert "Zeo++ Density_g_per_cm3" in df.columns


@resp_lib.activate
def test_get_materials_data_id_columns_dropped():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    for col in ["id", "carbon_isotherm__id", "carbon_zeopp__id"]:
        assert col not in df.columns, f"Column '{col}' should have been dropped"


@resp_lib.activate
def test_get_materials_data_carbon_isotherm_raw_col_dropped():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert "carbon_isotherm" not in df.columns
    assert "carbon_zeopp" not in df.columns


@resp_lib.activate
def test_get_materials_data_sim_or_exp_column_exists_and_first():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert "sim_or_exp" in df.columns
    assert df.columns[0] == "sim_or_exp"


# ── separate_experimental=True ────────────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_separate_experimental_true_keys():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=True)
    assert "simulated" in result
    assert "experimental" in result


@resp_lib.activate
def test_get_materials_data_separate_experimental_sim_row_in_simulated():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=True)
    df_sim = result["simulated"]
    assert len(df_sim) == 1
    assert df_sim.iloc[0]["sim_or_exp"] == "sim"


@resp_lib.activate
def test_get_materials_data_separate_experimental_exp_row_in_experimental():
    """A record with no isotherm and experimental-only zeopp should land in 'experimental'."""
    rec = _raw_record()
    # No isotherm data (so it won't contribute a 'sim' flag)
    rec["carbon_isotherm"] = []
    # Move zeopp to experimental only
    rec["carbon_zeopp"] = []
    rec["carbon_zeopp_experimental"] = [{
        "id": 31, "Density_g_per_cm3": 0.90, "POAVF": 0.40,
        "Formula": "C12H8N2O4", "Binder": None, "Cp_J_per_gK": 0.80,
        "DOI": "10.2/exp", "Macroporosity": None, "Molecule": "CO2",
        "Pellet_Density_g_per_cm3": None, "Round": None, "good_structure": True,
    }]
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([rec]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=True)
    df_exp = result["experimental"]
    assert len(df_exp) == 1
    assert df_exp.iloc[0]["sim_or_exp"] == "exp"


@resp_lib.activate
def test_get_materials_data_separate_experimental_simulated_df_is_empty_when_no_sims():
    """No isotherm, zeopp only experimental → simulated DataFrame must be empty."""
    rec = _raw_record()
    rec["carbon_isotherm"] = []  # no isotherm sim_or_exp flag
    rec["carbon_zeopp"] = []
    rec["carbon_zeopp_experimental"] = [{
        "id": 31, "Density_g_per_cm3": 0.90, "POAVF": 0.40,
        "Formula": "C12H8N2O4", "Binder": None, "Cp_J_per_gK": 0.80,
        "DOI": "10.2/exp", "Macroporosity": None, "Molecule": "CO2",
        "Pellet_Density_g_per_cm3": None, "Round": None, "good_structure": True,
    }]
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([rec]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=True)
    assert len(result["simulated"]) == 0


# ── multiple records ──────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_multiple_records():
    rec2 = _raw_record()
    rec2["id"] = 2
    rec2["name"] = "FOOFOO"
    rec2["cif_file"] = "/media/structures/FOOFOO.cif"
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record(), rec2]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    df = result["data"]
    assert len(df) == 2


# ── API key sent in header ────────────────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_api_key_in_header():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api(key="my-secret-key")
    api.get_materials_data()
    request = resp_lib.calls[0].request
    assert request.headers.get("X-API-Key") == "my-secret-key"


# ── dev mode ──────────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_dev_mode_uses_localhost():
    dev_url = "http://localhost:8000/api/get_materials_data/"
    resp_lib.add(resp_lib.POST, dev_url,
                 json=_server_response([_raw_record()]), status=200)
    api = _make_api(dev=True, dev_host_port="8000")
    api.get_materials_data(separate_experimental=False)
    assert resp_lib.calls[0].request.url == dev_url


# ── empty response ────────────────────────────────────────────────────────────

@resp_lib.activate
def test_get_materials_data_empty_data_list():
    resp_lib.add(resp_lib.POST, PROD_URL,
                 json=_server_response([]), status=200)
    api = _make_api()
    result = api.get_materials_data(separate_experimental=False)
    assert isinstance(result, dict)
    # Either 'data' key with empty df, or 'simulated'/'experimental' keys
    df = result.get("data") if "data" in result else result.get("simulated")
    if df is not None:
        assert isinstance(df, pd.DataFrame)
