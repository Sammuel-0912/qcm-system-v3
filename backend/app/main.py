from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.routes import router
from .db import init_db

app = FastAPI(title="品控力管理系統", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # v1 不做登入與權限控管（spec.md D-02）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
