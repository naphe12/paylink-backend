from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user_db
from app.models.users import Users
from app.schemas.savings import (
    SavingsAutoContributionRuleUpdate,
    SavingsAutoContributionRunCreate,
    SavingsGoalCreate,
    SavingsGoalMovementCreate,
    SavingsGoalRead,
    SavingsRoundUpApplyCreate,
    SavingsRoundUpRuleUpdate,
)
from app.services.savings_service import (
    apply_savings_round_up,
    configure_savings_auto_contribution,
    configure_savings_round_up,
    contribute_savings_goal,
    create_savings_goal,
    get_savings_goal_detail,
    list_savings_goals,
    run_due_savings_auto_contributions,
    run_savings_auto_contribution,
    withdraw_savings_goal,
)

router = APIRouter(tags=["Savings"])


@router.get("/savings/goals", response_model=list[SavingsGoalRead])
async def list_savings_goals_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await list_savings_goals(db, current_user=current_user)


@router.post("/savings/goals", response_model=SavingsGoalRead)
async def create_savings_goal_route(
    payload: SavingsGoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await create_savings_goal(db, current_user=current_user, payload=payload)


@router.post("/savings/goals/auto-contribution/run-due", response_model=list[SavingsGoalRead])
async def run_due_savings_auto_contributions_route(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await run_due_savings_auto_contributions(db, current_user=current_user)


@router.get("/savings/goals/{goal_id}", response_model=SavingsGoalRead)
async def get_savings_goal_detail_route(
    goal_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


@router.post("/savings/goals/{goal_id}/contribute", response_model=SavingsGoalRead)
async def contribute_savings_goal_route(
    goal_id: UUID,
    payload: SavingsGoalMovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await contribute_savings_goal(db, current_user=current_user, goal_id=goal_id, payload=payload)


@router.post("/savings/goals/{goal_id}/withdraw", response_model=SavingsGoalRead)
async def withdraw_savings_goal_route(
    goal_id: UUID,
    payload: SavingsGoalMovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await withdraw_savings_goal(db, current_user=current_user, goal_id=goal_id, payload=payload)


@router.put("/savings/goals/{goal_id}/round-up", response_model=SavingsGoalRead)
async def configure_savings_round_up_route(
    goal_id: UUID,
    payload: SavingsRoundUpRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await configure_savings_round_up(db, current_user=current_user, goal_id=goal_id, payload=payload)


@router.put("/savings/goals/{goal_id}/auto-contribution", response_model=SavingsGoalRead)
async def configure_savings_auto_contribution_route(
    goal_id: UUID,
    payload: SavingsAutoContributionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await configure_savings_auto_contribution(db, current_user=current_user, goal_id=goal_id, payload=payload)


@router.post("/savings/goals/{goal_id}/auto-contribution/run", response_model=SavingsGoalRead)
async def run_savings_auto_contribution_route(
    goal_id: UUID,
    payload: SavingsAutoContributionRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await run_savings_auto_contribution(db, current_user=current_user, goal_id=goal_id, payload=payload)


@router.post("/savings/goals/{goal_id}/round-up/apply", response_model=SavingsGoalRead)
async def apply_savings_round_up_route(
    goal_id: UUID,
    payload: SavingsRoundUpApplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    return await apply_savings_round_up(db, current_user=current_user, goal_id=goal_id, payload=payload)
