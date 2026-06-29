"""Human-readable wizard labels for known PDF forms (keyed by AcroForm widget name)."""
from __future__ import annotations

from typing import Any, Callable, Optional


def acro_key(placeholder: Optional[str]) -> str:
    ph = (placeholder or '').strip()
    if ph.startswith('acro:'):
        return ph[5:]
    return ph


def is_employee_information_form(typed_fields: list) -> bool:
    keys = {acro_key(getattr(tf, 'placeholder', None)) for tf in typed_fields}
    return 'Name3_es_:signer:fullname' in keys and 'Name5_es_:signer:fullname' in keys


# (label, section, hint)
EE_TYPED_LABELS: dict[str, tuple[str, str, str]] = {
    'Hire Date': ('Hire date', 'Personal information', ''),
    'Name3_es_:signer:fullname': (
        'Employee name', 'Personal information',
        'Your full legal name as it appears on payroll records.',
    ),
    'Text12': ('Phone number', 'Personal information', ''),
    'Text13': ('Home address', 'Personal information', ''),
    'EMail8_es_:signer:email': ('Email address', 'Personal information', ''),
    'Date9_es_:signer:date': ('Birthdate', 'Personal information', ''),
    'Text14': (
        'Social Security Number', 'Personal information',
        'Enter only the last 4 digits of your SSN or Tax ID.',
    ),
    'Name4_es_:signer:fullname': ('Primary emergency contact — name', 'Emergency contacts', ''),
    'Text15': (
        'Primary emergency contact — relationship to you', 'Emergency contacts',
        'e.g. Spouse, Parent, Friend',
    ),
    'Text16': ('Primary emergency contact — home phone', 'Emergency contacts', ''),
    'Text17': ('Primary emergency contact — cell phone', 'Emergency contacts', ''),
    'Text18': ('Primary emergency contact — work phone', 'Emergency contacts', ''),
    'Text19': ('Secondary emergency contact — name', 'Emergency contacts', ''),
    'Text23': ('Secondary emergency contact — relationship to you', 'Emergency contacts', ''),
    'Text20': ('Secondary emergency contact — home phone', 'Emergency contacts', ''),
    'Text21': ('Secondary emergency contact — cell phone', 'Emergency contacts', ''),
    'Text22': ('Secondary emergency contact — work phone', 'Emergency contacts', ''),
    'Carrier Name': (
        'Other health plan — carrier name', 'Medical information',
        'If covered under another group health plan, enter the carrier name.',
    ),
    'undefined': ('Other health plan — policy number', 'Medical information', ''),
    'Relationship': ('Other health plan — relationship to policyholder', 'Medical information', ''),
    'Name5_es_:signer:fullname': (
        'Dependent 1 — name', 'Dependent 1',
        'Full name of your first dependent.',
    ),
    'Date11_es_:signer:date': ('Dependent 1 — birthdate', 'Dependent 1', ''),
    'Text25': ('Dependent 1 — relationship to you', 'Dependent 1', 'e.g. Child, Spouse'),
    'Text24': ('Dependent 1 — Social Security Number', 'Dependent 1', 'Last 4 digits only, if applicable.'),
    'Text26': ('Dependent 1 — address', 'Dependent 1', 'Only if this dependent does not live with you.'),
    'Name6_es_:signer:fullname': ('Dependent 2 — name', 'Dependent 2', 'Leave blank if not applicable.'),
    'Text27': ('Dependent 2 — birthdate', 'Dependent 2', ''),
    'Text28': ('Dependent 2 — relationship to you', 'Dependent 2', ''),
    'Text29': ('Dependent 2 — Social Security Number', 'Dependent 2', 'Last 4 digits only, if applicable.'),
    'Text30': ('Dependent 2 — address', 'Dependent 2', 'Only if this dependent does not live with you.'),
    'Name7_es_:signer:fullname': ('Dependent 3 — name', 'Dependent 3', 'Leave blank if not applicable.'),
    'Date10_es_:signer:date': ('Dependent 3 — birthdate', 'Dependent 3', ''),
    'Text31': ('Dependent 3 — relationship to you', 'Dependent 3', ''),
    'Text32': ('Dependent 3 — Social Security Number', 'Dependent 3', 'Last 4 digits only, if applicable.'),
    'Text33': ('Dependent 3 — address', 'Dependent 3', 'Only if this dependent does not live with you.'),
    'Date': ('Employee signature — date', 'Signatures', ''),
    'Date_2': ('Manager signature — date', 'Signatures', 'Your manager completes this when reviewing your form.'),
}

