from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.db.health import ping
from app.db.session import get_session

app = FastAPI(title="HelpHub")
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    try:
        ok = await ping(session)
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if not ok:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}
