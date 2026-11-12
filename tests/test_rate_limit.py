from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from slot_api.models.rate_limit_attempt import RateLimitAttempt
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


# ---------------------------------------------------------------------------
# Which invalid requests count as attempts
# ---------------------------------------------------------------------------
# Every request whose body validates (parseable email) counts, whatever the
# outcome: 201, 400 (slot started), 404 (missing slot), 409 (slot taken),
# and even 429s themselves.  Requests rejected before body validation
# (malformed JSON, missing/invalid fields) are not attributable to an email
# and do not count.  Idempotent replays bypass the limiter and don't count.


async def test_slot_started_400_counts_toward_limit(client):
    past = make_slot("s1", start=datetime(2020, 1, 1, tzinfo=timezone.utc))
    await seed(client, past)

    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 400

    # 4 more attempts (valid booking + 3 missing-slot 404s) reach the cap…
    await seed(client, make_slot("s2"))
    assert (
        await client.post("/bookings", json={**VALID_BODY, "slot_id": "s2"})
    ).status_code == 201
    for _ in range(3):
        response = await client.post(
            "/bookings", json={**VALID_BODY, "slot_id": "missing"}
        )
        assert response.status_code == 404

    # …so the 6th attempt is rate limited.
    await seed(client, make_slot("s3"))
    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s3"})
    assert response.status_code == 429


async def test_conflict_409_counts_toward_limit(client):
    await seed(client, make_slot("s1"))

    assert (await client.post("/bookings", json=VALID_BODY)).status_code == 201
    # Same slot again → the slot is taken.
    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 409

    # Attempts so far: 2.  Three more missing-slot 404s reach the cap.
    for _ in range(3):
        response = await client.post(
            "/bookings", json={**VALID_BODY, "slot_id": "missing"}
        )
        assert response.status_code == 404

    await seed(client, make_slot("s2"))
    response = await client.post("/bookings", json={**VALID_BODY, "slot_id": "s2"})
    assert response.status_code == 429


async def test_rate_limited_429s_are_recorded_too(client):
    await seed(client, *(make_slot(f"s{i}") for i in range(6)))

    for i in range(5):
        await client.post("/bookings", json={**VALID_BODY, "slot_id": f"s{i}"})
    assert (
        await client.post("/bookings", json={**VALID_BODY, "slot_id": "s5"})
    ).status_code == 429

    result = await client.session.execute(
        select(func.count()).select_from(RateLimitAttempt)
    )
    assert result.scalar() == 6


async def test_invalid_email_does_not_count(client):
    await seed(client, make_slot("s1"))

    for _ in range(5):
        response = await client.post(
            "/bookings",
            json={"slot_id": "s1", "name": "Ada Obi", "email": "not-an-email"},
        )
        assert response.status_code == 400

    # None of those attempts counted, so a valid booking still succeeds.
    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 201


async def test_missing_email_does_not_count(client):
    for _ in range(5):
        response = await client.post(
            "/bookings", json={"slot_id": "s1", "name": "Ada Obi"}
        )
        assert response.status_code == 400

    await seed(client, make_slot("s1"))
    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 201


async def test_malformed_json_does_not_count(client):
    for _ in range(5):
        response = await client.post(
            "/bookings",
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400

    await seed(client, make_slot("s1"))
    response = await client.post("/bookings", json=VALID_BODY)
    assert response.status_code == 201
