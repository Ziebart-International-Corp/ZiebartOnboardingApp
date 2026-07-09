"""Step-by-step wizard for Application for Employment."""
from __future__ import annotations

from typing import Any, Callable, Optional

from document_wizard_labels import (
    WIZARD_SKIP_NA,
    acro_key,
    wizard_skip_value_for_step,
    wizard_value_counts_as_filled,
)
from employment_pdf_field_map import (
    EMP_ACRO_CHOICE_GROUPS,
    EMP_ACRO_TO_CHOICE_GROUP,
    EMP_EMPLOYER_BLOCKS,
    EMP_FORM_MARKER_ACROS,
    EMP_OPTIONAL_STATEMENT_ACRO,
    EMP_OVERLAY_FIELDS,
    EMP_PHONE_ACROS,
    EMP_REQUIRED_ACROS,
    EMP_REQUIRED_CHOICE_GROUPS,
    EMP_SIGNATURE_ACRO,
    EMP_SIGNATURE_DATE_ACRO,
)


def is_employment_application_form(typed_fields: list) -> bool:
    keys = {acro_key(getattr(tf, 'placeholder', None)) for tf in typed_fields}
    return EMP_FORM_MARKER_ACROS.issubset(keys)


def emp_id_by_acro(typed_fields: list) -> dict[str, list]:
    out: dict[str, list] = {}
    for tf in typed_fields:
        out.setdefault(acro_key(tf.placeholder), []).append(tf)
    return out


def repair_employment_application_field_groups(typed_fields: list) -> bool:
    changed = False
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice':
            continue
        ak = acro_key(tf.placeholder)
        expected = EMP_ACRO_TO_CHOICE_GROUP.get(ak)
        if expected and tf.choice_group != expected:
            tf.choice_group = expected
            changed = True
    return changed


def _field_sort_key(tf) -> tuple:
    return (tf.page_number or 1, tf.y_position or 0, tf.x_position or 0, tf.id or 0)


def emp_field_is_required(*, acro: Optional[str] = None, choice_group: Optional[str] = None) -> bool:
    if choice_group is not None:
        return choice_group in EMP_REQUIRED_CHOICE_GROUPS
    if acro is not None:
        if acro == EMP_OPTIONAL_STATEMENT_ACRO:
            return False
        return acro in EMP_REQUIRED_ACROS
    return False


