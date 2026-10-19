"""Readiness: can this process reach its database as the app role?"""

import asyncio
import logging

from app.core.config import settings
from app.core.errors import sqlstate_of, traceback_frames
from app.db.session import ping

logger = logging.getLogger(__name__)


async def database_ready() -> bool:
    """True when ``SELECT 1`` succeeds within the timeout.

    Failures are logged by class name, SQLSTATE and traceback frames only.
    """
    try:
        await asyncio.wait_for(ping(), settings.ready_timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - readiness reports any failure as not ready
        logger.error(
            "readiness check failed: error=%s sqlstate=%s frames=%s",
            type(exc).__name__,
            sqlstate_of(exc) or "-",
            traceback_frames(exc),
        )
        return False
    return True
