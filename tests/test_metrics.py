"""Alerting counters: increments are labelled, summed and rendered in the Prometheus text format."""

from proveit import metrics


def test_counters_render_in_prometheus_format():
    metrics.reset()
    metrics.increment("stage_failed", stage="phase1")
    metrics.increment("stage_failed", stage="phase1")
    metrics.increment("webhook_rejected", reason='bad "sig"')
    assert metrics.value("stage_failed", stage="phase1") == 2
    text = metrics.render_prometheus()
    assert 'proveit_stage_failed_total{stage="phase1"} 2' in text
    assert 'proveit_webhook_rejected_total{reason="bad \\"sig\\""} 1' in text
