"""Create the initial admin once, from explicit deployment credentials."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.main import SessionLocal, User, Role, password_hash


def bootstrap():
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    with SessionLocal() as db:
        existing_admin = db.scalar(select(User.id).where(User.role == Role.admin).limit(1))
        if existing_admin:
            print("Admin bootstrap skipped: an administrator already exists.")
            return
        if len(username) < 3 or len(password) < 16:
            raise RuntimeError("For an empty production database, set BOOTSTRAP_ADMIN_USERNAME and a BOOTSTRAP_ADMIN_PASSWORD of at least 16 characters.")
        if db.scalar(select(User.id).where(User.username == username)):
            raise RuntimeError("BOOTSTRAP_ADMIN_USERNAME already belongs to a non-admin user; choose a different username.")
        admin = User(username=username, password=password_hash.hash(password), role=Role.admin, must_change_password=True)
        db.add(admin)
        db.commit()
        print(f"Created initial administrator {username!r}; the password must be changed at first sign-in.")


if __name__ == "__main__":
    bootstrap()
