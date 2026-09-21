"""應用設定。

開發預設使用 SQLite（零安裝），正式部署以環境變數 QCM_DATABASE_URL 指向 PostgreSQL。
兩者共用同一套 SQLAlchemy 模型與查詢邏輯（見 spec.md §10）。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("QCM_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_raw_url = os.getenv("QCM_DATABASE_URL", f"sqlite:///{DATA_DIR / 'qcm.db'}")


def _normalize(url: str) -> str:
    """容錯處理雲端平台提供的連線字串。

    平台（如 Zeabur / Heroku）給的多半是 `postgresql://` 或 `postgres://`，
    但 SQLAlchemy 需要明確指定 driver，否則會落到未安裝的 psycopg2。
    這裡統一補成 `postgresql+psycopg://`（即 requirements 裡的 psycopg 3）。
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize(_raw_url)

# 偵測度切點：<= DETECTION_THRESHOLD 為「偵測能力高」（spec.md §2.1）
DETECTION_THRESHOLD = 5
