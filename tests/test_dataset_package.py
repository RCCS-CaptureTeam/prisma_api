"""Tests for prisma_api.dataset_package (validate / pack / upload of dataset packages)."""
from __future__ import annotations

import json
import zipfile

import pytest
import responses as resp_lib
import yaml

from prisma_api import dataset_package as dp
from prisma_api.prisma_api_v2 import _BASE_PROD, PrismaAPIv2

MANIFEST = {
    "_schema": "prisma.dataset.ingest.v1",
    "dataset": {"slug": "h2-test", "tag": "H2 Test"},
    "material_id": {"strip_suffixes": [".cif"]},
    "reference_systems": [{"name": "Ni-MOF", "aliases": ["Ni_MOF"]}],
    "parameter_sets": [{"key": "tea"}],
    "runs": [{"key": "h2-case1-2_cycle", "name": "Case 1", "case": "Case_1"}],
    "sources": [
        {"id": "features", "path": "Data/features.csv", "target": "mof_h2",
         "columns": {"LP (mol/kg)": "LP_uptake"}, "ignore_columns": ["junk"]},
        {"id": "lcos", "path": "TEA/Case {case}/{variant}/results.csv", "target": "h2_results",
         "run": "h2-case{case}-{variant}", "match_field_names": True},
        {"id": "tea", "path": "Data/tea.yaml", "target": "parameters", "parameter_set": "tea",
         "category": "tea_defaults", "layout": "mapping"},
        {"id": "figures", "path": "Results/**", "target": "skip", "reason": "derived"},
    ],
}


@pytest.fixture
def package(tmp_path):
    files = {
        "Data/features.csv": "MOF,LP (mol/kg),junk\nRSM1.cif,1.2,x\nNi-MOF,0.5,y\n",
        "TEA/Case 1/2_cycle/results.csv": "MOF,LCOS_USD_per_kWh\nRSM1,5.7\nRSM9,6.0\n",
        "Data/tea.yaml": "ElectricityCost: 73.9 # EUR/MWh\n",
        "Results/fig.pdf": "%PDF",
        "README.md": "notes",
        ".git/HEAD": "ref",
    }
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump(MANIFEST))
    return tmp_path, manifest


def test_compile_pattern_matches_server_rules():
    rx = dp.compile_pattern("TEA_files/Case {case}/LCOS_Results_tank_vol_{tank}_{variant}/x.csv")
    m = rx.match("TEA_files/Case 4/LCOS_Results_tank_vol_3.93_44_cycle/x.csv")
    assert m.groupdict() == {"case": "4", "tank": "3.93", "variant": "44_cycle"}
    assert dp.compile_pattern("**/*.json").match("a/b.json")
    assert not dp.compile_pattern("*.json").match("a/b.json")


def test_validate_reports_sources_orphans_and_unmentioned(package):
    root, manifest = package
    report = dp.validate(root, manifest)
    assert report["ok"], report["errors"]
    by_id = {s["id"]: s for s in report["sources"]}
    assert by_id["lcos"]["records"] == 2
    assert any("RSM9" in w for w in report["warnings"])          # results without features
    assert report["unmentioned_files"] == ["README.md", "manifest.yaml"]   # .git is ignored


def test_validate_finds_unmapped_columns_and_undeclared_runs(package):
    root, manifest = package
    data = yaml.safe_load(manifest.read_text())
    data["sources"][0]["ignore_columns"] = []
    data["sources"][1]["run"] = "h2-case{case}-other"
    manifest.write_text(yaml.safe_dump(data))
    report = dp.validate(root, manifest)
    assert not report["ok"]
    text = "\n".join(report["errors"])
    assert "column 'junk'" in text
    assert "'h2-case1-other', which is not declared" in text


def test_pack_zips_read_files_with_checksums(package, tmp_path):
    root, manifest = package
    out = tmp_path / "pkg.zip"
    report = dp.pack(root, manifest, out)
    assert report["files_packed"] == 3
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        packed = yaml.safe_load(zf.read(dp.MANIFEST_NAME))
    assert names == {dp.MANIFEST_NAME, "Data/features.csv", "Data/tea.yaml", "TEA/Case 1/2_cycle/results.csv"}
    assert set(packed["files"]) == names - {dp.MANIFEST_NAME}
    assert len(packed["files"]["Data/tea.yaml"]) == 64
    assert packed["package"]["packed_by"]


def test_pack_refuses_an_invalid_package(package, tmp_path):
    root, manifest = package
    (root / "Data/features.csv").unlink()
    with pytest.raises(ValueError, match="does not validate"):
        dp.pack(root, manifest, tmp_path / "pkg.zip")


@resp_lib.activate
def test_upload_defaults_to_dry_run_and_returns_400_reports(tmp_path):
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"PK")
    url = f"{_BASE_PROD}/datasets/ingest/"
    resp_lib.add(resp_lib.POST, url, json={"ok": True, "dry_run": True},
                 match=[resp_lib.matchers.query_param_matcher({"dry_run": "true"})])
    resp_lib.add(resp_lib.POST, url, status=400, json={"ok": False, "errors": ["no file matches"]},
                 match=[resp_lib.matchers.query_param_matcher({"dry_run": "false"})])
    api = PrismaAPIv2(key="k")
    assert dp.upload(zip_path, api=api) == {"ok": True, "dry_run": True}
    assert api.ingest_dataset(str(zip_path), dry_run=False)["errors"] == ["no file matches"]
    assert resp_lib.calls[0].request.headers["X-API-Key"] == "k"
    assert b'name="file"' in resp_lib.calls[0].request.body


@resp_lib.activate
def test_list_analysis_runs():
    resp_lib.add(resp_lib.GET, f"{_BASE_PROD}/analysis-runs/",
                 json={"count": 1, "results": [{"key": "h2-case1-2_cycle", "h2_results": 3}]})
    runs = PrismaAPIv2(key="k", return_format="json").list_analysis_runs(dataset="h2-test")
    assert runs[0]["key"] == "h2-case1-2_cycle"
    assert "dataset=h2-test" in resp_lib.calls[0].request.url


def test_cli_validate_exit_codes(package, capsys):
    root, manifest = package
    assert dp.main(["validate", str(root), "--manifest", str(manifest), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
