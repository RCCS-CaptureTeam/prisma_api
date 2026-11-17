"""prisma_api.case_sync / prisma-case: link file, ahead/behind detection, push, publish, pull, fork; study-build client calls."""
import copy
import hashlib
import json

import pytest
import requests
import responses as resp_lib

from prisma_api import PrismaAPIv2, PrismaConflictError
from prisma_api import case_sync as cs

BASE = "https://prisma-platform.org/api/v2/study-builds/"


def graph(**over):
    doc = {"format": cs.GRAPH_FORMAT, "template_id": "dac_mini", "label": None, "description": None,
           "evidence_refs": [], "warnings": [], "gaps": [],
           "graph": {"nodes": [{"node_id": "plant", "model_path": "prisma_v2.tea.plant", "config": {"hours_per_year": 8500}},
                               {"node_id": "contactor", "model_path": "prisma_v2.process.models.adsorber", "config": {}},
                               {"node_id": "tea", "model_path": "prisma_v2.tea", "role": "economics", "config": {}}],
                     "edges": [{"src_node_id": "plant", "dst_node_id": "contactor", "stream_id": "air", "lca_spec": None}]}}
    doc.update(over)
    return doc


class FakeServer:
    """The study-build endpoints in memory: a design is (graph, study); edits online change its hash."""

    def __init__(self):
        self.builds, self.next_id = {}, 1
        self._dev, self._dev_host_port = True, "8021"

    def _hash(self, b):
        return hashlib.sha256(json.dumps([b["graph"], b["study"]], sort_keys=True).encode()).hexdigest()

    def _out(self, b):
        return {"id": b["id"], "status": b["status"], "design_hash": self._hash(b), "fixes": [], "warns": [],
                "client": b["client"], "urls": {"edit": f"http://x/studies/builder-next/{b['id']}/"},
                "analysis": {"id": 9, "name": "s", "url": "http://x/studies/9/"} if b["status"] == "published" else None}

    def get_study_build(self, pk):
        if pk not in self.builds:
            r = requests.Response()
            r.status_code = 404
            raise requests.HTTPError("404", response=r)
        return self._out(self.builds[pk])

    def create_study_build(self, graph=None, study=None, client=None, state=None, dry_run=False):
        b = {"id": self.next_id, "status": "draft", "graph": copy.deepcopy(graph), "study": copy.deepcopy(study or {}),
             "client": client, "forked_from": None}
        self.next_id += 1
        self.builds[b["id"]] = b
        return self._out(b)

    def update_study_build(self, pk, base_hash, graph=None, study=None, client=None, **_):
        b = self.builds[pk]
        if b["status"] != "draft" or base_hash != self._hash(b):
            raise PrismaConflictError("409", {"conflict": "online_changed"})
        b.update(graph=copy.deepcopy(graph), study=copy.deepcopy(study or {}), client=client)
        return self._out(b)

    def publish_study_build(self, pk, base_hash):
        b = self.builds[pk]
        assert base_hash == self._hash(b)
        b["status"] = "published"
        return self._out(b)

    def fork_study_build(self, pk, name=None, graph=None, study=None, client=None, **_):
        out = self.create_study_build(graph, study, client)
        self.builds[out["id"]]["forked_from"] = pk
        return out

    def get_study_build_graph(self, pk):
        b = self.builds[pk]
        return {"graph": copy.deepcopy(b["graph"]), "study": copy.deepcopy(b["study"]), "placeholders": [],
                "design_hash": self._hash(b)}

    def edit_online(self, pk, **study):
        self.builds[pk]["study"].update(study)


@pytest.fixture
def case(tmp_path):
    folder = tmp_path / "cases" / "dac_mini"
    folder.mkdir(parents=True)
    path = folder / "dac_mini.json"
    path.write_text(json.dumps(graph(), indent=2) + "\n")
    (folder / "dac_mini.study.yaml").write_text("name: DAC mini\ntime: '2030'\n")
    return path


@pytest.fixture
def server():
    return FakeServer()


def edit_local(case, **study_lines):
    p = cs.study_path_for(case)
    p.write_text(p.read_text() + "".join(f"{k}: {v}\n" for k, v in study_lines.items()))


def test_unlinked_then_push_creates_a_draft_and_links_it(case, server):
    assert cs.check(server, case).state == "unlinked"
    entry = cs.push(server, case)
    assert entry["build_id"] == 1 and entry["status"] == "draft"
    link = json.loads(cs.link_path(case).read_text())
    assert link["targets"]["dev:8021"]["build_id"] == 1
    assert "key" not in json.dumps(link).lower()
    assert server.builds[1]["client"]["case_id"] == "dac_mini"
    assert server.builds[1]["study"] == {"name": "DAC mini", "time": "2030"}
    assert cs.check(server, case).state == "in_sync"


