"""Admin PDF test-form wizard session helpers."""
from __future__ import annotations

from flask import current_app, session

from pdf_form_wizard import (
    FITZ_AVAILABLE as PDF_WIZARD_FITZ_AVAILABLE,
    load_wizard_state,
    save_wizard_state,
)

def _test_form_wizard_state():
    sid = session.get('test_form_wizard_id')
    if not sid:
        return None
    return load_wizard_state(current_app.config['UPLOAD_FOLDER'], sid)

def _test_form_wizard_save(state):
    save_wizard_state(current_app.config['UPLOAD_FOLDER'], state)
    session['test_form_wizard_id'] = state['session_id']

def _test_form_field_is_last4(field):
    if not field:
        return False
    if field.get('type') == 'last4':
        return True
    label = (field.get('label') or '').lower()
    return (
        'social security' in label
        or 'ssn' in label
        or ('tax id' in label and 'number' in label)
    )

def _test_form_last4_digits(value):
    val = (value or '').strip().upper()
    if val.startswith('XXX-XX-'):
        return re.sub(r'\D', '', val[7:])[:4]
    digits = re.sub(r'\D', '', val)
    return digits[-4:] if len(digits) > 4 else digits[:4]

def _refresh_test_form_field_positions(state):
    """Re-map field rectangles from the PDF (fixes placement after layout engine updates)."""
    path = state.get('pdf_path')
    if not path or not PDF_WIZARD_FITZ_AVAILABLE:
        return state
    try:
        fresh = extract_fields_from_layout(path)
    except Exception:
        return state
    lookup = {}
    for f in fresh:
        lookup[(f['label'].lower().strip(), f['page'], f.get('type'))] = f
    for f in state.get('fields') or []:
        key = (f['label'].lower().strip(), f['page'], f.get('type'))
        hit = lookup.get(key)
        if hit and hit.get('rect'):
            f['rect'] = hit['rect']
    return state

