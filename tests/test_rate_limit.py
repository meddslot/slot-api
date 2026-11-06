from datetime import datetime, timedelta, timezone

from slot_api.models.slot import Slot

VALID_BODY = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}
OTHER_BODY = {"slot_id": "s1", "name": "Other", "email": "other@example.com"}


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
# 5 attempts allowed, 6th gets 429
# ---------------------------------------------------------------------------


async def test_five_attempts_allowed(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_slot("s3"),
        make_slot("s4"),
        make_slot("s5"),
    )

    for i in range(5):
        body = {**VALID_BODY, "slot_id": f"s{i + 1}"}
        response = await client.post("/bookings", json=body)
        assert response.status_code == 201


async def test_sixth_attempt_returns_429(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_slot("s3"),
        make_slot("s4"),
        make_slot("s5"),
    )

    for i in range(5):
        body = {**VALID_BODY, "slot_id": f"s{i + 1}"}
        await client.post("/bookings", json=body)

    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s1"})
    assert response.status_code == 429


# ---------------------------------------------------------------------------
# Retry-After header
# ---------------------------------------------------------------------------


async def test_429_has_retry_after_header(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_slot("s3"),
        make_slot("s4"),
        make_slot("s5"),
    )

    for i in range(5):
        body = {**VALID_BODY, "slot_id": f"s{i + 1}"}
        await client.post("/bookings", json=body)

    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s1"})

    assert "retry-after" in response.headers
    retry_after = int(response.headers["retry-after"])
    assert 1 <= retry_after <= 60


async def test_429_body(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_slot("s3"),
        make_slot("s4"),
        make_slot("s5"),
    )

    for i in range(5):
        body = {**VALID_BODY, "slot_id": f"s{i + 1}"}
        await client.post("/bookings", json=body)

    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s1"})

    assert response.json() == {"error": "slot not found"}


# ---------------------------------------------------------------------------
# Other emails are not affected
# ---------------------------------------------------------------------------


async def test_other_email_not_rate_limited(client):
    await seed(
        client,
        make_slot("s1"),
        make_slot("s2"),
        make_slot("s3"),
        make_slot("s4"),
        make_slot("s5"),
        make_slot("s6"),
    )

    # Exhaust the limit for ada@example.com.
    for i in range(5):
        body = {**VALID_BODY, "slot_id": f"s{i + 1}"}
        await client.post("/bookings", json=body)

    # other@example.com should still be able to book.
    response = await client.post("/bookings", json={**OTHER_BODY, "slot_id": "s6"})
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Failed attempts count toward the limit
# ---------------------------------------------------------------------------


async def test_failed_attempts_count_toward_limit(client):
    # All 5 attempts use a non-existent slot → 404, but they still count.
    for _ in range(5):
        response = await client.post(
            "/bookings", json={**VALID_BODY, "slot_id": "missing"}
        )
        assert response.status_code == 404

    # 6th attempt should be rate limited even though slot exists.
    await seed(client, make_slot("s1"))
    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 429
