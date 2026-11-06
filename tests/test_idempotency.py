from datetime import datetime, timedelta, timezone

from slot_api.models.slot import Slot

VALID_BODY = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}


def make_slot(id="s1", available=True, start=None):
    if start is None:
        start = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)
    return Slot(
        id=id,
        provider="Dr Ade",
        start=start,
        end=start + timedelta(minutes=30),
        available=available,
    )


async def seed(client, *rows):
    for row in rows:
        client.session.add(row)
    await client.session.flush()


# ---------------------------------------------------------------------------
# Same key, same body → same response, no duplicate
# ---------------------------------------------------------------------------


async def test_idempotent_same_key_same_body_returns_same_booking(client):
    await seed(client, make_slot("s1"))

    r1 = await client.post(
        "/bookings", json=VALID_BODY, headers={"Idempotency-Key": "k1"}
    )
    r2 = await client.post(
        "/bookings", json=VALID_BODY, headers={"Idempotency-Key": "k1"}
    )

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


async def test_idempotent_does_not_create_second_booking(client):
    await seed(client, make_slot("s1"))

    await client.post("/bookings", json=VALID_BODY, headers={"Idempotency-Key": "k1"})
    await client.post("/bookings", json=VALID_BODY, headers={"Idempotency-Key": "k1"})

    # Listing bookings for this email should return exactly one.
    listing = (
        await client.get("/bookings", params={"email": "ada@example.com"})
    ).json()
    assert len(listing["bookings"]) == 1


# ---------------------------------------------------------------------------
# Same key, different body → 422
# ---------------------------------------------------------------------------


async def test_idempotent_same_key_different_body_returns_422(client):
    await seed(client, make_slot("s1"))

    r1 = await client.post(
        "/bookings", json=VALID_BODY, headers={"Idempotency-Key": "k1"}
    )
    r2 = await client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Other", "email": "ada@example.com"},
        headers={"Idempotency-Key": "k1"},
    )

    assert r1.status_code == 201
    assert r2.status_code == 422
    assert r2.json() == {"error": "slot not found"}


# ---------------------------------------------------------------------------
# No key → normal behaviour (no caching)
# ---------------------------------------------------------------------------


async def test_no_idempotency_key_creates_independent_bookings(client):
    await seed(client, make_slot("s1"), make_slot("s2"))

    r1 = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s1"})
    r2 = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s2"})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


# ---------------------------------------------------------------------------
# Idempotency caches error responses too
# ---------------------------------------------------------------------------


async def test_idempotent_caches_404_response(client):
    r1 = await client.post(
        "/bookings",
        json={**VALID_BODY, "slot_id": "missing"},
        headers={"Idempotency-Key": "k1"},
    )
    r2 = await client.post(
        "/bookings",
        json={**VALID_BODY, "slot_id": "missing"},
        headers={"Idempotency-Key": "k1"},
    )

    assert r1.status_code == 404
    assert r2.status_code == 404
    assert r1.json() == r2.json()


# ---------------------------------------------------------------------------
# Whitespace differences in body are treated as same (validators normalise)
# ---------------------------------------------------------------------------


async def test_idempotent_treats_trimmed_name_as_same(client):
    await seed(client, make_slot("s1"))

    r1 = await client.post(
        "/bookings",
        json={**VALID_BODY, "name": "Ada Obi"},
        headers={"Idempotency-Key": "k1"},
    )
    r2 = await client.post(
        "/bookings",
        json={**VALID_BODY, "name": "  Ada Obi  "},
        headers={"Idempotency-Key": "k1"},
    )

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
