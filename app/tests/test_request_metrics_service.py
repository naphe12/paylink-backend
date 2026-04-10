from app.services.request_metrics import build_request_metric_payload


def test_build_request_metric_payload_marks_5xx_as_error():
    payload = build_request_metric_payload(
        method="GET",
        path="/api/test",
        status_code=503,
        duration_ms=12.3456,
        request_id="req-1",
    )

    assert payload["status_code"] == 503
    assert payload["duration_ms"] == 12.346
    assert payload["error_type"] is None
    assert payload["is_error"] is True


def test_build_request_metric_payload_keeps_non_5xx_with_exception_as_error():
    payload = build_request_metric_payload(
        method="POST",
        path="/api/test",
        status_code=409,
        duration_ms=7.5,
        request_id="req-2",
        error_type="HTTPException",
    )

    assert payload["status_code"] == 409
    assert payload["error_type"] == "HTTPException"
    assert payload["is_error"] is True
