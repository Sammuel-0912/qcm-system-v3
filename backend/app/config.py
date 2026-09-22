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

_URL_FORMAT_HINT = "正確格式為 postgresql://<使用者>:<密碼>@<主機>:<port>/<資料庫>"


def _normalize(url: str) -> str:
    """容錯處理雲端平台提供的連線字串。

    1. 去除前後空白與換行（從主控台輸入框複製貼上時很常帶入）。
    2. 平台（如 Zeabur / Heroku）給的多半是 `postgresql://` 或 `postgres://`，
       但 SQLAlchemy 需要明確指定 driver，否則會落到未安裝的 psycopg2。
       統一補成 `postgresql+psycopg://`（即 requirements 裡的 psycopg 3）。
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _validate(url: str) -> str:
    """提早檢查連線字串，把難懂的底層錯誤換成可行動的訊息。

    主機名為空或含非法字元時，psycopg 會在啟動階段丟出
    `UnicodeError: label empty or too long`（IDNA 編碼失敗），
    訊息完全看不出是哪個環境變數有問題。這裡先攔下來講清楚。
    """
    if url.startswith("sqlite"):
        return url

    from sqlalchemy.engine import make_url

    try:
        parsed = make_url(url)
    except Exception as exc:  # pragma: no cover - 設定錯誤路徑
        raise RuntimeError(
            f"QCM_DATABASE_URL 格式無法解析：{exc}。{_URL_FORMAT_HINT}"
        ) from exc

    host = parsed.host or ""
    if not host or "" in host.split("."):
        raise RuntimeError(
            "\n".join(
                [
                    "QCM_DATABASE_URL 的主機名不合法。",
                    f"解析結果：host={host!r} port={parsed.port!r} "
                    f"user={parsed.username!r} database={parsed.database!r}",
                    "常見原因：",
                    "  (1) 主機名漏填，例如 ...@:5432/db",
                    "  (2) 字串中混入空白或換行",
                    "  (3) 密碼含 @ : / 等字元未做 percent-encoding"
                    "（@ 改 %40、: 改 %3A、/ 改 %2F）",
                    _URL_FORMAT_HINT,
                ]
            )
        )
    return url


DATABASE_URL = _validate(_normalize(_raw_url))

# 偵測度切點：<= DETECTION_THRESHOLD 為「偵測能力高」（spec.md §2.1）
DETECTION_THRESHOLD = 5
