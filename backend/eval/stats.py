"""Small statistics helpers for the evaluation report. Pure functions."""

import math

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion; (0, 1) when there is no data."""
    if n < 0 or not 0 <= successes <= n:
        raise ValueError("need 0 <= successes <= n")
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return low, high


def count_pct(successes: int, n: int) -> str:
    """``7/8 = 88%`` (half rounds up); ``0/0`` when there is nothing to count."""
    if n == 0:
        return "0/0"
    return f"{successes}/{n} = {math.floor(100 * successes / n + 0.5)}%"
