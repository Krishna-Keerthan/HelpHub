from httpx import AsyncClient


async def test_health_db(client: AsyncClient) -> None:
    response = await client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
