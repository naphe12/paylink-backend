from __future__ import annotations


def build_request_metric_payload(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_id: str | None,
    error_type: str | None = None,
) -> dict[str, object]:
    normalized_status = int(status_code or 0)
    normalized_duration = round(float(duration_ms or 0), 3)
    normalized_error_type = str(error_type or "").strip() or None
    is_error = bool(normalized_error_type) or normalized_status >= 500
    return {
        "method": str(method or "GET"),
        "path": str(path or "/"),
        "status_code": normalized_status,
        "duration_ms": normalized_duration,
        "request_id": request_id,
        "error_type": normalized_error_type,
        "is_error": is_error,
    }
