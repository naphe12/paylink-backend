

# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.tontines import TontinesRead
    from app.schemas.users import UsersRead

class TontineMembersBase(BaseModel):
    tontine_id: str
    user_id: str
    join_order: int

class TontineMembersCreate(TontineMembersBase):
    tontine_id: str
    user_id: str
    join_order: int

class TontineMembersUpdate(BaseModel):
    tontine_id: Optional[str]
    user_id: Optional[str]
    join_order: Optional[int]

class TontineMembersRead(TontineMembersBase):
    tontine_id: str
    user_id: str
    join_order: int
    tontine: Optional["TontinesRead"] = None
    user: Optional["UsersRead"] = None
    class Config:
        from_attributes = True
