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
    Response,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies.auth import get_current_user, get_current_user_db,get_optional_current_user
from app.models.user_auth import UserAuth
from app.models.users import Users
from app.schemas.users import UsersCreate, UsersRead
from app.dependencies.step_up import (
    bind_admin_step_up_token_to_request,
    create_admin_step_up_token,
    is_admin_step_up_header_fallback_enabled,
    register_admin_step_up_token,
)
from app.services.audit_service import audit_log
from app.services.auth_sessions import get_request_ip, get_request_user_agent
from app.services.mailer import send_email
from app.services.mailjet_service import MailjetEmailService
from app.services.auth_sessions import issue_refresh_session, revoke_refresh_session, rotate_refresh_session
from app.services.user_provisioning import create_client_user

router = APIRouter()

# OAuth2 helper to pull token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _build_auth_response(user: Users, access_token: str, csrf_token: str | None = None) -> dict:
    payload = {
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
    if csrf_token:
        payload["csrf_token"] = csrf_token
    return payload

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UsersCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await create_client_user(db, payload=user_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(user)

    expires = timedelta(hours=24)
    verify_token = create_access_token(
        data={"sub": str(user.user_id), "action": "verify_email"},
        expires_delta=expires,
    )
    verify_link = f"{settings.FRONTEND_URL}/auth/verify-email?token={verify_token}"
    subject = "Confirmez votre adresse email PesaPaid"
    verification_body = f"""
    Bonjour {user.full_name},

    Merci de vous être inscrit sur paylink. Cliquez sur le lien ci-dessous pour vérifier votre adresse email :
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

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes_for_role(user.role))
    access_token = create_access_token(
        data={"sub": str(user.user_id), "role": user.role}, expires_delta=access_token_expires, role=user.role
    )
    csrf_token = await issue_refresh_session(db, response, user, request)
    await db.commit()

    payload = _build_auth_response(user, access_token, csrf_token)
    payload["user"] = UsersRead.model_validate(user, from_attributes=True)
    return payload


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
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    raw_username = form_data.username.strip()
    normalized = raw_username.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    try:
        user = await db.scalar(
            select(Users).where(
                or_(
                    func.lower(Users.email) == normalized,
                    func.lower(Users.paytag) == paytag,
                    func.lower(Users.username) == normalized,
                    Users.phone_e164 == raw_username,
                )
            )
        )
        if not user:
            raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

        auth_data = await db.scalar(select(UserAuth).where(UserAuth.user_id == user.user_id))
        if not auth_data or not verify_password(form_data.password, auth_data.password_hash):
            raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

        auth_data.last_login_at = datetime.utcnow()
        await db.commit()

        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes_for_role(user.role))
        access_token = create_access_token(
            data={"sub": str(user.user_id), "role": user.role},
            expires_delta=access_token_expires,
            role=user.role,
        )
        csrf_token = await issue_refresh_session(db, response, user, request)
        await db.commit()
        return _build_auth_response(user, access_token, csrf_token)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Service temporairement indisponible. Reessayez dans quelques instants.",
        ) from exc


@router.post("/refresh")
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    session_data = await rotate_refresh_session(db, request, response)
    user: Users = session_data["user"]
    access_token = create_access_token(
        data={"sub": str(user.user_id), "role": user.role},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes_for_role(user.role)),
        role=user.role,
    )
    await db.commit()
    return _build_auth_response(user, access_token, session_data["csrf_token"])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await revoke_refresh_session(db, request, response, require_csrf=True)
    await db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UsersRead)
async def read_current_user(current_user: Users = Depends(get_current_user_db)):
    # Retourne l'objet complet pour exposer les champs (paytag, limites, risque, etc.)
    return current_user


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class AdminStepUpRequest(BaseModel):
    password: str
    action: str | None = None


@router.post("/admin-step-up")
async def issue_admin_step_up(
    data: AdminStepUpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user_db),
):
    if str(getattr(current_user, "role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Acces reserve aux admin")

    auth_data = await db.scalar(select(UserAuth).where(UserAuth.user_id == current_user.user_id))
    if not auth_data or not verify_password(data.password, auth_data.password_hash or ""):
        raise HTTPException(status_code=401, detail="Mot de passe admin incorrect")

    token = create_admin_step_up_token(user=current_user, action=data.action)
    await register_admin_step_up_token(token=token, user=current_user, action=data.action)
    await bind_admin_step_up_token_to_request(token=token, request=request)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if hasattr(db, "execute"):
        try:
            await audit_log(
                db,
                actor_user_id=str(current_user.user_id),
                actor_role=str(current_user.role),
                action="ADMIN_STEP_UP_ISSUED",
                entity_type="ADMIN_STEP_UP",
                entity_id=None,
                before_state=None,
                after_state={
                    "requested_action": data.action or "*",
                    "expires_in_seconds": int(max(int(settings.ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES or 5), 1) * 60),
                    "session_bound": bool(request.headers.get("authorization")),
                    "request_id": request_id,
                },
                ip=get_request_ip(request),
                user_agent=get_request_user_agent(request),
            )
            if hasattr(db, "commit"):
                await db.commit()
        except Exception:
            pass
    return {
        "token": token,
        "token_type": "admin_step_up",
        "expires_in_seconds": int(max(int(settings.ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES or 5), 1) * 60),
        "header_name": str(settings.ADMIN_STEP_UP_TOKEN_HEADER_NAME or "X-Admin-Step-Up-Token"),
        "action": data.action or "*",
    }


@router.get("/admin-step-up/status")
async def get_admin_step_up_status(
    current_user: Users = Depends(get_current_user_db),
):
    if str(getattr(current_user, "role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Acces reserve aux admin")

    return {
        "enabled": bool(settings.ADMIN_STEP_UP_ENABLED),
        "header_name": str(settings.ADMIN_STEP_UP_HEADER_NAME or "X-Admin-Confirm"),
        "header_fallback_enabled": is_admin_step_up_header_fallback_enabled(),
        "token_header_name": str(settings.ADMIN_STEP_UP_TOKEN_HEADER_NAME or "X-Admin-Step-Up-Token"),
        "token_expires_in_seconds": int(max(int(settings.ADMIN_STEP_UP_TOKEN_EXPIRE_MINUTES or 5), 1) * 60),
    }


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
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
    subject = "Reinitialisation de votre mot de passe PesaPaid"
    plain_text = (
        f"Bonjour {user.full_name or ''},\n\n"
        "Pour reinitialiser votre mot de passe, cliquez sur le lien suivant :\n"
        f"{reset_link}\n\n"
        "Ce lien est valable pendant 1 heure."
    )

    try:
        mailer = MailjetEmailService()
        await run_in_threadpool(
            mailer.send_email,
            user.email,
            subject,
            "forgot_password.html",
            user_name=user.full_name or "Client",
            reset_link=reset_link,
            expiry_hours=1,
            year=datetime.utcnow().year,
            text=plain_text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Echec envoi email de reinitialisation: {exc}",
        ) from exc
    return {"message": "Un email de reinitialisation a ete envoye."}

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