EMP_TYPED_LABELS: dict[str, tuple[str, str, str]] = {
    'Job Applied for': ('Job applied for', 'Position', ''),
    'Wage Expectation': ('Wage expectation', 'Position', ''),
    'Date': ('Date', 'Personal information', 'Date you are completing this application.'),
    'Last Name': ('Last name', 'Personal information', ''),
    'First Name': ('First name', 'Personal information', ''),
    'Middle Initial': ('Middle initial', 'Personal information', ''),
    'Telephone Number': ('Telephone number', 'Personal information', ''),
    'Street Address': ('Street address', 'Personal information', ''),
    'City': ('City', 'Personal information', ''),
    'State': ('State', 'Personal information', ''),
    'Zip Code': ('Zip code', 'Personal information', ''),
    'if no state your age for child labor law purposes only': (
        'If under 18, state your age', 'Personal information', 'For child labor law purposes only.',
    ),
    'Other': ('If other start date, explain', 'Availability', ''),
    'If no please explain': ('If no, explain availability limits', 'Availability', ''),
    'Ad in': ('Where did you hear about us — ad details', 'Referral', ''),
    'Other_2': ('Where did you hear about us — other', 'Referral', ''),
    'If yes when': ('Have you ever applied here before? If yes, when?', 'Prior applications', ''),
    'If yes when_2': ('Were you ever employed here? If yes, when?', 'Prior employment', ''),
    'State_2': ("Driver's license state", 'License & driving record', ''),
    'Lic No': ("Driver's license number", 'License & driving record', ''),
    'If yes please explain': ('If yes, explain tickets', 'License & driving record', ''),
    'If yes please explain_2': ('If yes, explain suspension/revocation', 'License & driving record', ''),
    'explain': ('If yes, state when convicted and explain (DUI/DWI)', 'License & driving record', ''),
    'Name of Educational Institution': ('High school name', 'Education — high school', ''),
    'City and State of Educational InstitutionHigh School': ('High school city/state', 'Education — high school', ''),
    'Graduated YESNOHigh School': ('High school graduated (Yes/No)', 'Education — high school', ''),
    'Type of Degree or Degree ExpectedHigh School': ('High school degree or degree expected', 'Education — high school', ''),
    'MajorHigh School': ('High school major', 'Education — high school', ''),
    'MinorHigh School': ('High school minor', 'Education — high school', ''),
    'GPAHigh School': ('High school GPA', 'Education — high school', ''),
    'City and State of Educational InstitutionCollegeUniversity': ('College/university city/state', 'Education — college/university', ''),
    'Graduated YESNOCollegeUniversity': ('College/university graduated (Yes/No)', 'Education — college/university', ''),
    'Type of Degree or Degree ExpectedCollegeUniversity': ('College/university degree or degree expected', 'Education — college/university', ''),
    'MajorCollegeUniversity': ('College/university major', 'Education — college/university', ''),
    'MinorCollegeUniversity': ('College/university minor', 'Education — college/university', ''),
    'GPACollegeUniversity': ('College/university GPA', 'Education — college/university', ''),
    'City and State of Educational InstitutionTechnicalGED': ('Technical/GED city/state', 'Education — technical/GED', ''),
    'Graduated YESNOTechnicalGED': ('Technical/GED graduated (Yes/No)', 'Education — technical/GED', ''),
    'Type of Degree or Degree ExpectedTechnicalGED': ('Technical/GED degree or degree expected', 'Education — technical/GED', ''),
    'MajorTechnicalGED': ('Technical/GED major', 'Education — technical/GED', ''),
    'MinorTechnicalGED': ('Technical/GED minor', 'Education — technical/GED', ''),
    'GPATechnicalGED': ('Technical/GED GPA', 'Education — technical/GED', ''),
    'City and State of Educational InstitutionOther': ('Other education city/state', 'Education — other', ''),
    'Graduated YESNOOther': ('Other education graduated (Yes/No)', 'Education — other', ''),
    'Type of Degree or Degree ExpectedOther': ('Other education degree or degree expected', 'Education — other', ''),
    'MajorOther': ('Other education major', 'Education — other', ''),
    'MinorOther': ('Other education minor', 'Education — other', ''),
    'GPAOther': ('Other education GPA', 'Education — other', ''),
    'What skills or additional training do you have that are related to the job for which you are applying': (
        'Skills or additional training related to the job', 'Skills & training', '',
    ),
    'What machinesequipmentcomputers etc can you operate that are related to the job for which you are applying': (
        'Machines/equipment/computers you can operate', 'Skills & training', '',
    ),
    'Branch of Service': ('Branch of military service', 'Military service', 'Leave blank if not applicable.'),
    'Number of YearsMonths of Service': ('Number of years/months of service', 'Military service', ''),
    'Rank at Discharge': ('Rank at discharge', 'Military service', ''),
    'Discharge Date': ('Discharge date', 'Military service', ''),
    'Reason for Leaving': ('Reason for leaving (military)', 'Military service', ''),
    'Describe any military skills training or experience you believe are relevant to the job applied for': (
        'Military skills, training, or experience relevant to the job', 'Military service', '',
    ),
    'If yes whom do you suggest we contact': (
        'If presently employed, whom do you suggest we contact?', 'Current employment', '',
    ),
    'Please explain any gaps in your employment history 1': ('Explain any gaps in employment history', 'Employment history', ''),
    'Please explain any gaps in your employment history 2': (
        'Optional statement: why you are the best candidate and/or why you are interested',
        'Final questions', 'Optional.',
    ),
    'Have you ever been discharged or forced to resign  If yes explain 1': (
        'Have you ever been discharged or forced to resign? If yes, explain', 'Employment history', '',
    ),
    'Have you ever been discharged or forced to resign  If yes explain 2': (
        'Discharged or forced to resign — additional explanation', 'Employment history', '',
    ),
    'Did you receive any discipline in the last 12 months of active employment If yes please explain': (
        'Did you receive any discipline in the last 12 months? If yes, explain', 'Employment history', '',
    ),
    'range of scores used and what was your score': (
        'Performance evaluation — score range used and your score', 'Employment history',
        'Were you given a performance evaluation within the last 12 months?',
    ),
    EMP_SIGNATURE_DATE_ACRO: ('Signature date', 'Signature', ''),
}

