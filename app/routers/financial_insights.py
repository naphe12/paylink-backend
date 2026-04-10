from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.financial_insights import FinancialBudgetRuleUpsert, FinancialInsightsRead
from app.services.financial_insights_service import (
    delete_financial_budget_rule,
    get_financial_insights,
    upsert_financial_budget_rule,
)

router = APIRouter(tags=["Financial Insights"])


@router.get("/financial-insights/me", response_model=FinancialInsightsRead)
async def get_my_financial_insights_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_financial_insights(db, current_user=current_user)


@router.put("/financial-insights/budget-rules", response_model=FinancialInsightsRead)
async def upsert_my_financial_budget_rule_route(
    payload: FinancialBudgetRuleUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await upsert_financial_budget_rule(db, current_user=current_user, payload=payload)


@router.delete("/financial-insights/budget-rules/{category}", response_model=FinancialInsightsRead)
async def delete_my_financial_budget_rule_route(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await delete_financial_budget_rule(db, current_user=current_user, category=category)
