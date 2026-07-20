"""Self-serve password reset via one-time email links."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import func

from models import PasswordResetToken, User as UserModel, db
from services.user_accounts import normalize_email

RESET_TOKEN_HOURS = 1
GENERIC_REQUEST_MESSAGE = (
    'If an account exists for that email, we sent a password reset link. '
    'Check your inbox and spam folder.'
)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()


def _user_can_receive_reset(user: UserModel) -> bool:
    if not user or not normalize_email(getattr(user, 'email', None)):
        return False
    revoked = getattr(user, 'access_revoked_at', None)
    if revoked and date.today() >= revoked:
        return False
    return True


def find_user_by_email(email: str):
    norm = normalize_email(email)
    if not norm:
        return None
    return (
        UserModel.query.filter(UserModel.email.isnot(None))
        .filter(func.lower(UserModel.email) == norm)
        .first()
    )


def create_password_reset_token(user: UserModel, requested_ip: str | None = None) -> str:
    """Invalidate prior unused tokens and create a new one. Returns raw token."""
    now = datetime.utcnow()
    PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
        {PasswordResetToken.used_at: now}, synchronize_session=False
    )
    raw = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw),
        expires_at=now + timedelta(hours=RESET_TOKEN_HOURS),
        requested_ip=(requested_ip or '')[:50] or None,
        created_at=now,
    )
    db.session.add(row)
    db.session.commit()
    return raw


def lookup_valid_reset_token(raw_token: str):
    """Return (PasswordResetToken, User) if valid, else (None, None)."""
    if not raw_token or len(raw_token) < 20:
        return None, None
    token_hash = hash_reset_token(raw_token)
    row = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    if not row or row.used_at is not None:
        return None, None
    if row.expires_at < datetime.utcnow():
        return None, None
    user = UserModel.query.get(row.user_id)
    if not _user_can_receive_reset(user):
        return None, None
    return row, user


def consume_reset_token(row: PasswordResetToken) -> None:
    row.used_at = datetime.utcnow()
    PasswordResetToken.query.filter_by(user_id=row.user_id, used_at=None).filter(
        PasswordResetToken.id != row.id
    ).update({PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)


def apply_new_password(user: UserModel, new_password: str) -> None:
    from werkzeug.security import generate_password_hash
    user.password_hash = generate_password_hash(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.utcnow()


def request_password_reset(email: str, requested_ip: str | None = None, reset_url_for_token=None) -> str:
    """Always returns the same generic message. Sends email only when appropriate."""
    user = find_user_by_email(email)
    if not user or not _user_can_receive_reset(user):
        return GENERIC_REQUEST_MESSAGE
    raw = create_password_reset_token(user, requested_ip=requested_ip)
    if callable(reset_url_for_token):
        reset_url = reset_url_for_token(raw)
    else:
        from services.document_urls import onboarding_base_url
        reset_url = onboarding_base_url() + '/reset-password/' + raw
    from services.mail import send_password_reset_link_email
    send_password_reset_link_email(user, reset_url)
    return GENERIC_REQUEST_MESSAGE
