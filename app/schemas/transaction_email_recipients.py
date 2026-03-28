from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class TransactionEmailRecipientBase(BaseModel):
    user_id: Optional[uuid.UUID] = None
    email: EmailStr
    active: bool = True


class TransactionEmailRecipientCreate(TransactionEmailRecipientBase):
    pass


class TransactionEmailRecipientRead(TransactionEmailRecipientBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)