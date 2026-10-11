"""Attribution graphs in louped's own view: each node's share of the influence on the logits, and
pins kept where circuit-tracer's viewer reads them."""

import json

import pytest
from fastapi.testclient import TestClient

from louped.core import graphs_dir
from louped.server import create_app


@pytest.fixture
def graph() -> dict:
    """Two prompt tokens; a feature and an error node at layer 0; one logit."""
    nodes = [
        {"node_id": "E_1_0", "feature": 0, "layer": "E", "ctx_idx": 0, "feature_type": "embedding",
         "clerp": "Hi"},
        {"node_id": "E_2_1", "feature": 1, "layer": "E", "ctx_idx": 1, "feature_type": "embedding",
         "clerp": ""},
        {"node_id": "0_7_1", "feature": 7, "layer": "0", "ctx_idx": 1,
         "feature_type": "cross layer transcoder", "clerp": "", "activation": 1.5},
        {"node_id": "0_1_1", "feature": 1, "layer": "0", "ctx_idx": 1,
         "feature_type": "mlp reconstruction error", "clerp": ""},
        {"node_id": "2_9_1", "feature": 9, "layer": "2", "ctx_idx": 1, "feature_type": "logit",
         "token_prob": 0.6, "is_target_logit": True, "clerp": 'Output "x"'},
    ]  # fmt: skip
    links = [
        {"source": "E_1_0", "target": "2_9_1", "weight": 1.0},
        {"source": "0_7_1", "target": "2_9_1", "weight": -3.0},
        {"source": "E_2_1", "target": "0_7_1", "weight": 2.0},
        {"source": "0_1_1", "target": "0_7_1", "weight": 2.0},
    ]
    meta = {"slug": "g", "scan": "tiny", "prompt": "Hi there", "prompt_tokens": ["Hi", " there"]}
    data = {"metadata": meta, "qParams": {"pinnedIds": [], "supernodes": []}, "nodes": nodes,
            "links": links}  # fmt: skip
    graphs_dir().mkdir(parents=True, exist_ok=True)
    (graphs_dir() / "g.json").write_text(json.dumps(data))
    return data


def test_a_graph_scores_each_node_by_its_share_of_the_logit(graph: dict) -> None:
    client = TestClient(create_app(), base_url="http://localhost")
    got = client.get("/api/graphs/g").json()
    nodes = {n["id"]: n for n in got["nodes"]}
    assert {i: n["score"] for i, n in nodes.items()} == {
        "E_1_0": 0.25, "E_2_1": 0.375, "0_7_1": 0.75, "0_1_1": 0.375, "2_9_1": 1.0}  # fmt: skip
    assert {i: (n["kind"], n["row"]) for i, n in nodes.items()} == {
        "E_1_0": ("embedding", 0), "E_2_1": ("embedding", 0), "0_7_1": ("feature", 1),
        "0_1_1": ("error", 1), "2_9_1": ("logit", 2)}  # fmt: skip
    assert [nodes[i]["label"] for i in ("E_2_1", "0_7_1", "0_1_1")] == [
        " there", "feature 0.7", "error at layer 0, ' there'"]  # fmt: skip
    assert nodes["2_9_1"]["target"] and nodes["2_9_1"]["prob"] == 0.6
    assert {(x["source"], x["target"]): x["share"] for x in got["links"]}[
        ("0_7_1", "2_9_1")
    ] == 0.75
    assert got["tokens"] == ["Hi", " there"] and got["pinned"] == []


def test_pins_and_groups_are_kept_in_the_graph_file(graph: dict) -> None:
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    pins = {"pinned": ["0_7_1", "2_9_1"], "groups": [{"name": "greeting", "nodes": ["E_1_0"]}]}
    assert client.put("/api/graphs/g/pins", json=pins).json() == pins
    saved = json.loads((graphs_dir() / "g.json").read_text())["qParams"]
    assert saved["pinnedIds"] == ["0_7_1", "2_9_1"]
    assert saved["supernodes"] == [["greeting", "E_1_0"]]
    got = client.get("/api/graphs/g").json()
    assert (got["pinned"], got["groups"]) == (pins["pinned"], pins["groups"])

    bad = client.put("/api/graphs/g/pins", json={"pinned": ["nope"]})
    assert bad.status_code == 400 and "no node nope" in bad.json()["detail"]
    assert client.get("/api/graphs/none").status_code == 404
    assert client.get("/api/graphs/g.meta").status_code == 400
    shared = TestClient(create_app(), base_url="http://localhost")
    assert shared.put("/api/graphs/g/pins", json=pins).status_code == 403


def test_an_agent_reads_a_circuit_and_pins_its_nodes(graph: dict) -> None:
    from test_agent import call, tools

    mcp = tools()
    assert [g["slug"] for g in call(mcp, "circuit")["graphs"]] == []  # no metadata file here
    got = call(mcp, "circuit", slug="g", top=2)
    assert got["outputs"] == [{"id": "2_9_1", "label": 'Output "x"', "prob": 0.6, "target": True}]
    assert [(n["id"], n["token"]) for n in got["nodes"]] == [
        ("0_7_1", " there"),
        ("E_2_1", " there"),
    ]
    call(mcp, "pin_circuit", slug="g", pinned=["0_7_1"], groups=[{"name": "a", "nodes": ["E_1_0"]}])
    assert call(mcp, "circuit", slug="g")["pinned"] == ["0_7_1"]


def test_circuit_tracers_own_influence_comes_along_and_a_graph_needs_probabilities(
    graph: dict,
) -> None:
    graph["nodes"][2]["influence"] = 0.4
    (graphs_dir() / "g.json").write_text(json.dumps(graph))
    client = TestClient(create_app(), base_url="http://localhost")
    nodes = {n["id"]: n for n in client.get("/api/graphs/g").json()["nodes"]}
    assert nodes["0_7_1"]["influence"] == 0.4 and nodes["E_1_0"]["influence"] is None
    graph["nodes"][4].pop("token_prob")
    (graphs_dir() / "g.json").write_text(json.dumps(graph))
    bad = client.get("/api/graphs/g")
    assert bad.status_code == 400 and "no logit with a probability" in bad.json()["detail"]
