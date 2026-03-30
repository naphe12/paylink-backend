import csv
import io
import json

from fastapi import HTTPException
from fastapi.responses import Response


def build_json_download_response(payload, *, filename: str) -> Response:
    return Response(
        content=json.dumps(payload, default=str, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def build_csv_download_response(*, headers: list[str], rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def normalize_export_format(value: str | None) -> str:
    normalized = str(value or "json").strip().lower()
    if normalized not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Unsupported format")
    return normalized
