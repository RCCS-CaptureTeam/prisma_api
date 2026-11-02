"""prisma-outputs: packing v1 screening-result batches and sending them (ingest pipeline 13)."""
from __future__ import annotations

import zipfile

import pytest
import responses as resp_lib

from prisma_api import screening_outputs as so
from prisma_api.prisma_api_v2 import _BASE_PROD, PrismaAPIv2

CASE = "DAC_northernlights_NO_heatpump_80_year_mean"


def write_result(batch_dir, case=CASE, cond="TVSA01_150_10NL_wet_desiccant", kind="Simulated"):
    folder = batch_dir / "Screening_DAC" / case / cond / kind
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"screening-{kind}-{case}-{cond}-TSA"
    (folder / f"{stem}_L2-KPIs.csv").write_text(",MOF,CAC\n0,MOF_A,100\n")
    (folder / f"{stem}_L2_screening-Analysis.csv").write_text("n_materials,1\n")
    (folder / f"{stem}_L2-warnings.csv").write_text("not sent\n")


@pytest.fixture
def results(tmp_path):
    root = tmp_path / "screening_results"
    write_result(root / "liquefaction_26")
    write_result(root / "liquefaction_45")
    write_result(root / "liquefaction_45", cond="TVSA01_100_10_wet")
    (root / "liquefaction_45" / "notes").mkdir()
    (root / "liquefaction_45" / "notes" / "old_L2-KPIs.csv").write_text("x\n")
    (root / "scripts").mkdir()          # not a batch: no Screening_* folder
    return root


def test_scan_finds_batches_and_only_the_files_the_platform_reads(results):
    batches = so.scan(results)
    assert [b.name for b in batches] == ["liquefaction_26", "liquefaction_45"]
    b26, b45 = batches
    assert len(b26.files) == 2 and all(f.endswith(("_L2-KPIs.csv", "_L2_screening-Analysis.csv")) for f in b26.files)
    assert b45.skipped == ["notes/old_L2-KPIs.csv"]
    assert b45.scenarios == {("DAC_northernlights_NO_heatpump_80", "TVSA01_150_10NL_wet_desiccant", "Simulated"),
                             ("DAC_northernlights_NO_heatpump_80", "TVSA01_100_10_wet", "Simulated")}


def test_scan_of_one_batch_folder(results):
    (batch,) = so.scan(results / "liquefaction_26")
    assert batch.name == "liquefaction_26"


def test_repeats_lists_scenarios_in_several_batches(results):
    rep = so.repeats(so.scan(results))
    assert rep == {("DAC_northernlights_NO_heatpump_80", "TVSA01_150_10NL_wet_desiccant", "Simulated"):
                   ["liquefaction_26", "liquefaction_45"]}


def test_pack_puts_the_batch_folder_on_top(results, tmp_path):
    batch = so.scan(results)[0]
    with zipfile.ZipFile(so.pack(batch, tmp_path / "b.zip")) as zf:
        names = zf.namelist()
    assert len(names) == 2
    assert all(n.startswith("liquefaction_26/Screening_DAC/") for n in names)


@resp_lib.activate
def test_send_posts_each_batch_and_returns_the_reports(results, tmp_path):
    resp_lib.add(resp_lib.POST, f"{_BASE_PROD}/screening-outputs/ingest/",
                 json={"ok": True, "scenarios": [{"rows": 1, "created": True}], "warnings": [], "errors": [],
                       "zip_upload": 7})
    messages = []
    reports = so.send(so.scan(results), PrismaAPIv2(key="k"), keep=tmp_path / "zips", progress=messages.append)
    assert [r["batch"] for r in reports] == ["liquefaction_26", "liquefaction_45"]
    assert len(resp_lib.calls) == 2
    assert resp_lib.calls[0].request.headers["X-API-Key"] == "k"
    assert (tmp_path / "zips" / "liquefaction_45.zip").exists()
    assert any("1 scenarios (1 new) · 1 rows · upload #7" in m for m in messages)


def test_cli_send_needs_a_batch_choice(results, capsys):
    assert so.main(["send", str(results), "--dev", "--yes"]) == 1
    assert "--batch NAME" in capsys.readouterr().err


def test_cli_send_rejects_an_unknown_batch(results, capsys):
    assert so.main(["send", str(results), "--dev", "--yes", "--batch", "nope"]) == 1
    assert "no such batch: nope" in capsys.readouterr().err


def test_cli_list(results, capsys):
    assert so.main(["list", str(results), "--repeats"]) == 0
    out = capsys.readouterr().out
    assert "liquefaction_45" in out and "1 appear in more than one batch" in out
