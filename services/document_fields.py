"""Typed/signature field validation, completion, and AcroForm import."""
from __future__ import annotations

import re
from datetime import datetime

from flask import current_app

from models import (
    Document, DocumentAssignment, DocumentSignature, DocumentSignatureField,
    DocumentTypedField, DocumentTypedFieldValue, UserTask, db,
)
from pdf_form_wizard import FITZ_AVAILABLE as PDF_WIZARD_FITZ_AVAILABLE

TYPED_FIELD_PHONE_REGEX = re.compile(
    r"^(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}$"
)
TYPED_FIELD_PHONE_PATTERN_HTML = (
    r"(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}"
)
TYPED_FIELD_PHONE_REGEX_JS = TYPED_FIELD_PHONE_REGEX.pattern
TYPED_FIELD_LAST4_PREFIX = "XXX-XX-"
TYPED_FIELD_LAST4_REGEX = re.compile(r"^XXX-XX-[0-9]{4}$")
TYPED_FIELD_LAST4_REGEX_JS = TYPED_FIELD_LAST4_REGEX.pattern

ALLOWED_TYPED_FIELD_TYPES = frozenset({
    "text", "name", "typed_name", "typed_initials", "date", "number", "phone", "last4", "checkbox_choice",
})
TYPED_FIELD_TYPE_CHOICES = (
    ("text", "Text"),
    ("name", "Name"),
    ("typed_name", "Typed Name"),
    ("typed_initials", "Typed Initials"),
    ("date", "Date"),
    ("number", "Number"),
    ("phone", "Phone Number"),
    ("last4", "Last 4 (SSN)"),
    ("checkbox_choice", "Checkbox (pick one)"),
)
FIELD_EDITOR_TYPE_CHOICES = (("signature", "Signature"),) + TYPED_FIELD_TYPE_CHOICES


def _document_pdf_path(document):
    import app as main
    return main._document_pdf_path(document)


def _document_is_fillable_pdf(document):
    import app as main
    return main._document_is_fillable_pdf(document)


def collect_acroform_import_specs(pdf_path):
    from services.pdf_acroform_cache import collect_acroform_import_specs as _fn
    return _fn(pdf_path)


def count_pdf_acroform_widgets(pdf_path):
    from services.pdf_acroform_cache import count_pdf_acroform_widgets as _fn
    return _fn(pdf_path)


def document_uses_step_wizard(count, typed_fields):
    from document_wizard import document_uses_step_wizard as _fn
    return _fn(count, typed_fields)

def normalize_last4_typed_value(value):
    """Normalize to XXX-XX-####; reject/incomplete unless exactly 4 trailing digits."""
    val = (value or '').strip().upper()
    if val.startswith(TYPED_FIELD_LAST4_PREFIX):
        tail = val[len(TYPED_FIELD_LAST4_PREFIX):]
        digits = re.sub(r'\D', '', tail)
    else:
        digits = re.sub(r'\D', '', val)
    if len(digits) > 4:
        digits = digits[-4:]
    digits = digits[:4]
    if len(digits) != 4:
        return ''
    return TYPED_FIELD_LAST4_PREFIX + digits

def typed_field_is_phone_like(field):
    """True for phone type or fields whose label/acro name suggests a phone number."""
    if not field:
        return False
    return _field_is_phone_like(
        getattr(field, 'field_type', None),
        getattr(field, 'field_label', None),
        getattr(field, 'placeholder', None),
    )

def _field_is_phone_like(field_type, field_label=None, placeholder=None):
    if field_type == 'phone':
        return True
    label = (field_label or '').lower()
    if field_type in ('text', 'number', 'phone'):
        if 'phone' in label:
            return True
    ph = (placeholder or '').strip()
    if ph.startswith('acro:'):
        ph = ph[5:]
    if ph:
        try:
            from document_wizard_labels import EE_PHONE_ACROS
            if ph in EE_PHONE_ACROS:
                return True
        except ImportError:
            pass
    return field_type == 'number' and 'phone' in label


_document_typed_field_cols_migrated = False

