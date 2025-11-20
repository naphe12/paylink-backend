
# Auto-generated from SQLAlchemy model with relationships and imports
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.provideraccounts import ProviderAccountsRead
    from app.schemas.reconlines import ReconLinesRead


class ReconFilesBase(BaseModel):
    recon_id: str
    provider_account_id: str
    period_start: datetime
    period_end: datetime
    file_url: str
    created_at: datetime
    parsed_at: Optional[datetime]

class ReconFilesCreate(ReconFilesBase):
    recon_id: str
    provider_account_id: str
    period_start: datetime
    period_end: datetime
    file_url: str
    parsed_at: Optional[datetime]

class ReconFilesUpdate(BaseModel):
    recon_id: Optional[str]
    provider_account_id: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    file_url: Optional[str]
    created_at: Optional[datetime]
    parsed_at: Optional[Optional[datetime]]

class ReconFilesRead(ReconFilesBase):
    recon_id: str
    provider_account_id: str
    period_start: datetime
    period_end: datetime
    file_url: str
    created_at: datetime
    parsed_at: Optional[datetime]
    provider_account: Optional["ProviderAccountsRead"] = None
    recon_lines: list["ReconLinesRead"] = None
    class Config:
        from_attributes = True
