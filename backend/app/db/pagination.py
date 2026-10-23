from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    limit: int
    offset: int = 0