def _import_acroform_fields_for_document(document, created_by, replace_existing=False):
    """
    Import Adobe/PDF AcroForm widgets into DocumentSignatureField and DocumentTypedField rows.
    Returns (success: bool, message: str).
    """
    if not PDF_WIZARD_FITZ_AVAILABLE:
        return False, 'PyMuPDF is not installed on the server.'
    pdf_path = _document_pdf_path(document)
    if not pdf_path:
        return False, 'PDF file not found on disk.'
    if not _document_is_fillable_pdf(document):
        return False, 'Document is not a PDF.'

    sig_count = DocumentSignatureField.query.filter_by(document_id=document.id).count()
    typed_count = DocumentTypedField.query.filter_by(document_id=document.id).count()
    if (sig_count or typed_count) and not replace_existing:
        return False, 'This document already has fields. Use “Import from PDF” with replace to overwrite.'

    specs = collect_acroform_import_specs(pdf_path)
    if not specs.get('ok'):
        return False, specs.get('error', 'Could not read PDF form fields.')
    if specs.get('widget_count', 0) == 0:
        return False, 'No fillable form fields found in this PDF. Create fields in Acrobat or place them manually.'

    try:
        if replace_existing:
            DocumentTypedFieldValue.query.filter_by(document_id=document.id).delete(synchronize_session=False)
            DocumentTypedField.query.filter_by(document_id=document.id).delete(synchronize_session=False)
            DocumentSignatureField.query.filter_by(document_id=document.id).delete(synchronize_session=False)

        for spec in specs.get('signature_fields') or []:
            db.session.add(DocumentSignatureField(
                document_id=document.id,
                page_number=spec['page_number'],
                x_position=spec['x_position'],
                y_position=spec['y_position'],
                width=spec['width'],
                height=spec['height'],
                field_label=spec['field_label'],
                is_required=True,
                signature_type='image',
                created_by=created_by,
            ))
        for spec in specs.get('typed_fields') or []:
            db.session.add(DocumentTypedField(
                document_id=document.id,
                page_number=spec['page_number'],
                x_position=spec['x_position'],
                y_position=spec['y_position'],
                width=spec['width'],
                height=spec['height'],
                field_label=spec['field_label'],
                field_type=spec['field_type'],
                choice_group=spec.get('choice_group'),
                placeholder=spec.get('placeholder'),
                is_required=False if spec['field_type'] == 'checkbox_choice' else True,
                created_by=created_by,
            ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('acroform import failed for document %s', document.id)
        return False, f'Import failed: {e}'

    n_sig = len(specs.get('signature_fields') or [])
    n_typed = len(specs.get('typed_fields') or [])
    return True, (
        f'Imported {n_sig + n_typed} field(s) from the PDF '
        f'({n_sig} signature, {n_typed} typed). Review positions on Set Signature Fields if needed.'
    )

def _try_auto_import_acroform_fields(document, created_by):
    """Import AcroForm widgets when the document has none configured yet."""
    if not _document_is_fillable_pdf(document):
        return False, ''
    sig_count = DocumentSignatureField.query.filter_by(document_id=document.id).count()
    typed_count = DocumentTypedField.query.filter_by(document_id=document.id).count()
    if sig_count or typed_count:
        return False, ''
    pdf_path = _document_pdf_path(document)
    if not pdf_path or count_pdf_acroform_widgets(pdf_path) == 0:
        return False, ''
    return _import_acroform_fields_for_document(document, created_by, replace_existing=False)

def clear_choice_group_selections_except(doc_id, username, choice_group, keep_field_id):
    """Clear X marks on other checkbox_choice fields in the same group for this user."""
    if not choice_group or not str(choice_group).strip():
        return []
    group_key = str(choice_group).strip()
    siblings = DocumentTypedField.query.filter_by(
        document_id=doc_id,
        field_type='checkbox_choice',
    ).filter(DocumentTypedField.choice_group == group_key).all()
    cleared_ids = []
    for sib in siblings:
        if sib.id == keep_field_id:
            continue
        row = DocumentTypedFieldValue.query.filter_by(
            document_id=doc_id,
            typed_field_id=sib.id,
            username=username,
        ).first()
        if row:
            db.session.delete(row)
            cleared_ids.append(sib.id)
    return cleared_ids


def normalize_typed_field_type(field_type):
    ft = (field_type or 'text').strip().lower()
    return ft if ft in ALLOWED_TYPED_FIELD_TYPES else 'text'

def validate_typed_field_value(field_type, value, field_label=None, placeholder=None, wizard_type=None):
    """Return (ok, error_message) for a typed-field value before save."""
    val = (value or '').strip()
    if field_type == 'checkbox_choice':
        if not val:
            return True, None
        if val.upper() == 'X':
            return True, None
        return False, 'Invalid checkbox value.'
    if not val:
        return False, 'Field value is required'
    if val.upper() == 'N/A':
        return True, None
    phone_like = wizard_type == 'phone' or _field_is_phone_like(field_type, field_label, placeholder)
    if phone_like:
        if not TYPED_FIELD_PHONE_REGEX.match(val):
            return (
                False,
                'Please enter a valid phone number (e.g. (555) 123-4567 or 555-123-4567).',
            )
    elif field_type == 'number':
        try:
            float(val)
        except ValueError:
            return False, 'Please enter a valid number.'
    elif field_type == 'last4':
        normalized = normalize_last4_typed_value(val)
        if not normalized or not TYPED_FIELD_LAST4_REGEX.match(normalized):
            return (
                False,
                'Please enter only the last 4 digits of your SSN (shown as XXX-XX-####).',
            )
    return True, None

def is_signature_field_signed(document_id, field, username):
    """
    Check if a signature field is signed by a user.
    Handles cases where the field was deleted and recreated by checking:
    1. Signatures with matching signature_field_id
    2. Signatures with null signature_field_id that match field location (within tolerance)
    """
    # First check for signature with matching field ID
    if field.id:
        sig = DocumentSignature.query.filter_by(
            document_id=document_id,
            signature_field_id=field.id,
            username=username
        ).first()
        if sig:
            return True
    
    # If no match by ID, check for signatures with null field_id that match location
    # Use a tolerance of 10 pixels for position matching (in case field was slightly moved)
    # Check if new columns exist (handle case where database hasn't been migrated yet)
    try:
        # Try to query for orphaned signatures - this might fail if columns don't exist
        tolerance = 10.0
        try:
            orphaned_sigs = DocumentSignature.query.filter_by(
                document_id=document_id,
                username=username
            ).filter(DocumentSignature.signature_field_id.is_(None)).all()
        except Exception:
            # If query fails (columns don't exist), return False
            return False
        
        for sig in orphaned_sigs:
            # Safely access new fields (may not exist if database not migrated)
            try:
                field_page = getattr(sig, 'field_page_number', None)
                field_x = getattr(sig, 'field_x_position', None)
                field_y = getattr(sig, 'field_y_position', None)
                
                if (field_page == field.page_number and
                    field_x is not None and field_y is not None and
                    abs(field_x - field.x_position) <= tolerance and
                    abs(field_y - field.y_position) <= tolerance):
                    return True
            except (AttributeError, Exception):
                # If accessing fields fails, skip this signature
                continue
    except Exception:
        # If anything fails, just return False (no orphaned signature match)
        pass
    
    return False

def is_typed_field_filled(document_id, field, username):
    """True if the user has a saved value for this typed field."""
    if not field or not field.id:
        return False
    try:
        row = DocumentTypedFieldValue.query.filter_by(
            document_id=document_id,
            typed_field_id=field.id,
            username=username,
        ).first()
    except Exception:
        return False
    if not row:
        return False
    val = (row.field_value or '').strip()
    if field.field_type == 'checkbox_choice':
        return val.upper() == 'X'
    return bool(val)

def document_fully_completed_for_user(document_id, username):
    """All required signature fields, typed fields, and checkbox/radio groups are satisfied."""
    sig_fields = DocumentSignatureField.query.filter_by(document_id=document_id).all()
    typed_fields = DocumentTypedField.query.filter_by(document_id=document_id).all()
    if not sig_fields and not typed_fields:
        return False

    try:
        from conditional_offer_wizard_labels import is_conditional_offer_form
        from document_wizard_labels import is_employee_information_form
        from employment_wizard_labels import is_employment_application_form
        if (
            is_employee_information_form(typed_fields)
            or is_employment_application_form(typed_fields)
            or is_conditional_offer_form(typed_fields)
        ):
            from document_wizard import wizard_required_steps_complete
            from services.wizard import _load_document_wizard_steps

            document = Document.query.get(document_id)
            if document:
                steps, _, _ = _load_document_wizard_steps(document, username)
                return wizard_required_steps_complete(steps)
    except Exception:
        current_app.logger.exception('wizard completion check failed doc_id=%s', document_id)

    required_sig = sig_fields
    if required_sig and not all(
        is_signature_field_signed(document_id, f, username) for f in required_sig
    ):
        return False

    required_typed = [
        f for f in typed_fields
        if f.field_type != 'checkbox_choice'
    ]
    if not all(is_typed_field_filled(document_id, f, username) for f in required_typed):
        return False

    choice_groups = {}
    for f in typed_fields:
        if f.field_type == 'checkbox_choice':
            gkey = (f.choice_group or '').strip() or f'_field_{f.id}'
            choice_groups.setdefault(gkey, []).append(f)
    for fields in choice_groups.values():
        if not any(is_typed_field_filled(document_id, f, username) for f in fields):
            return False

    return True

def _mark_document_assignment_complete_if_ready(document_id, username):
    """Mark assignment and document task complete when all fields are filled."""
    if not document_fully_completed_for_user(document_id, username):
        return False
    assignment = DocumentAssignment.query.filter_by(
        document_id=document_id,
        username=username,
    ).first()
    if assignment and not assignment.is_completed:
        assignment.is_completed = True
        assignment.completed_at = datetime.utcnow()
    task = UserTask.query.filter_by(
        document_id=document_id,
        username=username,
        task_type='document',
    ).first()
    if task and task.status != 'completed':
        task.status = 'completed'
        task.completed_at = datetime.utcnow()
    return True

