# app/schemas/users.py
from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from pydantic import UUID4, BaseModel, EmailStr
from app.schemas.user_auth import UserAuthRead
from pydantic import BaseModel
from datetime import datetime

# ✅ Ces imports sont visibles uniquement pour l’éditeur (VSCode, Pylance)
if TYPE_CHECKING:
    from app.schemas.agents import AgentsRead
    from app.schemas.amlevents import AmlEventsRead
    from app.schemas.countries import CountriesRead
    from app.schemas.disputes import DisputesRead
    from app.schemas.invoices import InvoicesRead
    from app.schemas.kycdocuments import KycDocumentsRead
    from app.schemas.limitusage import LimitUsageRead
    from app.schemas.loans import LoansRead
    from app.schemas.merchants import MerchantsRead
    from app.schemas.notifications import NotificationsRead
    from app.schemas.sanctionsscreening import SanctionsScreeningRead
    from app.schemas.tontinecontributions import TontineContributionsRead
    from app.schemas.tontinemembers import TontineMembersRead
    from app.schemas.tontinepayouts import TontinePayoutsRead
    from app.schemas.tontines import TontinesRead
    from app.schemas.transactions import TransactionsRead
    from app.schemas.userdevices import UserDevicesRead
    from app.schemas.wallets import WalletsRead


class UsersBase(BaseModel):
    user_id: str
    status: str
    full_name: str
    kyc_status: str
    created_at: datetime
    updated_at: datetime
    email: Optional[str] = None
    phone_e164: Optional[str] = None
    country_code: Optional[str] = None
    referred_by: Optional[str] = None
    email_verified: Optional[bool] = False
    email_verified_at: Optional[datetime] = None


class UsersCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone_e164: Optional[str] = None
    country_code: Optional[str] = None


class UsersUpdate(BaseModel):
    status: Optional[str] = None
    full_name: Optional[str] = None
    kyc_status: Optional[str] = None
    email: Optional[str] = None
    phone_e164: Optional[str] = None
    country_code: Optional[str] = None
    referred_by: Optional[str] = None

class UserTokenData(BaseModel):
    """
    Contient les infos extraites du JWT — sans accès à la DB.
    Utilisé pour get_current_user_token().
    """
    user_id: UUID4
    email: str
    role: Optional[str] = None

    class Config:
        from_attributes = True


class UsersRead_all(UsersBase):
    countries: Optional["CountriesRead"] = None
    agents: Optional["AgentsRead"] = None
    kyc_documents: Optional[List["KycDocumentsRead"]] = None
    limit_usage: Optional[List["LimitUsageRead"]] = None
    loans: Optional[List["LoansRead"]] = None
    notifications: Optional[List["NotificationsRead"]] = None
    sanctions_screening: Optional[List["SanctionsScreeningRead"]] = None
    tontines: Optional[List["TontinesRead"]] = None
    user_devices: Optional[List["UserDevicesRead"]] = None
    wallets: Optional[List["WalletsRead"]] = None
    merchants: Optional["MerchantsRead"] = None
    tontine_members: Optional[List["TontineMembersRead"]] = None
    transactions: Optional[List["TransactionsRead"]] = None
    aml_events: Optional[List["AmlEventsRead"]] = None
    disputes: Optional[List["DisputesRead"]] = None
    invoices: Optional[List["InvoicesRead"]] = None
    tontine_contributions: Optional[List["TontineContributionsRead"]] = None
    tontine_payouts: Optional[List["TontinePayoutsRead"]] = None
    auth: Optional["UserAuthRead"] = None  # ✅ ajoute cette ligne
    class Config:
        from_attributes = True



class UsersRead(BaseModel):
    user_id: UUID4
    full_name: str
    email: str | None = None
    phone_e164: str | None = None
    country_code: str | None = None
    status: str
    kyc_status: str | None = None
    role: str
    created_at: datetime | None = None
    email_verified: bool | None = None
    email_verified_at: datetime | None = None

    model_config = {"from_attributes": True}
