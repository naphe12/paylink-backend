from typing import Literal

from pydantic import BaseModel, Field


AgentOnboardingStatus = Literal["NEED_INFO", "INFO", "ERROR", "CANCELLED"]
AgentOnboardingIntent = Literal[
    "cash_in",
    "cash_out",
    "scan_client",
    "external_transfer",
    "client_checks",
    "common_errors",
    "unknown",
]
AgentOnboardingScenario = Literal[
    "new_client",
    "missing_kyc",
    "blocked_cash_out",
    "none",
]


class AgentOnboardingChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class AgentOnboardingDraft(BaseModel):
    intent: AgentOnboardingIntent = "unknown"
    scenario: AgentOnboardingScenario = "none"
    raw_message: str


class AgentOnboardingChatResponse(BaseModel):
    status: AgentOnboardingStatus
    message: str
    data: AgentOnboardingDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    executable: bool = False
    suggestions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: dict | None = None
