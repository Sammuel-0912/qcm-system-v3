"""測試一律使用暫存資料庫與資料目錄。

app.db 的 engine 是模組層級物件，第一次 import 時就依環境變數決定連線。
若某個測試檔先 import 了 app.*，而設定暫存位置的測試檔較晚才被收集，
engine 會指到開發用的 backend/data/qcm.db，接著 drop_all 就會清掉開發資料。
conftest 比所有測試檔都先載入，在這裡設定才保證不會碰到真正的資料庫。
"""
from __future__ import annotations

import os
import pathlib
import tempfile

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="qcm-test-"))
os.environ["QCM_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["QCM_DATA_DIR"] = str(_TMP)
