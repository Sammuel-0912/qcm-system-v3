"""線上人數：前端定期心跳，超過 TTL 沒心跳就視為離開。

狀態只存在這個 process 的記憶體裡——後端目前是單一 uvicorn worker
（backend/Dockerfile）。若改成多 worker 或多副本，每個 process 只會看到
自己收到的心跳，屆時要改存 Redis 或資料庫。
"""
from __future__ import annotations

import threading
import time

TTL_SECONDS = 45.0

_sessions: dict[str, float] = {}
_lock = threading.Lock()


def touch(sid: str, now: float | None = None) -> None:
    with _lock:
        _sessions[sid] = time.monotonic() if now is None else now


def leave(sid: str) -> None:
    with _lock:
        _sessions.pop(sid, None)


def count(now: float | None = None) -> int:
    """回傳目前線上人數，順便清掉逾時的 session。"""
    cutoff = (time.monotonic() if now is None else now) - TTL_SECONDS
    with _lock:
        for sid in [s for s, t in _sessions.items() if t < cutoff]:
            del _sessions[sid]
        return len(_sessions)


def reset() -> None:
    """測試用。"""
    with _lock:
        _sessions.clear()