def test_client_link_carries_the_checkout_release(case, server):
    """The build's provenance names the case's repo (not its URL), commit and release tag, and the caller's version."""
    import subprocess
    root = case.parents[2]
    git = ["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "remote", "add", "origin", "https://tok@github.com/org/PrISMa-Platform-v2.git"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "case"], check=True)
    subprocess.run([*git, "tag", "v2.0.1"], check=True)
    cs.push(server, case, tool="prisma-v2", tool_version="2.0.1")
    client = server.builds[1]["client"]
    assert (client["tool"], client["tool_version"]) == ("prisma-v2", "2.0.1")
    assert (client["repo"], client["git_tag"]) == ("PrISMa-Platform-v2", "v2.0.1")
    assert client["git_commit"] and "tok" not in json.dumps(client)


def test_client_link_outside_a_checkout_has_no_git_keys(case, server):
    cs.push(server, case)
    assert not {"repo", "git_commit", "git_tag", "tool_version"} & set(server.builds[1]["client"])


def test_local_and_online_changes_are_told_apart(case, server):
    cs.push(server, case)
    edit_local(case, desc="local")
    assert cs.check(server, case).state == "local_ahead"
    cs.push(server, case)
    assert cs.check(server, case).state == "in_sync"
    server.edit_online(1, desc="online")
    st = cs.check(server, case)
    assert (st.state, st.actions) == ("online_ahead", ["pull"])
    edit_local(case, scen="SSP2-PkBudg500")
    st = cs.check(server, case)
    assert st.state == "diverged" and st.actions == ["fork", "pull", "overwrite"]
    with pytest.raises(cs.SyncError):
        cs.push(server, case)                       # never overwrites unseen


def test_publish_then_local_change_needs_a_fork(case, server):
    entry = cs.push(server, case, publish=True)
    assert entry["status"] == "published" and entry["study_url"]
    edit_local(case, desc="after publishing")
    st = cs.check(server, case)
    assert (st.state, st.actions) == ("local_ahead", ["fork"])
    with pytest.raises(cs.SyncError):
        cs.push(server, case)
    entry = cs.fork(server, case)
    assert entry["build_id"] == 2 and entry["history"] == [1]
    assert server.builds[2]["forked_from"] == 1 and server.builds[2]["study"]["desc"] == "after publishing"
    assert cs.check(server, case).state == "in_sync"


def test_pull_writes_the_case_in_its_own_layout(case, server):
    cs.push(server, case)
    online = server.builds[1]["graph"]
    online["graph"]["nodes"].reverse()              # the server may order nodes differently
    online["graph"]["nodes"][0]["config"] = {"t_des": 370}
    server.edit_online(1, desc="online")
    cs.pull(server, case)
    doc = json.loads(case.read_text())
    assert [n["node_id"] for n in doc["graph"]["nodes"]] == ["plant", "contactor", "tea"]
    assert doc["graph"]["nodes"][2]["config"] == {"t_des": 370}
    assert list(doc) == list(graph())
    assert case.read_text().endswith("}\n")
    assert "desc: online" in cs.study_path_for(case).read_text()
    assert cs.check(server, case).state == "in_sync"


def test_pull_refuses_to_discard_local_changes(case, server):
    cs.push(server, case)
    server.edit_online(1, desc="online")
    edit_local(case, scen="x")
    with pytest.raises(cs.SyncError, match="discard"):
        cs.pull(server, case)
    cs.pull(server, case, force=True)
    assert cs.check(server, case).state == "in_sync"


def test_missing_build_relinks_on_push(case, server):
    cs.push(server, case)
    del server.builds[1]
    assert cs.check(server, case).state == "missing"
    entry = cs.push(server, case)
    assert entry["build_id"] == 2 and entry["history"] == [1]


def test_overwrite_a_draft_that_changed_online(case, server):
    cs.push(server, case)
    server.edit_online(1, desc="online")
    edit_local(case, desc="local")
    cs.push(server, case, overwrite=True)
    assert server.builds[1]["study"]["desc"] == "local"


def test_unknown_study_keys_and_wrong_formats_are_refused(case, server):
    edit_local(case, colour="red")
    with pytest.raises(cs.SyncError, match="unknown study settings"):
        cs.load_case(case)
    case.write_text(json.dumps({"format": "other"}))
    with pytest.raises(cs.SyncError, match="process_graph"):
        cs.load_case(case)


def test_system_graphs_by_path(case):
    (case.parent / "alt.json").write_text(json.dumps(graph(template_id="alt")))
    edit_local(case, systems="[{name: Alt, graph: alt.json}]")
    _, study = cs.load_case(case)
    assert study["systems"][0]["graph"]["template_id"] == "alt"


def test_cli_without_a_terminal_needs_a_decision(case, server, monkeypatch, capsys):
    cs.push(server, case)
    server.edit_online(1, desc="online")
    edit_local(case, desc="local")

    class Api:
        v2 = server
    monkeypatch.setattr("prisma_api.init", lambda local_dev=False: Api)
    server.set_return_format = lambda fmt: None
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cs.main(["publish", str(case), "--dev"]) == 2
    assert "on-conflict" in capsys.readouterr().err
    assert cs.main(["publish", str(case), "--dev", "--on-conflict", "fork", "--yes"]) == 0
    assert server.builds[2]["forked_from"] == 1


def test_install_skill(tmp_path):
    dest = cs.install_skill(tmp_path)
    assert (dest / "SKILL.md").read_text().startswith("---\nname: prisma-case")
    with pytest.raises(FileExistsError):
        cs.install_skill(tmp_path)


# ── HTTP client methods ──────────────────────────────────────────────────────

@pytest.fixture
def api():
    return PrismaAPIv2(key="test-api-key", dev=False, return_format="json")


@resp_lib.activate
def test_create_sends_graph_study_and_client(api):
    resp_lib.add(resp_lib.POST, BASE, json={"id": 1, "design_hash": "h"}, status=201,
                 match=[resp_lib.matchers.header_matcher({"X-API-Key": "test-api-key"}),
                        resp_lib.matchers.json_params_matcher({"graph": graph(), "study": {"name": "x"},
                                                              "client": {"case_id": "c"}})])
    assert api.create_study_build(graph=graph(), study={"name": "x"}, client={"case_id": "c"})["id"] == 1


@resp_lib.activate
def test_dry_run_flag(api):
    resp_lib.add(resp_lib.POST, BASE, json={"dry_run": True},
                 match=[resp_lib.matchers.query_param_matcher({"dry_run": "true"})])
    assert api.create_study_build(graph=graph(), dry_run=True)["dry_run"]


@resp_lib.activate
def test_conflict_raises_with_the_current_build(api):
    resp_lib.add(resp_lib.PUT, BASE + "4/", status=409,
                 json={"detail": "changed", "conflict": "online_changed", "build": {"id": 4, "design_hash": "new"}})
    with pytest.raises(PrismaConflictError) as err:
        api.update_study_build(4, "old", graph=graph())
    assert err.value.conflict == "online_changed" and err.value.build["design_hash"] == "new"


@resp_lib.activate
def test_forbidden_is_an_http_error_with_the_server_message(api):
    resp_lib.add(resp_lib.GET, BASE + "catalogue/", status=403,
                 json={"detail": "The study builder API is restricted to the case study builder team."})
    with pytest.raises(requests.HTTPError, match="restricted"):
        api.study_build_catalogue()


@resp_lib.activate
def test_publish_fork_graph_and_status_paths(api):
    resp_lib.add(resp_lib.POST, BASE + "4/publish/", json={"status": "published"},
                 match=[resp_lib.matchers.json_params_matcher({"base_hash": "h"})])
    resp_lib.add(resp_lib.POST, BASE + "4/fork/", json={"id": 5}, status=201,
                 match=[resp_lib.matchers.json_params_matcher({"name": "N"})])
    resp_lib.add(resp_lib.GET, BASE + "4/graph/", json={"graph": {}})
    resp_lib.add(resp_lib.POST, BASE + "4/status/", json={"status": "abandoned"},
                 match=[resp_lib.matchers.json_params_matcher({"action": "abandon"})])
    assert api.publish_study_build(4, "h")["status"] == "published"
    assert api.fork_study_build(4, name="N")["id"] == 5
    assert api.get_study_build_graph(4) == {"graph": {}}
    assert api.set_study_build_status(4, "abandon")["status"] == "abandoned"


def test_exactly_one_design(api):
    with pytest.raises(ValueError):
        api.create_study_build()
    with pytest.raises(ValueError):
        api.create_study_build(graph=graph(), state={})
