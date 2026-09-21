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

DATABASE_URL = os.getenv("QCM_DATABASE_URL", f"sqlite:///{DATA_DIR / 'qcm.db'}")

# 偵測度切點：<= DETECTION_THRESHOLD 為「偵測能力高」（spec.md §2.1）
DETECTION_THRESHOLD = 5
