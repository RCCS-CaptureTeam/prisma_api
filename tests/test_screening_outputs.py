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


INGEST = f"{_BASE_PROD}/screening-outputs/ingest/"
DONE = {"ok": True, "state": "done", "scenarios": [{"rows": 3, "created": False}], "warnings": [], "errors": [],
        "zip_upload": 9}


@pytest.fixture
def zipped(tmp_path):
    path = tmp_path / "b.zip"
    path.write_bytes(b"PK")
    return path


@resp_lib.activate
def test_a_background_ingest_is_polled_until_done(zipped):
    resp_lib.add(resp_lib.POST, INGEST, status=202, json={"zip_upload": 9, "state": "queued"})
    resp_lib.add(resp_lib.GET, f"{INGEST}9/", json={"zip_upload": 9, "state": "running",
                                                    "files_done": 4, "files_total": 10})
    resp_lib.add(resp_lib.GET, f"{INGEST}9/", json=DONE)
    messages = []
    report = PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped), poll_every=0, progress=messages.append)
    assert report == DONE
    assert "background=true" in resp_lib.calls[0].request.url
    assert messages == ["server ingesting upload #9: queued", "server ingesting upload #9: 4/10 files"]


@resp_lib.activate
def test_a_server_without_background_ingests_answers_with_the_report(zipped):
    resp_lib.add(resp_lib.POST, INGEST, json={**DONE, "state": None})
    assert PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped))["zip_upload"] == 9
    assert len(resp_lib.calls) == 1


@resp_lib.activate
def test_a_failed_background_ingest_is_returned_with_its_error(zipped):
    resp_lib.add(resp_lib.POST, INGEST, status=202, json={"zip_upload": 9, "state": "queued"})
    resp_lib.add(resp_lib.GET, f"{INGEST}9/", json={"zip_upload": 9, "state": "failed", "ok": False,
                                                    "error": "RuntimeError: boom"})
    report = PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped), poll_every=0)
    assert report["state"] == "failed" and "boom" in so.summary(report, "b")


@resp_lib.activate
def test_an_ingest_still_running_after_the_timeout_names_the_upload(zipped):
    resp_lib.add(resp_lib.POST, INGEST, status=202, json={"zip_upload": 9, "state": "running"})
    with pytest.raises(TimeoutError, match="prisma-outputs status 9"):
        PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped), timeout=0, poll_every=0)


@resp_lib.activate
def test_an_http_error_carries_the_servers_message(zipped):
    resp_lib.add(resp_lib.POST, INGEST, status=500, json={"state": "failed", "error": "RuntimeError: boom"})
    with pytest.raises(Exception, match="500 .*RuntimeError: boom"):
        PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped))


@resp_lib.activate
def test_an_html_error_page_is_shortened_into_the_message(zipped):
    resp_lib.add(resp_lib.POST, INGEST, status=500, body="<html><body><h1>Internal Server Error</h1>" + "x" * 2000,
                 content_type="text/html")
    with pytest.raises(Exception, match="Internal Server Error") as err:
        PrismaAPIv2(key="k").ingest_screening_outputs(str(zipped))
    assert len(str(err.value)) < 500


@resp_lib.activate
def test_send_reports_a_failed_batch_and_sends_the_next(results, tmp_path):
    resp_lib.add(resp_lib.POST, INGEST, status=500, body="Internal Server Error")
    resp_lib.add(resp_lib.POST, INGEST, json={**DONE, "zip_upload": 8})
    messages = []
    reports = so.send(so.scan(results), PrismaAPIv2(key="k"), progress=messages.append)
    assert [(r["batch"], r["ok"]) for r in reports] == [("liquefaction_26", False), ("liquefaction_45", True)]
    assert any(m.startswith("liquefaction_26: FAILED: 500") for m in messages)
    assert any("upload #8" in m for m in messages)


@resp_lib.activate
def test_cli_status(monkeypatch, capsys):
    import prisma_api
    monkeypatch.setattr(prisma_api, "init", lambda local_dev=False: PrismaAPIv2(key="k"))
    resp_lib.add(resp_lib.GET, f"{INGEST}9/", json={"zip_upload": 9, "state": "running",
                                                    "files_done": 4, "files_total": 10})
    assert so.main(["status", "9", "--prod"]) == 0
    assert "upload #9: running · 4/10 files" in capsys.readouterr().out
