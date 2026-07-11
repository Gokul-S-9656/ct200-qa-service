"""
End-to-end API tests using FastAPI's TestClient (which triggers the app's
lifespan, so startup seeding runs exactly like it would in production).

Run with: pytest -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "sqlite:///./test_ct200.db"
os.environ["TINYDB_PATH"] = "./test_tinydb_generations.json"
os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    for f in ("test_ct200.db", "test_tinydb_generations.json"):
        if os.path.exists(f):
            os.remove(f)
    from app.main import app
    with TestClient(app) as c:
        yield c
    for f in ("test_ct200.db", "test_tinydb_generations.json"):
        if os.path.exists(f):
            os.remove(f)


def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_top_level_sections_seeded_on_startup(client):
    resp = client.get("/nodes")
    assert resp.status_code == 200
    sections = resp.json()
    assert len(sections) == 10  # 1..10 top-level sections in the manual
    assert sections[0]["heading"] == "1. Introduction"
    assert sections[4]["heading"] == "5. Error Codes"


def test_get_node_includes_children_and_body(client):
    resp = client.get("/nodes")
    error_codes_id = next(s["id"] for s in resp.json() if s["heading"] == "5. Error Codes")

    detail = client.get(f"/nodes/{error_codes_id}").json()
    assert detail["heading"] == "5. Error Codes"
    assert len(detail["children"]) == 3
    child_headings = {c["heading"] for c in detail["children"]}
    assert child_headings == {"5.1 E1", "5.2 E2", "5.3 E3"}


def test_get_unknown_node_returns_404(client):
    resp = client.get("/nodes/99999")
    assert resp.status_code == 404


def test_search_finds_overpressure_section(client):
    resp = client.get("/nodes/search", params={"q": "overpressure"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["heading"] == "5.3 E3" for r in results)


def test_selection_create_and_retrieve(client):
    e3_id = client.get("/nodes/search", params={"q": "E3"}).json()[0]["id"]

    create_resp = client.post("/selections", json={"node_ids": [e3_id], "name": "overpressure case"})
    assert create_resp.status_code == 201
    selection_id = create_resp.json()["id"]

    get_resp = client.get(f"/selections/{selection_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["nodes"][0]["id"] == e3_id


def test_selection_with_unknown_node_returns_400(client):
    resp = client.post("/selections", json={"node_ids": [99999]})
    assert resp.status_code == 400


def test_generate_and_retrieve_test_cases(client):
    e3_id = client.get("/nodes/search", params={"q": "E3"}).json()[0]["id"]
    selection_id = client.post("/selections", json={"node_ids": [e3_id]}).json()["id"]

    gen_resp = client.post(f"/selections/{selection_id}/generate")
    assert gen_resp.status_code == 201
    body = gen_resp.json()
    assert 3 <= len(body["test_cases"]) <= 5
    assert body["provider"] == "mock"
    # The mock provider is keyword-aware: E3/overpressure content should
    # surface an overpressure-specific test case, not a generic one only.
    titles = " ".join(tc["title"].lower() for tc in body["test_cases"])
    assert "overpressure" in titles or "e3" in titles

    by_selection = client.get(f"/selections/{selection_id}/generations").json()
    assert len(by_selection) == 1

    by_node = client.get(f"/nodes/{e3_id}/generations").json()
    assert len(by_node) == 1
    assert by_node[0]["id"] == body["id"]


def test_generate_for_unknown_selection_returns_404(client):
    resp = client.post("/selections/99999/generate")
    assert resp.status_code == 404
