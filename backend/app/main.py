from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import query, sessions, articles


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler, scheduler
    try:
        start_scheduler()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")
    yield
    try:
        scheduler.shutdown()
    except Exception:
        pass  # Already stopped or never started


app = FastAPI(title="勞基法 RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
