"""prisma_api.ontology / prisma-ontology: reading an ontology folder, provenance from git, hashes, the v2 calls."""
import hashlib
import json
import subprocess

import pytest
import responses as resp_lib

from prisma_api import PrismaAPIv2, PrismaConflictError
from prisma_api import ontology as on

BASE = "https://prisma-platform.org/api/v2/ontologies/"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def folder(tmp_path):
    """A small ontology laid out like PrISMa-Platform-v2/src/ontology."""
    root = tmp_path / "src" / "ontology"
    t = root / "tree"
    write(t / "_node.yaml", "id: home\nt: PrISMa layers\ntype: home\nchildren:\n  - folder: 01-material-layer\n  - folder: 02-common\n")
    write(t / "01-material-layer" / "_node.yaml",
          "id: material\nt: Material layer\nlayer: m\nnote: A material has an identity.\nchildren:\n  - folder: 01-material\n")
    write(t / "01-material-layer" / "01-material" / "_node.yaml",
          "id: mat\nt: Material\nk: mat\nchildren:\n  - id: ident\n    t: Identity\n    k: ident\n")
    write(t / "01-material-layer" / "01-material" / "mat-material.yaml", """key: mat
label: Material
summary: One record per material.
groups:
  - title: Keys
    note: false
    items:
      - item: id
        definition: Unique key.
        source: definitions_v2.json
        basis: proposed
        matches:
          - relation: close
            ontology: afo
            iri: http://purl.allotrope.org/AFR_0000917
            label: identifier
            difference: broader
      - item: name
      - item: +purity · %
  - title: Notes
    note: true
    items:
      - item: Purity is a Value.
""")
    write(t / "01-material-layer" / "01-material" / "ident-identity.yaml",
          "key: ident\nlabel: Identity\nsummary: Names.\ngroups:\n  - title: Keys\n    items:\n      - item: cas\n"
          "unmatched_definitions:\n")
    write(t / "02-common" / "_node.yaml", "id: common\nt: Cross-layer\nlayer: x\nchildren:\n  - ref: mat\n    t: Material\n")
    write(t / "_data" / "sources.yaml", "- name: afo\n  version: REC/2026/09\n  licence: CC-BY 4.0\n  source: https://purl.allotrope.org/afo.ttl\n"
          "- name: envo\n  version: 2026-10-23\n  licence: CC0\n  source: https://example.org/envo.owl\n")
    write(t / "_data" / "ont_sets.json", '["pgas", "pliq"]')
    write(root / "simpletree" / "01-material-layer" / "01-material" / "mat-material.yaml",
          "key: mat\nlabel: Material\ngroups:\n  - title: Keys\n    items:\n      - name\n      - id\n")
    write(root / "tools" / "build.py", 'BASE = "https://example.org/ontology#"\n')
    return root


def test_build_payload_reads_the_folder(folder):
    doc = on.build_payload(folder)
    assert doc["_schema"] == on.SCHEMA
    assert doc["ontology"] == {"slug": "prisma", "name": "PrISMa ontology", "base_iri": "https://example.org/ontology#"}
    assert [b["key"] for b in doc["blocks"]] == ["mat", "ident"]                    # navigation order
    mat = doc["blocks"][0]
    assert mat["path"] == "tree/01-material-layer/01-material/mat-material.yaml"
    assert mat["groups"][0]["items"][1] == {"item": "name"}
    assert mat["groups"][0]["items"][0]["matches"][0]["relation"] == "close"
    assert doc["blocks"][1]["unmatched_definitions"] == []                         # present though empty
    assert doc["blocks"][1]["groups"][0]["note"] is False                          # note defaults to false
    nav = doc["nav"]
    assert "folder" not in nav and nav["children"][0]["folder"] == "01-material-layer"
    assert nav["children"][0]["children"][0]["children"][0] == {"id": "ident", "t": "Identity", "k": "ident", "children": []}
    assert doc["sources"][1]["version"] == "2026-10-23"                             # dates stay text
    assert doc["profiles"] == [{"name": "simple", "label": "Simpler version (sorbents)", "blocks": [
        {"key": "mat", "groups": [{"title": "Keys", "items": ["id", "name"]}]}]}]   # tree order
    assert doc["data"] == {"ont_sets.json": ["pgas", "pliq"]}


def test_hashes(folder):
    doc = on.build_payload(folder)
    files = doc["hashes"]["files"]
    rel = "tree/01-material-layer/01-material/mat-material.yaml"
    assert files[rel] == hashlib.sha256((folder / rel).read_bytes()).hexdigest()
    assert "simpletree/01-material-layer/01-material/mat-material.yaml" in files
    assert "tools/build.py" not in files
    assert doc["hashes"]["files_hash"] == on.files_hash(files)
    assert doc["hashes"]["content"] == on.content_hash(doc)
    # formatting is not content; a changed definition is
    path = folder / rel
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    again = on.build_payload(folder)
    assert again["hashes"]["content"] == doc["hashes"]["content"]
    assert again["hashes"]["files_hash"] != doc["hashes"]["files_hash"]
    path.write_text(path.read_text(encoding="utf-8").replace("Unique key.", "Unique key of a material."), encoding="utf-8")
    assert on.build_payload(folder)["hashes"]["content"] != doc["hashes"]["content"]


def test_accepts_the_tree_folder_and_manifest(folder):
    write(folder / "ontology.yaml", "slug: prisma-core\nname: PrISMa core\nversion: 0.3\n")
    doc = on.build_payload(folder / "tree")
    assert doc["ontology"]["slug"] == "prisma-core"
    assert doc["ontology"]["version"] == "0.3"
    assert "ontology.yaml" in doc["hashes"]["files"]
    assert on.build_payload(folder, slug="other")["ontology"]["slug"] == "other"


