"""登入、帳號與資料集清單（spec §15 RBAC）。"""
from __future__ import annotations

import datetime as dt
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import User
from ..services import auth as A
from .deps import current_user, require_admin, visible_batches

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return (value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value).isoformat()


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "displayName": u.display_name,
        "role": u.role,
        "roleLabel": A.ROLE_LABELS.get(u.role, u.role),
        "plant": u.plant,
        "isActive": u.is_active,
        "createdAt": _iso(u.created_at),
        "lastLoginAt": _iso(u.last_login_at),
    }


def _dataset_out(b) -> dict:
    return {
        "key": b.dataset,
        "plant": b.plant,
        "factory": b.factory,
        "line": b.line_code,
        "filename": b.filename,
        "importedAt": _iso(b.imported_at),
    }


# --------------------------------------------------------------------------- 登入


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.split(",")[0].strip() == "https"


@router.post("/auth/login")
def login(data: LoginIn, request: Request, response: Response, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.username == data.username.strip()))
    # 帳號不存在與密碼錯誤回同一個訊息，避免被拿來探測帳號
    if user is None or not A.verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="帳號已停用，請洽管理者")
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    response.set_cookie(
        A.COOKIE_NAME,
        A.issue_token(user.id, user.token_version),
        max_age=A.TOKEN_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )
    return user_out(user)


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(A.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return {**user_out(user), "datasets": [_dataset_out(b) for b in visible_batches(session, user)]}


class PasswordIn(BaseModel):
    oldPassword: str
    newPassword: str


@router.post("/auth/password")
def change_password(data: PasswordIn, response: Response, request: Request, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    if not A.verify_password(data.oldPassword, user.password_hash):
        raise HTTPException(status_code=400, detail="舊密碼錯誤")
    try:
        A.check_password_policy(data.newPassword)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.password_hash = A.hash_password(data.newPassword)
    user.token_version += 1
    session.commit()
    # 自己改密碼後換發新權杖，維持登入；其他裝置上的舊權杖失效
    response.set_cookie(A.COOKIE_NAME, A.issue_token(user.id, user.token_version), max_age=A.TOKEN_HOURS * 3600,
                        httponly=True, samesite="lax", secure=_secure(request), path="/")
    return {"ok": True}


@router.get("/datasets")
def list_datasets(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """使用者看得到的資料集（每條線一筆生效批次）。"""
    return [_dataset_out(b) for b in visible_batches(session, user)]


# --------------------------------------------------------------------------- 使用者管理


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-@]+$")
    displayName: str = Field(min_length=1, max_length=64)
    password: str
    role: str = A.ROLE_USER
    plant: str | None = None


class UserUpdate(BaseModel):
    displayName: str | None = Field(None, min_length=1, max_length=64)
    role: str | None = None
    plant: str | None = None
    isActive: bool | None = None


class PasswordReset(BaseModel):
    password: str


def _normalize_target(role: str, plant: str | None) -> tuple[str, str | None]:
    if role not in A.ROLE_LABELS:
        raise HTTPException(status_code=422, detail=f"角色只能是 {'、'.join(A.ROLE_LABELS)}")
    if role == A.ROLE_SUPER:
        return role, None
    plant = (plant or "").strip().upper()
    if plant not in A.PLANTS:
        raise HTTPException(status_code=422, detail=f"廠別只能是 {'、'.join(A.PLANTS)}")
    return role, plant


def _get_manageable(session: Session, actor: User, user_id: int) -> User:
    target = session.get(User, user_id)
    if target is None or not A.can_manage_user(actor.role, actor.plant, target.role, target.plant):
        raise HTTPException(status_code=404, detail="找不到這個帳號")
    return target


@router.get("/users")
def list_users(actor: User = Depends(require_admin), session: Session = Depends(get_session)):
    users = session.scalars(select(User).order_by(User.plant.is_(None).desc(), User.plant, User.role, User.username)).all()
    if actor.role != A.ROLE_SUPER:
        users = [u for u in users if u.plant == actor.plant]
    return [user_out(u) for u in users]


@router.post("/users", status_code=201)
def create_user(data: UserCreate, actor: User = Depends(require_admin), session: Session = Depends(get_session)):
    role, plant = _normalize_target(data.role, data.plant if actor.role == A.ROLE_SUPER else actor.plant)
    if not A.can_manage_user(actor.role, actor.plant, role, plant):
        raise HTTPException(status_code=403, detail="廠管理者只能新增自己廠的一般使用者；廠管理者由最高權限管理者指派")
    try:
        A.check_password_policy(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    username = data.username.strip()
    if session.scalar(select(func.count()).select_from(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail=f"帳號 {username} 已存在")
    user = User(
        username=username,
        display_name=data.displayName.strip(),
        password_hash=A.hash_password(data.password),
        role=role,
        plant=plant,
    )
    session.add(user)
    session.commit()
    return user_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, actor: User = Depends(require_admin),
                session: Session = Depends(get_session)):
    target = _get_manageable(session, actor, user_id)
    if data.role is not None or data.plant is not None:
        if actor.role != A.ROLE_SUPER:
            raise HTTPException(status_code=403, detail="只有最高權限管理者可以變更角色或廠別")
        if target.id == actor.id:
            raise HTTPException(status_code=400, detail="不能變更自己的角色或廠別")
        role, plant = _normalize_target(data.role or target.role, data.plant if data.plant is not None else target.plant)
        if (role, plant) != (target.role, target.plant):
            target.role, target.plant = role, plant
            target.token_version += 1
    if data.isActive is not None and data.isActive != target.is_active:
        if target.id == actor.id:
            raise HTTPException(status_code=400, detail="不能停用自己的帳號")
        target.is_active = data.isActive
        target.token_version += 1
    if data.displayName is not None:
        target.display_name = data.displayName.strip()
    session.commit()
    return user_out(target)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, data: PasswordReset, actor: User = Depends(require_admin),
                   session: Session = Depends(get_session)):
    target = _get_manageable(session, actor, user_id)
    try:
        A.check_password_policy(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target.password_hash = A.hash_password(data.password)
    target.token_version += 1
    session.commit()
    return user_out(target)


# --------------------------------------------------------------------------- 初始管理者


def ensure_bootstrap_admin(session: Session) -> None:
    """還沒有任何最高權限管理者時，依 QCM_ADMIN_USERNAME／QCM_ADMIN_PASSWORD 建立第一位。"""
    if session.scalar(select(func.count()).select_from(User).where(User.role == A.ROLE_SUPER)):
        return
    username = os.getenv("QCM_ADMIN_USERNAME", "").strip()
    password = os.getenv("QCM_ADMIN_PASSWORD", "")
    if not username or not password:
        log.warning("尚無最高權限管理者：請設定 QCM_ADMIN_USERNAME 與 QCM_ADMIN_PASSWORD 後重啟，系統才能登入")
        return
    try:
        A.check_password_policy(password)
    except ValueError as exc:
        log.error("QCM_ADMIN_PASSWORD 不符規則（%s），未建立管理者", exc)
        return
    session.add(User(username=username, display_name="系統管理員", password_hash=A.hash_password(password),
                     role=A.ROLE_SUPER, plant=None))
    session.commit()
    log.warning("已建立最高權限管理者帳號：%s", username)
