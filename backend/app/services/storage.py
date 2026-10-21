"""上傳檔（拍照點檢照片、AR 設備圖）的儲存層。

- 本機／VM（預設 `QCM_STORAGE=local`）：存在 `QCM_DATA_DIR/ar-uploads`，搭配 volume 保存。
- Cloudflare（`QCM_STORAGE=s3`）：Containers 的磁碟是暫時的，改存 R2（S3 相容 API）。
  需要 `QCM_S3_ENDPOINT`（例：https://<帳號 ID>.r2.cloudflarestorage.com）、`QCM_S3_BUCKET`、
  `QCM_S3_ACCESS_KEY_ID`、`QCM_S3_SECRET_ACCESS_KEY`；`QCM_S3_REGION` 預設 auto（R2 的要求）。

對外網址一律是 `/api/ar/uploads/<key>`，由後端讀出後回傳，前端不必知道檔案實際存在哪裡。
key 只允許「子目錄/檔名」形式，不得有 `..` 或絕對路徑，避免讀寫到上傳區以外。
"""
from __future__ import annotations

import mimetypes
import os
import re
from functools import lru_cache
from pathlib import Path

from ..config import AR_UPLOAD_DIR, AR_UPLOAD_URL_PREFIX

_KEY = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*\.[A-Za-z0-9]+$")


class StorageError(Exception):
    pass


def valid_key(key: str) -> bool:
    return bool(_KEY.match(key)) and ".." not in key


def key_from_url(url: str | None) -> str | None:
    """`/api/ar/uploads/checks/abc.jpg` -> `checks/abc.jpg`；不是上傳網址或 key 不合法時回 None。"""
    prefix = f"{AR_UPLOAD_URL_PREFIX}/"
    if not url or not url.startswith(prefix):
        return None
    key = url[len(prefix) :]
    return key if valid_key(key) else None


def url_for(key: str) -> str:
    return f"{AR_UPLOAD_URL_PREFIX}/{key}"


def content_type_for(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        if not valid_key(key):
            raise StorageError(f"不合法的檔案路徑：{key}")
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """Cloudflare R2（或任何 S3 相容儲存，例：本機測試用的 MinIO）。"""

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str = "auto"):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        if not valid_key(key):
            raise StorageError(f"不合法的檔案路徑：{key}")
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type or content_type_for(key)
        )

    def get(self, key: str) -> bytes | None:
        if not valid_key(key):
            return None
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception as exc:  # 403／404 等以 ClientError 回報
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def delete(self, key: str) -> None:
        if valid_key(key):
            self.client.delete_object(Bucket=self.bucket, Key=key)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"QCM_STORAGE=s3 時必須設定環境變數 {name}")
    return value


@lru_cache(maxsize=1)
def get_storage() -> LocalStorage | S3Storage:
    kind = os.getenv("QCM_STORAGE", "local").strip().lower()
    if kind == "s3":
        return S3Storage(
            endpoint=_required("QCM_S3_ENDPOINT"),
            bucket=_required("QCM_S3_BUCKET"),
            access_key=_required("QCM_S3_ACCESS_KEY_ID"),
            secret_key=_required("QCM_S3_SECRET_ACCESS_KEY"),
            region=os.getenv("QCM_S3_REGION", "auto"),
        )
    if kind != "local":
        raise RuntimeError(f"QCM_STORAGE 只能是 local 或 s3（目前為 {kind!r}）")
    return LocalStorage(AR_UPLOAD_DIR)
