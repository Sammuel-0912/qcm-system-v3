"""線上人數（presence）測試。"""
from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

# 與 test_ar 相同理由：app.db 的 engine 在匯入時建立，要先把資料庫指到暫存位置。
# 若其他測試檔已先匯入 app，setdefault 不會覆蓋它們的設定。
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="qcm-presence-test-"))
os.environ.setdefault("QCM_DATABASE_URL", f"sqlite:///{_TMP / 'presence.db'}")
os.environ.setdefault("QCM_DATA_DIR", str(_TMP))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app as fastapi_app  # noqa: E402
from app.services import presence  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    presence.reset()
    yield
    presence.reset()


@pytest.fixture()
def client():
    # 線上人數也需要登入（spec §15）：進 context manager 讓 startup 建立管理者後登入
    with TestClient(fastapi_app) as c:
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass-1234"}).status_code == 200
        yield c


def test_heartbeat_counts_distinct_sessions(client):
    assert client.post("/api/v1/presence/heartbeat", json={"sid": "a"}).json() == {"online": 1}
    assert client.post("/api/v1/presence/heartbeat", json={"sid": "b"}).json() == {"online": 2}
    # 同一個 sid 重複心跳不重複計算
    assert client.post("/api/v1/presence/heartbeat", json={"sid": "a"}).json() == {"online": 2}


def test_leave_removes_immediately(client):
    client.post("/api/v1/presence/heartbeat", json={"sid": "a"})
    client.post("/api/v1/presence/heartbeat", json={"sid": "b"})
    assert client.post("/api/v1/presence/leave", json={"sid": "a"}).status_code == 204
    assert presence.count() == 1
    # 離開不存在的 sid 不報錯
    assert client.post("/api/v1/presence/leave", json={"sid": "zzz"}).status_code == 204


def test_expired_sessions_are_dropped():
    presence.touch("old", now=100.0)
    presence.touch("new", now=100.0 + presence.TTL_SECONDS)
    assert presence.count(now=100.0 + presence.TTL_SECONDS + 1) == 1


def test_rejects_empty_sid(client):
    assert client.post("/api/v1/presence/heartbeat", json={"sid": ""}).status_code == 422