EE_CHOICE_GROUPS: dict[str, tuple[str, str, str, dict[str, str]]] = {
    'ee_marital': ('Marital status', 'Personal information', '', {'Single': 'Single', 'Married': 'Married'}),
    'ee_gender': ('Gender', 'Personal information', '', {'Male': 'Male', 'Female': 'Female'}),
    'ee_race': (
        'Race / ethnicity (EEOC)', 'Personal information',
        'Select the option that best describes you. Used for EEO reporting only.',
        {
            'BlackAfrican American': 'Black / African American',
            'American Indian': 'American Indian',
            'Asian': 'Asian',
            'Native HawaiianPacific Islanders': 'Native Hawaiian / Pacific Islander',
            'HispanicSpanish': 'Hispanic / Spanish origin',
            'White Caucasian': 'White (Caucasian)',
        },
    ),
    'ee_tobacco': ('Are you a tobacco user?', 'Medical information', '', {'Yes': 'Yes', 'No': 'No'}),
    'ee_medicare': ('Are you enrolled in Medicare?', 'Medical information', '', {'Yes_2': 'Yes', 'No_2': 'No'}),
    'ee_medicaid': ('Are you enrolled in Medicaid?', 'Medical information', '', {'Check Box34': 'Yes', 'Check Box35': 'No'}),
    'ee_group_health': (
        'Are you covered under another group health plan?', 'Medical information', '',
        {'Check Box36': 'Yes', 'Check Box37': 'No'},
    ),
    'ee_dep1_gender': ('Dependent 1 — gender', 'Dependent 1', '', {'Male_2': 'Male', 'Check Box40': 'Female'}),
}

EE_GENDER_CHECKBOX_ACROS: dict[str, tuple[str, str, str]] = {
    'Male_3': ('Dependent 2 — male', 'Dependent 2', 'Check if this dependent is male.'),
    'Male_4': ('Dependent 3 — male', 'Dependent 3', 'Check if this dependent is male.'),
}

EE_ACK_CHECKBOXES: dict[str, tuple[str, str]] = {
    'Employee Handbook Received': (
        'Employee Handbook received',
        'Check each acknowledgement that applies to you.',
    ),
    'Harassment Training Completed': (
        'Harassment training completed',
        'Check each acknowledgement that applies to you.',
    ),
    'Technical Training Received': (
        'Technical training received',
        'Check each acknowledgement that applies to you.',
    ),
    'Hepatitis B Vaccine Declination': (
        'Hepatitis B vaccine declination',
        'Check each acknowledgement that applies to you.',
    ),
    'Safety Data SheetsSafety Handbook Reviewed': (
        'Safety Data Sheets / Safety Handbook reviewed',
        'Check each acknowledgement that applies to you.',
    ),
    'Urethane Liner Safety Received Rhino Technician only': (
        'Urethane Liner Safety received (Rhino Technicians only)',
        'Check each acknowledgement that applies to you.',
    ),
}

EE_SIGNATURE_LABELS: dict[str, tuple[str, str]] = {
    'employee': ('Employee signature', 'Signatures'),
    'manager': ('Manager signature', 'Signatures'),
}

WIZARD_SKIP_NA = 'N/A'

# AcroForm widget names the employee must complete (cannot skip).
EE_REQUIRED_ACROS = {
    'Hire Date',
    'Name3_es_:signer:fullname',
    'Text12',
    'Text13',
    'EMail8_es_:signer:email',
    'Date9_es_:signer:date',
    'Text14',
    'Name4_es_:signer:fullname',
    'Text15',
    'Text17',
    'Date',
}

EE_REQUIRED_CHOICE_GROUPS = {
    'ee_marital',
    'ee_gender',
    'ee_race',
    'ee_tobacco',
    'ee_medicare',
    'ee_medicaid',
    'ee_group_health',
}

