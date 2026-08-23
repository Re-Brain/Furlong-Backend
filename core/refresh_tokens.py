import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

import models.models as models
from core.auth import REFRESH_TOKEN_EXPIRE_DAYS

logger = logging.getLogger(__name__)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user_id: int, family_id: str | None = None) -> tuple[str, models.RefreshToken]:
    raw = secrets.token_urlsafe(48)
    row = models.RefreshToken(
        user_id=user_id,
        family_id=family_id or uuid.uuid4().hex,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.family_id == family_id)
        .values(revoked=True)
    )
    db.commit()


def revoke_all_for_user(db: Session, user_id: int) -> None:
    """Kills every refresh-token family for this user, not just one -- used on a
    credential-change event (password reset) that must force re-login everywhere,
    including the session that requested the reset.
    """
    db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.user_id == user_id, models.RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    db.commit()


def rotate_refresh_token(db: Session, raw_token: str) -> models.RefreshToken | None:
    """Atomically claims raw_token for this request. Returns the claimed row on
    success, or None if it was invalid/expired/already used.

    The claim itself is a single UPDATE ... WHERE used=false ... RETURNING, so
    under concurrent requests presenting the same token, only one can ever win
    the race — there is no separate check-then-write step to lose to a TOCTOU
    race, which is exactly the scenario reuse detection has to catch.
    """
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    stmt = (
        update(models.RefreshToken)
        .where(
            models.RefreshToken.token_hash == token_hash,
            models.RefreshToken.used.is_(False),
            models.RefreshToken.revoked.is_(False),
            models.RefreshToken.expires_at > now,
        )
        .values(used=True)
        .execution_options(synchronize_session=False)
        .returning(models.RefreshToken)
    )
    row = db.execute(stmt).scalars().first()
    if row is not None:
        db.commit()
        return row

    # Didn't win the claim. Not a security decision at this point (nothing is
    # granted below) -- just figuring out whether there's a family to shut down.
    existing = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash).first()
    if existing is not None:
        if existing.used:
            logger.warning("Refresh token reuse detected for family %s (user %s)", existing.family_id, existing.user_id)
        revoke_family(db, existing.family_id)
    else:
        db.commit()
    return None


def revoke_token(db: Session, raw_token: str) -> None:
    """Best-effort revoke for /logout: if the token is known, kill its family."""
    token_hash = hash_token(raw_token)
    existing = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash).first()
    if existing is not None:
        revoke_family(db, existing.family_id)
