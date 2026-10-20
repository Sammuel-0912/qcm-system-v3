from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=_connect_args)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 連線層設定
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        # WAL：Cloudflare 部署以 Litestream 把 SQLite 持續備份到 R2，Litestream 需要 WAL 模式；
        # busy_timeout：Litestream 做 checkpoint 時短暫持有鎖，寫入改為等待而不是立刻報 database is locked
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")


SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401  確保模型已註冊
    from .migrations import ensure_schema

    Base.metadata.create_all(engine)
    # create_all 只建立不存在的表，不會修改既有表；既有資料庫的結構變更走這裡
    ensure_schema(engine)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