def test_bad_folders(folder, tmp_path):
    with pytest.raises(on.OntologyError, match="holds no ontology"):
        on.build_payload(tmp_path)
    write(folder / "tree" / "02-common" / "x-x.yaml", "key: x\nkey: y\nlabel: X\n")
    with pytest.raises(on.OntologyError, match="repeated"):
        on.build_payload(folder)


def test_profile_must_match_the_tree(folder):
    write(folder / "simpletree" / "01-material-layer" / "01-material" / "mat-material.yaml",
          "key: mat\nlabel: Material\ngroups:\n  - title: Keys\n    items:\n      - nothere\n")
    with pytest.raises(on.OntologyError, match="items not in the tree"):
        on.build_payload(folder)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_git_provenance(folder, tmp_path):
    repo = tmp_path
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Ada")
    git(repo, "config", "user.email", "ada@example.org")
    git(repo, "remote", "add", "origin", "https://user:token123@github.com/team/PrISMa-Platform-v2.git")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "ontology")
    git(repo, "tag", "v2.0.1")
    src = on.git_provenance(folder)
    assert src["repo"] == "PrISMa-Platform-v2"
    assert src["repo_url"] == "https://github.com/team/PrISMa-Platform-v2"
    assert src["path"] == "src/ontology"
    assert src["branch"] == "main"
    assert len(src["commit"]) == 40 and src["tag"] == "v2.0.1" and src["exact_tag"] == "v2.0.1"
    assert src["commit_author"] == "Ada" and src["path_commit"] == src["commit"]
    assert src["dirty"] is False
    assert src["links"]["tree"] == f"https://github.com/team/PrISMa-Platform-v2/tree/{src['commit']}/src/ontology"
    assert src["links"]["tag"] == "https://github.com/team/PrISMa-Platform-v2/releases/tag/v2.0.1"
    doc = on.build_payload(folder, tool="prisma-v2", tool_version="2.0.1")
    assert "token123" not in json.dumps(doc)
    assert doc["provenance"]["tool"] == "prisma-v2" and doc["provenance"]["sent_by"] == "Ada"
    write(folder / "tree" / "01-material-layer" / "_node.yaml", "id: material\nt: Material layer (edited)\nlayer: m\nchildren:\n  - folder: 01-material\n")
    assert on.git_provenance(folder)["dirty"] is True


def test_client_provenance(folder):
    from prisma_api import __version__
    client = on.client_provenance()
    assert client["name"] == "prisma_api" and client["version"] == __version__
    assert client["install"] in ("checkout", "editable", "vcs", "local", "index", "source")
    if client["install"] in ("checkout", "editable"):                 # tests run from the prisma_api repository
        assert len(client["commit"]) == 40                          # the tag needs tags fetched (CI checks out shallow, without them)
    assert "@" not in client.get("repo_url", "")
    doc = on.build_payload(folder, tool="prisma-v2", tool_version="2.0.1")
    assert doc["provenance"]["client"] == client                     # the caller and the library both recorded
    assert (doc["provenance"]["tool"], doc["provenance"]["tool_version"]) == ("prisma-v2", "2.0.1")


def test_clean_url():
    assert on.clean_url("git@github.com:team/repo.git") == "https://github.com/team/repo"
    assert on.clean_url("https://x:y@gitlab.com/a/b/") == "https://gitlab.com/a/b"
    assert on.clean_url("/local/path") == ""


@resp_lib.activate
def test_push_ontology(folder):
    resp_lib.add(resp_lib.POST, BASE + "ingest/", json={"changed": True, "created": False, "dry_run": True, "release": 1,
                                                        "ontology": "prisma", "counts": {}, "diff": None})
    v2 = PrismaAPIv2(key="k")
    out = v2.push_ontology(folder, dry_run=True)
    assert out["release"] == 1
    call = resp_lib.calls[0]
    assert "dry_run=true" in call.request.url
    assert call.request.headers["X-API-Key"] == "k"
    body = json.loads(call.request.body)
    assert body["_schema"] == on.SCHEMA and body["hashes"]["content"] == on.content_hash(body)


@resp_lib.activate
def test_conflict_and_reads(folder):
    resp_lib.add(resp_lib.POST, BASE + "ingest/", status=409, json={"detail": "older than release 3", "conflict": "older_than_current"})
    resp_lib.add(resp_lib.GET, BASE, json={"count": 0, "records": []})
    resp_lib.add(resp_lib.GET, BASE + "prisma/", json={"release": {"number": 2}})
    resp_lib.add(resp_lib.GET, BASE + "prisma/releases/", json={"records": []})
    v2 = PrismaAPIv2(key="k")
    with pytest.raises(PrismaConflictError, match="older than release 3"):
        v2.push_ontology(folder)
    assert v2.list_ontologies()["count"] == 0
    assert v2.get_ontology("prisma", release=2)["release"]["number"] == 2
    assert "release=2" in resp_lib.calls[2].request.url
    v2.list_ontology_releases("prisma", limit=5)
    assert "limit=5" in resp_lib.calls[3].request.url


def test_cli_build(folder, tmp_path, capsys):
    out = tmp_path / "doc.json"
    assert on.main(["build", str(folder), "--out", str(out)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["blocks"] == 2 and summary["items"] == 5 and summary["profiles"] == ["simple"]
    assert json.loads(out.read_text(encoding="utf-8"))["hashes"]["content"] == summary["content_hash"]
