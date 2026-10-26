"""Tests for prisma_api.dataset_package (validate / pack / upload of dataset packages).

The target names here (features, results, settings) are made up on purpose:
the client must work with whatever targets the server's catalogue lists.
"""
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
        {"id": "features", "path": "Data/features.csv", "target": "features",
         "columns": {"LP (mol/kg)": "LP_uptake"}, "ignore_columns": ["junk"]},
        {"id": "lcos", "path": "TEA/Case {case}/{variant}/results.csv", "target": "results",
         "run": "h2-case{case}-{variant}", "match_field_names": True},
        {"id": "tea", "path": "Data/tea.yaml", "target": "settings", "parameter_set": "tea",
         "category": "tea_defaults", "layout": "mapping"},
        {"id": "figures", "path": "Results/**", "target": "skip", "reason": "derived"},
    ],
}


COMMON_KEYS = ["id", "path", "exclude", "target", "format", "description", "by_others"]
CATALOGUE = {
    "_schema": "prisma.dataset.targets.v1",
    "manifest_schema": "prisma.dataset.ingest.v1",
    "defaults": {"id_column": "MOF"},
    "targets": {
        "features": {"kind": "rows", "description": "per-material features",
                     "keys": COMMON_KEYS + ["id_column", "columns", "ignore_columns", "match_field_names"],
                     "fields": {"LP_uptake": {"type": "float", "help": "mol/kg"}}},
        "results": {"kind": "run_rows", "description": "per-run results",
                    "keys": COMMON_KEYS + ["id_column", "columns", "run", "runs_where", "match_field_names"],
                    "fields": {"LCOS_USD_per_kWh": {"type": "float", "help": "USD/kWh"}}},
        "notes": {"kind": "run_rows", "description": "free-form", "keys": COMMON_KEYS + ["columns", "run", "units"],
                  "fields": None},
        "settings": {"kind": "parameters", "description": "shared inputs",
                     "keys": COMMON_KEYS + ["parameter_set", "category", "layout"], "fields": None},
        "skip": {"kind": "skip", "description": "not ingested", "keys": COMMON_KEYS + ["reason", "pack"],
                 "fields": None},
    },
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
    report = dp.validate(root, manifest, CATALOGUE)
    assert report["ok"], report["errors"]
    assert report["targets_checked"]
    by_id = {s["id"]: s for s in report["sources"]}
    assert by_id["lcos"]["records"] == 2
    assert any("RSM9" in w for w in report["warnings"])          # run rows without a per-material row
    assert report["unmentioned_files"] == ["README.md", "manifest.yaml"]   # .git is ignored


def test_validate_finds_unmapped_columns_and_undeclared_runs(package):
    root, manifest = package
    data = yaml.safe_load(manifest.read_text())
    data["sources"][0]["ignore_columns"] = []
    data["sources"][1]["run"] = "h2-case{case}-other"
    manifest.write_text(yaml.safe_dump(data))
    report = dp.validate(root, manifest, CATALOGUE)
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
    assert names == {dp.MANIFEST_NAME, dp.SOURCE_TREE_NAME,
                     "Data/features.csv", "Data/tea.yaml", "TEA/Case 1/2_cycle/results.csv"}
    assert set(packed["files"]) == names - {dp.MANIFEST_NAME, dp.SOURCE_TREE_NAME}
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


@resp_lib.activate
def test_get_analysis_run_rows_spreads_values_into_columns():
    resp_lib.add(resp_lib.GET, f"{_BASE_PROD}/analysis-runs/co2-298K/rows/", json={
        "run": "co2-298K", "table": "results", "count": 2, "units": {"co2_uptake": "mmol/g"},
        "results": [{"subject": "ABC", "subject_type": "material", "values": {"co2_uptake": 3.2}},
                    {"subject": "13X", "subject_type": "reference_system", "values": {"co2_uptake": 4.9}}]})
    df = PrismaAPIv2(key="k", return_format="dataframe").get_analysis_run_rows("co2-298K")
    assert list(df.columns) == ["subject", "subject_type", "co2_uptake"]
    assert df["co2_uptake"].tolist() == [3.2, 4.9]
    rows = PrismaAPIv2(key="k", return_format="json").get_analysis_run_rows("co2-298K", table="inputs")
    assert rows[1]["subject_type"] == "reference_system"
    assert "table=inputs" in resp_lib.calls[1].request.url


def test_pack_lists_the_whole_source_tree(package, tmp_path):
    root, manifest = package
    out = tmp_path / "pkg.zip"
    dp.pack(root, manifest, out)
    with zipfile.ZipFile(out) as zf:
        tree = json.loads(zf.read(dp.SOURCE_TREE_NAME))
    by_path = {f["path"]: f for f in tree["files"]}
    assert tree["_schema"] == dp.SOURCE_TREE_SCHEMA
    assert by_path["Results/fig.pdf"] == {"path": "Results/fig.pdf", "size": 4, "status": "skipped",
                                          "source": "figures", "reason": "derived"}
    assert by_path["README.md"]["status"] == "unmentioned"
    assert by_path["Data/features.csv"]["status"] == "read" and len(by_path["Data/features.csv"]["sha256"]) == 64
    assert ".git/HEAD" not in by_path
    assert tree["total_files"] == len(tree["files"])


def test_upload_needs_an_explicit_target(tmp_path):
    with pytest.raises(ValueError, match="say where to upload"):
        dp.upload(tmp_path / "pkg.zip")
    with pytest.raises(SystemExit):
        dp.main(["upload", str(tmp_path / "pkg.zip")])        # neither --dev nor --prod


def test_without_a_catalogue_only_the_format_is_checked(package):
    root, manifest = package
    report = dp.validate(root, manifest)
    assert report["ok"], report["errors"]
    assert not report["targets_checked"]
    assert any("no target catalogue" in w for w in report["warnings"])


def test_catalogue_checks_target_names_keys_and_fields(package):
    root, manifest = package
    data = yaml.safe_load(manifest.read_text())
    data["sources"][0]["columns"] = {"LP (mol/kg)": "LP_uptakee"}
    data["sources"][1]["target"] = "resultz"
    data["sources"][2]["records_key"] = "General"
    manifest.write_text(yaml.safe_dump(data))
    text = "\n".join(dp.validate(root, manifest, CATALOGUE)["errors"])
    assert "maps to 'LP_uptakee', which target 'features' does not have" in text
    assert "the server has no target 'resultz'" in text
    assert "key 'records_key' is not used by target 'settings'" in text


def test_match_field_names_only_accepts_real_fields(package):
    root, manifest = package
    (root / "TEA/Case 1/2_cycle/results.csv").write_text("MOF,LCOS_USD_per_kWh,typo_col\nRSM1,5.7,1\n")
    assert "column 'typo_col'" in "\n".join(dp.validate(root, manifest, CATALOGUE)["errors"])
    assert dp.validate(root, manifest)["ok"]       # without the catalogue the server dry run decides


def test_manifest_at_the_root_is_not_a_data_file(package):
    root, manifest = package
    (root / dp.MANIFEST_NAME).write_text(manifest.read_text())
    report = dp.validate(root)
    assert dp.MANIFEST_NAME not in report["unmentioned_files"]


def test_saved_catalogue_file_and_targets_cli(package, tmp_path, capsys):
    root, manifest = package
    saved = tmp_path / "targets.json"
    saved.write_text(json.dumps(CATALOGUE))
    assert dp.main(["validate", str(root), "--manifest", str(manifest), "--targets", str(saved), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["targets_checked"] is True


@resp_lib.activate
def test_targets_command_fetches_and_saves(tmp_path, capsys, monkeypatch):
    resp_lib.add(resp_lib.GET, f"{_BASE_PROD}/datasets/targets/", json=CATALOGUE)
    monkeypatch.setattr(dp, "_client", lambda dev, prod: PrismaAPIv2(key="k"))
    out = tmp_path / "t.json"
    assert dp.main(["targets", "--prod", "--save", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "LCOS_USD_per_kWh" in printed and "any names you choose" in printed
    assert json.loads(out.read_text())["targets"]["results"]["kind"] == "run_rows"


def test_guide_and_skill_ship_with_the_package(tmp_path):
    assert "prisma_manifest.yaml" in dp.guide()
    dest = dp.install_skill(tmp_path)
    assert (dest / "SKILL.md").read_text().startswith("---\nname: prisma-dataset")
    assert (dest / "manifest_guide.md").exists()
    with pytest.raises(FileExistsError):
        dp.install_skill(tmp_path)
    dp.install_skill(tmp_path, force=True)


def test_packaged_docs_name_no_server_tables():
    """The client ships no knowledge of the platform's tables."""
    text = (dp.DOCS / "SKILL.md").read_text() + dp.guide()
    for name in ("mof_h2", "h2_results", "Hydrogen", "H2_Results"):
        assert name not in text


def test_pack_adds_tags_to_the_manifest(package, tmp_path):
    root, manifest = package
    out = tmp_path / "pkg.zip"
    report = dp.pack(root, manifest, out, tags=["H2 Review", "H2 Test"])
    assert report["tags"] == ["H2 Test", "H2 Review"]           # manifest tag first, no repeats
    with zipfile.ZipFile(out) as zf:
        assert yaml.safe_load(zf.read(dp.MANIFEST_NAME))["dataset"]["tag"] == ["H2 Test", "H2 Review"]


@resp_lib.activate
def test_upload_sends_extra_tags(tmp_path):
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"PK")
    resp_lib.add(resp_lib.POST, f"{_BASE_PROD}/datasets/ingest/", json={"ok": True},
                 match=[resp_lib.matchers.query_param_matcher({"dry_run": "true", "tags": "A,B"})])
    assert dp.upload(zip_path, api=PrismaAPIv2(key="k"), tags=["A", "B"]) == {"ok": True}


def test_virtualenvs_are_not_part_of_the_dataset(package):
    root, _ = package
    for path in (".venv/lib/python3.11/site.py", "Data/.venv/bin/python"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("x")
    files = dp.list_files(root)
    assert not [f for f in files if ".venv" in f]


GITIGNORE_CASES = {
    ".gitignore": "*.log\nbuild/\n/secret.txt\n!keep.log\ndata/raw/**\n",
    "sub/.gitignore": "local_*.csv\n",
}
GITIGNORE_FILES = ["a.csv", "x.log", "keep.log", "build/out.bin", "sub/build/y.bin", "secret.txt", "sub/secret.txt",
                   "data/raw/r1.csv", "data/clean.csv", "sub/local_1.csv", "sub/global.csv", ".venv/lib/z.py"]


def _write_tree(root, files, ignores):
    for path in files:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("x")
    for path, text in ignores.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)


def test_gitignore_is_respected_with_and_without_git(tmp_path):
    import shutil
    import subprocess
    plain, repo = tmp_path / "plain", tmp_path / "repo"
    for root in (plain, repo):
        _write_tree(root, GITIGNORE_FILES, GITIGNORE_CASES)
    expected = ["a.csv", "data/clean.csv", "keep.log", "sub/global.csv", "sub/secret.txt"]   # no .gitignore files
    assert sorted(dp.list_files(plain)) == sorted(expected)                 # .gitignore parsed directly
    if shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        assert sorted(dp.list_files(repo)) == sorted(expected)              # the same through git
    assert ".venv/lib/z.py" not in dp.list_files(plain, gitignore=False)    # .venv is always left out
    assert "x.log" in dp.list_files(plain, gitignore=False)


@resp_lib.activate
def test_send_tree_posts_the_listing_gzipped(package):
    import gzip
    root, manifest = package
    (root / ".gitignore").write_text("README.md\n")
    resp_lib.add(resp_lib.POST, f"{_BASE_PROD}/datasets/trees/",
                 json={"package": 7, "dataset": "h2-test", "files": 4, "selected": 3, "has_zip": False}, status=201)
    result = dp.send_tree(root, PrismaAPIv2(key="k"), manifest=manifest, tags="T")
    assert result["package"] == 7 and result["ok"]
    request = resp_lib.calls[0].request
    body = request.body
    tree = json.loads(gzip.decompress(body[body.index(b"\x1f\x8b"):body.rindex(b"\r\n--")]))
    paths = {f["path"] for f in tree["files"]}
    assert "README.md" not in paths and ".gitignore" not in paths and "Data/features.csv" in paths
    assert b'"dataset": "h2-test"' in body and b'"tags": ["T"]' in body


def test_send_tree_without_a_manifest_needs_a_slug(tmp_path):
    (tmp_path / "a.csv").write_text("x")
    with pytest.raises(ValueError, match="--dataset"):
        dp.send_tree(tmp_path, api=PrismaAPIv2(key="k"))


def test_pack_sends_only_ticked_files(package, tmp_path):
    root, manifest = package
    (root / "Data/new.csv").write_text("MOF\n")                     # appeared after the tree was sent
    selection = {"package": 42, "columns": ["path", "integrated", "exclude_from_zenodo", "status"],
                 "files": [["Data/features.csv", True, False, "read"],
                           ["TEA/Case 1/2_cycle/results.csv", False, False, "read"],     # unticked
                           ["Data/tea.yaml", True, False, "read"],
                           ["README.md", True, False, "unmentioned"],                    # ticked, but unread
                           ["Results/fig.pdf", False, False, "skipped"]]}
    out = tmp_path / "pkg.zip"
    report = dp.pack(root, manifest, out, selection=selection)
    assert report["ok"], report["errors"]                           # an all-unticked source is no error
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        packed = yaml.safe_load(zf.read(dp.MANIFEST_NAME))
    assert names == {dp.MANIFEST_NAME, dp.SOURCE_TREE_NAME, "Data/features.csv", "Data/tea.yaml"}
    assert packed["package"]["tree_package"] == 42
    text = "\n".join(report["warnings"])
    assert "newer than tree #42" in text and "Data/new.csv" in text
    assert "not read by any manifest source" in text and "README.md" in text
    assert dp.packed_tree(out) == 42


@resp_lib.activate
def test_upload_attaches_to_the_tree_it_was_packed_from(package, tmp_path):
    root, manifest = package
    out = tmp_path / "pkg.zip"
    dp.pack(root, manifest, out, selection={"package": 9, "columns": ["path", "integrated"],
                                            "files": [["Data/features.csv", True]]})
    resp_lib.add(resp_lib.POST, f"{_BASE_PROD}/datasets/ingest/", json={"ok": True},
                 match=[resp_lib.matchers.query_param_matcher({"dry_run": "true", "package": "9"})])
    assert dp.upload(out, api=PrismaAPIv2(key="k")) == {"ok": True}
