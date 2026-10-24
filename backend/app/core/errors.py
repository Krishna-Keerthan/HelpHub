"""Safe error descriptions for logs and stored summaries.

Exception messages can echo bound values (document text, emails), so logs carry
the class name, the SQLSTATE and traceback frames (file:line) only.
"""

import traceback
from pathlib import Path


def sqlstate_of(exc: BaseException) -> str | None:
    """SQLSTATE of a database error, if any.

    Walks SQLAlchemy's wrapper (.orig) and the cause chain down to the asyncpg
    exception; both levels carry the same code.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "sqlstate", None)
        if isinstance(code, str):
            return code
        current = getattr(current, "orig", None) or current.__cause__
    return None


def traceback_frames(exc: BaseException) -> str:
    """Traceback frames as ``file:line in func``, outermost first.

    traceback.extract_tb rather than format_tb: the frame locations are what
    we need; format_tb would also print each frame's source line.
    """
    return " > ".join(
        f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
