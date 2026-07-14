"""Document step-wizard session keys, step loading, and field persistence."""
from __future__ import annotations

from datetime import datetime

from flask import current_app, request, session
from flask_login import current_user

from models import (
    Document, DocumentAssignment, DocumentSignature, DocumentSignatureField,
    DocumentTypedField, DocumentTypedFieldValue, NewHire, User as UserModel, db,
)


def _ensure_document_typed_field_columns():
    from db.migrations_runtime import _ensure_document_typed_field_columns as _fn
    return _fn()


def clear_choice_group_selections_except(doc_id, username, choice_group, keep_field_id):
    import app as main
    return main.clear_choice_group_selections_except(doc_id, username, choice_group, keep_field_id)


def document_fully_completed_for_user(doc_id, username):
    import app as main
    return main.document_fully_completed_for_user(doc_id, username)


def _mark_document_assignment_complete_if_ready(doc_id, username):
    import app as main
    return main._mark_document_assignment_complete_if_ready(doc_id, username)


def _persist_signed_pdf_copy(document, username):
    from services.documents_pdf import _persist_signed_pdf_copy as _fn
    return _fn(document, username)


def typed_field_is_phone_like(field):
    import app as main
    return main.typed_field_is_phone_like(field)

def _document_wizard_index_key(doc_id):
    return f'doc_wizard_idx_{doc_id}'


def _document_wizard_has_dependents_key(doc_id):
    return f'doc_wizard_deps_{doc_id}'


def _document_wizard_overlay_key(doc_id):
    return f'doc_wizard_overlay_{doc_id}'


def _document_wizard_emp_parts_key(doc_id):
    return f'doc_wizard_emp_parts_{doc_id}'


def _document_wizard_emp_acks_key(doc_id):
    return f'doc_wizard_emp_acks_{doc_id}'


def _user_can_fill_document(document, username, is_admin=None):
    if is_admin is None:
        is_admin = current_user.is_admin() if current_user else False
    if is_admin:
        return True
    return DocumentAssignment.query.filter_by(
        document_id=document.id, username=username
    ).first() is not None


def _document_wizard_user_defaults(username):
    user_display_name = username
    user_initials = (username[:2] if len(username) >= 2 else username).upper()
    try:
        nh = NewHire.query.filter_by(username=username).first()
        if nh:
            first = (nh.first_name or '').strip()
            last = (nh.last_name or '').strip()
            user_display_name = f'{first} {last}'.strip() or username
            user_initials = ((first[:1] if first else '') + (last[:1] if last else '')).upper() or user_initials
        else:
            user_row = UserModel.query.filter_by(username=username).first()
            if user_row and (user_row.full_name or '').strip():
                parts = user_row.full_name.strip().split()
                user_display_name = user_row.full_name.strip()
                user_initials = (parts[0][:1] + (parts[1][:1] if len(parts) > 1 else '')).upper() if parts else user_initials
    except Exception:
        db.session.rollback()
    from datetime import date
    return user_display_name, user_initials, date.today().isoformat()


def _load_document_wizard_steps(document, username):
    signature_fields = DocumentSignatureField.query.filter_by(document_id=document.id).order_by(
        DocumentSignatureField.page_number, DocumentSignatureField.id
    ).all()
    try:
        typed_fields = DocumentTypedField.query.filter_by(document_id=document.id).order_by(
            DocumentTypedField.page_number, DocumentTypedField.id
        ).all()
    except Exception:
        typed_fields = []
    try:
        typed_values = {
            v.typed_field_id: v.field_value
            for v in DocumentTypedFieldValue.query.filter_by(
                document_id=document.id, username=username
            ).all()
        }
    except Exception:
        typed_values = {}
    try:
        signed_field_ids = {
            s.signature_field_id
            for s in DocumentSignature.query.filter_by(
                document_id=document.id, username=username
            ).all()
            if s.signature_field_id
        }
    except Exception:
        signed_field_ids = set()
    user_display_name, user_initials, today_date = _document_wizard_user_defaults(username)
    try:
        from document_wizard_labels import (
            filter_ee_wizard_steps,
            is_employee_information_form,
            repair_employee_information_field_groups,
            resolve_has_dependents_answer,
        )
        from employment_wizard_labels import (
            hydrate_education_location_parts,
            hydrate_employment_parts_from_overlays,
            is_employment_application_form,
            migrate_employment_applied_employed_values,
            repair_employment_application_field_groups,
        )
        if is_employee_information_form(typed_fields):
            if repair_employee_information_field_groups(typed_fields):
                db.session.commit()
        elif is_employment_application_form(typed_fields):
            emp_changed = repair_employment_application_field_groups(typed_fields)
            from employment_wizard_labels import (
                ensure_employment_education_table_positions,
                ensure_employment_radio_pair_fields,
            )
            if ensure_employment_radio_pair_fields(document, typed_fields):
                emp_changed = True
                typed_fields = DocumentTypedField.query.filter_by(document_id=document.id).all()
            if ensure_employment_education_table_positions(typed_fields):
                emp_changed = True
            if migrate_employment_applied_employed_values(document.id, username, typed_fields):
                emp_changed = True
            if emp_changed:
                db.session.commit()
    except Exception:
        current_app.logger.exception('repair form field groups failed doc_id=%s', document.id)
    has_dependents = session.get(_document_wizard_has_dependents_key(document.id))
    try:
        has_dependents = resolve_has_dependents_answer(has_dependents, typed_values, typed_fields)
    except Exception:
        pass
    overlay_values = session.get(_document_wizard_overlay_key(document.id)) or {}
    composite_parts = session.get(_document_wizard_emp_parts_key(document.id)) or {}
    try:
        from employment_wizard_labels import (
            hydrate_education_location_parts,
            hydrate_education_name_from_overlays,
            hydrate_employment_parts_from_overlays,
            is_employment_application_form as _is_emp_app,
            load_employment_wizard_parts,
            resolve_education_section_gates,
            resolve_employment_employer_count,
        )
        if _is_emp_app(typed_fields):
            if not composite_parts:
                composite_parts = load_employment_wizard_parts(document.id, username)
            composite_parts = hydrate_employment_parts_from_overlays(overlay_values, composite_parts)
            composite_parts = hydrate_education_name_from_overlays(overlay_values, composite_parts)
            composite_parts = hydrate_education_location_parts(typed_fields, typed_values, composite_parts)
            composite_parts = resolve_education_section_gates(
                composite_parts, typed_fields, typed_values,
            )
            composite_parts = resolve_employment_employer_count(
                composite_parts, typed_fields, typed_values,
            )
    except Exception:
        pass
    emp_wizard_acks = session.get(_document_wizard_emp_acks_key(document.id)) or {}
    from document_wizard import build_wizard_fields_for_document
    steps = build_wizard_fields_for_document(
        document.id,
        signature_fields,
        typed_fields,
        typed_values,
        signed_field_ids,
        user_display_name,
        user_initials,
        today_date,
        typed_field_is_phone_like,
        has_dependents=has_dependents,
        overlay_values=overlay_values,
        composite_parts=composite_parts,
        emp_wizard_acks=emp_wizard_acks,
    )
    try:
        from document_wizard_labels import filter_ee_wizard_steps, is_employee_information_form
        from employment_wizard_labels import filter_employment_wizard_steps, is_employment_application_form
        if is_employee_information_form(typed_fields):
            steps = filter_ee_wizard_steps(steps, has_dependents)
        elif is_employment_application_form(typed_fields):
            steps = filter_employment_wizard_steps(
                steps, typed_fields, typed_values, composite_parts=composite_parts,
            )
    except Exception:
        current_app.logger.exception('filter wizard steps failed doc_id=%s', document.id)
    return steps, signature_fields, typed_fields


