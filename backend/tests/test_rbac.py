"""RBAC（spec §15）：帳號、JWT、依廠別的資料隔離、同廠多線、匯入與使用者管理權限。"""
from __future__ import annotations

import datetime as dt
import io
import pathlib

import pytest

from app.services import auth as A

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
V1019 = ROOT / "數據庫-1019.xlsx"
V1026 = ROOT / "WJ1-DCS-PM1-數據庫-1026.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ADMIN = {"username": "admin", "password": "admin-pass-1234"}


# --------------------------------------------------------------------------- 單元


def test_password_hash_and_policy():
    stored = A.hash_password("correct-horse")
    assert stored.startswith("scrypt$") and "correct-horse" not in stored
    assert A.verify_password("correct-horse", stored)
    assert not A.verify_password("wrong-horse", stored)
    assert not A.verify_password("x", "garbage")
    assert A.hash_password("same-pass1") != A.hash_password("same-pass1")  # 每次 salt 不同
    with pytest.raises(ValueError, match="8"):
        A.check_password_policy("1234567")
    A.check_password_policy("12345678")


def test_jwt_issue_tamper_and_expiry():
    token = A.issue_token(7, 3)
    payload = A.decode_token(token)
    assert payload["sub"] == "7" and payload["ver"] == 3
    # 竄改簽章倒數第二個字元（換成一定不同的字元；原本固定換成 "A"，剛好是 "A" 時等於沒改，約 1/64 機率誤判）
    assert A.decode_token(token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]) is None
    old = A.issue_token(7, 3, now=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=A.TOKEN_HOURS + 1))
    assert A.decode_token(old) is None
    assert A.decode_token("not-a-jwt") is None


def test_dataset_filename_parsing():
    d = A.parse_dataset_filename("WJ1-DCS-PM1-數據庫-1026.xlsx")
    assert (d.plant, d.factory, d.line, d.date, d.key) == ("WJ1", "DCS", "PM1", "1026", "WJ1-DCS-PM1")
    assert A.parse_dataset_filename("wj8-dcs-pm2-數據庫-0101.XLSX").key == "WJ8-DCS-PM2"
    for bad in ("WJ9-DCS-PM1-數據庫-1026.xlsx", "WJ0-DCS-PM1-數據庫-1026.xlsx", "數據庫-1019.xlsx",
                "WJ1-DCS-數據庫-1026.xlsx", "WJ1-DCS-PM1-數據庫-10.xlsx", "WJ1-DCS-PM1-資料-1026.xlsx"):
        with pytest.raises(ValueError, match="WJ1-DCS-PM1-數據庫-1026.xlsx"):
            A.parse_dataset_filename(bad)


def test_permission_matrix():
    assert A.can_view_plant(A.ROLE_SUPER, None, "WJ5")
    assert A.can_view_plant(A.ROLE_USER, "WJ2", "WJ2") and not A.can_view_plant(A.ROLE_USER, "WJ2", "WJ1")
    assert A.can_import(A.ROLE_SUPER, None, "WJ3")
    assert A.can_import(A.ROLE_PLANT_ADMIN, "WJ2", "WJ2") and not A.can_import(A.ROLE_PLANT_ADMIN, "WJ2", "WJ1")
    assert not A.can_import(A.ROLE_USER, "WJ2", "WJ2")
    assert A.can_manage_user(A.ROLE_SUPER, None, A.ROLE_PLANT_ADMIN, "WJ2")
    assert A.can_manage_user(A.ROLE_PLANT_ADMIN, "WJ2", A.ROLE_USER, "WJ2")
    assert not A.can_manage_user(A.ROLE_PLANT_ADMIN, "WJ2", A.ROLE_PLANT_ADMIN, "WJ2")  # 廠管理者由 super 指派
    assert not A.can_manage_user(A.ROLE_PLANT_ADMIN, "WJ2", A.ROLE_USER, "WJ1")
    assert not A.can_manage_user(A.ROLE_USER, "WJ2", A.ROLE_USER, "WJ2")


# --------------------------------------------------------------------------- 整合


@pytest.fixture()
def app_ctx():
    from fastapi.testclient import TestClient

    from app.db import Base, engine
    from app.main import app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clients = []

    def new_client(login: dict | None = None):
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        if login:
            res = c.post("/api/v1/auth/login", json=login)
            assert res.status_code == 200, res.text
        return c

    yield new_client
    for c in clients:
        c.__exit__(None, None, None)
    Base.metadata.drop_all(engine)


def _import(client, path: pathlib.Path, name: str):
    with path.open("rb") as fh:
        return client.post("/api/v1/import", files={"file": (name, fh, XLSX)})


needs_data = pytest.mark.skipif(not (V1019.exists() and V1026.exists()), reason="需要數據庫-1019 與 1026")


