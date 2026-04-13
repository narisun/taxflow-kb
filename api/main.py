"""FastAPI application factory for Tax Brain API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.db.engine import init_db
    await init_db()
    yield

def create_app() -> FastAPI:
    app = FastAPI(
        title="Tax Brain API",
        description="CPA tax preparation platform backend",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from api.routers import health, clients, chat, documents, tax_returns, auth
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(clients.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(tax_returns.router)
    return app
