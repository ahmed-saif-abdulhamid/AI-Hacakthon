"""Hardening: no path can leave the runs folder, and link parameters cannot inject script."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_run_id_path_traversal_is_refused():
    for path in ("/api/runs/%2E%2E/files/.env", "/api/runs/../files/README.md", "/api/runs/..%2F..%2F/files/x",
                 "/p/..%2F.env", "/store/%2E%2E"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert "NVIDIA" not in r.text and "Apache" not in r.text


def test_file_name_cannot_climb_out():
    for name in ("..", ".env", "..%2F..%2F.env"):
        r = client.get(f"/api/runs/r20261117-000000-abcd/files/{name}")
        assert r.status_code == 404, name


def test_mode_parameter_cannot_inject_script():
    assert client.get('/hud?mode=";alert(1)//').status_code == 422
    assert client.get("/hud?mode=</script><script>alert(1)</script>").status_code == 422
    html = client.get("/hud?mode=dual").text
    assert 'mode:"dual"' in html


def test_api_base_parameter_is_escaped():
    html = client.get("/hud?api=</script><script>alert(1)</script>").text
    assert "<script>alert(1)</script>" not in html
