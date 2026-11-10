from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api.ar.routes import router as ar_router
from .api.auth_routes import ensure_bootstrap_admin
from .api.auth_routes import router as auth_router
from .api.deps import current_user
from .api.v1.routes import router
from .config import AR_UPLOAD_URL_PREFIX, STATIC_DIR
from .db import SessionLocal, get_session, init_db
from .models import CheckPhotoInspection, User
from .services.auth import ROLE_SUPER, can_view_plant, dataset_plant
from .services.storage import content_type_for, get_storage, url_for, valid_key

app = FastAPI(title="品控力管理系統", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    # 前端與 API 同源（nginx／vite 轉發），登入靠同源 cookie；不需要也不開放跨站帶 cookie
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router)
app.include_router(ar_router)

# 上傳檔（拍照點檢照片、AR 設備圖）。掛在 /api/ar/uploads 之下，前端的 /api/ 轉發規則即可涵蓋
#（nginx 或 Cloudflare Worker）。檔案實際存在本機磁碟或 R2，由儲存層讀出（services/storage.py）。
# 需要登入；拍照點檢照片只給有該廠權限的人看，其餘上傳檔（AR 設備圖）只給最高權限管理者。
@app.get(AR_UPLOAD_URL_PREFIX + "/{key:path}")
def get_upload(key: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    if not valid_key(key):
        raise HTTPException(status_code=404, detail="找不到檔案")
    record = session.scalar(select(CheckPhotoInspection).where(CheckPhotoInspection.photo_url == url_for(key)))
    if record is not None:
        allowed = bool(record.dataset) and can_view_plant(user.role, user.plant, dataset_plant(record.dataset))
    else:
        allowed = user.role == ROLE_SUPER
    if not allowed:
        raise HTTPException(status_code=404, detail="找不到檔案")
    data = get_storage().get(key)
    if data is None:
        raise HTTPException(status_code=404, detail="找不到檔案")
    # 需登入才能看：不讓瀏覽器快取（登出或帳號停用後，共用電腦上不能再從快取看到照片）
    return Response(data, media_type=content_type_for(key), headers={"Cache-Control": "private, no-store"})


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with SessionLocal() as session:
        ensure_bootstrap_admin(session)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def mount_frontend(target: FastAPI, directory: str | Path) -> None:
    """由後端直接提供前端（Windows 安裝版沒有 nginx）。必須在所有 API 路由之後註冊。

    檔案存在就回檔案，其餘路徑一律回 index.html，交給前端路由（BrowserRouter）。
    /api/ 底下找不到的路徑仍回 404，不會被當成網頁。
    """
    root = Path(directory).resolve()
    index = root / "index.html"
    # 檔名帶內容 hash，可以長期快取；index.html 每次都要回源，才拿得到新版的 asset 檔名
    target.mount("/assets", StaticFiles(directory=root / "assets"), name="frontend-assets")

    @target.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        file = (root / path).resolve()
        if path and file.is_file() and root in file.parents:
            return FileResponse(file)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


if STATIC_DIR:
    mount_frontend(app, STATIC_DIR)
