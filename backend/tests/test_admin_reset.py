"""QCM_ADMIN_RESET（一次性重設管理者密碼）：Cloudflare 容器沒有 shell，忘記唯一管理者密碼時用。"""
from __future__ import annotations

from tests.test_rbac import ADMIN, app_ctx  # noqa: F401  (app_ctx 為 fixture)


def test_admin_reset_overrides_password_and_revokes_sessions(app_ctx, monkeypatch):
    from app.api.auth_routes import ensure_bootstrap_admin
    from app.db import SessionLocal

    old = app_ctx(ADMIN)  # conftest 的管理者已存在
    assert old.get("/api/v1/auth/me").status_code == 200

    # 沒開重設：已有管理者時，改環境變數不會影響既有帳號
    monkeypatch.setenv("QCM_ADMIN_PASSWORD", "new-pass-5678")
    with SessionLocal() as s:
        ensure_bootstrap_admin(s)
    assert app_ctx().post("/api/v1/auth/login", json={"username": "admin", "password": "new-pass-5678"}).status_code == 401

    # 開重設：密碼換成新的、舊登入失效
    monkeypatch.setenv("QCM_ADMIN_RESET", "1")
    with SessionLocal() as s:
        ensure_bootstrap_admin(s)
    assert old.get("/api/v1/auth/me").status_code == 401
    assert app_ctx().post("/api/v1/auth/login", json={"username": "admin", "password": "new-pass-5678"}).status_code == 200

    # 帳號不存在時建立；密碼太短不動作
    monkeypatch.setenv("QCM_ADMIN_USERNAME", "boss")
    with SessionLocal() as s:
        ensure_bootstrap_admin(s)
    assert app_ctx().post("/api/v1/auth/login", json={"username": "boss", "password": "new-pass-5678"}).status_code == 200
    monkeypatch.setenv("QCM_ADMIN_PASSWORD", "short")
    with SessionLocal() as s:
        ensure_bootstrap_admin(s)
    assert app_ctx().post("/api/v1/auth/login", json={"username": "boss", "password": "new-pass-5678"}).status_code == 200