EE_REQUIRED_ACK_ACROS = {
    'Employee Handbook Received',
    'Harassment Training Completed',
    'Technical Training Received',
    'Hepatitis B Vaccine Declination',
    'Safety Data SheetsSafety Handbook Reviewed',
}

EE_PHONE_ACROS = {
    'Text12', 'Text16', 'Text17', 'Text18', 'Text20', 'Text21', 'Text22',
}

EE_LAST4_ACROS = {'Text14', 'Text24', 'Text29', 'Text32'}

EE_HAS_DEPENDENTS_GATE_ID = 'gate:has_dependents'

EE_DEPENDENT_ACROS = frozenset({
    'Name5_es_:signer:fullname',
    'Date11_es_:signer:date',
    'Text25',
    'Text24',
    'Text26',
    'Name6_es_:signer:fullname',
    'Text27',
    'Text28',
    'Text29',
    'Text30',
    'Name7_es_:signer:fullname',
    'Date10_es_:signer:date',
    'Text31',
    'Text32',
    'Text33',
    'Male_2',
    'Male_3',
    'Male_4',
    'Check Box40',
})

EE_DEPENDENT_CHOICE_GROUPS = frozenset({'ee_dep1_gender'})

EE_ACK_GROUP_ID = 'ack:ee_acknowledgements'

EE_ACK_ORDER = [
    'Employee Handbook Received',
    'Harassment Training Completed',
    'Technical Training Received',
    'Hepatitis B Vaccine Declination',
    'Safety Data SheetsSafety Handbook Reviewed',
    'Urethane Liner Safety Received Rhino Technician only',
]

EE_STEP_ORDER = [
    'Hire Date', 'Name3_es_:signer:fullname', 'Text12', 'Text13', 'EMail8_es_:signer:email',
    'Date9_es_:signer:date', 'Text14',
    'ee_marital', 'ee_gender', 'ee_race',
    'Name4_es_:signer:fullname', 'Text15', 'Text16', 'Text17', 'Text18',
    'Text19', 'Text23', 'Text20', 'Text21', 'Text22',
    'ee_tobacco', 'ee_medicare', 'ee_medicaid', 'ee_group_health',
    'Carrier Name', 'undefined', 'Relationship',
    EE_HAS_DEPENDENTS_GATE_ID,
    'Name5_es_:signer:fullname', 'ee_dep1_gender', 'Date11_es_:signer:date',
    'Text25', 'Text24', 'Text26',
    'Name6_es_:signer:fullname', 'Male_3', 'Text27', 'Text28', 'Text29', 'Text30',
    'Name7_es_:signer:fullname', 'Male_4', 'Date10_es_:signer:date',
    'Text31', 'Text32', 'Text33',
    EE_ACK_GROUP_ID,
    'sig:employee', 'Date', 'sig:manager', 'Date_2',
]


def ee_field_is_required(
    *,
    acro: Optional[str] = None,
    choice_group: Optional[str] = None,
    ack_acro: Optional[str] = None,
    signature_role: Optional[str] = None,
) -> bool:
    if signature_role == 'employee':
        return True
    if signature_role == 'manager':
        return False
    if ack_acro is not None:
        return ack_acro in EE_REQUIRED_ACK_ACROS
    if choice_group is not None:
        return choice_group in EE_REQUIRED_CHOICE_GROUPS
    if acro is not None:
        if acro == 'Date_2':
            return False
        return acro in EE_REQUIRED_ACROS
    return True


def ee_id_by_acro(typed_fields: list) -> dict[str, list]:
    id_by_acro: dict[str, list] = {}
    for tf in typed_fields:
        id_by_acro.setdefault(acro_key(tf.placeholder), []).append(tf)
    return id_by_acro


# Correct choice_group per AcroForm name (fixes bad import grouping in existing DB rows).
EE_WIZARD_CHOICE_GROUP_BY_ACRO: dict[str, str] = {}
for _gid, (_lbl, _sec, _hint, _opts) in EE_CHOICE_GROUPS.items():
    for _acro in _opts:
        EE_WIZARD_CHOICE_GROUP_BY_ACRO[_acro] = _gid

