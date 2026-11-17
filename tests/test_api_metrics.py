"""The versioned JSON API: business events at the HTTP edge show up on the Prometheus endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app
from app.settings import API_PREFIX
from proveit import metrics

client = TestClient(app)


def test_metrics_endpoint_counts_rejected_webhooks():
    metrics.reset()
    assert client.post("/webhooks/mock", json={}).status_code == 400
    r = client.get(f"{API_PREFIX}/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert 'proveit_webhook_rejected_total{status="400"} 1' in r.text


def test_json_routes_are_versioned():
    assert client.get(f"{API_PREFIX}/runs").status_code == 200
    unversioned = client.get("/api/runs")
    assert unversioned.status_code == 404 and unversioned.json()["ok"] is False
