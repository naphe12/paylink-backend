from app.models.users import Users
async def apply_kyc_limits(user: Users):
    if user.kyc_tier == 0:
        user.daily_limit = 30000
        user.monthly_limit = 30000
    elif user.kyc_tier == 1:
        user.daily_limit = 1_000_000
        user.monthly_limit = 5_000_000
    elif user.kyc_tier == 2:
        user.daily_limit = 10_000_000
        user.monthly_limit = 30_000_000
    elif user.kyc_tier == 3:
        user.daily_limit = 999_999_999
        user.monthly_limit = 999_999_999
