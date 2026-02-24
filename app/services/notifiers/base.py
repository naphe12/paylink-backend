from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class NotificationMessage:
    subject: str
    body_text: str
    body_html: str | None = None


class Notifier(Protocol):
    async def notify(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
    ) -> None: ...

