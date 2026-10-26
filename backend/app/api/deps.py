"""請求層的權限依賴（spec §15 RBAC）。

- `current_user`：從 httpOnly cookie 的 JWT 取得登入者；未登入、權杖無效、帳號停用或 token_version 不符一律 401。
- `require_admin`：最高權限管理者或廠管理者。
- `current_scope`：本次請求要看的資料集（一條線）與其生效批次。
  前端以 header `X-QCM-Dataset: WJ1-DCS-PM1` 指定；未指定時用使用者可看的第一個資料集。
  非 super_admin 指定別廠的資料集回 403；該資料集還沒有資料回 404。
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ImportBatch, User
from ..services import auth as A
from ..services.query import active_datasets

DATASET_HEADER = "X-QCM-Dataset"


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(A.COOKIE_NAME)
    payload = A.decode_token(token) if token else None
    if payload is None:
        raise HTTPException(status_code=401, detail="請先登入")
    try:
        user = session.get(User, int(payload["sub"]))
    except (TypeError, ValueError):
        user = None
    if user is None or not user.is_active or payload.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="登入已失效，請重新登入")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role not in (A.ROLE_SUPER, A.ROLE_PLANT_ADMIN):
        raise HTTPException(status_code=403, detail="需要管理者權限")
    return user


def require_super(user: User = Depends(current_user)) -> User:
    if user.role != A.ROLE_SUPER:
        raise HTTPException(status_code=403, detail="需要最高權限管理者")
    return user


def visible_batches(session: Session, user: User) -> list[ImportBatch]:
    """使用者看得到的各資料集生效批次。"""
    return [b for b in active_datasets(session) if b.plant and A.can_view_plant(user.role, user.plant, b.plant)]


@dataclass
class Scope:
    user: User
    dataset: str
    batch: ImportBatch


def current_scope(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    x_qcm_dataset: str | None = Header(None, alias=DATASET_HEADER),
) -> Scope:
    batches = visible_batches(session, user)
    wanted = (x_qcm_dataset or "").strip().upper()
    if wanted:
        if not A.can_view_plant(user.role, user.plant, A.dataset_plant(wanted)):
            raise HTTPException(status_code=403, detail=f"沒有 {A.dataset_plant(wanted)} 的權限")
        batch = next((b for b in batches if b.dataset == wanted), None)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"{wanted} 尚無資料，請管理者匯入 Excel")
        return Scope(user, wanted, batch)
    if not batches:
        raise HTTPException(status_code=404, detail="尚無資料，請管理者匯入 Excel")
    return Scope(user, batches[0].dataset, batches[0])
