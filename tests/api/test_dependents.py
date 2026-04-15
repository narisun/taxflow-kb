"""Tests for dependent CRUD with PII encryption."""
import pytest


@pytest.mark.asyncio
async def test_add_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    resp = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01",
        "relationship": "daughter", "is_qualifying_child": True,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["first_name"] == "Emily"
    assert body["ssn_masked"] == "***-**-3333"
    assert body["dob_masked"] == "**/**/2015"


@pytest.mark.asyncio
async def test_list_dependents_masked(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "A", "last_name": "S", "ssn": "111111111",
        "dob": "2015-01-01", "relationship": "son",
    })
    await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "B", "last_name": "S", "ssn": "222222222",
        "dob": "2018-06-01", "relationship": "daughter",
    })
    resp = await client.get(f"/api/clients/{cid}/dependents")
    assert resp.status_code == 200
    deps = resp.json()
    assert len(deps) == 2
    assert deps[0]["ssn_masked"] == "***-**-1111"
    assert "111111111" not in str(deps)


@pytest.mark.asyncio
async def test_update_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    dep = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01", "relationship": "daughter",
    })
    dep_id = dep.json()["id"]
    resp = await client.patch(f"/api/clients/{cid}/dependents/{dep_id}", json={
        "relationship": "stepdaughter",
    })
    assert resp.status_code == 200
    assert resp.json()["relationship"] == "stepdaughter"


@pytest.mark.asyncio
async def test_delete_dependent(client):
    c = await client.post("/api/clients", json={"name": "Smith", "tax_year": 2024})
    cid = c.json()["id"]
    dep = await client.post(f"/api/clients/{cid}/dependents", json={
        "first_name": "Emily", "last_name": "Smith",
        "ssn": "111223333", "dob": "2015-06-01", "relationship": "daughter",
    })
    dep_id = dep.json()["id"]
    resp = await client.delete(f"/api/clients/{cid}/dependents/{dep_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/clients/{cid}/dependents")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_dependent_nonexistent_client(client):
    resp = await client.post("/api/clients/9999/dependents", json={
        "first_name": "A", "last_name": "B", "ssn": "111111111",
        "dob": "2015-01-01", "relationship": "son",
    })
    assert resp.status_code == 404
