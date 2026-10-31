"""Argon2 parameters, hashing off the event loop, one hash at a time, register order."""

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient

from app.core import security
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    hash_password_async,
    verify_password_async,
)
from app.services import auth as auth_service
from tests.auth import test_auth_flow as flow

PASSWORD = flow.PASSWORD
# Reuse the register fixtures of test_auth_flow (pytest finds them by module name).
registered_ids = flow.registered_ids
register = flow.register


def test_new_hashes_and_the_dummy_use_the_configured_parameters() -> None:
    expected = ["argon2id", "v=19", "m=19456,t=2,p=1"]
    assert hash_password("x").split("$")[1:4] == expected
    assert DUMMY_HASH.split("$")[1:4] == expected


async def test_async_wrappers_round_trip() -> None:
    hashed = await hash_password_async(PASSWORD)
    assert await verify_password_async(PASSWORD, hashed) is True
    assert await verify_password_async("wrong", hashed) is False


BLOCK_SECONDS = 0.2
TICK_SECONDS = 0.005


def _blocking_hash(password: str) -> str:
    """Stand-in for Argon2 with a fixed cost, so the result does not depend on the CPU."""
    time.sleep(BLOCK_SECONDS)
    return "h"


async def _max_loop_gap(work: Callable[[], Awaitable[object]]) -> float:
    """Longest time between two ticks of a 5 ms ticker while `work` runs."""
    gaps: list[float] = []
    stop = False

    async def ticker() -> None:
        last = time.monotonic()
        while not stop:
            await asyncio.sleep(TICK_SECONDS)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    task = asyncio.create_task(ticker())
    await asyncio.sleep(10 * TICK_SECONDS)  # let the ticker start before the work
    started = time.monotonic()
    await work()
    assert time.monotonic() - started >= BLOCK_SECONDS * 0.9
    await asyncio.sleep(
        10 * TICK_SECONDS
    )  # let the ticker record the gap after the work
    stop = True
    await task
    return max(gaps)


async def test_event_loop_stays_responsive_while_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The stand-in is called by hash_password_async (semaphore + thread) as in production.
    monkeypatch.setattr(security, "hash_password", _blocking_hash)
    worst = await _max_loop_gap(lambda: hash_password_async(PASSWORD))
    assert worst < BLOCK_SECONDS / 2


async def test_only_one_hash_runs_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_hash(password: str) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "h"

    monkeypatch.setattr(security, "hash_password", slow_hash)
    await asyncio.gather(*[hash_password_async("p") for _ in range(5)])
    assert peak == 1


@pytest.mark.usefixtures("registration_open")
async def test_register_with_a_taken_slug_does_not_hash(
    client: AsyncClient,
    register: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slug = f"acme-{uuid.uuid4().hex[:10]}"
    assert (await register(slug)).status_code == 201

    async def must_not_run(password: str) -> str:
        raise AssertionError("hashed before the slug check")

    monkeypatch.setattr(auth_service, "hash_password_async", must_not_run)
    assert (await register(slug)).status_code == 409
