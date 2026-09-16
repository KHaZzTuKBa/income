from httpx import AsyncClient

from tests.test_dashboard import _seed
from tests.test_sync import _payload


async def test_categories_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/categories")
    assert response.status_code == 401


async def test_categories_empty(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/categories")
    assert response.status_code == 200
    body = response.json()
    assert body["tree"] == []
    assert body["portfolio_value"] == "0.00"
    assert body["unassigned"] == []


async def test_category_crud_and_fact(auth_client: AsyncClient, monkeypatch) -> None:
    await _seed(auth_client, monkeypatch, _payload(), prices={})

    created = await auth_client.post(
        "/api/categories",
        json={"name": "Акции", "target_share": 60},
    )
    assert created.status_code == 201
    stocks_id = created.json()["id"]

    nested = await auth_client.post(
        "/api/categories",
        json={"name": "Сбер", "parent_id": stocks_id, "target_share": 50},
    )
    assert nested.status_code == 201
    child_id = nested.json()["id"]

    assigned = await auth_client.put(
        "/api/categories/assignments",
        json={"figi": "BBG004730N88", "category_id": child_id},
    )
    assert assigned.status_code == 204

    body = (await auth_client.get("/api/categories")).json()
    assert body["portfolio_value"] == "4200.00"
    assert body["root_target"] == "60.00"
    assert body["unassigned_value"] == "1500.00"
    assert body["unassigned_share"] == "35.71"
    assert len(body["unassigned"]) == 1
    assert body["unassigned"][0]["ticker"] == "RUB"

    assert body["unassigned_pnl"] == "0.00"
    assert body["unassigned_pnl_percent"] is None

    root = body["tree"][0]
    assert root["name"] == "Акции"
    assert root["target_share"] == "60.00"
    assert root["value"] == "2700.00"
    assert root["cost"] == "2500.00"
    assert root["pnl"] == "200.00"
    assert root["pnl_percent"] == "8.00"
    assert root["fact_share"] == "64.29"
    assert root["delta_share"] == "4.29"
    assert root["own_value"] == "0.00"
    child = root["children"][0]
    assert child["name"] == "Сбер"
    assert child["value"] == "2700.00"
    assert child["cost"] == "2500.00"
    assert child["pnl"] == "200.00"
    assert child["pnl_percent"] == "8.00"
    assert child["fact_share"] == "64.29"
    assert child["holdings"][0]["ticker"] == "SBER"

    renamed = await auth_client.patch(
        f"/api/categories/{stocks_id}",
        json={"name": "Акции РФ", "target_share": 70},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Акции РФ"

    moved = await auth_client.put(
        "/api/categories/assignments",
        json={"figi": "BBG004730N88", "category_id": stocks_id},
    )
    assert moved.status_code == 204
    after_move = (await auth_client.get("/api/categories")).json()
    assert after_move["tree"][0]["own_value"] == "2700.00"
    assert after_move["tree"][0]["children"][0]["holdings"] == []

    await auth_client.put(
        "/api/categories/assignments",
        json={"figi": "BBG004730N88", "category_id": None},
    )
    cleared = (await auth_client.get("/api/categories")).json()
    assert cleared["unassigned_value"] == "4200.00"
    assert cleared["tree"][0]["value"] == "0.00"


async def test_category_cycle_rejected(auth_client: AsyncClient) -> None:
    parent = await auth_client.post("/api/categories", json={"name": "Родитель"})
    child = await auth_client.post(
        "/api/categories",
        json={"name": "Дитя", "parent_id": parent.json()["id"]},
    )
    response = await auth_client.patch(
        f"/api/categories/{parent.json()['id']}",
        json={"parent_id": child.json()["id"]},
    )
    assert response.status_code == 400
    assert "потомка" in response.json()["detail"]


async def test_delete_category_cascades(auth_client: AsyncClient, monkeypatch) -> None:
    await _seed(auth_client, monkeypatch, _payload(), prices={})
    parent = await auth_client.post("/api/categories", json={"name": "Корень"})
    child = await auth_client.post(
        "/api/categories",
        json={"name": "Вложенная", "parent_id": parent.json()["id"]},
    )
    await auth_client.put(
        "/api/categories/assignments",
        json={"figi": "BBG004730N88", "category_id": child.json()["id"]},
    )
    deleted = await auth_client.delete(f"/api/categories/{parent.json()['id']}")
    assert deleted.status_code == 204
    body = (await auth_client.get("/api/categories")).json()
    assert body["tree"] == []
    assert any(item["ticker"] == "SBER" for item in body["unassigned"])


async def test_unknown_category(auth_client: AsyncClient) -> None:
    response = await auth_client.patch("/api/categories/999", json={"name": "Нет"})
    assert response.status_code == 404
