"""FastAPI application factory for Tax Brain API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

def create_app() -> FastAPI:
    app = FastAPI(
        title="Tax Brain API",
        description="CPA tax preparation platform backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from api.routers import health
    app.include_router(health.router)
    return app
