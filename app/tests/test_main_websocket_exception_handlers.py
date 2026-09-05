import asyncio
import logging

from fastapi import HTTPException, WebSocket

from app import main


def _websocket(sent):
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "wss",
        "path": "/ws/test",
        "raw_path": b"/ws/test",
        "query_string": b"",
        "headers": [(b"x-request-id", b"ws-request-1")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
        "subprotocols": [],
        "state": {},
    }

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    return WebSocket(scope, receive=receive, send=send)


def test_http_exception_handler_closes_websocket_without_reading_http_method(monkeypatch, caplog):
    sent = []
    persisted = []

    async def fake_persist(connection, exc, **kwargs):
        persisted.append((connection, exc, kwargs))

    monkeypatch.setattr(main, "persist_app_error", fake_persist)
    websocket = _websocket(sent)

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(main.http_exception_handler(websocket, HTTPException(status_code=403, detail="Refuse")))

    assert result is None
    assert persisted[0][2]["status_code"] == 403
    assert sent == [{"type": "websocket.close", "code": 4400, "reason": ""}]
    assert "method=WEBSOCKET" in caplog.text
    assert "request_id=ws-request-1" in caplog.text
