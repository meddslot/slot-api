from datetime import datetime, timezone

from slot_api.models.slot import Slot


def make_slot(id, provider, start, end, available=True):
    return Slot(
        id=id,
        provider=provider,
        start=start,
        end=end,
        available=available,
    )


DR_ADE = "Dr Ade"
DR_BOLA = "Dr Bola"


def slot_1():
    return make_slot(
        "s1",
        DR_ADE,
        datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
    )


def slot_2():
    return make_slot(
        "s2",
        DR_ADE,
        datetime(2026, 12, 10, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 10, 10, 30, tzinfo=timezone.utc),
        available=False,
    )


def slot_3():
    return make_slot(
        "s3",
        DR_BOLA,
        datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
    )


async def seed(client, *slots):
    """Add rows and flush so the same session can read them back."""
    for slot in slots:
        client.session.add(slot)
    await client.session.flush()


async def test_list_slots_returns_all(client):
    await seed(client, slot_1(), slot_2(), slot_3())

    response = await client.get("/slots")

    assert response.status_code == 200
    data = response.json()
    assert "slots" in data
    assert len(data["slots"]) == 3


async def test_list_slots_response_shape(client):
    await seed(client, slot_1())

    response = await client.get("/slots")

    slot = response.json()["slots"][0]
    assert set(slot.keys()) == {"id", "provider", "start", "end", "available"}
    assert slot["id"] == "s1"
    assert slot["provider"] == DR_ADE
    assert slot["available"] is True


async def test_list_slots_filter_by_provider(client):
    await seed(client, slot_1(), slot_2(), slot_3())

    response = await client.get("/slots", params={"provider": DR_ADE})

    assert response.status_code == 200
    slots = response.json()["slots"]
    assert len(slots) == 2
    assert all(s["provider"] == DR_ADE for s in slots)


async def test_list_slots_filter_no_match(client):
    await seed(client, slot_1())

    response = await client.get("/slots", params={"provider": "Dr Unknown"})

    assert response.status_code == 200
    assert response.json()["slots"] == []


async def test_list_slots_ordered_by_start(client):
    # Seed in reverse order to confirm the query sorts correctly.
    await seed(client, slot_2(), slot_1())

    response = await client.get("/slots")

    starts = [s["start"] for s in response.json()["slots"]]
    assert starts == sorted(starts)


async def test_list_slots_empty(client):
    response = await client.get("/slots")

    assert response.status_code == 200
    assert response.json() == {"slots": []}
