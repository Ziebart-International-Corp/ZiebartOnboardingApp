"""Human-readable wizard labels for known PDF forms (keyed by AcroForm widget name)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from ee_pdf_field_map import (
    EE_ACRO_CHOICE_GROUPS,
    EE_ACRO_TO_CHOICE_GROUP,
    EE_ACK_ACROS,
    EE_FORM_MARKER_ACROS,
    EE_SIGNATURE_ACROS,
    canonical_acro,
)


def acro_key(placeholder: Optional[str]) -> str:
    ph = (placeholder or '').strip()
    if ph.startswith('acro:'):
        return canonical_acro(ph[5:])
    return canonical_acro(ph)


def is_employee_information_form(typed_fields: list) -> bool:
    keys = {acro_key(getattr(tf, 'placeholder', None)) for tf in typed_fields}
    return EE_FORM_MARKER_ACROS.issubset(keys)


# (label, section, hint) — keys are canonical AcroForm names
EE_TYPED_LABELS: dict[str, tuple[str, str, str]] = {
    'Employee_Hire_Date': ('Hire date', 'Personal information', ''),
    'Employee_Name': (
        'Employee name', 'Personal information',
        'Your full legal name as it appears on payroll records.',
    ),
    'Employee_Phone_Number': ('Phone number', 'Personal information', ''),
    'Employee_Address': ('Home address', 'Personal information', ''),
    'Employee_Email': ('Email address', 'Personal information', ''),
    'Employee_Birthdate': ('Birthdate', 'Personal information', ''),
    'Employee_SSN_Last4': (
        'Social Security Number', 'Personal information',
        'Enter only the last 4 digits of your SSN or Tax ID.',
    ),
    'Emergency_Contact_1_Name': ('Primary emergency contact — name', 'Emergency contacts', ''),
    'Emergency_Contact_1_Relationship': (
        'Primary emergency contact — relationship to you', 'Emergency contacts',
        'e.g. Spouse, Parent, Friend',
    ),
    'Emergency_Contact_1_Home_Phone': ('Primary emergency contact — home phone', 'Emergency contacts', ''),
    'Emergency_Contact_1_Cell_Phone': ('Primary emergency contact — cell phone', 'Emergency contacts', ''),
    'Emergency_Contact_1_Work_Phone': ('Primary emergency contact — work phone', 'Emergency contacts', ''),
    'Emergency_Contact_2_Name': ('Secondary emergency contact — name', 'Emergency contacts', ''),
    'Emergency_Contact_2_Relationship': ('Secondary emergency contact — relationship to you', 'Emergency contacts', ''),
    'Emergency_Contact_2_Home_Phone': ('Secondary emergency contact — home phone', 'Emergency contacts', ''),
    'Emergency_Contact_2_Cell_Phone': ('Secondary emergency contact — cell phone', 'Emergency contacts', ''),
    'Emergency_Contact_2_Work_Phone': ('Secondary emergency contact — work phone', 'Emergency contacts', ''),
    'Other_Health_Plan_Carrier_Name': (
        'Other health plan — carrier name', 'Medical information',
        'If covered under another group health plan, enter the carrier name.',
    ),
    'Other_Health_Plan_Policy_Number': ('Other health plan — policy number', 'Medical information', ''),
    'Other_Health_Plan_Policyholder_Name': ('Other health plan — policyholder name', 'Medical information', ''),
    'Other_Health_Plan_Relationship': (
        'Other health plan — relationship to policyholder', 'Medical information', '',
    ),
    'Dependent_1_Name': ('Dependent 1 — name', 'Dependent 1', 'Full name of your first dependent.'),
    'Dependent_1_Birthdate': ('Dependent 1 — birthdate', 'Dependent 1', ''),
    'Dependent_1_Relationship': ('Dependent 1 — relationship to you', 'Dependent 1', 'e.g. Child, Spouse'),
    'Dependent_1_SSN_Last4': ('Dependent 1 — Social Security Number', 'Dependent 1', 'Last 4 digits only, if applicable.'),
    'Dependent_1_Address': (
        'Dependent 1 — address', 'Dependent 1', 'Only if this dependent does not live with you.',
    ),
    'Dependent_2_Name': ('Dependent 2 — name', 'Dependent 2', 'Leave blank if not applicable.'),
    'Dependent_2_Birthdate': ('Dependent 2 — birthdate', 'Dependent 2', ''),
    'Dependent_2_Relationship': ('Dependent 2 — relationship to you', 'Dependent 2', ''),
    'Dependent_2_SSN_Last4': ('Dependent 2 — Social Security Number', 'Dependent 2', 'Last 4 digits only, if applicable.'),
    'Dependent_2_Address': ('Dependent 2 — address', 'Dependent 2', 'Only if this dependent does not live with you.'),
    'Dependent_3_Name': ('Dependent 3 — name', 'Dependent 3', 'Leave blank if not applicable.'),
    'Dependent_3_Birthdate': ('Dependent 3 — birthdate', 'Dependent 3', ''),
    'Dependent_3_Relationship': ('Dependent 3 — relationship to you', 'Dependent 3', ''),
    'Dependent_3_SSN_Last4': ('Dependent 3 — Social Security Number', 'Dependent 3', 'Last 4 digits only, if applicable.'),
    'Dependent_3_Address': ('Dependent 3 — address', 'Dependent 3', 'Only if this dependent does not live with you.'),
    'Employee_Signature_Date': ('Employee signature — date', 'Signatures', ''),
    'Manager_Signature_Date': (
        'Manager signature — date', 'Signatures', 'Your manager completes this when reviewing your form.',
    ),
}

# Choice groups: group_id -> (label, section, hint, {acro: option label})
EE_CHOICE_GROUPS: dict[str, tuple[str, str, str, dict[str, str]]] = {
    'ee_marital': (
        'Marital status', 'Personal information', '',
        {'Employee_Marital_Status_Single': 'Single', 'Employee_Marital_Status_Married': 'Married'},
    ),
    'ee_gender': (
        'Gender', 'Personal information', '',
        {'Employee_Gender_Male': 'Male', 'Employee_Gender_Female': 'Female'},
    ),
    'ee_race': (
        'Race / ethnicity (EEOC)', 'Personal information',
        'Select the option that best describes you. Used for EEO reporting only.',
        {
            'Race_Black_African_American': 'Black / African American',
            'Race_American_Indian': 'American Indian',
            'Race_Asian': 'Asian',
            'Race_Native_Hawaiian_Pacific_Islander': 'Native Hawaiian / Pacific Islander',
            'Race_Hispanic_Spanish': 'Hispanic / Spanish origin',
            'Race_White_Caucasian': 'White (Caucasian)',
        },
    ),
    'ee_tobacco': ('Are you a tobacco user?', 'Medical information', '', {'Tobacco_User_Yes': 'Yes', 'Tobacco_User_No': 'No'}),
    'ee_medicare': ('Are you enrolled in Medicare?', 'Medical information', '', {'Medicare_Yes': 'Yes', 'Medicare_No': 'No'}),
    'ee_medicaid': ('Are you enrolled in Medicaid?', 'Medical information', '', {'Medicaid_Yes': 'Yes', 'Medicaid_No': 'No'}),
    'ee_group_health': (
        'Are you covered under another group health plan?', 'Medical information', '',
        {'Other_Health_Plan_Yes': 'Yes', 'Other_Health_Plan_No': 'No'},
    ),
    'ee_health_plan_relationship': (
        'Relationship to policyholder', 'Medical information', '',
        {'Other_Health_Plan_Relationship_Spouse': 'Spouse', 'Other_Health_Plan_Relationship_Child': 'Child'},
    ),
    'ee_dep1_gender': (
        'Dependent 1 — gender', 'Dependent 1', '',
        {'Dependent_1_Gender_Male': 'Male', 'Dependent_1_Gender_Female': 'Female'},
    ),
    'ee_dep2_gender': (
        'Dependent 2 — gender', 'Dependent 2', '',
        {'Dependent_2_Gender_Male': 'Male', 'Dependent_2_Gender_Female': 'Female'},
    ),
    'ee_dep3_gender': (
        'Dependent 3 — gender', 'Dependent 3', '',
        {'Dependent_3_Gender_Male': 'Male', 'Dependent_3_Gender_Female': 'Female'},
    ),
}

EE_ACK_CHECKBOXES: dict[str, tuple[str, str]] = {
    'Ack_Employee_Handbook': ('Employee Handbook received', 'Check each acknowledgement that applies to you.'),
    'Ack_Harassment_Training': ('Harassment training completed', 'Check each acknowledgement that applies to you.'),
    'Ack_Technical_Training': ('Technical training received', 'Check each acknowledgement that applies to you.'),
    'Ack_Hepatitis_B_Declination': ('Hepatitis B vaccine declination', 'Check each acknowledgement that applies to you.'),
    'Ack_Safety_Handbook_Reviewed': (
        'Safety Data Sheets / Safety Handbook reviewed', 'Check each acknowledgement that applies to you.',
    ),
    'Ack_Urethane_Liner_Safety': (
        'Urethane Liner Safety received (Rhino Technicians only)', 'Check each acknowledgement that applies to you.',
    ),
}

EE_SIGNATURE_LABELS: dict[str, tuple[str, str]] = {
    'employee': ('Employee signature', 'Signatures'),
    'manager': ('Manager signature', 'Signatures'),
}

WIZARD_SKIP_NA = 'N/A'

EE_REQUIRED_ACROS = {
    'Employee_Hire_Date', 'Employee_Name', 'Employee_Phone_Number', 'Employee_Address',
    'Employee_Email', 'Employee_Birthdate', 'Employee_SSN_Last4',
    'Emergency_Contact_1_Name', 'Emergency_Contact_1_Relationship', 'Emergency_Contact_1_Cell_Phone',
    'Employee_Signature_Date',
}

EE_REQUIRED_CHOICE_GROUPS = {
    'ee_marital', 'ee_gender', 'ee_race', 'ee_tobacco', 'ee_medicare', 'ee_medicaid', 'ee_group_health',
}

EE_REQUIRED_ACK_ACROS = {
    'Ack_Employee_Handbook', 'Ack_Harassment_Training', 'Ack_Technical_Training',
    'Ack_Hepatitis_B_Declination', 'Ack_Safety_Handbook_Reviewed',
}

EE_PHONE_ACROS = {
    'Employee_Phone_Number',
    'Emergency_Contact_1_Home_Phone', 'Emergency_Contact_1_Cell_Phone', 'Emergency_Contact_1_Work_Phone',
    'Emergency_Contact_2_Home_Phone', 'Emergency_Contact_2_Cell_Phone', 'Emergency_Contact_2_Work_Phone',
}

EE_LAST4_ACROS = {'Employee_SSN_Last4', 'Dependent_1_SSN_Last4', 'Dependent_2_SSN_Last4', 'Dependent_3_SSN_Last4'}

EE_HAS_DEPENDENTS_GATE_ID = 'gate:has_dependents'

EE_DEPENDENT_ACROS = frozenset({
    'Dependent_1_Name', 'Dependent_1_Birthdate', 'Dependent_1_Relationship',
    'Dependent_1_SSN_Last4', 'Dependent_1_Address',
    'Dependent_1_Gender_Male', 'Dependent_1_Gender_Female',
    'Dependent_2_Name', 'Dependent_2_Birthdate', 'Dependent_2_Relationship',
    'Dependent_2_SSN_Last4', 'Dependent_2_Address',
    'Dependent_2_Gender_Male', 'Dependent_2_Gender_Female',
    'Dependent_3_Name', 'Dependent_3_Birthdate', 'Dependent_3_Relationship',
    'Dependent_3_SSN_Last4', 'Dependent_3_Address',
    'Dependent_3_Gender_Male', 'Dependent_3_Gender_Female',
})

EE_DEPENDENT_CHOICE_GROUPS = frozenset({'ee_dep1_gender', 'ee_dep2_gender', 'ee_dep3_gender'})

EE_ACK_GROUP_ID = 'ack:ee_acknowledgements'
EE_ACK_ORDER = list(EE_ACK_ACROS)

EE_STEP_ORDER = [
    'Employee_Hire_Date', 'Employee_Name', 'Employee_Phone_Number', 'Employee_Address',
    'Employee_Email', 'Employee_Birthdate', 'Employee_SSN_Last4',
    'ee_marital', 'ee_gender', 'ee_race',
    'Emergency_Contact_1_Name', 'Emergency_Contact_1_Relationship',
    'Emergency_Contact_1_Home_Phone', 'Emergency_Contact_1_Cell_Phone', 'Emergency_Contact_1_Work_Phone',
    'Emergency_Contact_2_Name', 'Emergency_Contact_2_Relationship',
    'Emergency_Contact_2_Home_Phone', 'Emergency_Contact_2_Cell_Phone', 'Emergency_Contact_2_Work_Phone',
    'ee_tobacco', 'ee_medicare', 'ee_medicaid', 'ee_group_health',
    'Other_Health_Plan_Carrier_Name', 'Other_Health_Plan_Policy_Number',
    'Other_Health_Plan_Policyholder_Name', 'Other_Health_Plan_Relationship',
    'ee_health_plan_relationship',
    EE_HAS_DEPENDENTS_GATE_ID,
    'Dependent_1_Name', 'ee_dep1_gender', 'Dependent_1_Birthdate',
    'Dependent_1_Relationship', 'Dependent_1_SSN_Last4', 'Dependent_1_Address',
    'Dependent_2_Name', 'ee_dep2_gender', 'Dependent_2_Birthdate',
    'Dependent_2_Relationship', 'Dependent_2_SSN_Last4', 'Dependent_2_Address',
    'Dependent_3_Name', 'ee_dep3_gender', 'Dependent_3_Birthdate',
    'Dependent_3_Relationship', 'Dependent_3_SSN_Last4', 'Dependent_3_Address',
    EE_ACK_GROUP_ID,
    'sig:employee', 'Employee_Signature_Date', 'sig:manager', 'Manager_Signature_Date',
]

EE_WIZARD_CHOICE_GROUP_BY_ACRO = dict(EE_ACRO_TO_CHOICE_GROUP)
EE_INDEPENDENT_CHECKBOX_ACROS = frozenset(EE_ACK_ACROS)


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
        if acro == 'Manager_Signature_Date':
            return False
        return acro in EE_REQUIRED_ACROS
    return True


def ee_id_by_acro(typed_fields: list) -> dict[str, list]:
    id_by_acro: dict[str, list] = {}
    for tf in typed_fields:
        id_by_acro.setdefault(acro_key(tf.placeholder), []).append(tf)
    return id_by_acro


def repair_employee_information_field_groups(typed_fields: list) -> bool:
    """Fix incorrect shared choice_groups on imported checkbox fields."""
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
    ans = (session_val or '').strip().lower()
    if ans in ('yes', 'no'):
        return ans
    id_by_acro = ee_id_by_acro(typed_fields)
    for ak in ('Dependent_1_Name', 'Dependent_2_Name', 'Dependent_3_Name'):
        for tf in id_by_acro.get(ak, []):
            val = (typed_values.get(tf.id) or '').strip()
            if val and val.upper() != WIZARD_SKIP_NA:
                return 'yes'
    dep_values = []
    for ak in EE_DEPENDENT_ACROS:
        if ak in EE_INDEPENDENT_CHECKBOX_ACROS or 'Gender_' in ak:
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
        'hint': 'Check each item that applies to you. Required items are marked with an asterisk (*).',
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
    ans = (has_dependents or '').strip().lower() if has_dependents else None
    if ans == 'yes':
        return steps
    return [s for s in steps if not is_ee_dependent_wizard_step(s)]


def apply_ee_dependents_not_applicable(persist_fn, id_by_acro: dict[str, list]) -> None:
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
        return {
            'wizard_id': f'choice:{group_id}',
            'kind': 'choice_group',
            'label': label,
            'section': section,
            'page': page,
            'sort_y': sort_y,
            'sort_x': 0,
            'required': ee_field_is_required(choice_group=group_id),
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
        elif not val and tf.field_type == 'date' and ak == 'Employee_Signature_Date':
            val = today_date
            auto = True
        required = ee_field_is_required(acro=ak)
        skip_val = wizard_skip_value_for_step({
            'required': required, 'wizard_type': wtype, 'field_type': tf.field_type,
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
                'skip_value': '', 'hint': '', 'value': '',
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
                if tf.id in ee_choice_member_ids or acro_by_id[tf.id] in EE_ACK_ORDER:
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
