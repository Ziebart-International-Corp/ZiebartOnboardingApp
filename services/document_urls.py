"""User-facing document URL helpers."""
from __future__ import annotations

import os

from flask import url_for

from models import DocumentSignatureField, DocumentTypedField
from document_wizard import document_uses_step_wizard

def _document_configured_field_count(doc_id):
    sig = DocumentSignatureField.query.filter_by(document_id=doc_id).count()
    typed = DocumentTypedField.query.filter_by(document_id=doc_id).count()
    return sig + typed

def user_sign_document_url(doc_id):
    """Sign or step-by-step wizard URL for users (IIS-friendly /documents?query)."""
    typed_fields = DocumentTypedField.query.filter_by(document_id=doc_id).all()
    if document_uses_step_wizard(_document_configured_field_count(doc_id), typed_fields):
        return url_for('view_documents', wizard=doc_id)
    return url_for('view_documents', sign=doc_id)

def user_document_wizard_url(doc_id):
    return url_for('view_documents', wizard=doc_id)

def user_sign_document_classic_url(doc_id):
    return url_for('view_documents', sign=doc_id, classic=1)

def user_document_completed_print_url(doc_id):
    return url_for('print_document_completed', doc_id=doc_id)

def user_document_completed_view_url(doc_id):
    return url_for('view_document_completed', doc_id=doc_id)

def onboarding_base_url():
    """Public base URL for onboarding links in outbound emails."""
    base = (
        os.getenv('ONBOARDING_BASE_URL')
        or os.getenv('APP_BASE_URL')
        or os.getenv('SITE_URL')
        or 'https://ziebartonboarding.com'
    )
    base = (base or '').strip()
    if not base:
        base = 'https://ziebartonboarding.com'
    if not base.lower().startswith(('http://', 'https://')):
        base = 'https://' + base
    return base.rstrip('/')

def onboarding_tasks_url():
    """Public URL for the user tasks page, used in outbound emails."""
    return onboarding_base_url() + '/tasks'

def onboarding_login_url():
    """Public URL for the login page, used in outbound emails."""
    return onboarding_base_url() + '/login'


# Flask-Mail configuration: support both MAIL_* and EMAIL_* from .env

