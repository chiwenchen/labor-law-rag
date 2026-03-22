from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import query, sessions, articles


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # scheduler starts here in Task 8


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
