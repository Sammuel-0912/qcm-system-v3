"""上傳檔儲存層：本機磁碟與 S3 相容儲存（Cloudflare R2；測試用 moto 模擬 S3 API）。"""
from __future__ import annotations

import io

import pytest

from app.services import storage as S


@pytest.fixture()
def s3_env(monkeypatch):
    """把儲存層切到 S3 模式，並用 moto 模擬一個 bucket。"""
    from moto import mock_aws

    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="qcm-test")
        monkeypatch.setenv("QCM_STORAGE", "s3")
        monkeypatch.setenv("QCM_S3_ENDPOINT", "https://s3.amazonaws.com")
        monkeypatch.setenv("QCM_S3_BUCKET", "qcm-test")
        monkeypatch.setenv("QCM_S3_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("QCM_S3_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("QCM_S3_REGION", "us-east-1")
        S.get_storage.cache_clear()
        yield
    S.get_storage.cache_clear()


@pytest.fixture(autouse=True)
def _reset_cache():
    S.get_storage.cache_clear()
    yield
    S.get_storage.cache_clear()


def test_key_validation_blocks_traversal():
    assert S.valid_key("checks/abc123.jpg")
    assert S.valid_key("device_1_ab12cd34.png")
    for bad in ("../etc/passwd", "checks/../../x.jpg", "/abs/x.jpg", "checks/a b.jpg", "noext", ""):
        assert not S.valid_key(bad), bad
    assert S.key_from_url("/api/ar/uploads/checks/abc.jpg") == "checks/abc.jpg"
    assert S.key_from_url("/api/ar/uploads/../x.jpg") is None
    assert S.key_from_url("https://evil.example/x.jpg") is None


def test_local_storage_roundtrip(tmp_path):
    st = S.LocalStorage(tmp_path)
    st.put("checks/a.jpg", b"jpeg")
    assert (tmp_path / "checks" / "a.jpg").read_bytes() == b"jpeg"
    assert st.get("checks/a.jpg") == b"jpeg"
    assert st.get("checks/missing.jpg") is None
    st.delete("checks/a.jpg")
    assert st.get("checks/a.jpg") is None
    with pytest.raises(S.StorageError):
        st.put("../x.jpg", b"x")


def test_s3_storage_roundtrip(s3_env):
    st = S.get_storage()
    assert isinstance(st, S.S3Storage)
    st.put("checks/b.png", b"png-bytes", "image/png")
    assert st.get("checks/b.png") == b"png-bytes"
    head = st.client.head_object(Bucket="qcm-test", Key="checks/b.png")
    assert head["ContentType"] == "image/png"
    assert st.get("checks/missing.png") is None
    st.delete("checks/b.png")
    assert st.get("checks/b.png") is None


def test_s3_mode_requires_settings(monkeypatch):
    monkeypatch.setenv("QCM_STORAGE", "s3")
    for name in ("QCM_S3_ENDPOINT", "QCM_S3_BUCKET", "QCM_S3_ACCESS_KEY_ID", "QCM_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="QCM_S3_ENDPOINT"):
        S.get_storage()
    monkeypatch.setenv("QCM_STORAGE", "ftp")
    S.get_storage.cache_clear()
    with pytest.raises(RuntimeError, match="local 或 s3"):
        S.get_storage()


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (200, 80, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_photo_upload_serve_and_export_through_s3(s3_env):
    """整合：S3 模式下拍照上傳 → 照片存進 bucket → /api/ar/uploads 讀得到 → 匯出 Excel 嵌入縮圖。"""
    import openpyxl
    from fastapi.testclient import TestClient

    from app.db import Base, engine
    from app.main import app
    from tests.test_ar import DATA, _import_v3

    if not DATA.exists():
        pytest.skip("數據庫-1019.xlsx 不存在")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        _import_v3(client)
        station = client.get("/api/v1/check-items").json()["stations"][0]
        item = client.get("/api/v1/check-items", params={"station": station}).json()["items"][0]
        data = _png()
        res = client.post(
            "/api/v1/check-inspections",
            data={"equipmentCode": item["equipmentCode"], "kpovNo": item["kpovNo"], "checkContent": item["checkContent"]},
            files={"file": ("p.png", data, "image/png")},
        )
        assert res.status_code == 201, res.text
        url = res.json()["photoUrl"]
        key = S.key_from_url(url)
        # 檔案在 bucket 裡，不在本機上傳目錄
        assert S.get_storage().get(key) == data
        served = client.get(url)
        assert served.status_code == 200 and served.content == data
        assert served.headers["content-type"] == "image/png"
        assert client.get("/api/ar/uploads/checks/nope.png").status_code == 404
        assert client.get("/api/ar/uploads/..%2F..%2Fapp%2Fconfig.py").status_code == 404

        export = client.get("/api/v1/check-inspections/export")
        ws = openpyxl.load_workbook(io.BytesIO(export.content)).active
        assert len(ws._images) == 1
    Base.metadata.drop_all(engine)
