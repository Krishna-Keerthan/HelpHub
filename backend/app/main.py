from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


def create_app() -> FastAPI:
    """Build the app from the current settings (tests call it with other settings)."""
    production = settings.is_production
    application = FastAPI(
        title="HelpHub",
        lifespan=lifespan,
        # The interactive docs and the schema are not served in production.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    if settings.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,  # bearer tokens in headers, no cookies
            max_age=600,
        )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(users_router)
    application.include_router(documents_router)
    application.include_router(search_router)
    application.include_router(chat_router)
    application.include_router(conversations_router)
    return application


app = create_app()
