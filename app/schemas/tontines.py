from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from pydantic import BaseModel, Field
from pydantic import BaseModel

# Auto-generated from SQLAlchemy model with relationships and imports
from uuid import UUID

if TYPE_CHECKING:
    from app.schemas.currencies import CurrenciesRead
    from app.schemas.tontinecontributions import TontineContributionsRead
    from app.schemas.tontinemembers import TontineMembersRead
    from app.schemas.tontinepayouts import TontinePayoutsRead
    from app.schemas.users import UsersRead




class TontinesBase(BaseModel):
    tontine_id: str
    owner_user: str
    name: str
    currency_code: str
    periodicity_days: int
    status: str
    created_at: datetime
    updated_at: datetime

class TontinesCreate(TontinesBase):
    tontine_id: str
    owner_user: str
    name: str
    currency_code: str
    periodicity_days: int
    status: str

class TontinesUpdate(BaseModel):
    tontine_id: Optional[str]
    owner_user: Optional[str]
    name: Optional[str]
    currency_code: Optional[str]
    periodicity_days: Optional[int]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

class TontinesRead(TontinesBase):
    tontine_id: str
    owner_user: str
    name: str
    currency_code: str
    periodicity_days: int
    status: str
    created_at: datetime
    updated_at: datetime
    currencies: Optional["CurrenciesRead"] = None
    users: Optional["UsersRead"] = None
    tontine_members: list["TontineMembersRead"] = None
    tontine_contributions: list["TontineContributionsRead"] = None
    tontine_payouts: list["TontinePayoutsRead"] = None
    class Config:
        from_attributes = True

class TontineListRead(TontinesBase):
    tontine_id: str
    owner_user: str
    name: str
    currency_code: str
    periodicity_days: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class TontineMemberOut(BaseModel):
    user_id: UUID
    full_name: str | None = None

    class Config:
        from_attributes = True


class TontineOut(BaseModel):
    tontine_id: UUID
    owner_user: UUID
    name: str
    currency_code: str
    periodicity_days: int
    status: str
    amount_per_member: float
    current_round: int | None = None
    next_rotation_at: datetime | None = None
    members: list[TontineMemberOut] = Field(default=[], alias="tontine_members")

    class Config:
        from_attributes = True   # remplace orm_mode=True en Pydantic v2


class TontineMemberDetail(BaseModel):
    user_id: UUID
    name: str | None = None
    phone: str | None = None
    is_online: bool = False


class TontineDetailResponse(BaseModel):
    tontine_id: UUID
    owner_user: UUID
    name: str
    currency_code: str
    periodicity_days: int
    status: str
    tontine_type: str
    amount_per_member: float
    current_round: int | None = None
    next_rotation_at: datetime | None = None
    common_pot: float | None = None
    members: list[TontineMemberDetail] = Field(default_factory=list)

    class Config:
        from_attributes = True
