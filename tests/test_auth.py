from httpx import ASGITransport, AsyncClient

from slot_api.core.config import settings
from slot_api.main import app


def make_client(**headers) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    )


async def test_valid_api_key_passes(client):
    response = await client.get("/health", headers={"X-API-Key": settings.api_key})
    assert response.status_code == 200


async def test_missing_api_key_returns_401():
    async with make_client() as ac:
        response = await ac.get("/health")
    assert response.status_code == 401


async def test_incorrect_api_key_returns_401():
    async with make_client(**{"X-API-Key": "wrong-key"}) as ac:
        response = await ac.get("/health")
    assert response.status_code == 401


async def test_401_applies_to_api_endpoints():
    async with make_client() as ac:
        for method, path in (
            ("GET", "/slots"),
            ("GET", "/bookings"),
            ("GET", "/bookings/abc"),
        ):
            response = await ac.request(method, path)
            assert response.status_code == 401, path
