from app.core.ratelimit import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks_with_a_retry_time() -> None:
    clock = Clock()
    limiter = RateLimiter(clock)
    assert [limiter.hit("k", 3, 60) for _ in range(3)] == [None, None, None]
    clock.now += 20
    retry = limiter.hit("k", 3, 60)
    assert retry == 40  # the oldest hit leaves the window at t0 + 60


def test_window_slides_and_a_blocked_attempt_is_not_recorded() -> None:
    clock = Clock()
    limiter = RateLimiter(clock)
    for _ in range(2):
        assert limiter.hit("k", 2, 10) is None
    for _ in range(5):
        assert limiter.hit("k", 2, 10) is not None  # blocked, not counted
    clock.now += 10
    assert limiter.hit("k", 2, 10) is None


def test_keys_are_independent() -> None:
    limiter = RateLimiter(Clock())
    assert limiter.hit("a", 1, 60) is None
    assert limiter.hit("a", 1, 60) is not None
    assert limiter.hit("b", 1, 60) is None


def test_memory_is_bounded_by_max_keys() -> None:
    limiter = RateLimiter(Clock(), max_keys=100)
    for i in range(1000):
        limiter.hit(f"k{i}", 1, 60)
    assert len(limiter._events) <= 100
    assert limiter.hit("k999", 1, 60) is not None  # newest keys are kept
