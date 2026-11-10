"""應用設定。

開發預設使用 SQLite（零安裝），正式部署以環境變數 QCM_DATABASE_URL 指向 PostgreSQL。
兩者共用同一套 SQLAlchemy 模型與查詢邏輯（見 spec.md §10）。
"""
from __future__ import annotations

import datetime as dt
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


# ---------------------------------------------------------------------------
# AR 設備點檢（ar-integration-spec.md §5 / D-04）
# ---------------------------------------------------------------------------
# 上傳的設備圖檔放在 DATA_DIR 底下，與資料庫共用同一個 volume，
# 重新部署後才不會遺失。對外網址統一掛在 /api/ar/uploads，
# 讓前端的 nginx 以單一 /api/ 規則轉發，不必為靜態檔另開規則。
AR_UPLOAD_DIR = DATA_DIR / "ar-uploads"
AR_UPLOAD_URL_PREFIX = "/api/ar/uploads"

# Windows 安裝版（desktop/，spec §21）沒有 nginx：設定時由後端直接提供前端建置好的靜態檔
STATIC_DIR = os.getenv("QCM_STATIC_DIR", "").strip() or None


# ---------------------------------------------------------------------------
# 高風險項點檢班別
# ---------------------------------------------------------------------------
# 資料庫一律存 UTC；班別以廠區當地時間切分。預設 UTC+8，
# 部署在其他時區的廠區以 QCM_SITE_UTC_OFFSET 調整。
SITE_UTC_OFFSET_HOURS = float(os.getenv("QCM_SITE_UTC_OFFSET", "8"))
# (班別名稱, 開始時, 時長小時)。夜班跨午夜。兩班之間的空檔顯示剛結束的那一班。
CHECK_SHIFTS: tuple[tuple[str, int, int], ...] = (("日班", 8, 10), ("夜班", 20, 10))
# 點檢趨勢的漏點檢（spec §18，v2.12）：起算日（之前為試運行，不算漏點檢）與不生產的星期（0＝週一 … 6＝週日，逗號分隔）
CHECK_MISSED_FROM = dt.date.fromisoformat(os.getenv("QCM_CHECK_MISSED_FROM", "2026-10-27"))
CHECK_OFF_WEEKDAYS = frozenset(int(d) for d in os.getenv("QCM_CHECK_OFF_WEEKDAYS", "6").split(",") if d.strip())