EMP_CHOICE_GROUPS: dict[str, tuple[str, str, str]] = {
    'emp_age_18': ('Are you 18 years of age or older?', 'Personal information', ''),
    'emp_work_type': ('Seeking full-time, part-time, or temporary work?', 'Availability', ''),
    'emp_overtime': ('Will you work overtime if required?', 'Availability', ''),
    'emp_start_work': ('When could you start work?', 'Availability', 'Now, two weeks, or other.'),
    'emp_illegal_drugs': ('Have you taken any illegal drugs in the last 30 days?', 'Availability', ''),
    'emp_work_any_days': ('Can you work any days, shifts, hours?', 'Availability', ''),
    'emp_heard_about': ('Where did you hear about us?', 'Referral', ''),
    'emp_applied_before': ('Have you ever applied here before?', 'Prior applications', ''),
    'emp_employed_before': ('Were you ever employed here?', 'Prior employment', ''),
    'emp_work_eligible': ('If hired, can you furnish proof you are eligible to work in the U.S.?', 'Work eligibility', ''),
    'emp_drivers_license': ("Do you have a valid driver's license?", 'License & driving record', ''),
    'emp_had_tickets': ('Have you had any tickets?', 'License & driving record', ''),
    'emp_license_suspended': ('Has your license ever been suspended or revoked?', 'License & driving record', ''),
    'emp_dui': ('Do you have any DUI or DWI convictions?', 'License & driving record', ''),
    'emp_presently_employed': ('Are you presently employed?', 'Current employment', ''),
}

EMP_CONDITIONAL_ACROS: dict[str, dict] = {
    'if no state your age for child labor law purposes only': {'group': 'emp_age_18', 'acro': 'No'},
    'Other': {'group': 'emp_start_work', 'acro': 'undefined'},
    'If no please explain': {'group': 'emp_work_any_days', 'acro': 'No_4'},
    'Ad in': {'group': 'emp_heard_about', 'acro': 'undefined_2'},
    'Other_2': {'group': 'emp_heard_about', 'acro': 'undefined_3'},
    'If yes when': {'group': 'emp_applied_before', 'acro': 'Check Box1'},
    'If yes when_2': {'group': 'emp_employed_before', 'acro': 'Check Box3'},
    'If yes please explain': {'group': 'emp_had_tickets', 'label_yes': True},
    'If yes please explain_2': {'group': 'emp_license_suspended', 'label_yes': True},
    'explain': {'group': 'emp_dui', 'label_yes': True},
    'If yes whom do you suggest we contact': {'group': 'emp_presently_employed', 'label_yes': True},
}


def _choice_selected_acro(typed_fields: list, typed_values: dict[int, str], group_id: str) -> Optional[str]:
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice' or (tf.choice_group or '') != group_id:
            continue
        if (typed_values.get(tf.id) or '').strip().upper() == 'X':
            return acro_key(tf.placeholder)
    return None


def _choice_is_yes(typed_fields: list, typed_values: dict[int, str], group_id: str) -> bool:
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice' or (tf.choice_group or '') != group_id:
            continue
        if (typed_values.get(tf.id) or '').strip().upper() != 'X':
            continue
        label = (tf.field_label or '').strip().lower()
        if label == 'yes' or label.startswith('yes'):
            return True
        ak = acro_key(tf.placeholder)
        if ak.startswith('Yes') or ak == 'Check Box1' or ak == 'Check Box3':
            return True
    return False


def _should_show_conditional(ak: str, typed_fields: list, typed_values: dict[int, str]) -> bool:
    rule = EMP_CONDITIONAL_ACROS.get(ak)
    if not rule:
        return True
    group_id = rule['group']
    if rule.get('label_yes'):
        return _choice_is_yes(typed_fields, typed_values, group_id)
    selected = _choice_selected_acro(typed_fields, typed_values, group_id)
    return selected == rule.get('acro')


def _overlay_step(overlay_key, label, section, hint, overlay_values) -> dict[str, Any]:
    val = (overlay_values.get(overlay_key) or '').strip()
    return {
        'wizard_id': f'overlay:{overlay_key}',
        'kind': 'overlay',
        'overlay_key': overlay_key,
        'wizard_type': 'text',
        'label': label,
        'section': section,
        'page': EMP_OVERLAY_FIELDS.get(overlay_key, (1, (0, 0, 0, 0)))[0],
        'required': False,
        'skip_value': WIZARD_SKIP_NA,
        'hint': hint,
        'value': val,
        'filled': wizard_value_counts_as_filled(val, wizard_type='text'),
    }


