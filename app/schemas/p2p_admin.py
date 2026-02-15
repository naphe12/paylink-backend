from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class DisputeResolveIn(BaseModel):
    resolution: str
    release_to: str  # "BUYER" | "SELLER"
    note: Optional[str] = None
