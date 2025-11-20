from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from app.core.database import get_db
from app.models.users import Users
from app.core.security import get_current_user
from app.services.storage import upload_to_storage

router = APIRouter(prefix="/kyc", tags=["KYC"])

@router.post("/submit")
async def submit_kyc(
    legal_name: str = Form(...),
    birth_date: date = Form(...),
    national_id_number: str = Form(...),
    kyc_document_type: str = Form(...),
    document_front: UploadFile = File(...),
    document_back: UploadFile | None = File(None),
    selfie: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    front_url = await upload_to_storage(document_front)
    back_url = await upload_to_storage(document_back)
    selfie_url = await upload_to_storage(selfie)

    current_user.legal_name = legal_name
    current_user.birth_date = birth_date
    current_user.national_id_number = national_id_number
    current_user.kyc_document_type = kyc_document_type
    current_user.kyc_document_front_url = front_url
    current_user.kyc_document_back_url = back_url
    current_user.selfie_url = selfie_url
    current_user.kyc_status = "pending"

    await db.commit()

    return {"message": "✅ KYC soumis. Vérification en cours."}
