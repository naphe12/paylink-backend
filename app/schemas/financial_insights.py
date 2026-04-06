from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class FinancialBudgetRuleUpsert(BaseModel):
    category: str
    limit_amount: Decimal = Field(gt=0)


class FinancialBudgetRuleRead(BaseModel):
    category: str
    limit_amount: Decimal
    spent_amount: Decimal = Decimal("0")
    remaining_amount: Decimal = Decimal("0")
    progress_percent: float = 0
    is_over_limit: bool = False


class FinancialCategoryInsightRead(BaseModel):
    category: str
    amount: Decimal
    share_percent: float
    budget_limit: Decimal | None = None
    remaining_budget: Decimal | None = None
    is_over_limit: bool = False


class FinancialInsightsRead(BaseModel):
    currency_code: str
    month_inflows: Decimal
    month_outflows: Decimal
    month_net: Decimal
    suggested_budget: Decimal
    active_budget: Decimal
    budget_source: str
    remaining_to_spend: Decimal
    current_savings: Decimal
    budget_usage_percent: float = 0
    over_limit_count: int = 0
    alert_level: str = "healthy"
    alert_message: str = ""
    top_spending_categories: list[FinancialCategoryInsightRead] = Field(default_factory=list)
    budget_rules: list[FinancialBudgetRuleRead] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
