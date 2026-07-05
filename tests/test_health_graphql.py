from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_healthcheck_query_success(http_client: AsyncClient) -> None:
    query = """
        query {
            healthcheck { isRunning model version }
        }
    """

    response = await http_client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    body = response.json()
    assert body.get("errors") is None
    payload = body["data"]["healthcheck"]
    assert payload["isRunning"] is True
    assert payload["model"] == "integration-model"
    assert payload["version"]
