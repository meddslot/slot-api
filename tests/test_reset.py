from datetime import datetime, timedelta, timezone

from slot_api.models.booking import Booking
from slot_api.models.slot import Slot

FUTURE_START = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)


def slot_payload(id="r1", provider="Dr Ade", start=None, available=True):
    if start is None:
        start = FUTURE_START
    return {
        "id": id,
        "provider": provider,
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=30)).isoformat(),
        "available": available,
    }


def make_slot(id, available=False, start=None):
    if start is None:
        start = FUTURE_START
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
# Replacing slots
# ---------------------------------------------------------------------------


async def test_reset_replaces_all_slots(client):
    await seed(client, make_slot("old1"), make_slot("old2"))

    response = await client.post("/reset", json={"slots": [slot_payload("r1")]})

    assert response.status_code == 200
    data = (await client.get("/slots")).json()
    ids = [s["id"] for s in data["slots"]]
    assert ids == ["r1"]


async def test_reset_returns_inserted_slots(client):
    response = await client.post(
        "/reset",
        json={"slots": [slot_payload("r1"), slot_payload("r2", available=False)]},
    )

    assert response.status_code == 200
    slots = {s["id"]: s for s in response.json()["slots"]}
    assert slots["r1"]["available"] is True
    assert slots["r2"]["available"] is False


async def test_reset_with_empty_list_clears_all_slots(client):
    await seed(client, make_slot("old1"))

    response = await client.post("/reset", json={"slots": []})

    assert response.status_code == 200
    assert (await client.get("/slots")).json() == {"slots": []}


# ---------------------------------------------------------------------------
# Deleting bookings
# ---------------------------------------------------------------------------


async def test_reset_deletes_existing_bookings(client):
    slot = make_slot("s1")
    booking = Booking(
        slot_id="s1", name="Ada Obi", email="ada@example.com", status="confirmed"
    )
    await seed(client, slot, booking)

    await client.post("/reset", json={"slots": [slot_payload("r1")]})

    data = (await client.get("/bookings", params={"email": "ada@example.com"})).json()
    assert data == {"bookings": [], "next_cursor": None}


async def test_reset_frees_slots_held_by_bookings(client):
    slot = make_slot("s1", available=False)
    booking = Booking(
        slot_id="s1", name="Ada Obi", email="ada@example.com", status="confirmed"
    )
    await seed(client, slot, booking)

    response = await client.post(
        "/reset", json={"slots": [slot_payload("r1", available=True)]}
    )

    assert response.status_code == 200
    data = (await client.get("/slots")).json()
    assert data["slots"][0]["available"] is True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_reset_invalid_body_returns_400(client):
    response = await client.post("/reset", json={"slots": "not-a-list"})

    assert response.status_code == 400


async def test_reset_slot_end_before_start_returns_400(client):
    body = slot_payload("r1")
    body["end"] = body["start"]

    response = await client.post("/reset", json={"slots": [body]})

    assert response.status_code == 400


async def test_reset_slot_blank_provider_returns_400(client):
    body = slot_payload("r1", provider="   ")

    response = await client.post("/reset", json={"slots": [body]})

    assert response.status_code == 400