def _wizard_persist_typed(doc_id, typed_field, field_value, username):
    """Wizard manages its own choice groups; never cross-clear shared DB groups."""
    return _persist_typed_field_for_user(
        doc_id, typed_field, field_value, username, manage_choice_group=False,
    )


def _persist_typed_field_for_user(doc_id, typed_field, field_value, username, manage_choice_group=True):
    _ensure_document_typed_field_columns()
    cleared_field_ids = []
    if (
        manage_choice_group
        and typed_field.field_type == 'checkbox_choice'
        and field_value == 'X'
    ):
        cleared_field_ids = clear_choice_group_selections_except(
            doc_id, username, typed_field.choice_group, typed_field.id
        )
    existing_value = DocumentTypedFieldValue.query.filter_by(
        document_id=doc_id,
        typed_field_id=typed_field.id,
        username=username,
    ).first()
    if field_value == '' and existing_value:
        db.session.delete(existing_value)
    elif field_value == '':
        pass
    elif existing_value:
        existing_value.field_value = field_value
        existing_value.filled_at = datetime.utcnow()
        existing_value.ip_address = request.remote_addr
        existing_value.user_agent = request.headers.get('User-Agent', '')
    else:
        db.session.add(DocumentTypedFieldValue(
            document_id=doc_id,
            typed_field_id=typed_field.id,
            username=username,
            field_value=field_value,
            filled_at=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
        ))
    return cleared_field_ids


def _persist_signature_for_user(doc_id, signature_field, signature_image_b64, username, consent_given=True):
    existing_signature = DocumentSignature.query.filter_by(
        document_id=doc_id,
        signature_field_id=signature_field.id,
        username=username,
    ).first()
    if existing_signature:
        existing_signature.signature_image = signature_image_b64
        existing_signature.signed_at = datetime.utcnow()
        existing_signature.ip_address = request.remote_addr
        existing_signature.user_agent = request.headers.get('User-Agent', '')
        existing_signature.consent_given = consent_given
    else:
        new_signature = DocumentSignature(
            document_id=doc_id,
            signature_field_id=signature_field.id,
            username=username,
            signature_image=signature_image_b64,
            signature_type='image',
            signed_at=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            consent_given=consent_given,
        )
        try:
            new_signature.field_page_number = signature_field.page_number
            new_signature.field_x_position = signature_field.x_position
            new_signature.field_y_position = signature_field.y_position
            new_signature.field_width = signature_field.width
            new_signature.field_height = signature_field.height
            new_signature.field_label = signature_field.field_label
        except (AttributeError, Exception):
            pass
        db.session.add(new_signature)


def _finalize_document_completion(doc_id, username):
    all_complete = document_fully_completed_for_user(doc_id, username)
    if not all_complete:
        return False
    _mark_document_assignment_complete_if_ready(doc_id, username)
    document = Document.query.get(doc_id)
    if document:
        try:
            from services.jobs import enqueue_or_persist_signed_pdf
            enqueue_or_persist_signed_pdf(document, username)
        except Exception as e:
            current_app.logger.warning('Failed to enqueue/persist signed PDF after wizard: %s', e)
    db.session.commit()
    return True

