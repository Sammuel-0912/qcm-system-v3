"""Windows 安裝版的進入點（spec §21）：由 Windows 服務以內附的 python\\python.exe 執行。

設定與資料都放在 %ProgramData%\\QCM（解除安裝時保留）：
  settings.json   port、JWT 金鑰、第一位管理者（安裝程式寫入；建立管理者後密碼即從檔案移除）
  qcm.db          SQLite 資料庫
  ar-uploads\\    拍照點檢照片
app.config 在 import 時就讀環境變數，所以一定要先設好環境變數，才能 import app。
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys
from pathlib import Path

DATA_DIR = Path(os.getenv("QCM_DATA_DIR") or Path(os.getenv("PROGRAMDATA", r"C:\ProgramData")) / "QCM")
SETTINGS = DATA_DIR / "settings.json"
# 安裝版的前端放在 launcher.py 旁的 web\；在 repo 裡直接執行時改用 frontend\dist
HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web" if (HERE / "web").is_dir() else HERE.parent / "frontend" / "dist"
DEFAULT_PORT = 8080


def _load() -> dict:
    if not SETTINGS.exists():
        return {}
    # 安裝程式（Inno Setup）寫出的 UTF-8 帶 BOM
    return json.loads(SETTINGS.read_text(encoding="utf-8-sig") or "{}")


def _save(settings: dict) -> None:
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def _lan_addresses() -> list[str]:
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos if not i[4][0].startswith("127.")})


def _port_problem(port: int) -> OSError | None:
    """先試著佔用埠號；Windows 保留的埠號（WinError 10013）或已被占用時回傳錯誤。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("0.0.0.0", port))
    except OSError as exc:
        return exc
    finally:
        probe.close()
    return None


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings = _load()
    if not settings.get("jwtSecret"):
        # 第一次啟動產生並保存；之後沿用，重啟服務不會讓所有人被登出
        settings["jwtSecret"] = secrets.token_hex(32)
        _save(settings)
    override = DATA_DIR / "port-override.txt"
    if override.exists():
        # 更新安裝時改了埠號：安裝程式只寫這個檔，由這裡寫回 settings.json
        settings["port"] = int(override.read_text(encoding="ascii").strip())
        _save(settings)
        override.unlink()
    port = int(settings.get("port") or DEFAULT_PORT)
    problem = _port_problem(port)
    if problem:
        # 不用 uvicorn 那行難懂的錯誤；服務會每 10 秒重試，記錄裡要看得出該怎麼處理
        print(
            f"[qcm] 無法使用埠號 {port}：{problem}\n"
            f"[qcm] 常見原因：埠號已被其他程式占用，或被 Windows 保留（Hyper-V／WSL／Docker）。\n"
            f"[qcm] 檢查：netstat -ano | findstr :{port}，以及 netsh interface ipv4 show excludedportrange protocol=tcp\n"
            f"[qcm] 處理：以系統管理員編輯 {SETTINGS} 的 \"port\" 換成沒被占用的埠號（例 8765），再執行 sc.exe start QCM",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    os.environ["QCM_DATA_DIR"] = str(DATA_DIR)
    os.environ.setdefault("QCM_DATABASE_URL", f"sqlite:///{DATA_DIR / 'qcm.db'}")
    os.environ["QCM_JWT_SECRET"] = settings["jwtSecret"]
    os.environ["QCM_STATIC_DIR"] = str(WEB_DIR)
    if settings.get("adminUsername") and settings.get("adminPassword"):
        os.environ["QCM_ADMIN_USERNAME"] = settings["adminUsername"]
        os.environ["QCM_ADMIN_PASSWORD"] = settings["adminPassword"]

    import uvicorn

    from app.api.auth_routes import ensure_bootstrap_admin
    from app.db import SessionLocal, init_db
    from app.main import app
    from app.models import User
    from app.services.auth import ROLE_SUPER

    # 先建好資料表與第一位管理者，確定建立後就把明文密碼從設定檔拿掉
    init_db()
    with SessionLocal() as session:
        ensure_bootstrap_admin(session)
        has_super = session.query(User).filter(User.role == ROLE_SUPER).count() > 0
    if has_super and "adminPassword" in settings:
        settings.pop("adminPassword")
        _save(settings)

    urls = ", ".join(f"http://{ip}:{port}" for ip in _lan_addresses()) or "（查不到本機 IP，請執行 ipconfig）"
    print(f"[qcm] 資料目錄 {DATA_DIR}；本機 http://localhost:{port}；平板連 {urls}", flush=True)
    # 單一 worker：線上人數（presence）存在程序記憶體內
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1, log_level="info")


if __name__ == "__main__":
    main()
