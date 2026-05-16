from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.db.session import check_db_connection, dispose_connector
from app.presentation.routers.accentuation import router as accentuation_router
from app.presentation.routers.auth import router as auth_router
from app.presentation.routers.body_expression import router as body_expression_router
from app.presentation.routers.consistency import router as consistency_router
from app.presentation.routers.facial_expression import router as facial_expression_router
from app.presentation.routers.fluency import router as fluency_router
from app.presentation.routers.linguistic_versatility import (
    router as linguistic_versatility_router,
)
from app.presentation.routers.live import router as live_router
from app.presentation.routers.live_ws import router as live_ws_router
from app.presentation.routers.loudness import router as loudness_router
from app.presentation.routers.muletillas import router as muletillas_router
from app.presentation.routers.pauses import router as pauses_router
from app.presentation.routers.phonation import router as phonation_router
from app.presentation.routers.precision import router as precision_router
from app.presentation.routers.pronunciation import router as pronunciation_router
from app.presentation.routers.profile import router as profile_router
from app.presentation.routers.video_router import router as video_router
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_connector()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(phonation_router, prefix="/api")
app.include_router(loudness_router, prefix="/api")
app.include_router(pauses_router, prefix="/api")
app.include_router(accentuation_router, prefix="/api")
app.include_router(pronunciation_router, prefix="/api")
app.include_router(muletillas_router, prefix="/api")
app.include_router(facial_expression_router, prefix="/api")
app.include_router(body_expression_router, prefix="/api")
app.include_router(precision_router, prefix="/api")
app.include_router(linguistic_versatility_router, prefix="/api")
app.include_router(fluency_router, prefix="/api")
app.include_router(consistency_router, prefix="/api")
app.include_router(video_router, prefix="/api")
app.include_router(profile_router, prefix="/api")

app.include_router(live_router, prefix="/api")
app.include_router(live_ws_router, prefix="/api")


@app.get("/health")
async def health_check():
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }
