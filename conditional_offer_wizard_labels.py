"""Step-by-step wizard for Conditional Offer Letter."""
from __future__ import annotations

from typing import Any, Callable, Optional

from conditional_offer_pdf_field_map import (
    COL_OFFER_APPLICANT_DATE_ACRO,
    COL_OFFER_APPLICANT_NAME_ACRO,
    COL_OFFER_FLOW,
    COL_OFFER_FORM_MARKER_ACROS,
    COL_OFFER_LOCATION_ACRO,
    COL_OFFER_POSITION_ACRO,
    COL_OFFER_SECTION_APPLICANT,
    COL_OFFER_SECTION_MANAGER,
    COL_OFFER_SECTION_OFFER,
    COL_OFFER_STORE_MANAGER_DATE_ACRO,
)
from document_wizard_labels import (
    wizard_skip_value_for_step,
    wizard_value_counts_as_filled,
)


def col_offer_acro_key(placeholder: Optional[str]) -> str:
    ph = (placeholder or '').strip()
    if ph.startswith('acro:'):
        return ph[5:].strip()
    return ph


def is_conditional_offer_form(typed_fields: list) -> bool:
    keys = {col_offer_acro_key(getattr(tf, 'placeholder', None)) for tf in typed_fields}
    return COL_OFFER_FORM_MARKER_ACROS.issubset(keys)


def col_offer_id_by_acro(typed_fields: list) -> dict[str, list]:
    out: dict[str, list] = {}
    for tf in typed_fields:
        out.setdefault(col_offer_acro_key(tf.placeholder), []).append(tf)
    return out


COL_OFFER_TYPED_LABELS: dict[str, tuple[str, str, str]] = {
    COL_OFFER_APPLICANT_NAME_ACRO: (
        'Your name',
        COL_OFFER_SECTION_OFFER,
        'Your full legal name as it appears on the offer letter.',
    ),
    COL_OFFER_POSITION_ACRO: (
        'Position title',
        COL_OFFER_SECTION_OFFER,
        'The job title shown in your conditional offer.',
    ),
    COL_OFFER_LOCATION_ACRO: (
        'Location',
        COL_OFFER_SECTION_OFFER,
        'The store or location name for this position.',
    ),
    COL_OFFER_STORE_MANAGER_DATE_ACRO: (
        'Store manager signature date',
        COL_OFFER_SECTION_MANAGER,
        'Date the store manager signed (if already signed). Leave blank if not yet signed.',
    ),
    COL_OFFER_APPLICANT_DATE_ACRO: (
        'Your signature date',
        COL_OFFER_SECTION_APPLICANT,
        'Today\'s date when you sign this offer.',
    ),
}

COL_OFFER_SIGNATURE_LABELS: dict[str, tuple[str, str, str]] = {
    'store_manager': (
        'Store manager signature',
        COL_OFFER_SECTION_MANAGER,
        'If your manager has not signed yet, you can skip this and return later.',
    ),
    'applicant': (
        'Your signature',
        COL_OFFER_SECTION_APPLICANT,
        'Draw your signature to accept the conditional offer.',
    ),
}


def _field_sort_key(field) -> tuple:
    return (field.page_number or 1, field.y_position or 0, field.x_position or 0, field.id or 0)


def _signature_for_role(signature_fields: list, role: str):
    role_l = role.lower()
    for sf in signature_fields:
        lbl = (sf.field_label or '').lower()
        if role_l == 'store_manager' and 'store manager' in lbl:
            return sf
        if role_l == 'applicant' and 'applicant' in lbl:
            return sf
    sig_sorted = sorted(signature_fields, key=_field_sort_key)
    if role_l == 'store_manager' and sig_sorted:
        return sig_sorted[0]
    if role_l == 'applicant' and len(sig_sorted) > 1:
        return sig_sorted[1]
    if role_l == 'applicant' and sig_sorted:
        return sig_sorted[-1]
    return None


def build_conditional_offer_wizard_steps(
    typed_fields: list,
    signature_fields: list,
    typed_values: dict[int, str],
    signed_field_ids: set[int],
    user_display_name: str,
    user_initials: str,
    today_date: str,
    wizard_type_for_typed: Callable[[str, bool], str],
    phone_like_fn: Callable,
) -> list[dict[str, Any]]:
    id_by_acro = col_offer_id_by_acro(typed_fields)
    steps: list[dict[str, Any]] = []

    def _typed_step(tf, *, required: bool = True) -> dict[str, Any]:
        ak = col_offer_acro_key(tf.placeholder)
        label, section, hint = COL_OFFER_TYPED_LABELS.get(
            ak,
            (tf.field_label or 'Field', COL_OFFER_SECTION_OFFER, ''),
        )
        wtype = wizard_type_for_typed(tf.field_type, phone_like_fn(tf))
        val = (typed_values.get(tf.id) or '').strip()
        auto = False
        if not val and tf.field_type == 'typed_name':
            val = user_display_name
            auto = True
        elif not val and tf.field_type == 'date' and ak == COL_OFFER_APPLICANT_DATE_ACRO:
            val = today_date
            auto = True
        elif not val and tf.field_type == 'date' and ak == COL_OFFER_STORE_MANAGER_DATE_ACRO:
            pass
        return {
            'wizard_id': f'typed:{tf.id}',
            'kind': 'typed',
            'db_id': tf.id,
            'field_type': tf.field_type,
            'wizard_type': wtype,
            'label': label.strip(),
            'section': section,
            'page': tf.page_number or 1,
            'required': required,
            'skip_value': wizard_skip_value_for_step({
                'required': required, 'wizard_type': wtype, 'field_type': tf.field_type,
            }),
            'hint': (hint or '')[:500],
            'value': val,
            'filled': wizard_value_counts_as_filled(val, wizard_type=wtype) if not auto else bool(
                (typed_values.get(tf.id) or '').strip(),
            ),
            'auto_value': val if auto else '',
            'col_offer_acro': ak,
        }

    def _sig_step(role: str) -> Optional[dict[str, Any]]:
        sf = _signature_for_role(signature_fields, role)
        if not sf:
            return None
        label, section, hint = COL_OFFER_SIGNATURE_LABELS.get(
            role, (sf.field_label or 'Signature', COL_OFFER_SECTION_APPLICANT, ''),
        )
        required = role == 'applicant'
        return {
            'wizard_id': f'sig:{sf.id}',
            'kind': 'signature',
            'db_id': sf.id,
            'wizard_type': 'signature',
            'label': label,
            'section': section,
            'page': sf.page_number or 1,
            'required': required,
            'skip_value': '' if required else '',
            'hint': hint,
            'value': '',
            'filled': sf.id in signed_field_ids,
        }

    for kind, key in COL_OFFER_FLOW:
        if kind == 'typed':
            for tf in id_by_acro.get(key, []):
                if tf.field_type == 'checkbox_choice':
                    continue
                required = key != COL_OFFER_STORE_MANAGER_DATE_ACRO
                steps.append(_typed_step(tf, required=required))
        elif kind == 'sig':
            step = _sig_step(key)
            if step:
                steps.append(step)

    return steps
