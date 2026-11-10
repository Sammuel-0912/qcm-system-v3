"""Windows 安裝版由後端直接提供前端（spec §21，REQ-WIN-02）。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


def _client(tmp_path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "Roboto-msdf.json").write_text("{}", encoding="utf-8")
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("no", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/v1/ping")
    def ping() -> dict:
        return {"ok": True}

    mount_frontend(app, tmp_path)
    return TestClient(app)


def test_serves_assets_public_files_and_spa_fallback(tmp_path):
    c = _client(tmp_path)
    assert c.get("/assets/index-abc.js").text == "console.log(1)"
    assert c.get("/fonts/Roboto-msdf.json").json() == {}
    for path in ("/", "/ar/dashboard", "/login"):
        r = c.get(path)
        assert r.status_code == 200 and 'id=root' in r.text
        assert r.headers["cache-control"] == "no-cache"


def test_api_routes_win_and_unknown_api_is_404(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/v1/ping").json() == {"ok": True}
    assert c.get("/api/v1/nope").status_code == 404
    assert c.get("/assets/missing.js").status_code == 404


def test_does_not_serve_files_outside_the_frontend_dir(tmp_path):
    c = _client(tmp_path)
    r = c.get("/..%2Fsecret.txt")
    assert "no" != r.text and 'id=root' in r.text