EE_INDEPENDENT_CHECKBOX_ACROS = frozenset(EE_ACK_CHECKBOXES.keys()) | frozenset(EE_GENDER_CHECKBOX_ACROS.keys())


def repair_employee_information_field_groups(typed_fields: list) -> bool:
    """
    Fix PDF import mistakes where unrelated checkboxes share one choice_group
    (e.g. Employee Handbook + Harassment Training, or Tobacco + Medicare Yes/No).
    """
    changed = False
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice':
            continue
        ak = acro_key(tf.placeholder)
        if ak in EE_INDEPENDENT_CHECKBOX_ACROS:
            if tf.choice_group is not None:
                tf.choice_group = None
                changed = True
            continue
        expected = EE_WIZARD_CHOICE_GROUP_BY_ACRO.get(ak)
        if expected and tf.choice_group != expected:
            tf.choice_group = expected
            changed = True
    return changed


def resolve_has_dependents_answer(
    session_val: Optional[str],
    typed_values: dict[int, str],
    typed_fields: list,
) -> Optional[str]:
    """Session answer, or infer from saved dependent field values."""
    ans = (session_val or '').strip().lower()
    if ans in ('yes', 'no'):
        return ans
    id_by_acro = ee_id_by_acro(typed_fields)
    for ak in ('Name5_es_:signer:fullname', 'Name6_es_:signer:fullname', 'Name7_es_:signer:fullname'):
        for tf in id_by_acro.get(ak, []):
            val = (typed_values.get(tf.id) or '').strip()
            if val and val.upper() != WIZARD_SKIP_NA:
                return 'yes'
    dep_values = []
    for ak in EE_DEPENDENT_ACROS:
        if ak in EE_INDEPENDENT_CHECKBOX_ACROS or ak.startswith('Male') or ak == 'Check Box40':
            continue
        for tf in id_by_acro.get(ak, []):
            if tf.field_type == 'checkbox_choice':
                continue
            dep_values.append((typed_values.get(tf.id) or '').strip())
    if dep_values and all(v.upper() == WIZARD_SKIP_NA for v in dep_values if v):
        return 'no'
    return None


def is_ee_dependent_wizard_step(step: dict[str, Any]) -> bool:
    wid = (step.get('wizard_id') or '').strip()
    if wid == EE_HAS_DEPENDENTS_GATE_ID:
        return False
    if wid.startswith('choice:'):
        group_id = wid.split(':', 1)[1]
        if group_id in EE_DEPENDENT_CHOICE_GROUPS:
            return True
    if step.get('ee_acro') in EE_DEPENDENT_ACROS:
        return True
    return False


def build_ee_ack_group_step(
    id_by_acro: dict[str, list],
    typed_values: dict[int, str],
) -> dict[str, Any]:
    """Single wizard step for all training/handbook acknowledgements."""
    options: list[dict[str, Any]] = []
    page = 2
    sort_y = 0.0
    for ak in EE_ACK_ORDER:
        label, hint = EE_ACK_CHECKBOXES.get(ak, (ak, ''))
        required = ee_field_is_required(ack_acro=ak)
        for tf in id_by_acro.get(ak, []):
            val = (typed_values.get(tf.id) or '').strip().upper()
            is_checked = val == 'X'
            page = tf.page_number or page
            sort_y = max(sort_y, tf.y_position or 0.0)
            options.append({
                'field_id': tf.id,
                'label': label,
                'required': required,
                'checked': is_checked,
                'acro': ak,
            })
    required_opts = [o for o in options if o.get('required')]
    filled = bool(required_opts) and all(o.get('checked') for o in required_opts)
    return {
        'wizard_id': EE_ACK_GROUP_ID,
        'kind': 'ack_group',
        'wizard_type': 'checkbox_group',
        'label': 'Training and handbook acknowledgements',
        'section': 'Acknowledgements',
        'page': page,
        'sort_y': sort_y,
        'sort_x': 0,
        'required': bool(required_opts),
        'skip_value': '',
        'hint': (
            'Check each item that applies to you. Required items are marked with an asterisk (*).'
        ),
        'value': '',
        'filled': filled,
        'options': options,
    }


