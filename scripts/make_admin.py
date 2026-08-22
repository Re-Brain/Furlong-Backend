"""One-off: promote a user to role="admin" by email.

Usage:
    python -m scripts.make_admin someone@example.com
"""
import sys

from dotenv import load_dotenv

from database import SessionLocal
import models.models as models

load_dotenv()


def run(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            raise SystemExit(f"No user found with email '{email}'")
        user.role = "admin"
        db.commit()
        print(f"'{email}' is now an admin.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m scripts.make_admin <email>")
    run(sys.argv[1])
