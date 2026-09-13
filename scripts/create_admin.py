"""One-off: create the admin account.

Usage:
    python -m scripts.create_admin
"""
from dotenv import load_dotenv

from database import SessionLocal
from core.auth import hash_password
import models.models as models

load_dotenv()

ADMIN_NAME = "Admin"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "@I_have_0_enemy"


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first():
            raise SystemExit(f"A user with email '{ADMIN_EMAIL}' already exists.")

        admin = models.User(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            email_verified=True,
        )
        db.add(admin)
        db.commit()
        print(f"Admin account created: {ADMIN_EMAIL}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
