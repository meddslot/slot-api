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


def make_booking(slot_id="s1", status="confirmed"):
    return Booking(
        slot_id=slot_id, name="Ada Obi", email="ada@example.com", status=status
    )


async def seed(client, *rows):
    for row in rows:
        client.session.add(row)
    await client.session.flush()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_cancel_booking_returns_200(client):
    slot = make_slot(available=False)
    booking = make_booking()
    await seed(client, slot, booking)

    response = await client.delete(f"/bookings/{booking.id}")

    assert response.status_code == 200


async def test_cancel_booking_response_status_is_cancelled(client):
    slot = make_slot(available=False)
    booking = make_booking()
    await seed(client, slot, booking)

    data = (await client.delete(f"/bookings/{booking.id}")).json()

    assert data["status"] == "cancelled"


async def test_cancel_booking_response_shape(client):
    slot = make_slot(available=False)
    booking = make_booking()
    await seed(client, slot, booking)

    data = (await client.delete(f"/bookings/{booking.id}")).json()

    assert set(data.keys()) == {
        "id",
        "slot_id",
        "name",
        "email",
        "status",
        "created_at",
    }


async def test_cancel_booking_frees_slot(client):
    slot = make_slot(available=False)
    booking = make_booking()
    await seed(client, slot, booking)

    await client.delete(f"/bookings/{booking.id}")

    slots = (await client.get("/slots")).json()["slots"]
    assert slots[0]["available"] is True


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


async def test_cancel_booking_not_found_returns_404(client):
    response = await client.delete("/bookings/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": "slot not found"}


async def test_cancel_booking_already_cancelled_returns_409(client):
    slot = make_slot(available=False)
    booking = make_booking(status="cancelled")
    await seed(client, slot, booking)

    response = await client.delete(f"/bookings/{booking.id}")

    assert response.status_code == 409
    assert response.json() == {"error": "slot not found"}
