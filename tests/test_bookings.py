from datetime import datetime, timezone

from slot_api.models.slot import Slot


def make_slot(id, available=True):
    return Slot(
        id=id,
        provider="Dr Ade",
        start=datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
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

    response = await client.post("/bookings", json=VALID_BODY)
    data = response.json()

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

    response = await client.post("/bookings", json=VALID_BODY)
    data = response.json()

    assert data["slot_id"] == "s1"
    assert data["name"] == "Ada Obi"
    assert data["email"] == "ada@example.com"
    assert data["status"] == "confirmed"
    assert data["id"]  # non-empty uuid string
    assert data["created_at"]  # non-empty timestamp


async def test_create_booking_marks_slot_unavailable(client):
    await seed(client, make_slot("s1"))

    await client.post("/bookings", json=VALID_BODY)

    # Confirm the slot is now unavailable.
    slots = (await client.get("/slots")).json()["slots"]
    assert slots[0]["available"] is False


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


async def test_create_booking_slot_not_found(client):
    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "bad"})

    assert response.status_code == 404


async def test_create_booking_slot_already_taken(client):
    await seed(client, make_slot("s1", available=False))

    response = await client.post("/bookings", json=VALID_BODY)

    assert response.status_code == 409


async def test_create_booking_invalid_email(client):
    await seed(client, make_slot("s1"))

    response = await client.post(
        "/bookings", json={**VALID_BODY, "email": "not-an-email"}
    )

    assert response.status_code == 422
