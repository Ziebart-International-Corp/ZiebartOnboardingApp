"""User email/password and login bookkeeping helpers."""
from __future__ import annotations

from datetime import datetime

from models import Department, NewHire, User as UserModel, db
from sqlalchemy import func
from db.migrations_runtime import (
    _ensure_users_must_change_password_column,
    _ensure_users_last_login_column,
)



def get_email_for_username(username):
    """Get best available email for a username (NewHire first, then User)."""
    new_hire = NewHire.query.filter_by(username=username).first()
    if new_hire and getattr(new_hire, 'email', None) and new_hire.email.strip():
        return new_hire.email.strip()
    user = UserModel.query.filter_by(username=username).first()
    if user and getattr(user, 'full_name', None):
        pass  # keep checking email
    if user and getattr(user, 'email', None) and user.email and str(user.email).strip():
        return str(user.email).strip()
    return None



def email_in_use_by_other_user(email, exclude_user_id=None):
    """True when another user account already has this email (case-insensitive)."""
    norm = normalize_email(email)
    if not norm:
        return False
    q = UserModel.query.filter(UserModel.email.isnot(None)).filter(func.lower(UserModel.email) == norm)
    if exclude_user_id is not None:
        q = q.filter(UserModel.id != exclude_user_id)
    return q.first() is not None



def update_last_login(username):
    """Update last_login for user after successful login."""
    try:
        user_record = UserModel.query.filter_by(username=username).first()
        if user_record:
            user_record.last_login = datetime.utcnow()
            db.session.commit()
    except Exception:
        db.session.rollback()


# Database tables are created using init_db.py script
# Run: python init_db.py to create tables

# Helper functions



def resolve_department_from_form(department_id_raw):
    """Return (department_id, department_name) from wizard/edit form department_id field."""
    raw = (department_id_raw or '').strip()
    if not raw or raw == '__add__':
        return None, None
    try:
        dept = Department.query.get(int(raw))
    except (TypeError, ValueError):
        return None, None
    if not dept:
        return None, None
    return dept.id, dept.name

def normalize_email(email):
    """Normalize email input for login/uniqueness checks."""
    val = (email or '').strip().lower()
    return val or None

def user_must_change_password(username):
    """True when the user must set a new password before using the app."""
    _ensure_users_must_change_password_column()
    user = UserModel.query.filter_by(username=username).first()
    return bool(user and getattr(user, 'must_change_password', False))

