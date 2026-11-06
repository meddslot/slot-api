from datetime import datetime, timezone

from slot_api.models.booking import Booking
from slot_api.models.slot import Slot


def make_slot(id="s1", available=True):
    return Slot(
        id=id,
        provider="Dr Ade",
        start=datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
        available=available,
    )


def make_booking(slot_id="s1"):
    return Booking(slot_id=slot_id, name="Ada Obi", email="ada@example.com")


async def seed(client, *rows):
    for row in rows:
        client.session.add(row)
    await client.session.flush()


async def test_get_booking_returns_200(client):
    slot = make_slot()
    booking = make_booking()
    await seed(client, slot, booking)

    response = await client.get(f"/bookings/{booking.id}")

    assert response.status_code == 200


async def test_get_booking_response_shape(client):
    slot = make_slot()
    booking = make_booking()
    await seed(client, slot, booking)

    data = (await client.get(f"/bookings/{booking.id}")).json()

    assert set(data.keys()) == {
        "id",
        "slot_id",
        "name",
        "email",
        "status",
        "created_at",
    }


async def test_get_booking_response_values(client):
    slot = make_slot()
    booking = make_booking()
    await seed(client, slot, booking)

    data = (await client.get(f"/bookings/{booking.id}")).json()

    assert data["id"] == booking.id
    assert data["slot_id"] == "s1"
    assert data["name"] == "Ada Obi"
    assert data["email"] == "ada@example.com"
    assert data["status"] == "confirmed"


async def test_get_booking_not_found_returns_404(client):
    response = await client.get("/bookings/does-not-exist")

    assert response.status_code == 404


async def test_get_booking_not_found_error_body(client):
    response = await client.get("/bookings/does-not-exist")

    assert response.json() == {"error": "slot not found"}
