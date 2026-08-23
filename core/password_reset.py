import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import models.models as models

RESET_TOKEN_EXPIRE_MINUTES = 20


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_password_reset_token(db: Session, user_id: int) -> str:
    """Invalidates any previous still-valid reset token for this user, then issues
    a new one -- only the newest link should ever work.
    """
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user_id,
        models.PasswordResetToken.used_at.is_(None),
    ).delete(synchronize_session=False)

    raw = secrets.token_urlsafe(48)
    row = models.PasswordResetToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
    )
    db.add(row)
    db.commit()
    return raw


def get_valid_password_reset_token(db: Session, raw_token: str) -> models.PasswordResetToken | None:
    """Looks up raw_token without consuming it. Callers must call
    mark_password_reset_token_used only after the password change actually
    succeeds -- a rejected (e.g. too-short) new_password must not burn the link.
    """
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    return (
        db.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.token_hash == token_hash,
            models.PasswordResetToken.used_at.is_(None),
            models.PasswordResetToken.expires_at > now,
        )
        .first()
    )


def mark_password_reset_token_used(row: models.PasswordResetToken) -> None:
    row.used_at = datetime.now(timezone.utc)
