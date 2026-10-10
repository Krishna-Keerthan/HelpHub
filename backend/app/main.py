from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.db.health import ping
from app.db.session import get_session
from app.services.embeddings import warm_up_default_provider


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await warm_up_default_provider()
    yield


app = FastAPI(title="HelpHub", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(users_router)


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