def build_has_dependents_gate_step(has_dependents: Optional[str] = None) -> dict[str, Any]:
    ans = (has_dependents or '').strip().lower()
    return {
        'wizard_id': EE_HAS_DEPENDENTS_GATE_ID,
        'kind': 'gate',
        'wizard_type': 'yes_no',
        'label': 'Do you have any dependents to report?',
        'section': 'Dependents',
        'page': 2,
        'sort_y': 0,
        'sort_x': 0,
        'required': True,
        'skip_value': '',
        'hint': (
            'Select Yes if you need to list dependents on this form. '
            'If you select No, all dependent fields will be skipped automatically.'
        ),
        'value': ans,
        'filled': ans in ('yes', 'no'),
        'options': [
            {'value': 'yes', 'label': 'Yes, I have dependents to report'},
            {'value': 'no', 'label': 'No, I do not have any dependents'},
        ],
    }


def filter_ee_wizard_steps(
    steps: list[dict[str, Any]],
    has_dependents: Optional[str],
) -> list[dict[str, Any]]:
    """Hide dependent detail steps until user answers Yes; hide entirely after No."""
    ans = (has_dependents or '').strip().lower() if has_dependents else None
    if ans == 'yes':
        return steps
    return [s for s in steps if not is_ee_dependent_wizard_step(s)]


def apply_ee_dependents_not_applicable(persist_fn, id_by_acro: dict[str, list]) -> None:
    """Mark all dependent PDF fields N/A (or blank for checkboxes) when user has no dependents."""
    seen: set[int] = set()
    for ak in EE_DEPENDENT_ACROS:
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            if tf.field_type == 'checkbox_choice':
                persist_fn(tf.id, '')
            else:
                persist_fn(tf.id, WIZARD_SKIP_NA)
    for group_id in EE_DEPENDENT_CHOICE_GROUPS:
        opt_map = EE_CHOICE_GROUPS.get(group_id, (None, None, None, {}))[3]
        for ak in opt_map:
            for tf in id_by_acro.get(ak, []):
                if tf.id in seen:
                    continue
                seen.add(tf.id)
                persist_fn(tf.id, '')


def clear_ee_dependents_values(persist_fn, id_by_acro: dict[str, list]) -> None:
    """Clear dependent fields when user changes answer from No to Yes."""
    seen: set[int] = set()
    for ak in EE_DEPENDENT_ACROS:
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            persist_fn(tf.id, '')
    for group_id in EE_DEPENDENT_CHOICE_GROUPS:
        opt_map = EE_CHOICE_GROUPS.get(group_id, (None, None, None, {}))[3]
        for ak in opt_map:
            for tf in id_by_acro.get(ak, []):
                if tf.id in seen:
                    continue
                seen.add(tf.id)
                persist_fn(tf.id, '')


def wizard_skip_value_for_step(step: dict[str, Any]) -> str:
    """Value stored when the user skips an optional wizard step."""
    if step.get('required'):
        return ''
    wt = step.get('wizard_type') or step.get('field_type') or ''
    if wt in ('text', 'phone', 'date', 'last4', 'number'):
        return WIZARD_SKIP_NA
    return ''


def wizard_value_counts_as_filled(value: str, *, wizard_type: str = '', is_checkbox: bool = False) -> bool:
    val = (value or '').strip()
    if is_checkbox:
        return val.upper() == 'X'
    if not val:
        return False
    if val.upper() == WIZARD_SKIP_NA:
        return True
    return True


def _field_sort_key(tf) -> tuple:
    return (tf.page_number or 1, tf.y_position or 0, tf.x_position or 0, tf.id or 0)