def build_employment_application_wizard_steps(
    typed_fields: list,
    signature_fields: list,
    typed_values: dict[int, str],
    signed_field_ids: set[int],
    user_display_name: str,
    user_initials: str,
    today_date: str,
    wizard_type_for_typed: Callable[[str, bool], str],
    phone_like_fn: Callable,
    overlay_values: Optional[dict[str, str]] = None,
    composite_parts: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    acro_by_id = {tf.id: acro_key(tf.placeholder) for tf in typed_fields}
    id_by_acro = emp_id_by_acro(typed_fields)
    overlay_values = overlay_values or {}
    composite_parts = composite_parts or {}
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _choice_step(group_id: str) -> Optional[dict[str, Any]]:
        if group_id in seen:
            return None
        cfg = EMP_CHOICE_GROUPS.get(group_id)
        if not cfg:
            return None
        label, section, hint = cfg
        members = [tf for tf in typed_fields if tf.field_type == 'checkbox_choice' and (tf.choice_group or '') == group_id]
        if not members:
            return None
        members.sort(key=_field_sort_key)
        options = []
        for tf in members:
            opt_label = (tf.field_label or '').strip()
            ak = acro_key(tf.placeholder)
            if not opt_label or opt_label.lower() in ('undefined', 'yes', 'no'):
                opt_label = EMP_ACRO_CHOICE_GROUPS.get(group_id, {}).get(ak, opt_label or ak)
            options.append({'field_id': tf.id, 'label': opt_label})
        selected_id = next((tf.id for tf in members if (typed_values.get(tf.id) or '').strip().upper() == 'X'), None)
        seen.add(group_id)
        return {
            'wizard_id': f'choice:{group_id}', 'kind': 'choice_group', 'label': label, 'section': section,
            'page': min(tf.page_number for tf in members), 'required': emp_field_is_required(choice_group=group_id),
            'hint': hint, 'options': options, 'value': str(selected_id) if selected_id else '',
            'filled': selected_id is not None,
        }

    def _typed_step(tf, force_section: str = '') -> dict[str, Any]:
        ak = acro_by_id[tf.id]
        label, section, hint = EMP_TYPED_LABELS.get(ak, (tf.field_label or 'Field', '', ''))
        if force_section:
            section = force_section
        phone_like = ak in EMP_PHONE_ACROS or phone_like_fn(tf)
        wtype = wizard_type_for_typed(tf.field_type, phone_like)
        val = (typed_values.get(tf.id) or '').strip()
        if not val and tf.field_type == 'date' and ak == EMP_SIGNATURE_DATE_ACRO:
            val = today_date
        required = emp_field_is_required(acro=ak)
        return {
            'wizard_id': f'typed:{tf.id}', 'kind': 'typed', 'db_id': tf.id, 'field_type': tf.field_type,
            'wizard_type': wtype, 'label': label.strip(), 'section': section, 'page': tf.page_number,
            'required': required, 'skip_value': wizard_skip_value_for_step({'required': required, 'wizard_type': wtype}),
            'hint': hint[:500], 'value': val, 'filled': wizard_value_counts_as_filled(val, wizard_type=wtype),
            'emp_acro': ak,
        }

    def _part_text(part_key, role, label, section, target_acro, required=False):
        val = (composite_parts.get(f'{part_key}:{role}') or '').strip()
        return {
            'wizard_id': f'emp_part:{part_key}:{role}', 'kind': 'emp_part', 'part_key': part_key,
            'part_role': role, 'target_acro': target_acro, 'wizard_type': 'text', 'label': label,
            'section': section, 'page': 3, 'required': required,
            'skip_value': WIZARD_SKIP_NA if not required else '', 'value': val, 'filled': bool(val) or not required,
            'emp_composite': True,
        }

    def _part_choice(part_key, role, label, section, target_acro):
        val = (composite_parts.get(f'{part_key}:{role}') or '').strip().lower()
        return {
            'wizard_id': f'emp_part:{part_key}:{role}', 'kind': 'gate', 'part_key': part_key,
            'part_role': role, 'target_acro': target_acro, 'wizard_type': 'yes_no', 'label': label,
            'section': section, 'page': 3, 'required': False, 'value': val, 'filled': val in ('yes', 'no'),
            'options': [{'value': 'yes', 'label': 'Yes'}, {'value': 'no', 'label': 'No'}],
            'emp_composite': True,
        }

    for ak in ['Job Applied for', 'Wage Expectation', 'Date', 'Last Name', 'First Name', 'Middle Initial',
               'Telephone Number', 'Street Address', 'City', 'State', 'Zip Code']:
        for tf in id_by_acro.get(ak, []):
            if tf.field_type != 'checkbox_choice':
                steps.append(_typed_step(tf))

    for gid in ['emp_age_18', 'emp_work_type', 'emp_overtime', 'emp_start_work', 'emp_illegal_drugs',
                'emp_work_any_days', 'emp_heard_about', 'emp_applied_before', 'emp_employed_before', 'emp_work_eligible']:
        s = _choice_step(gid)
        if s:
            steps.append(s)

    for ak in ['if no state your age for child labor law purposes only', 'Other', 'If no please explain',
               'Ad in', 'Other_2', 'If yes when', 'If yes when_2']:
        if _should_show_conditional(ak, typed_fields, typed_values):
            for tf in id_by_acro.get(ak, []):
                steps.append(_typed_step(tf))

    for gid in ['emp_drivers_license', 'emp_had_tickets', 'emp_license_suspended', 'emp_dui']:
        s = _choice_step(gid)
        if s:
            steps.append(s)

    for ak in ['If yes please explain', 'If yes please explain_2', 'explain', 'State_2', 'Lic No']:
        if ak in EMP_CONDITIONAL_ACROS and not _should_show_conditional(ak, typed_fields, typed_values):
            continue
        for tf in id_by_acro.get(ak, []):
            steps.append(_typed_step(tf))

    edu = [
        'Name of Educational Institution', 'City and State of Educational InstitutionHigh School',
        'Graduated YESNOHigh School', 'Type of Degree or Degree ExpectedHigh School',
        'MajorHigh School', 'MinorHigh School', 'GPAHigh School',
        'City and State of Educational InstitutionCollegeUniversity', 'Graduated YESNOCollegeUniversity',
        'Type of Degree or Degree ExpectedCollegeUniversity', 'MajorCollegeUniversity', 'MinorCollegeUniversity', 'GPACollegeUniversity',
        'City and State of Educational InstitutionTechnicalGED', 'Graduated YESNOTechnicalGED',
        'Type of Degree or Degree ExpectedTechnicalGED', 'MajorTechnicalGED', 'MinorTechnicalGED', 'GPATechnicalGED',
        'City and State of Educational InstitutionOther', 'Graduated YESNOOther', 'Type of Degree or Degree ExpectedOther',
        'MajorOther', 'MinorOther', 'GPAOther',
    ]
    for ak in edu:
        for tf in id_by_acro.get(ak, []):
            steps.append(_typed_step(tf))

    for ak in [
        'What skills or additional training do you have that are related to the job for which you are applying',
        'What machinesequipmentcomputers etc can you operate that are related to the job for which you are applying',
    ]:
        for tf in id_by_acro.get(ak, []):
            steps.append(_typed_step(tf))

    for ak in ['Branch of Service', 'Number of YearsMonths of Service', 'Rank at Discharge', 'Discharge Date',
               'Reason for Leaving',
               'Describe any military skills training or experience you believe are relevant to the job applied for']:
        for tf in id_by_acro.get(ak, []):
            steps.append(_typed_step(tf))

    for block in EMP_EMPLOYER_BLOCKS:
        sec = block['label']
        part_key = block['dates_overlay_key'].replace('_dates', '')
        for ak in (block['company'], block['phone'], block['address']):
            for tf in id_by_acro.get(ak, []):
                steps.append(_typed_step(tf, force_section=sec))
        steps.append(_overlay_step(block['dates_overlay_key'], 'Dates employed (from – to)', sec,
                                   'Include month and year, e.g. 01/2020 – 06/2023', overlay_values))
        steps.append(_part_text(part_key, 'supervisor_name', 'Supervisor name', sec, block['supervisor_acro']))
        steps.append(_part_choice(part_key, 'may_contact', 'May we contact this employer?', sec, block['supervisor_acro']))
        steps.append(_part_text(part_key, 'pay_start', 'Rate of pay — starting', sec, block['pay_acro']))
        steps.append(_part_text(part_key, 'pay_end', 'Rate of pay — ending', sec, block['pay_acro']))
        for ak in (block['job_acro'], block['reason_acro']):
            for tf in id_by_acro.get(ak, []):
                steps.append(_typed_step(tf, force_section=sec))

    s = _choice_step('emp_presently_employed')
    if s:
        steps.append(s)
    if _should_show_conditional('If yes whom do you suggest we contact', typed_fields, typed_values):
        for tf in id_by_acro.get('If yes whom do you suggest we contact', []):
            steps.append(_typed_step(tf))

    for ak in [
        'Please explain any gaps in your employment history 1',
        'Have you ever been discharged or forced to resign  If yes explain 1',
        'Have you ever been discharged or forced to resign  If yes explain 2',
        'Did you receive any discipline in the last 12 months of active employment If yes please explain',
        'range of scores used and what was your score', EMP_OPTIONAL_STATEMENT_ACRO,
    ]:
        for tf in id_by_acro.get(ak, []):
            steps.append(_typed_step(tf))

    sig_sorted = sorted(signature_fields, key=_field_sort_key)
    if sig_sorted:
        sf = sig_sorted[0]
        steps.append({
            'wizard_id': f'sig:{sf.id}', 'kind': 'signature', 'db_id': sf.id, 'wizard_type': 'signature',
            'label': 'Signature', 'section': 'Signature', 'page': sf.page_number, 'required': True,
            'filled': sf.id in signed_field_ids, 'hint': '', 'value': '', 'skip_value': '',
        })
    else:
        for tf in id_by_acro.get(EMP_SIGNATURE_ACRO, []):
            steps.append({
                'wizard_id': f'typed:{tf.id}', 'kind': 'typed', 'db_id': tf.id, 'wizard_type': 'text',
                'label': 'Signature (type your full name)', 'section': 'Signature', 'page': tf.page_number,
                'required': True, 'hint': 'Type your full legal name as your signature.',
                'value': (typed_values.get(tf.id) or user_display_name).strip(),
                'filled': bool((typed_values.get(tf.id) or '').strip()), 'emp_acro': EMP_SIGNATURE_ACRO,
                'skip_value': '',
            })

    for tf in id_by_acro.get(EMP_SIGNATURE_DATE_ACRO, []):
        steps.append(_typed_step(tf))

    return steps


def filter_employment_wizard_steps(steps, typed_fields, typed_values):
    id_by_acro = emp_id_by_acro(typed_fields)
    out = []
    for step in steps:
        ak = step.get('emp_acro')
        if ak and ak in EMP_CONDITIONAL_ACROS and not _should_show_conditional(ak, typed_fields, typed_values):
            continue
        if step.get('kind') in ('emp_part', 'overlay') or step.get('emp_composite'):
            part_key = step.get('part_key') or ''
            if step.get('kind') == 'overlay':
                part_key = (step.get('overlay_key') or '').replace('_dates', '')
            if part_key and not _employer_block_started(id_by_acro, typed_values, part_key):
                continue
        out.append(step)
    return out


def _employer_block_started(id_by_acro, typed_values, part_key) -> bool:
    try:
        idx = int(part_key.rsplit('_', 1)[-1]) - 1
    except ValueError:
        return True
    if idx < 0 or idx >= len(EMP_EMPLOYER_BLOCKS):
        return True
    for tf in id_by_acro.get(EMP_EMPLOYER_BLOCKS[idx]['company'], []):
        if (typed_values.get(tf.id) or '').strip():
            return True
    return False


def apply_employment_composite_to_acro(typed_fields, typed_values, part_key, parts):
    block = None
    for b in EMP_EMPLOYER_BLOCKS:
        if part_key == b['dates_overlay_key'].replace('_dates', ''):
            block = b
            break
    if not block:
        return
    id_by_acro = emp_id_by_acro(typed_fields)
    sup = (parts.get(f'{part_key}:supervisor_name') or '').strip()
    contact = (parts.get(f'{part_key}:may_contact') or '').strip()
    if sup or contact:
        combined = f'{sup} / {contact.title()}'.strip(' /') if contact else sup
        for tf in id_by_acro.get(block['supervisor_acro'], []):
            typed_values[tf.id] = combined
    ps = (parts.get(f'{part_key}:pay_start') or '').strip()
    pe = (parts.get(f'{part_key}:pay_end') or '').strip()
    if ps or pe:
        combined = f'{ps} – {pe}'.strip(' –') if pe else ps
        for tf in id_by_acro.get(block['pay_acro'], []):
            typed_values[tf.id] = combined


def persist_employment_composites_to_db(doc_id, typed_fields, parts, username, persist_fn):
    """Write merged composite employer values to DocumentTypedFieldValue rows."""
    merged: dict[int, str] = {}
    scratch: dict[int, str] = {}
    for block in EMP_EMPLOYER_BLOCKS:
        pk = block['dates_overlay_key'].replace('_dates', '')
        apply_employment_composite_to_acro(typed_fields, scratch, pk, parts)
    for tf_id, val in scratch.items():
        if val:
            merged[tf_id] = val
    for tf_id, val in merged.items():
        tf = next((t for t in typed_fields if t.id == tf_id), None)
        if tf:
            persist_fn(doc_id, tf, val, username)
