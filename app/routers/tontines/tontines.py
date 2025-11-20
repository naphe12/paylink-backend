from datetime import datetime, timedelta, timezone

# app/routers/tontines_debts.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select, cast
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tontinecontributions import ContributionStatus
from app.auth.roles import require_admin_or_creator
from app.core.database import get_db
from app.schemas.users import UserTokenData
from app.dependencies.auth import get_current_user
from app.models.tontine_invitations import TontineInvitations
from app.models.tontinecontributions import TontineContributions
from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.schemas.tontines import TontineListRead, TontineOut, TontineDetailResponse
from app.websocket_manager import ws_push_room
from app.services.wallet_history import log_wallet_movement
from sqlalchemy.orm import joinedload
from uuid import uuid4

from sqlalchemy.orm import selectinload
router = APIRouter()





@router.get("/", response_model=list[TontineOut])
async def list_tontines(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    q = (
        select(Tontines)
        .where(Tontines.owner_user == current_user.user_id)
        .options(
            selectinload(Tontines.tontine_members)
            .selectinload(TontineMembers.user)
        )
    )

    res = await db.scalars(q)
    return res.all()




@router.post("/{tontine_id}/invitation")
async def generate_invite(tontine_id: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    code = str(uuid4())[:8]
    inv = TontineInvitations(
        tontine_id=tontine_id,
        created_by=current_user.user_id,
        invite_code=code
    )
    db.add(inv)
    await db.commit()
    return {"invite_url": f"https://paylink.app/join-tontine/{code}"}


# POST /tontines/join/{invite_code}

@router.post("/join/{invite_code}")
async def join_tontine(invite_code: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    inv = await db.scalar(select(TontineInvitations).where(TontineInvitations.invite_code == invite_code))

    if inv is None:
        raise HTTPException(404, "Lien invalide")

    new_member = TontineMembers(tontine_id=inv.tontine_id, user_id=current_user.user_id)
    db.add(new_member)
    await db.commit()
    return {"message": "✅ Vous avez rejoint la tontine"}

from uuid import UUID

@router.get("/{tontine_id}/common-pot")
async def get_common_pot(tontine_id: UUID,    db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tontines.common_pot).where(Tontines.tontine_id == tontine_id)
    )
    common_pot = result.scalar_one_or_none()

    return {"common_pot": float(common_pot or 0)}


@router.post("/{tontine_id}/withdraw")
async def withdraw_from_pot(
    tontine_id: str,
    amount: float,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    # Seul le créateur ou l'admin peut retirer
    if current_user.user_id != tontine.owner_user and current_user.role != "admin":
        raise HTTPException(403, "Non autorisé")

    if tontine.common_pot < amount:
        raise HTTPException(400, "Montant supérieur au pot")

    tontine.common_pot -= amount
    await db.commit()

    return {"message": "✅ Retrait effectué", "new_common_pot": float(tontine.common_pot)}




@router.post("/{tontine_id}/contribute")
async def contribute(
    tontine_id: str,
    amount: float,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    # 1) Vérifier solde wallet du contributeur
    wallet = await db.scalar(
        select(Wallets).where(Wallets.user_id == current_user.user_id)
    )
    if wallet is None:
        raise HTTPException(404, "Wallet introuvable")

    if wallet.available < amount:
        raise HTTPException(400, "Solde insuffisant ❌")

    # 2) Déduire montant
    wallet.available -= amount
    await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="tontine_contribution",
        reference=tontine_id,
        description=f"Contribution tontine {tontine_id}",
    )

    # 3) Enregistrer contribution
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        amount=amount
    )
    db.add(contrib)

    # 4) Charger tontine + membres
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if tontine is None:
        raise HTTPException(404, "Tontine introuvable")

    members = await db.scalars(
        select(TontineMembers).where(TontineMembers.tontine_id == tontine_id)
    )
    members = list(members)

    # 5) Vérifier paiement complet (Tontine Rotative)
    if tontine.tontine_type == "rotative":
        total_contributions = await db.scalar(
            select(func.sum(TontineContributions.amount))
            .where(TontineContributions.tontine_id == tontine_id)
            .where(TontineContributions.paid_at > tontine.last_rotation_at)
        ) or 0

        expected = tontine.amount_per_member * len(members)

        # ✅ Lorsque tout le monde a payé → on verse au gagnant
        if total_contributions >= expected:
            winner = members[tontine.current_round]

            winner_wallet = await db.scalar(
                select(Wallets).where(Wallets.user_id == winner.user_id)
            )
            winner_wallet.available += expected
            await log_wallet_movement(
                db,
                wallet=winner_wallet,
                user_id=winner.user_id,
                amount=expected,
                direction="credit",
                operation_type="tontine_payout",
                reference=tontine_id,
                description=f"Payout rotation tontine {tontine_id}",
            )

            # On passe au prochain membre
            tontine.current_round = (tontine.current_round + 1) % len(members)
            tontine.last_rotation_at = datetime.utcnow()

    # 6) Gestion du Pot Commun (Tontine Épargne)
    if tontine.tontine_type == "epargne":
        tontine.common_pot = (tontine.common_pot or 0) + amount

    await db.commit()

    # ✅ 7) Annoncer l’événement aux membres (websocket room = tontine_id)
    await ws_push_room(str(tontine_id), {
        "type": "contribution_update",
        "data": {
            "tontine_id": tontine_id,
            "user_id": str(current_user.user_id),
            "amount": float(amount),
            "tontine_type": tontine.tontine_type
        }
    })

    return {"message": "✅ Contribution enregistrée avec succès"}







@router.post("/{tontine_id}/contribute/wallet")
async def contribute_wallet(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if wallet.balance < tontine.amount_per_member:
        raise HTTPException(400, "Solde insuffisant 💸")

    # Débit wallet
    wallet.balance -= tontine.amount_per_member

    # Create a transaction
    tx = Transactions(
        user_id=current_user.user_id,
        amount=tontine.amount_per_member,
        currency_code=tontine.currency_code,
        status="success",
        channel="wallet",
        description=f"Contribution tontine {tontine.name}"
    )
    db.add(tx)
    await db.flush()  # récupère tx_id

    # Enregistrer contribution
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        tx_id=tx.tx_id,
        amount=tontine.amount_per_member,
        status=ContributionStatus.paid
    )
    db.add(contrib)

    await db.commit()
    return {"message": "Contribution effectuée ✅"}

    

@router.post("/{tontine_id}/contribute/promise")
async def contribute_promise(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        amount=0,  # pas encore payé
        status=ContributionStatus.promised
    )
    db.add(contrib)
    await db.commit()
    return {"message": "Contribution marquée comme promesse 📝"}

    

@router.post("/{tontine_id}/contribute/mobilemoney")
async def contribute_mobilemoney(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    # Appel interne à ton API Lumicash
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.post("http://localhost:8000/payments/lumicash/send", json={
            "phone": current_user.phone,
            "amount": tontine.amount_per_member
        })

    # On enregistre une contribution en attente
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        amount=tontine.amount_per_member,
        status=ContributionStatus.pending
    )
    db.add(contrib)
    await db.commit()

    return {"message": "Paiement Mobile Money en cours ⏳"}

# app/routers/tontines.py (extrait contribute_mobilemoney)
@router.post("/{tontine_id}/contribute/mobilemoney2")
async def contribute_mobilemoney(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.post("http://127.0.0.1:8000/payments/lumicash/send", json={
            "phone": current_user.phone_e164,
            "amount": str(tontine.amount_per_member),  # en string selon prestataire
        })
    data = r.json()
    external_ref = data.get("external_ref")  # <- important (ex: TX12345)

    # Créer la transaction en attente
    tx = Transactions(
        initiated_by=current_user.user_id,
        amount=tontine.amount_per_member,
        currency_code=tontine.currency_code,
        channel="mobile_money",
        status="pending",
        external_ref=external_ref,
        description=f"Contribution MM {tontine.name}"
    )
    db.add(tx)
    await db.flush()  # tx_id

    # Enregistrer contribution en attente (liée à tx)
    contrib = TontineContributions(
        tontine_id=tontine_id,
        user_id=current_user.user_id,
        tx_id=tx.tx_id,
        amount=tontine.amount_per_member,
        status=ContributionStatus.pending
    )
    db.add(contrib)
    await db.commit()

    return {"message": "Paiement en cours ⏳", "external_ref": external_ref}



@router.get("/{tontine_id}/debts")
async def tontine_debts(tontine_id: str, db: AsyncSession = Depends(get_db)):
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    # Déterminer la période du cycle courant
    now = datetime.now(timezone.utc)
    if tontine.tontine_type == "rotative":
        # Suppose qu’on a next_rotation_at en DB; sinon choisis frequency_days
        start = (tontine.next_rotation_at - timedelta(days=tontine.periodicity_days)) if tontine.next_rotation_at else now - timedelta(days=30)
        end = tontine.next_rotation_at or now
    else:
        # Epargne: mois courant
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now

    # Membres
    members = await db.execute(select(TontineMembers.user_id, TontineMembers.user_name).where(TontineMembers.tontine_id == tontine_id))
    members = members.fetchall()

    # Sommes payées par membre dans la période pour cette tontine (status paid)
    paid_rows = await db.execute(
        select(
            TontineContributions.user_id,
            func.coalesce(func.sum(TontineContributions.amount), 0).label("paid")
        )
        .where(
            and_(
                TontineContributions.tontine_id == tontine_id,
                TontineContributions.status == 'paid',
                TontineContributions.paid_at >= start,
                TontineContributions.paid_at < end
            )
        )
        .group_by(TontineContributions.user_id)
    )
    paid_map = {str(r.user_id): float(r.paid) for r in paid_rows.fetchall()}

    expected = float(tontine.amount_per_member)

    result = []
    for user_id, user_name in members:
        uid = str(user_id)
        paid = paid_map.get(uid, 0.0)
        due = max(0.0, expected - paid)
        result.append({
            "user_id": uid,
            "user_name": user_name,
            "expected": expected,
            "paid": paid,
            "due": round(due, 2)
        })

    return {
        "tontine_id": tontine_id,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "currency_code": tontine.currency_code,
        "rows": result
    }



@router.post("/{tontine_id}/rotation/next")
async def next_rotation(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)  # Step 1
):
    # Charger la tontine
    tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    # Appliquer la règle d’accès (step 2)
    await require_admin_or_creator(tontine.owner_user, current_user)

    # Vérifier si tous ont contribué
    total_members = len(tontine.members)
    contributions = await db.scalar(
        select(func.count(TontineContributions.contribution_id))
        .where(TontineContributions.tontine_id == tontine_id)
        .where(TontineContributions.paid_at > tontine.last_rotation_at)
    )

    expected = total_members  # 1 contribution par membre

    if contributions < expected:
        raise HTTPException(400, "Tous les membres n'ont pas encore contribué ⛔")

    # Passer au suivant
    tontine.current_round = (tontine.current_round + 1) % total_members
    tontine.last_rotation_at = datetime.utcnow()

    await db.commit()
    return {"message": "✅ Rotation effectuée avec succès"}


# @router.get("/{tontine_id}/debts")
# async def get_tontine_debts(tontine_id: str, db: AsyncSession = Depends(get_db), current_user: Users = Depends(get_current_user)):

#     # 1) Charger la tontine
#     tontine = await db.scalar(select(Tontines).where(Tontines.tontine_id == tontine_id))
#     if not tontine:
#         raise HTTPException(404, "Tontine introuvable")

#     amount = tontine.amount_per_member

#     # 2) Charger les membres
#     members = await db.execute(
#         select(Users.user_id, Users.name)
#         .join(TontineMembers, TontineMembers.user_id == Users.user_id)
#         .where(TontineMembers.tontine_id == tontine_id)
#     )
#     members = members.fetchall()

#     # 3) Charger les contributions déjà payées
#     paid = await db.execute(
#         select(
#             TontineContributions.user_id,
#             func.sum(TontineContributions.amount)
#         )
#         .where(TontineContributions.tontine_id == tontine_id)
#         .group_by(TontineContributions.user_id)
#     )
#     paid = {row[0]: float(row[1]) for row in paid.fetchall()}

#     rows = []
#     for m in members:
#         expected = float(amount)
#         paid_amount = paid.get(m.user_id, 0)
#         due = expected - paid_amount

#         rows.append({
#             "user_id": str(m.user_id),
#             "user_name": m.name,
#             "expected": expected,
#             "paid": paid_amount,
#             "due": due,
#         })

#     return {
#         "period_start": tontine.period_start,
#         "period_end": tontine.period_end,
#         "rows": rows
#     }

@router.get("/{tontine_id}", response_model=TontineDetailResponse)
async def get_tontine_detail(
    tontine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserTokenData = Depends(get_current_user)
):
    q = (
        select(Tontines)
        .where(Tontines.tontine_id == tontine_id)
        .options(
            selectinload(Tontines.tontine_members)
            .selectinload(TontineMembers.user)
        )
    )
    tontine = await db.scalar(q)

    if not tontine:
        raise HTTPException(404, "Tontine introuvable")

    members = []
    for member in tontine.tontine_members:
        user = member.user
        members.append({
            "user_id": member.user_id,
            "name": member.user_name or (user.full_name if user else None),
            "phone": user.phone_e164 if user else None,
            "is_online": getattr(member, "is_online", False)
        })

    return {
        "tontine_id": tontine.tontine_id,
        "owner_user": tontine.owner_user,
        "name": tontine.name,
        "currency_code": tontine.currency_code,
        "periodicity_days": tontine.periodicity_days,
        "status": tontine.status,
        "tontine_type": tontine.tontine_type,
        "amount_per_member": float(tontine.amount_per_member),
        "current_round": tontine.current_round,
        "next_rotation_at": tontine.next_rotation_at,
        "common_pot": float(tontine.common_pot) if tontine.common_pot is not None else None,
        "members": members
    }




@router.get("/{tontine_id}/contributions")
async def get_contributions(
    tontine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),  # ✅ Ajout essentiel
):
    q = (
        select(
            TontineContributions.contribution_id,
            Users.full_name.label("user_name"),
            TontineContributions.amount,
            TontineContributions.status,
            TontineContributions.created_at
        )
        .join(Users, Users.user_id == TontineContributions.user_id)
        .where(TontineContributions.tontine_id == tontine_id)
        .order_by(TontineContributions.created_at.desc())
    )

    rows = (await db.execute(q)).mappings().all()

    return [
        {
            "contribution_id": r.contribution_id,
            "user_name": r.user_name,
            "amount": float(r.amount),
            "status": r.status,
            "created_at": r.created_at.isoformat()
        }
        for r in rows
    ]