def build_ee_information_wizard_steps(
    typed_fields: list,
    signature_fields: list,
    typed_values: dict[int, str],
    signed_field_ids: set[int],
    user_display_name: str,
    user_initials: str,
    today_date: str,
    wizard_type_for_typed: Callable[[str, bool], str],
    phone_like_fn: Callable,
    has_dependents: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build ordered, labeled wizard steps for the Employee Information PDF."""
    acro_by_id = {tf.id: acro_key(tf.placeholder) for tf in typed_fields}
    id_by_acro: dict[str, list] = {}
    for tf in typed_fields:
        id_by_acro.setdefault(acro_by_id[tf.id], []).append(tf)

    ee_choice_member_ids: set[int] = set()
    for _gid, (_lbl, _sec, _hint, opts) in EE_CHOICE_GROUPS.items():
        for ak in opts:
            for tf in id_by_acro.get(ak, []):
                ee_choice_member_ids.add(tf.id)

    steps: list[dict[str, Any]] = []
    seen_step_keys: set[str] = set()

    def _choice_step(group_id: str) -> Optional[dict[str, Any]]:
        if group_id in seen_step_keys:
            return None
        cfg = EE_CHOICE_GROUPS.get(group_id)
        if not cfg:
            return None
        label, section, hint, opt_map = cfg
        options = []
        members = []
        for ak, opt_label in opt_map.items():
            for tf in id_by_acro.get(ak, []):
                members.append(tf)
                options.append({'field_id': tf.id, 'label': opt_label})
        if not options:
            return None
        seen_step_keys.add(group_id)
        selected_id: Optional[int] = None
        for tf in members:
            if (typed_values.get(tf.id) or '').strip().upper() == 'X':
                selected_id = tf.id
                break
        page = min(tf.page_number for tf in members)
        sort_y = min(tf.y_position for tf in members)
        required = ee_field_is_required(choice_group=group_id)
        return {
            'wizard_id': f'choice:{group_id}',
            'kind': 'choice_group',
            'label': label,
            'section': section,
            'page': page,
            'sort_y': sort_y,
            'sort_x': 0,
            'required': required,
            'skip_value': '',
            'hint': hint,
            'options': options,
            'value': str(selected_id) if selected_id else '',
            'filled': selected_id is not None,
        }

    def _typed_step(tf) -> dict[str, Any]:
        ak = acro_by_id[tf.id]
        label, section, hint = EE_TYPED_LABELS.get(
            ak, (tf.field_label or 'Field', '', (tf.placeholder or '')[:500]),
        )
        phone_like = ak in EE_PHONE_ACROS
        wtype = wizard_type_for_typed(tf.field_type, phone_like)
        if ak in EE_LAST4_ACROS or tf.field_type == 'last4':
            wtype = 'last4'
        val = (typed_values.get(tf.id) or '').strip()
        auto = False
        if not val and tf.field_type == 'typed_name':
            val = user_display_name
            auto = True
        elif not val and tf.field_type == 'typed_initials':
            val = user_initials
            auto = True
        elif not val and tf.field_type == 'date' and ak == 'Date':
            val = today_date
            auto = True
        required = ee_field_is_required(acro=ak)
        skip_val = wizard_skip_value_for_step({
            'required': required,
            'wizard_type': wtype,
            'field_type': tf.field_type,
        })
        filled = wizard_value_counts_as_filled(val, wizard_type=wtype)
        if auto and tf.id in typed_values:
            filled = bool(val)
        return {
            'wizard_id': f'typed:{tf.id}',
            'kind': 'typed',
            'db_id': tf.id,
            'field_type': tf.field_type,
            'wizard_type': wtype,
            'label': label.strip(),
            'section': section,
            'page': tf.page_number,
            'sort_y': tf.y_position,
            'sort_x': tf.x_position,
            'required': required,
            'skip_value': skip_val,
            'hint': (hint or '')[:500],
            'value': val,
            'filled': filled,
            'auto_value': val if auto else '',
            'ee_acro': ak,
        }

    def _ack_step(tf) -> dict[str, Any]:
        ak = acro_by_id[tf.id]
        if ak in EE_GENDER_CHECKBOX_ACROS:
            label, section, hint = EE_GENDER_CHECKBOX_ACROS[ak]
        else:
            label, hint = EE_ACK_CHECKBOXES.get(ak, (tf.field_label or 'Acknowledgement', ''))
            section = 'Acknowledgements'
        val = (typed_values.get(tf.id) or '').strip().upper()
        required = ee_field_is_required(ack_acro=ak)
        is_checked = val == 'X'
        return {
            'wizard_id': f'typed:{tf.id}',
            'kind': 'typed',
            'db_id': tf.id,
            'field_type': 'checkbox_choice',
            'wizard_type': 'checkbox',
            'label': label,
            'section': section,
            'page': tf.page_number,
            'sort_y': tf.y_position,
            'sort_x': tf.x_position,
            'required': required,
            'skip_value': '',
            'hint': hint,
            'value': 'X' if is_checked else '',
            'filled': is_checked,
            'ee_acro': ak,
        }

    sig_sorted = sorted(signature_fields, key=_field_sort_key)

    for step_key in EE_STEP_ORDER:
        if step_key == EE_HAS_DEPENDENTS_GATE_ID:
            steps.append(build_has_dependents_gate_step(has_dependents))
            continue
        if step_key == EE_ACK_GROUP_ID:
            ack_step = build_ee_ack_group_step(id_by_acro, typed_values)
            if ack_step.get('options'):
                steps.append(ack_step)
            continue
        if step_key in EE_CHOICE_GROUPS:
            step = _choice_step(step_key)
            if step:
                steps.append(step)
            continue
        if step_key == 'sig:employee' and sig_sorted:
            sf = sig_sorted[0]
            label, section = EE_SIGNATURE_LABELS['employee']
            steps.append({
                'wizard_id': f'sig:{sf.id}',
                'kind': 'signature',
                'db_id': sf.id,
                'wizard_type': 'signature',
                'label': label,
                'section': section,
                'page': sf.page_number,
                'sort_y': sf.y_position,
                'sort_x': sf.x_position,
                'required': ee_field_is_required(signature_role='employee'),
                'skip_value': '',
                'hint': '',
                'value': '',
                'filled': sf.id in signed_field_ids,
            })
            continue
        if step_key == 'sig:manager' and len(sig_sorted) > 1:
            sf = sig_sorted[1]
            label, section = EE_SIGNATURE_LABELS['manager']
            steps.append({
                'wizard_id': f'sig:{sf.id}',
                'kind': 'signature',
                'db_id': sf.id,
                'wizard_type': 'signature',
                'label': label,
                'section': section,
                'page': sf.page_number,
                'sort_y': sf.y_position,
                'sort_x': sf.x_position,
                'required': ee_field_is_required(signature_role='manager'),
                'skip_value': '',
                'hint': 'Your manager will sign here when reviewing your form.',
                'value': '',
                'filled': sf.id in signed_field_ids,
            })
            continue
        for tf in id_by_acro.get(step_key, []):
            if tf.field_type == 'checkbox_choice':
                if tf.id in ee_choice_member_ids:
                    continue
                ak = acro_by_id[tf.id]
                if ak in EE_ACK_ORDER:
                    continue
                if ak in EE_GENDER_CHECKBOX_ACROS:
                    key = f'ack:{tf.id}'
                    if key not in seen_step_keys:
                        seen_step_keys.add(key)
                        steps.append(_ack_step(tf))
                continue
            key = f'typed:{tf.id}'
            if key not in seen_step_keys:
                seen_step_keys.add(key)
                steps.append(_typed_step(tf))

    order_index = {key: i for i, key in enumerate(EE_STEP_ORDER)}

    def _step_order(s: dict) -> tuple:
        wid = s.get('wizard_id') or ''
        if wid.startswith('choice:'):
            gid = wid.split(':', 1)[1]
            return (order_index.get(gid, 999), 0, s.get('sort_y') or 0)
        if wid.startswith('sig:'):
            lbl = s.get('label') or ''
            sk = 'sig:manager' if 'Manager' in lbl else 'sig:employee'
            return (order_index.get(sk, 999), 0, s.get('sort_y') or 0)
        if wid == EE_HAS_DEPENDENTS_GATE_ID:
            return (order_index.get(EE_HAS_DEPENDENTS_GATE_ID, 999), 0, 0)
        if wid == EE_ACK_GROUP_ID:
            return (order_index.get(EE_ACK_GROUP_ID, 999), 0, s.get('sort_y') or 0)
        db_id = s.get('db_id')
        if db_id and s.get('kind') != 'signature':
            ak = acro_by_id.get(db_id, '')
            return (order_index.get(ak, 999), s.get('sort_x') or 0, s.get('sort_y') or 0)
        return (999, s.get('sort_y') or 0, s.get('sort_x') or 0)

    steps.sort(key=_step_order)
    return steps
