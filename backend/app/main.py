from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.ar.routes import router as ar_router
from .api.v1.routes import router
from .config import AR_UPLOAD_DIR, AR_UPLOAD_URL_PREFIX
from .db import init_db

app = FastAPI(title="品控力管理系統", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # v1 不做登入與權限控管（spec.md D-02）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ar_router)

# AR 設備圖檔。掛在 /api/ar/uploads 之下，前端 nginx 既有的 /api/ 規則即可轉發。
AR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount(AR_UPLOAD_URL_PREFIX, StaticFiles(directory=AR_UPLOAD_DIR), name="ar-uploads")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
