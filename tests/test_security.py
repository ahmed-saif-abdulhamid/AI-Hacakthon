"""Hardening: no path can leave the runs folder, and link parameters cannot inject script."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_run_id_path_traversal_is_refused():
    for path in (
        "/api/v1/runs/%2E%2E/files/.env",
        "/api/v1/runs/../files/README.md",
        "/api/v1/runs/..%2F..%2F/files/x",
        "/p/..%2F.env",
        "/store/%2E%2E",
    ):
        r = client.get(path)
        assert r.status_code == 404, path
        assert "NVIDIA" not in r.text and "Apache" not in r.text


def test_file_name_cannot_climb_out():
    for name in ("..", ".env", "..%2F..%2F.env"):
        r = client.get(f"/api/v1/runs/r20261117-000000-abcd/files/{name}")
        assert r.status_code == 404, name


def test_mode_parameter_cannot_inject_script():
    assert client.get('/hud?mode=";alert(1)//').status_code == 422
    assert client.get("/hud?mode=</script><script>alert(1)</script>").status_code == 422
    html = client.get("/hud?mode=dual").text
    assert 'mode: "dual"' in html


def test_api_base_parameter_is_escaped():
    html = client.get("/hud?api=</script><script>alert(1)</script>").text
    assert "<script>alert(1)</script>" not in html


def test_dns_rebinding_host_is_refused():
    assert client.get("/api/v1/approvals", headers={"host": "evil.example"}).status_code == 400


def test_cross_site_and_non_json_posts_are_refused():
    r = client.post("/api/v1/ask", json={"text": "hi"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/v1/runs", content=b'{"fields":{"idea":"x"}}', headers={"content-type": "text/plain"})
    assert r.status_code == 415


def test_public_placeholder_is_never_the_signing_secret(monkeypatch, tmp_path):
    from proveit import secrets_store

    secrets_store.secret_key.cache_clear()
    monkeypatch.setenv("PROVEIT_ENV", "dev")
    monkeypatch.setenv("SECRET_KEY", "dev-only-change-me")
    monkeypatch.setenv("PROVEIT_DATA", str(tmp_path))
    key = secrets_store.secret_key()
    assert key != "dev-only-change-me" and len(key) == 64
    assert (tmp_path / "secret_key").read_text() == key
    secrets_store.secret_key.cache_clear()
