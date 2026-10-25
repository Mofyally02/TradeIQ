"""Admin tooling: python -m app.cli create-admin --email ... --name ... [--password ...]"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.api.auth import password_hash
from app.db import SessionLocal
from app.models import User


def create_admin(email: str, name: str, password: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, password_hash=password_hash.hash(password))
            db.add(user)
        else:
            user.full_name = name
            user.password_hash = password_hash.hash(password)
        user.role = "admin"
        db.commit()
    print(f"Admin ready: {email}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--password")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Admin password: ")
    if len(password) < 12:
        sys.exit("Password must be at least 12 characters")
    create_admin(args.email.strip().lower(), args.name, password)


if __name__ == "__main__":
    main()
