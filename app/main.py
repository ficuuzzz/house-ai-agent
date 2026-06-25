from fastapi import FastAPI

from app.api.routes import agent, checklist, debug, memory, profile, rag, summary
from app.db import models
from app.db.session import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="House AI Agent MVP",
    version="0.1.0"
)

app.include_router(
    profile.router,
    prefix="/profile",
    tags=["HouseProfile"]
)

app.include_router(
    memory.router,
    prefix="/memory",
    tags=["HouseMemory"]
)

app.include_router(
    summary.router,
    prefix="/summary",
    tags=["Summary"]
)

app.include_router(
    checklist.router,
    prefix="/checklist",
    tags=["Checklist"]
)

app.include_router(
    rag.router,
    prefix="/rag",
    tags=["RAG"]
)

app.include_router(
    agent.router,
    prefix="/agent",
    tags=["Agent"]
)

app.include_router(
    debug.router,
    prefix="/debug",
    tags=["Debug"]
)


@app.get("/health")
def health_check():
    return {"status": "ok"}