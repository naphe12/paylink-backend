import decimal
from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
    Body,
    Form,
    Request,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies.auth import get_current_user, get_current_user_db
from app.models.user_auth import UserAuth
from app.models.users import Users
from app.models.wallets import Wallets
from app.schemas.users import UsersCreate, UsersRead
from app.services.mailer import send_email

router = APIRouter()

# OAuth2 helper to pull token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UsersCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    existing_user = await db.scalar(select(Users).where(Users.email == user_in.email))
    if existing_user:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")

    paytag = None
    if user_in.full_name:
        paytag = "@" + user_in.full_name.strip().lower().replace(" ", "_")

    user = Users(
        full_name=user_in.full_name,
        email=user_in.email,
        phone_e164=user_in.phone_e164,
        country_code=user_in.country_code,
        status="active",
        kyc_status="unverified",
        role="client",
        paytag=paytag,
    )
    db.add(user)
    await db.flush()

    auth_entry = UserAuth(
        user_id=user.user_id,
        password_hash=hash_password(user_in.password),
        mfa_enabled=False,
    )
    db.add(auth_entry)

    new_wallet = Wallets(
        user_id=user.user_id,
        type="consumer",
        currency_code="EUR",
        available=decimal.Decimal("0.00"),
        pending=decimal.Decimal("0.00"),
    )
    db.add(new_wallet)

    await db.commit()
    await db.refresh(user)

    expires = timedelta(hours=24)
    verify_token = create_access_token(
        data={"sub": str(user.user_id), "action": "verify_email"},
        expires_delta=expires,
    )
    verify_link = f"{settings.FRONTEND_URL}/auth/verify-email?token={verify_token}"
    subject = "Confirmez votre adresse email PayLink"
    verification_body = f"""
    Bonjour {user.full_name},

    Merci de vous être inscrit sur PayLink. Cliquez sur le lien ci-dessous pour vérifier votre adresse email :
    <a href="{verify_link}">Vérifier mon adresse</a>

    Ce lien est valide 24 heures.
    """
    background_tasks.add_task(
        send_email,
        user.email,
        subject,
        None,
        body_html=verification_body,
    )

    access_token_expires = timedelta(hours=24)
    access_token = create_access_token(
        data={"sub": str(user.user_id)}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UsersRead.model_validate(user, from_attributes=True),
    }


@router.get("/verify-email")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    if payload.get("action") != "verify_email":
        raise HTTPException(status_code=400, detail="Token invalide pour cette action")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Token invalide")

    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    await db.commit()

    return {"message": "Email vérifié avec succès"}


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(Users).where(Users.email == form_data.username))
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    auth_data = await db.scalar(select(UserAuth).where(UserAuth.user_id == user.user_id))
    if not auth_data or not verify_password(form_data.password, auth_data.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    auth_data.last_login_at = datetime.utcnow()
    await db.commit()

    access_token_expires = timedelta(hours=24)
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "user": {
            "user_id": str(user.user_id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
        },
    }


@router.get("/me", response_model=UsersRead)
async def read_current_user(current_user: Users = Depends(get_current_user)):
    return current_user


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(Users).where(Users.email == body.email))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    expires = timedelta(hours=1)
    reset_token = create_access_token(
        data={"sub": str(user.user_id), "action": "reset_password"},
        expires_delta=expires,
    )

    reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?token={reset_token}"
    subject = "Réinitialisation de votre mot de passe PayLink"
    body_text = f"""
    Bonjour {user.full_name or ''},

    Pour réinitialiser votre mot de passe, cliquez sur le lien suivant :
    {reset_link}

    Ce lien est valable pendant 1 heure.
    """

    background_tasks.add_task(send_email, to=user.email, subject=subject, body=body_text)
    return {"message": "Un email de réinitialisation a été envoyé."}


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/reset-password")
async def reset_password(
    request: Request,
    data: ResetPasswordRequest | None = Body(None),
    token_form: str | None = Form(None),
    password_form: str | None = Form(None),
    token_query: str | None = Query(None),
    password_query: str | None = Query(None),
    current_user_opt: Users | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = (data.token if data and data.token else None) or token_form or token_query
    new_password = (data.password if data and data.password else None) or password_form or password_query

    # Fallback: essayer de parser le JSON brut si toujours vide
    if request and (not token or not new_password):
        try:
            body_json = await request.json()
            token = token or body_json.get("token")
            new_password = new_password or body_json.get("password")
        except Exception:
            pass

    if not token or not new_password:
        # Fallback : si utilisateur authentifié, on autorise le reset direct
        if current_user_opt:
            auth_entry = await db.scalar(select(UserAuth).where(UserAuth.user_id == current_user_opt.user_id))
            if not auth_entry:
                raise HTTPException(status_code=404, detail="Utilisateur introuvable")
            auth_entry.password_hash = hash_password(new_password)
            await db.commit()
            return {"message": "Mot de passe mis à jour"}
        raise HTTPException(status_code=400, detail="Token et mot de passe requis")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("action") != "reset_password":
            raise HTTPException(status_code=403, detail="Token invalide pour cette action")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="Token invalide")

    except JWTError:
        raise HTTPException(status_code=401, detail="Token expiré ou invalide")

    auth_entry = await db.scalar(select(UserAuth).where(UserAuth.user_id == user_id))
    if not auth_entry:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    auth_entry.password_hash = hash_password(new_password)
    await db.commit()

    return {"message": "Mot de passe réinitialisé avec succès"}
# Optional auth helper for reset-password fallback
async def get_optional_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Users | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    return user
