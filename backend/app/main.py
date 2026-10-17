from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.search import router as search_router
from app.api.users import router as users_router
from app.core.config import settings
from app.services.embeddings import warm_up_default_provider
from app.services.llm import close_groq_client


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.warm_up_embeddings:
        await warm_up_default_provider()
    yield
    await close_groq_client()


app = FastAPI(title="HelpHub", lifespan=lifespan)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(conversations_router)
