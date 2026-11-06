from datetime import datetime, timedelta, timezone

from slot_api.models.booking import Booking
from slot_api.models.slot import Slot


def make_slot(id, available=False):
    return Slot(
        id=id,
        provider="Dr Ade",
        start=datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
        available=available,
    )


BASE_TIME = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)


def make_booking(slot_id, email="ada@example.com", offset_seconds=0):
    return Booking(
        slot_id=slot_id,
        name="Ada Obi",
        email=email,
        created_at=BASE_TIME + timedelta(seconds=offset_seconds),
    )


async def seed(client, *rows):
    for row in rows:
        client.session.add(row)
    await client.session.flush()


# ---------------------------------------------------------------------------
# Basic listing
# ---------------------------------------------------------------------------


async def test_list_bookings_returns_200(client):
    await seed(client, make_slot("s1"), make_booking("s1"))

    response = await client.get("/bookings")

    assert response.status_code == 200


async def test_list_bookings_response_shape(client):
    await seed(client, make_slot("s1"), make_booking("s1"))

    data = (await client.get("/bookings")).json()

    assert "bookings" in data
    assert "next_cursor" in data


async def test_list_bookings_empty(client):
    data = (await client.get("/bookings")).json()

    assert data == {"bookings": [], "next_cursor": None}


async def test_list_bookings_returns_all_by_default(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_booking("s1", offset_seconds=0),
        make_booking("s2", offset_seconds=1),
    )

    data = (await client.get("/bookings")).json()

    assert len(data["bookings"]) == 2


async def test_list_bookings_ordered_oldest_first(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_booking("s1", offset_seconds=10),
        make_booking("s2", offset_seconds=0),
    )

    data = (await client.get("/bookings")).json()
    times = [b["created_at"] for b in data["bookings"]]

    assert times == sorted(times)


# ---------------------------------------------------------------------------
# Email filter
# ---------------------------------------------------------------------------


async def test_list_bookings_filter_by_email(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_booking("s1", email="ada@example.com", offset_seconds=0),
        make_booking("s2", email="other@example.com", offset_seconds=1),
    )

    data = (await client.get("/bookings", params={"email": "ada@example.com"})).json()

    assert len(data["bookings"]) == 1
    assert data["bookings"][0]["email"] == "ada@example.com"


async def test_list_bookings_email_filter_case_insensitive(client):
    await seed(client, make_slot("s1"), make_booking("s1", email="Ada@Example.COM"))

    data = (await client.get("/bookings", params={"email": "ada@example.com"})).json()

    assert len(data["bookings"]) == 1


async def test_list_bookings_email_no_match(client):
    await seed(client, make_slot("s1"), make_booking("s1"))

    data = (
        await client.get("/bookings", params={"email": "nobody@example.com"})
    ).json()

    assert data["bookings"] == []


# ---------------------------------------------------------------------------
# Cursor pagination
# ---------------------------------------------------------------------------


async def test_list_bookings_next_cursor_null_when_no_more_pages(client):
    await seed(client, make_slot("s1"), make_booking("s1"))

    data = (await client.get("/bookings", params={"limit": 10})).json()

    assert data["next_cursor"] is None


async def test_list_bookings_next_cursor_present_when_more_pages(client):
    slots = [make_slot(f"s{i}") for i in range(5)]
    bookings = [make_booking(f"s{i}", offset_seconds=i) for i in range(5)]
    await seed(client, *slots, *bookings)

    data = (await client.get("/bookings", params={"limit": 3})).json()

    assert data["next_cursor"] is not None
    assert len(data["bookings"]) == 3


async def test_list_bookings_cursor_returns_next_page(client):
    slots = [make_slot(f"s{i}") for i in range(5)]
    bookings = [make_booking(f"s{i}", offset_seconds=i) for i in range(5)]
    await seed(client, *slots, *bookings)

    first = (await client.get("/bookings", params={"limit": 3})).json()
    second = (
        await client.get(
            "/bookings", params={"limit": 3, "cursor": first["next_cursor"]}
        )
    ).json()

    assert len(second["bookings"]) == 2
    assert second["next_cursor"] is None


async def test_list_bookings_cursor_no_overlap(client):
    slots = [make_slot(f"s{i}") for i in range(6)]
    bookings = [make_booking(f"s{i}", offset_seconds=i) for i in range(6)]
    await seed(client, *slots, *bookings)

    first = (await client.get("/bookings", params={"limit": 3})).json()
    second = (
        await client.get(
            "/bookings", params={"limit": 3, "cursor": first["next_cursor"]}
        )
    ).json()

    first_ids = {b["id"] for b in first["bookings"]}
    second_ids = {b["id"] for b in second["bookings"]}
    assert first_ids.isdisjoint(second_ids)


# ---------------------------------------------------------------------------
# Limit validation
# ---------------------------------------------------------------------------


async def test_list_bookings_limit_zero_returns_400(client):
    response = await client.get("/bookings", params={"limit": 0})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_list_bookings_limit_51_returns_400(client):
    response = await client.get("/bookings", params={"limit": 51})

    assert response.status_code == 400
    assert response.json() == {"error": "slot not found"}


async def test_list_bookings_limit_50_is_valid(client):
    response = await client.get("/bookings", params={"limit": 50})

    assert response.status_code == 200


async def test_list_bookings_limit_1_is_valid(client):
    response = await client.get("/bookings", params={"limit": 1})

    assert response.status_code == 200
