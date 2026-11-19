import uuid

import pytest

from tests.factories import add_model, add_request


@pytest.fixture
async def history(session):
    alpha = await add_model(session, "alpha")
    beta = await add_model(session, "beta", provider="demo")
    records = [
        await add_request(session, alpha, latency_ms=100, minutes_ago=1, prompt="Summarise the quarterly report"),
        await add_request(session, alpha, latency_ms=200, minutes_ago=2, prompt="Translate to French"),
        await add_request(
            session, alpha, latency_ms=300, minutes_ago=3, status="error", error_message="gateway exploded"
        ),
        await add_request(session, beta, latency_ms=50, minutes_ago=4, prompt="Discount is 100% today"),
        await add_request(session, beta, latency_ms=60, minutes_ago=600, prompt="An old request"),
    ]
    return alpha, beta, records


async def test_lists_newest_first_with_metrics(client, history):
    page = (await client.get("/api/logs")).json()

    assert page["total"] == 5
    assert [item["latency_ms"] for item in page["items"]] == [100, 200, 300, 50, 60]
    first = page["items"][0]
    assert first["prompt_preview"] == "Summarise the quarterly report"
    assert first["token_count_source"] == "exact"
    assert first["total_tokens"] == 30


async def test_search_matches_prompt_and_error_text(client, history):
    by_prompt = (await client.get("/api/logs", params={"search": "quarterly"})).json()
    by_error = (await client.get("/api/logs", params={"search": "EXPLODED"})).json()

    assert by_prompt["total"] == 1
    assert by_error["total"] == 1 and by_error["items"][0]["status"] == "error"


async def test_search_treats_wildcards_literally(client, history):
    page = (await client.get("/api/logs", params={"search": "100%"})).json()

    assert page["total"] == 1
    assert page["items"][0]["prompt_preview"] == "Discount is 100% today"


async def test_search_by_request_id(client, history):
    _, _, records = history
    page = (await client.get("/api/logs", params={"search": str(records[1].id)})).json()

    assert page["total"] == 1 and page["items"][0]["id"] == str(records[1].id)


async def test_filters_combine(client, history):
    alpha, _, _ = history

    errors = (await client.get("/api/logs", params={"status": "error"})).json()
    alpha_only = (await client.get("/api/logs", params={"model_id": str(alpha.id)})).json()
    real_only = (await client.get("/api/logs", params={"data_source": "real"})).json()
    demo_recent = (await client.get("/api/logs", params={"data_source": "demo", "window": "1h"})).json()

    assert errors["total"] == 1
    assert alpha_only["total"] == 3
    assert real_only["total"] == 3 and not any(item["is_demo"] for item in real_only["items"])
    assert demo_recent["total"] == 1


async def test_pagination(client, history):
    first = (await client.get("/api/logs", params={"page_size": 2, "page": 1})).json()
    last = (await client.get("/api/logs", params={"page_size": 2, "page": 3})).json()

    assert first["total"] == 5 and len(first["items"]) == 2
    assert len(last["items"]) == 1
    assert {item["id"] for item in first["items"]}.isdisjoint({item["id"] for item in last["items"]})


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 101}, {"status": "weird"}, {"window": "3d"}])
async def test_invalid_query_parameters(client, params):
    assert (await client.get("/api/logs", params=params)).status_code == 422


async def test_detail_returns_full_record(client, history):
    _, _, records = history
    errored = records[2]

    detail = (await client.get(f"/api/logs/{errored.id}")).json()

    assert detail["status"] == "error"
    assert detail["error_message"] == "gateway exploded"
    assert detail["metrics"]["latency_ms"] == 300
    assert detail["prompt"] == "test prompt"


async def test_detail_for_missing_request(client):
    response = await client.get(f"/api/logs/{uuid.uuid4()}")
    assert response.status_code == 404
