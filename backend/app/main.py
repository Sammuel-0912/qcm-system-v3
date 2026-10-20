from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from .api.ar.routes import router as ar_router
from .api.v1.routes import router
from .config import AR_UPLOAD_URL_PREFIX
from .db import init_db
from .services.storage import content_type_for, get_storage, valid_key

app = FastAPI(title="品控力管理系統", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # v1 不做登入與權限控管（spec.md D-02）
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ar_router)

# 上傳檔（拍照點檢照片、AR 設備圖）。掛在 /api/ar/uploads 之下，前端的 /api/ 轉發規則即可涵蓋
#（nginx 或 Cloudflare Worker）。檔案實際存在本機磁碟或 R2，由儲存層讀出（services/storage.py）。
@app.get(AR_UPLOAD_URL_PREFIX + "/{key:path}")
def get_upload(key: str) -> Response:
    if not valid_key(key):
        raise HTTPException(status_code=404, detail="找不到檔案")
    data = get_storage().get(key)
    if data is None:
        raise HTTPException(status_code=404, detail="找不到檔案")
    # 檔名含隨機碼，內容不會變，可長期快取
    return Response(data, media_type=content_type_for(key), headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