def test_login_required_and_bad_credentials(app_ctx):
    anon = app_ctx()
    assert anon.get("/api/v1/filters").status_code == 401
    assert anon.get("/api/v1/auth/me").status_code == 401
    assert anon.post("/api/v1/import").status_code == 401
    assert anon.get("/api/ar/uploads/checks/x.png").status_code == 401
    assert anon.get("/health").status_code == 200
    assert anon.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    assert anon.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever1"}).status_code == 401
    res = anon.post("/api/v1/auth/login", json=ADMIN)
    assert res.status_code == 200 and res.json()["role"] == A.ROLE_SUPER
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    me = anon.get("/api/v1/auth/me").json()
    assert me["username"] == "admin" and me["datasets"] == []
    anon.post("/api/v1/auth/logout")
    assert anon.get("/api/v1/auth/me").status_code == 401


@needs_data
def test_plant_isolation_multi_line_and_import_rules(app_ctx):
    su = app_ctx(ADMIN)
    # 三個資料集：WJ1 兩條線、WJ2 一條線
    assert _import(su, V1019, "WJ1-DCS-PM1-數據庫-1019.xlsx").status_code == 200
    assert _import(su, V1026, "WJ1-DCS-PM2-數據庫-1026.xlsx").status_code == 200
    assert _import(su, V1026, "WJ2-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    keys = [d["key"] for d in su.get("/api/v1/datasets").json()]
    assert keys == ["WJ1-DCS-PM1", "WJ1-DCS-PM2", "WJ2-DCS-PM1"]
    # 不合格的檔名
    bad = _import(su, V1019, "數據庫-1019.xlsx")
    assert bad.status_code == 422 and "WJ1-DCS-PM1-數據庫-1026.xlsx" in bad.json()["detail"]

    # 指派 WJ2 的廠管理者；廠管理者新增 WJ2 一般使用者
    pa = su.post("/api/v1/users", json={"username": "wj2admin", "displayName": "WJ2 管理者", "password": "wj2-admin-pw",
                                        "role": A.ROLE_PLANT_ADMIN, "plant": "WJ2"})
    assert pa.status_code == 201, pa.text
    wj2a = app_ctx({"username": "wj2admin", "password": "wj2-admin-pw"})
    created = wj2a.post("/api/v1/users", json={"username": "wj2op", "displayName": "WJ2 作業員", "password": "wj2-op-pass",
                                               "role": A.ROLE_USER, "plant": "WJ1"})  # 廠別強制為自己的廠
    assert created.status_code == 201 and created.json()["plant"] == "WJ2"
    assert wj2a.post("/api/v1/users", json={"username": "xx2", "displayName": "x", "password": "12345678",
                                            "role": A.ROLE_PLANT_ADMIN}).status_code == 403
    assert wj2a.post("/api/v1/users", json={"username": "short", "displayName": "x", "password": "1234567"}).status_code == 422
    assert wj2a.post("/api/v1/users", json={"username": "wj2op", "displayName": "x", "password": "12345678"}).status_code == 409
    # 廠管理者只看得到自己廠的帳號，也動不了別廠或管理者帳號
    su.post("/api/v1/users", json={"username": "wj1op", "displayName": "WJ1", "password": "wj1-op-pass", "plant": "WJ1"})
    wj1op_id = next(u["id"] for u in su.get("/api/v1/users").json() if u["username"] == "wj1op")
    assert {u["username"] for u in wj2a.get("/api/v1/users").json()} == {"wj2admin", "wj2op"}
    assert wj2a.patch(f"/api/v1/users/{wj1op_id}", json={"isActive": False}).status_code == 404
    self_id = next(u["id"] for u in wj2a.get("/api/v1/users").json() if u["username"] == "wj2admin")
    assert wj2a.patch(f"/api/v1/users/{self_id}", json={"isActive": False}).status_code in (400, 404)

    # 一般使用者：只看得到自己廠；指定別廠 403；不能匯入
    op = app_ctx({"username": "wj2op", "password": "wj2-op-pass"})
    assert [d["key"] for d in op.get("/api/v1/auth/me").json()["datasets"]] == ["WJ2-DCS-PM1"]
    assert op.get("/api/v1/repairs", params={"pageSize": 50}).json()["total"] == 30  # 預設＝自己廠第一條線（1026）
    assert op.get("/api/v1/filters", headers={"X-QCM-Dataset": "WJ1-DCS-PM1"}).status_code == 403
    assert op.get("/api/v1/filters", headers={"X-QCM-Dataset": "WJ2-DCS-PM9"}).status_code == 404
    # 匯出 Excel 是瀏覽器直接下載，帶不了 header，改用 ?dataset=，權限檢查相同
    assert op.get("/api/v1/check-inspections/export", params={"dataset": "WJ1-DCS-PM1"}).status_code == 403
    assert op.get("/api/v1/check-inspections/export", params={"dataset": "WJ2-DCS-PM1"}).json()["detail"] == "沒有符合條件的點檢紀錄可匯出"  # 有權限，只是還沒有紀錄
    assert _import(op, V1026, "WJ2-DCS-PM1-數據庫-1026.xlsx").status_code == 403
    assert op.get("/api/v1/users").status_code == 403
    # 廠管理者不能匯入別廠
    assert _import(wj2a, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 403
    assert _import(wj2a, V1026, "WJ2-DCS-PM1-數據庫-1026.xlsx").status_code == 200

    # 同廠多線各自生效：WJ1-PM1 是 1019（28 筆維修）、WJ1-PM2 是 1026（30 筆）；重新匯入 PM1 不影響 PM2
    h1 = {"X-QCM-Dataset": "WJ1-DCS-PM1"}
    h2 = {"X-QCM-Dataset": "WJ1-DCS-PM2"}
    assert su.get("/api/v1/repairs", params={"pageSize": 50}, headers=h1).json()["total"] == 28
    assert su.get("/api/v1/repairs", params={"pageSize": 50}, headers=h2).json()["total"] == 30
    assert _import(su, V1019, "WJ1-DCS-PM1-數據庫-1019.xlsx").status_code == 200
    assert su.get("/api/v1/repairs", params={"pageSize": 50}, headers=h2).json()["total"] == 30
    history = su.get("/api/v1/import/history").json()
    assert sum(1 for b in history if b["isActive"]) == 3
    assert {b["dataset"] for b in op.get("/api/v1/import/history").json()} == {"WJ2-DCS-PM1"}


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@needs_data
def test_photos_are_scoped_to_plant_and_tokens_revoked(app_ctx):
    su = app_ctx(ADMIN)
    _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx")
    _import(su, V1026, "WJ2-DCS-PM1-數據庫-1026.xlsx")
    su.post("/api/v1/users", json={"username": "op1", "displayName": "WJ1", "password": "op1-password", "plant": "WJ1"})
    su.post("/api/v1/users", json={"username": "op2", "displayName": "WJ2", "password": "op2-password", "plant": "WJ2"})
    op1 = app_ctx({"username": "op1", "password": "op1-password"})
    op2 = app_ctx({"username": "op2", "password": "op2-password"})

    station = op1.get("/api/v1/check-items").json()["stations"][0]
    item = op1.get("/api/v1/check-items", params={"station": station}).json()["items"][0]
    res = op1.post("/api/v1/check-inspections",
                   data={"equipmentCode": item["equipmentCode"], "kpovNo": item["kpovNo"], "checkContent": item["checkContent"]},
                   files={"file": ("p.png", _png(), "image/png")})
    assert res.status_code == 201, res.text
    url = res.json()["photoUrl"]
    # WJ1 看得到、WJ2 看不到（同模板、相同設備代碼也不會混在一起）
    assert op1.get(url).status_code == 200
    assert op2.get(url).status_code == 404
    assert op1.get("/api/v1/check-inspections").json()["total"] == 1
    assert op2.get("/api/v1/check-inspections").json()["total"] == 0
    wj2_item = next(i for i in op2.get("/api/v1/check-monitor").json()["items"]
                    if (i["equipmentCode"], i["checkContent"]) == (item["equipmentCode"], item["checkContent"]))
    assert wj2_item["lastInspectedAt"] is None

    # 停用後舊權杖立即失效；重設密碼後舊權杖也失效
    users = {u["username"]: u["id"] for u in su.get("/api/v1/users").json()}
    assert su.patch(f"/api/v1/users/{users['op2']}", json={"isActive": False}).status_code == 200
    assert op2.get("/api/v1/auth/me").status_code == 401
    assert app_ctx().post("/api/v1/auth/login", json={"username": "op2", "password": "op2-password"}).status_code == 403
    assert su.post(f"/api/v1/users/{users['op1']}/reset-password", json={"password": "new-pass-123"}).status_code == 200
    assert op1.get("/api/v1/auth/me").status_code == 401
    op1b = app_ctx({"username": "op1", "password": "new-pass-123"})
    # 自己改密碼：舊密碼錯 400、太短 422、成功後仍維持登入
    assert op1b.post("/api/v1/auth/password", json={"oldPassword": "wrong", "newPassword": "another-pass"}).status_code == 400
    assert op1b.post("/api/v1/auth/password", json={"oldPassword": "new-pass-123", "newPassword": "short"}).status_code == 422
    assert op1b.post("/api/v1/auth/password", json={"oldPassword": "new-pass-123", "newPassword": "another-pass"}).status_code == 200
    assert op1b.get("/api/v1/auth/me").status_code == 200
    # 最高權限管理者不能停用自己，也不能改自己的角色
    admin_id = su.get("/api/v1/auth/me").json()["id"]
    assert su.patch(f"/api/v1/users/{admin_id}", json={"isActive": False}).status_code == 400
    assert su.patch(f"/api/v1/users/{admin_id}", json={"role": "user", "plant": "WJ1"}).status_code == 400
    # AR 路由只給最高權限管理者
    assert op1b.get("/api/ar/devices").status_code == 403
