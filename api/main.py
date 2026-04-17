"""FastAPI application factory for Tax Brain API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings, print_settings_banner


@asynccontextmanager
async def lifespan(app: FastAPI):
    print_settings_banner()
    from api.db.engine import init_db

    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Tax Brain API",
        description="CPA tax preparation platform backend",
        version="0.3.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    from api.routers import (
        auth,
        chat,
        clients,
        conversations,
        dependents,
        documents,
        health,
        tax_returns,
    )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(clients.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(documents.router)
    app.include_router(tax_returns.router)
    app.include_router(dependents.router)
    return app
