"""Step-by-step document form wizard helpers (maps Document* fields to wizard steps)."""
from __future__ import annotations

from typing import Any, Optional

from document_wizard_labels import (
    build_ee_information_wizard_steps,
    is_employee_information_form,
    wizard_skip_value_for_step,
)

# Use wizard UI when a document has at least this many configured fields.
DOCUMENT_WIZARD_MIN_FIELDS = 8


def document_wizard_eligible(field_count: int) -> bool:
    return field_count >= DOCUMENT_WIZARD_MIN_FIELDS


def _wizard_type_for_typed(field_type: str, phone_like: bool) -> str:
    if field_type == 'date':
        return 'date'
    if field_type == 'last4':
        return 'last4'
    if field_type == 'number':
        return 'number'
    if phone_like:
        return 'phone'
    if field_type in ('typed_name', 'typed_initials', 'text', 'name'):
        return 'text'
    return 'text'


def build_wizard_fields_for_document(
    document_id: int,
    signature_fields: list,
    typed_fields: list,
    typed_values: dict[int, str],
    signed_field_ids: set[int],
    user_display_name: str,
    user_initials: str,
    today_date: str,
    phone_like_fn,
    has_dependents: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Build ordered wizard steps from admin-configured document fields.
    Checkbox choice groups collapse into a single step with radio options.
    """
    if is_employee_information_form(typed_fields):
        return build_ee_information_wizard_steps(
            typed_fields,
            signature_fields,
            typed_values,
            signed_field_ids,
            user_display_name,
            user_initials,
            today_date,
            _wizard_type_for_typed,
            phone_like_fn,
            has_dependents=has_dependents,
        )

    tf_sort = {tf.id: (tf.page_number, tf.y_position, tf.x_position) for tf in typed_fields}
    sig_sort = {sf.id: (sf.page_number, sf.y_position, sf.x_position) for sf in signature_fields}

    steps: list[dict[str, Any]] = []
    seen_choice_groups: set[str] = set()

    for tf in typed_fields:
        if tf.field_type == 'checkbox_choice':
            gkey = (tf.choice_group or '').strip()
            if gkey:
                if gkey in seen_choice_groups:
                    continue
                seen_choice_groups.add(gkey)
                siblings = [
                    t for t in typed_fields
                    if t.field_type == 'checkbox_choice' and (t.choice_group or '').strip() == gkey
                ]
                siblings.sort(key=lambda t: (t.page_number, t.id))
                selected_id: Optional[int] = None
                for s in siblings:
                    if (typed_values.get(s.id) or '').strip().upper() == 'X':
                        selected_id = s.id
                        break
                label = gkey.replace('_', ' ').strip().title()
                if gkey.startswith('marital_status'):
                    label = 'Marital status'
                elif gkey.startswith('gender'):
                    label = 'Gender'
                elif 'race' in gkey or 'ethnicity' in gkey:
                    label = 'Race / Ethnicity'
                elif gkey.startswith('yes_no'):
                    label = 'Yes / No'
                if len(siblings) == 1:
                    label = (siblings[0].field_label or label).strip()
                steps.append({
                    'wizard_id': f'choice:{gkey}',
                    'kind': 'choice_group',
                    'label': label,
                    'section': '',
                    'page': min(s.page_number for s in siblings),
                    'required': True,
                    'hint': '',
                    'options': [
                        {'field_id': s.id, 'label': (s.field_label or gkey).strip()}
                        for s in siblings
                    ],
                    'value': str(selected_id) if selected_id else '',
                    'filled': selected_id is not None,
                })
                continue
            # Ungrouped checkbox — single yes/no step
            val = (typed_values.get(tf.id) or '').strip().upper()
            steps.append({
                'wizard_id': f'typed:{tf.id}',
                'kind': 'typed',
                'db_id': tf.id,
                'field_type': 'checkbox_choice',
                'wizard_type': 'checkbox',
                'label': (tf.field_label or 'Checkbox').strip(),
                'section': '',
                'page': tf.page_number,
                'required': bool(tf.is_required),
                'hint': (tf.placeholder or '').strip(),
                'value': 'X' if val == 'X' else '',
                'filled': val == 'X',
            })
            continue

        phone_like = phone_like_fn(tf)
        wtype = _wizard_type_for_typed(tf.field_type, phone_like)
        val = (typed_values.get(tf.id) or '').strip()
        auto = False
        if not val and tf.field_type == 'typed_name':
            val = user_display_name
            auto = True
        elif not val and tf.field_type == 'typed_initials':
            val = user_initials
            auto = True
        elif not val and tf.field_type == 'date':
            val = today_date
            auto = True
        filled = tf.id in typed_values and bool((typed_values.get(tf.id) or '').strip())
        if auto and val and not filled:
            filled = False  # still need user to confirm step unless already saved
        elif auto and tf.id in typed_values:
            filled = bool(val)

        steps.append({
            'wizard_id': f'typed:{tf.id}',
            'kind': 'typed',
            'db_id': tf.id,
            'field_type': tf.field_type,
            'wizard_type': wtype,
            'label': (tf.field_label or 'Field').strip(),
            'section': '',
            'page': tf.page_number,
            'required': bool(tf.is_required),
            'hint': (tf.placeholder or '').strip()[:500],
            'value': val,
            'filled': filled or (auto and tf.field_type in ('typed_name', 'typed_initials', 'date') and tf.id in typed_values),
            'auto_value': val if auto else '',
        })

    for sf in signature_fields:
        filled = sf.id in signed_field_ids
        steps.append({
            'wizard_id': f'sig:{sf.id}',
            'kind': 'signature',
            'db_id': sf.id,
            'wizard_type': 'signature',
            'label': (sf.field_label or 'Signature').strip(),
            'section': '',
            'page': sf.page_number,
            'required': bool(sf.is_required),
            'hint': '',
            'value': '',
            'filled': filled,
        })

    def _generic_step_order(s: dict) -> tuple:
        wid = s.get('wizard_id') or ''
        page = s.get('page') or 1
        if wid.startswith('typed:'):
            db_id = s.get('db_id')
            y, x = 0.0, 0.0
            if db_id and db_id in tf_sort:
                _, y, x = tf_sort[db_id]
            return (page, y, x, 1, wid)
        if wid.startswith('sig:'):
            db_id = s.get('db_id')
            y, x = 0.0, 0.0
            if db_id and db_id in sig_sort:
                _, y, x = sig_sort[db_id]
            return (page, y, x, 2, wid)
        if wid.startswith('choice:'):
            return (page, 0.0, 0.0, 0, wid)
        return (page, 0.0, 0.0, 3, wid)

    steps.sort(key=_generic_step_order)
    return steps


def wizard_required_steps_complete(steps: list[dict[str, Any]]) -> bool:
    """True when every required wizard step has a saved value (optional steps may be empty)."""
    return all(s.get('filled') for s in steps if s.get('required'))


def apply_wizard_field_skip(step: dict[str, Any], persist_fn) -> None:
    """
    Persist skip for an optional wizard step. persist_fn(typed_field, value) saves one field.
    """
    skip_val = step.get('skip_value') or wizard_skip_value_for_step(step)
    kind = step.get('kind')
    if kind == 'typed':
        persist_fn(step['db_id'], skip_val if skip_val else '')
    elif kind == 'choice_group':
        for opt in step.get('options') or []:
            persist_fn(opt['field_id'], '')
    # Optional signatures: nothing to save.


def first_incomplete_wizard_index(steps: list[dict[str, Any]]) -> int:
    for i, step in enumerate(steps):
        if not step.get('filled'):
            return i
    return max(0, len(steps) - 1)


def wizard_progress_counts(steps: list[dict[str, Any]]) -> tuple[int, int]:
    total = len(steps)
    done = sum(1 for s in steps if s.get('filled'))
    return done, total


def wizard_required_progress_counts(steps: list[dict[str, Any]]) -> tuple[int, int]:
    required = [s for s in steps if s.get('required')]
    done = sum(1 for s in required if s.get('filled'))
    return done, len(required)
