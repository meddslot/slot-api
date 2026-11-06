from datetime import datetime, timedelta, timezone

from slot_api.models.slot import Slot


def make_slot(id, available=True, start=None):
    if start is None:
        start = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)
    return Slot(
        id=id,
        provider="Dr Ade",
        start=start,
        end=start + timedelta(minutes=30),
        available=available,
    )


VALID_BODY = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}


async def seed(client, *rows):
    for row in rows:
        client.session.add(row)
    await client.session.flush()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_create_booking_returns_201(client):
    await seed(client, make_slot("s1"))

    response = await client.post("/bookings", json=VALID_BODY)

    assert response.status_code == 201


async def test_create_booking_response_shape(client):
    await seed(client, make_slot("s1"))

    data = (await client.post("/bookings", json=VALID_BODY)).json()

    assert set(data.keys()) == {
        "id",
        "slot_id",
        "name",
        "email",
        "status",
        "created_at",
    }


async def test_create_booking_response_values(client):
    await seed(client, make_slot("s1"))

    data = (await client.post("/bookings", json=VALID_BODY)).json()

    assert data["slot_id"] == "s1"
    assert data["name"] == "Ada Obi"
    assert data["email"] == "ada@example.com"
    assert data["status"] == "confirmed"
    assert data["id"]
    assert data["created_at"]


async def test_create_booking_marks_slot_unavailable(client):
    await seed(client, make_slot("s1"))

    await client.post("/bookings", json=VALID_BODY)

    slots = (await client.get("/slots")).json()["slots"]
    assert slots[0]["available"] is False


# ---------------------------------------------------------------------------
# Trimming & lowercasing
# ---------------------------------------------------------------------------


async def test_create_booking_trims_name(client):
    await seed(client, make_slot("s1"))

    data = (
        await client.post("/bookings", json={**VALID_BODY, "name": "  Ada Obi  "})
    ).json()

    assert data["name"] == "Ada Obi"


async def test_create_booking_trims_and_lowercases_email(client):
    await seed(client, make_slot("s1"))

    data = (
        await client.post(
            "/bookings", json={**VALID_BODY, "email": "  ADA@Example.COM  "}
        )
    ).json()

    assert data["email"] == "ada@example.com"


# ---------------------------------------------------------------------------
# 400 — missing / empty fields & invalid email
# ---------------------------------------------------------------------------


async def test_create_booking_missing_slot_id_returns_400(client):
    response = await client.post("/bookings", json={"name": "Ada", "email": "a@b.com"})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_missing_name_returns_400(client):
    response = await client.post(
        "/bookings", json={"slot_id": "s1", "email": "a@b.com"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_missing_email_returns_400(client):
    response = await client.post("/bookings", json={"slot_id": "s1", "name": "Ada"})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_empty_slot_id_returns_400(client):
    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "  "})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_empty_name_returns_400(client):
    response = await client.post("/bookings", json={**VALID_BODY, "name": "  "})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_empty_email_returns_400(client):
    response = await client.post("/bookings", json={**VALID_BODY, "email": "  "})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_create_booking_invalid_email_returns_400(client):
    await seed(client, make_slot("s1"))

    response = await client.post(
        "/bookings", json={**VALID_BODY, "email": "not-an-email"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


# ---------------------------------------------------------------------------
# 404 — slot not found
# ---------------------------------------------------------------------------


async def test_create_booking_slot_not_found(client):
    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "bad"})

    assert response.status_code == 404
    assert response.json() == {"error": "slot not found"}


# ---------------------------------------------------------------------------
# 409 — slot already taken
# ---------------------------------------------------------------------------


async def test_create_booking_slot_already_taken(client):
    await seed(client, make_slot("s1", available=False))

    response = await client.post("/bookings", json=VALID_BODY)

    assert response.status_code == 409
    assert response.json() == {"error": "slot not found"}


# ---------------------------------------------------------------------------
# 400 — slot already started
# ---------------------------------------------------------------------------


async def test_create_booking_slot_already_started_returns_400(client):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await seed(client, make_slot("s1", start=past))

    response = await client.post("/bookings", json=VALID_BODY)

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}
