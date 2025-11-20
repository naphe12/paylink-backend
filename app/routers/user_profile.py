from fastapi import APIRouter, Depends
from app.core.database import get_db
from app.models.users import Users
from app.dependencies.auth import get_current_user
from app.services.qr import sign_uid

router = APIRouter(prefix="/me", tags=["Profile"])

@router.get("/qr")
async def generate_qr(current_user: Users = Depends(get_current_user)):
    payload = {
        "uid": str(current_user.user_id),
        "phone": current_user.phone_e164,
        "sig": sign_uid(str(current_user.user_id))
    }
    return payload
