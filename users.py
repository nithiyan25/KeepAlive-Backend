"""
users.py — User CRUD using MySQL via SQLAlchemy.
Drop-in replacement for the old JSON-based users.py.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from database import SessionLocal, UserRow, user_to_dict


# ── Internal session helper ───────────────────────────────────────────────────

def _db() -> Session:
    return SessionLocal()


# ── Public API ────────────────────────────────────────────────────────────────

def get_all_users() -> List[dict]:
    db = _db()
    try:
        return [user_to_dict(u) for u in db.query(UserRow).all()]
    finally:
        db.close()


def get_user_by_id(user_id: str) -> Optional[dict]:
    db = _db()
    try:
        row = db.query(UserRow).filter(UserRow.id == user_id).first()
        return user_to_dict(row) if row else None
    finally:
        db.close()


def get_user_by_email(email: str) -> Optional[dict]:
    db = _db()
    try:
        row = db.query(UserRow).filter(
            UserRow.email == email.lower()
        ).first()
        return user_to_dict(row) if row else None
    finally:
        db.close()


def get_pending_users() -> List[dict]:
    db = _db()
    try:
        rows = db.query(UserRow).filter(UserRow.status == "pending").all()
        return [user_to_dict(r) for r in rows]
    finally:
        db.close()


def get_approved_users() -> List[dict]:
    db = _db()
    try:
        rows = db.query(UserRow).filter(UserRow.status == "approved").all()
        return [user_to_dict(r) for r in rows]
    finally:
        db.close()


def create_user(email: str, name: str, picture: str, admin_email: str) -> dict:
    """
    Create a new user.
    - If email matches ADMIN_EMAIL → auto-approve with role=admin
    - Otherwise → pending, role=user
    """
    is_admin = email.lower() == admin_email.lower()
    now      = datetime.now(timezone.utc)

    row = UserRow(
        id          = str(uuid.uuid4()),
        email       = email.lower(),
        name        = name,
        picture     = picture,
        role        = "admin" if is_admin else "user",
        status      = "approved" if is_admin else "pending",
        created_at  = now,
        approved_at = now if is_admin else None,
    )

    db = _db()
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        print(f"[USERS] New {'admin' if is_admin else 'pending user'}: {email}")
        return user_to_dict(row)
    finally:
        db.close()


def update_user_status(user_id: str, status: str) -> Optional[dict]:
    """Set user status to 'approved' or 'rejected'."""
    db = _db()
    try:
        row = db.query(UserRow).filter(UserRow.id == user_id).first()
        if not row:
            return None
        row.status = status
        if status == "approved":
            row.approved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return user_to_dict(row)
    finally:
        db.close()


def delete_user(user_id: str) -> bool:
    db = _db()
    try:
        row = db.query(UserRow).filter(UserRow.id == user_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()