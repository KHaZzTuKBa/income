from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health
from app.config import settings
from app.seed import seed_user


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from app.db import SessionLocal

    async with SessionLocal() as session:
        await seed_user(session)
    yield


app = FastAPI(
    title="Portfel",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
