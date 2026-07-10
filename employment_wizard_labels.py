"""Step-by-step wizard for Application for Employment."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional

from document_wizard_labels import (
    WIZARD_SKIP_NA,
    wizard_skip_value_for_step,
    wizard_value_counts_as_filled,
)
from employment_pdf_field_map import (
    EMP_ACRO_CHOICE_GROUPS,
    EMP_ACRO_TO_CHOICE_GROUP,
    EMP_EMPLOYER_BLOCKS,
    EMP_EDUCATION_LOCATION_BLOCKS,
    EMP_FORM_MARKER_ACROS,
    EMP_OPTIONAL_STATEMENT_ACRO,
    EMP_OVERLAY_FIELDS,
    EMP_PAGE1_POLICY_ID,
    EMP_PAGE1_SECTION,
    EMP_PAGE2_SECTION,
    EMP_PAGE3_SECTION,
    EMP_PAGE3_INTRO_ID,
    EMP_PAGE4_SECTION,
    EMP_PAGE4_ACK_ID,
    EMP_PHONE_ACROS,
    EMP_RADIO_NO_SUFFIX,
    EMP_REQUIRED_ACROS,
    EMP_REQUIRED_CHOICE_GROUPS,
    EMP_SIGNATURE_ACRO,
    EMP_SIGNATURE_DATE_ACRO,
    EMP_TEXTAREA_ACROS,
    EMP_TRUTH_PDF_REL_PATH,
    EMP_YESNO_TEXT_ACROS,
)

EMP_PAGE1_POLICY_HTML = """
<p><strong>We are an Equal Opportunity Employer.</strong> We do not discriminate on account of race, color,
religion, sex, national origin, age, disability, or any other legally protected status.</p>
<p>In accordance with the Americans with Disabilities Act, we will make every reasonable accommodation to
known physical and mental limitations of qualified individuals with disabilities unless doing so would
impose an undue hardship on the company.</p>
<p>Employment applications are active for <strong>30 days</strong> after receipt.</p>
<p>Answer all questions on this application honestly and completely. Questions on this application are not
intended to seek information about an individual's legally protected status.</p>
"""

# Page 1 interactive flow — policy first, then fields in PDF order with follow-ups inline.
EMP_PAGE1_FLOW: list[tuple[str, str]] = [
    ('info', EMP_PAGE1_POLICY_ID),
    ('typed', 'Job Applied for'),
    ('typed', 'Wage Expectation'),
    ('typed', 'Date'),
    ('typed', 'Last Name'),
    ('typed', 'First Name'),
    ('typed', 'Middle Initial'),
    ('typed', 'Telephone Number'),
    ('typed', 'Street Address'),
    ('typed', 'City'),
    ('typed', 'State'),
    ('typed', 'Zip Code'),
    ('choice', 'emp_age_18'),
    ('conditional', 'if no state your age for child labor law purposes only'),
    ('choice', 'emp_work_type'),
    ('choice', 'emp_overtime'),
    ('choice', 'emp_start_work'),
    ('conditional', 'Other'),
    ('choice', 'emp_illegal_drugs'),
    ('choice', 'emp_heard_about'),
    ('conditional', 'Ad in'),
    ('conditional', 'Other_2'),
    ('choice', 'emp_applied_before'),
    ('conditional', 'If yes when'),
    ('choice', 'emp_employed_before'),
    ('conditional', 'If yes when_2'),
    ('choice', 'emp_work_eligible'),
    # Remaining page 1 PDF fields (after eligibility block on the printed form)
    ('choice', 'emp_work_any_days'),
    ('conditional', 'If no please explain'),
]

# Education/background sections — gate first; detail fields only when user answers Yes.
EMP_EDUCATION_SECTIONS: dict[str, dict[str, Any]] = {
    'edu_high_school': {
        'gate_label': 'Did you attend high school (or equivalent)?',
        'gate_hint': (
            'Select No to skip all high school questions. '
            'Those fields will be marked N/A on your form automatically.'
        ),
        'typed_acros': [
            'Name of Educational Institution',
            'City and State of Educational InstitutionHigh School',
            'Graduated YESNOHigh School',
            'Type of Degree or Degree ExpectedHigh School',
            'MajorHigh School',
            'MinorHigh School',
            'GPAHigh School',
        ],
    },
    'edu_college': {
        'gate_label': 'Did you attend college or university?',
        'gate_hint': (
            'Select No to skip all college/university questions. '
            'Those fields will be marked N/A on your form automatically.'
        ),
        'location_part_key': 'edu_college',
        'typed_acros': [
            'Graduated YESNOCollegeUniversity',
            'Type of Degree or Degree ExpectedCollegeUniversity',
            'MajorCollegeUniversity',
            'MinorCollegeUniversity',
            'GPACollegeUniversity',
        ],
    },
    'edu_technical': {
        'gate_label': 'Did you attend technical school or complete a GED program?',
        'gate_hint': (
            'Select No to skip all technical/GED questions. '
            'Those fields will be marked N/A on your form automatically.'
        ),
        'location_part_key': 'edu_technical',
        'typed_acros': [
            'Graduated YESNOTechnicalGED',
            'Type of Degree or Degree ExpectedTechnicalGED',
            'MajorTechnicalGED',
            'MinorTechnicalGED',
            'GPATechnicalGED',
        ],
    },
    'edu_other': {
        'gate_label': 'Do you have any other education to report?',
        'gate_hint': (
            'Select No to skip all other-education questions. '
            'Those fields will be marked N/A on your form automatically.'
        ),
        'location_part_key': 'edu_other',
        'typed_acros': [
            'Graduated YESNOOther',
            'Type of Degree or Degree ExpectedOther',
            'MajorOther',
            'MinorOther',
            'GPAOther',
        ],
    },
    'military': {
        'gate_label': 'Do you have any military service to report?',
        'gate_hint': (
            'Select No to skip all military service questions. '
            'Those fields will be marked N/A on your form automatically.'
        ),
        'typed_acros': [
            'Branch of Service',
            'Number of YearsMonths of Service',
            'Rank at Discharge',
            'Discharge Date',
            'Reason for Leaving',
            'Describe any military skills training or experience you believe are relevant to the job applied for',
        ],
    },
}

_ACRO_TO_EDU_SECTION: dict[str, str] = {}
for _section_key, _section_cfg in EMP_EDUCATION_SECTIONS.items():
    for _acro in _section_cfg.get('typed_acros', ()):
        _ACRO_TO_EDU_SECTION[_acro] = _section_key

_EDU_LOCATION_TO_SECTION: dict[str, str] = {
    cfg['location_part_key']: section_key
    for section_key, cfg in EMP_EDUCATION_SECTIONS.items()
    if cfg.get('location_part_key')
}


def education_section_is_active(section_key: str, parts: dict) -> bool:
    return (parts.get(f'{section_key}:attended') or '').strip().lower() == 'yes'


def employment_edu_section_for_step(step: dict[str, Any]) -> Optional[str]:
    if step.get('kind') == 'emp_part':
        pk = (step.get('part_key') or '').strip()
        if pk in EMP_EDUCATION_SECTIONS:
            return pk
        return _EDU_LOCATION_TO_SECTION.get(pk)
    ak = (step.get('emp_acro') or '').strip()
    if ak:
        return _ACRO_TO_EDU_SECTION.get(ak)
    return None


def is_employment_edu_section_field_step(step: dict[str, Any]) -> bool:
    return employment_edu_section_for_step(step) is not None


# Page 2 — license, education (4 levels), skills, military
EMP_PAGE2_FLOW: list[tuple[str, str]] = [
    ('choice', 'emp_drivers_license'),
    ('conditional', 'State_2'),
    ('conditional', 'Lic No'),
    ('choice', 'emp_had_tickets'),
    ('conditional', 'If yes please explain'),
    ('choice', 'emp_license_suspended'),
    ('conditional', 'If yes please explain_2'),
    ('choice', 'emp_dui'),
    ('conditional', 'explain'),
    ('gate', 'edu_high_school'),
    ('typed', 'Name of Educational Institution'),
    ('typed', 'City and State of Educational InstitutionHigh School'),
    ('typed', 'Graduated YESNOHigh School'),
    ('typed', 'Type of Degree or Degree ExpectedHigh School'),
    ('typed', 'MajorHigh School'),
    ('typed', 'MinorHigh School'),
    ('typed', 'GPAHigh School'),
    ('gate', 'edu_college'),
    ('edu_location', 'edu_college'),
    ('typed', 'Graduated YESNOCollegeUniversity'),
    ('typed', 'Type of Degree or Degree ExpectedCollegeUniversity'),
    ('typed', 'MajorCollegeUniversity'),
    ('typed', 'MinorCollegeUniversity'),
    ('typed', 'GPACollegeUniversity'),
    ('gate', 'edu_technical'),
    ('edu_location', 'edu_technical'),
    ('typed', 'Graduated YESNOTechnicalGED'),
    ('typed', 'Type of Degree or Degree ExpectedTechnicalGED'),
    ('typed', 'MajorTechnicalGED'),
    ('typed', 'MinorTechnicalGED'),
    ('typed', 'GPATechnicalGED'),
    ('gate', 'edu_other'),
    ('edu_location', 'edu_other'),
    ('typed', 'Graduated YESNOOther'),
    ('typed', 'Type of Degree or Degree ExpectedOther'),
    ('typed', 'MajorOther'),
    ('typed', 'MinorOther'),
    ('typed', 'GPAOther'),
    ('typed', 'What skills or additional training do you have that are related to the job for which you are applying'),
    ('typed', 'What machinesequipmentcomputers etc can you operate that are related to the job for which you are applying'),
    ('gate', 'military'),
    ('typed', 'Branch of Service'),
    ('typed', 'Number of YearsMonths of Service'),
    ('typed', 'Rank at Discharge'),
    ('typed', 'Discharge Date'),
    ('typed', 'Reason for Leaving'),
    ('typed', 'Describe any military skills training or experience you believe are relevant to the job applied for'),
]

EMP_PAGE4_FLOW: list[tuple[str, str]] = [
    ('choice', 'emp_presently_employed'),
    ('conditional', 'If yes whom do you suggest we contact'),
    ('typed', 'Please explain any gaps in your employment history 1'),
    ('typed', EMP_OPTIONAL_STATEMENT_ACRO),
    ('typed', 'Have you ever been discharged or forced to resign  If yes explain 1'),
    ('typed', 'Have you ever been discharged or forced to resign  If yes explain 2'),
    ('typed', 'Did you receive any discipline in the last 12 months of active employment If yes please explain'),
    ('typed', 'range of scores used and what was your score'),
    ('info', EMP_PAGE4_ACK_ID),
]

EMP_PAGE3_INTRO_HTML = """
<p><strong>Employment history</strong> — list all employment in consecutive order with
<strong>most recent employer first</strong>.</p>
<p>On the next step, choose how many previous jobs you want to enter. You will only be asked
about that many employers.</p>
"""

EMP_PAGE3_EMPLOYER_COUNT_ID = 'emp:employer_count'
EMP_EMPLOYER_COUNT_PART_KEY = 'employment_history'
EMP_EMPLOYER_COUNT_ROLE = 'job_count'

EMP_PAGE4_ACK_HTML = """
<p><strong>Applicant's acknowledgement — please read each statement carefully before signing.</strong></p>
<p>I certify that all information provided in this application is true and complete. I understand that
false information or omissions may disqualify me from employment or result in dismissal if discovered
after I am hired.</p>
<p>I authorize an investigation of all statements contained in this application and authorize former
employers, schools, and other persons or organizations to provide relevant information. I release all
parties from liability for providing such information.</p>
<p>I understand that employment is contingent upon satisfactory results of any required background
investigation and tests. I authorize the company to release employment information to other companies
I may apply to in the future.</p>
<p><strong>I understand that, if employed, my employment is not for a specific term and may be terminated
by me or my Employer with or without notice or cause at any time. I further understand that no oral
promise, Employer policy, custom, business practice, or other procedure (including the Associate
Handbook/Manual) constitute an employment contract or modification of the at-will employment
relationship between me and the Employer.</strong></p>
<p>I have read, understand, and by my signature consent to these statements.</p>
<p><em>This application for employment will remain active for a 30-day period and on file for one year.</em></p>
"""


def _employer_part_key(block: dict) -> str:
    return block['dates_overlay_key'].replace('_dates', '')


def employment_employer_count(parts: dict) -> Optional[int]:
    raw = (parts.get(f'{EMP_EMPLOYER_COUNT_PART_KEY}:{EMP_EMPLOYER_COUNT_ROLE}') or '').strip()
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= len(EMP_EMPLOYER_BLOCKS):
            return n
    return None


def employment_employer_index_for_step(step: dict[str, Any]) -> Optional[int]:
    pk = (step.get('part_key') or '').strip()
    match = re.match(r'emp_employer_(\d+)$', pk)
    if match:
        return int(match.group(1))
    section = (step.get('section') or '').strip()
    match = re.match(r'Employer (\d+)', section)
    if match:
        return int(match.group(1))
    return None


def is_employment_employer_field_step(step: dict[str, Any]) -> bool:
    return employment_employer_index_for_step(step) is not None


def employment_employer_step_is_active(step: dict[str, Any], parts: dict) -> bool:
    idx = employment_employer_index_for_step(step)
    if idx is None:
        return True
    count = employment_employer_count(parts)
    return count is not None and idx <= count


def _employer_block_has_real_data(
    block: dict,
    parts: dict,
    id_by_acro: dict[str, list],
    typed_values: dict[int, str],
) -> bool:
    pk = _employer_part_key(block)
    for role in ('date_from', 'date_to', 'supervisor_name', 'may_contact', 'pay_start', 'pay_end'):
        val = (parts.get(f'{pk}:{role}') or '').strip()
        if val and val.upper() != WIZARD_SKIP_NA:
            return True
    for ak in (
        block['company'], block['phone'], block['address'],
        block['job_acro'], block['reason_acro'],
        block['supervisor_acro'], block['pay_acro'],
    ):
        for tf in id_by_acro.get(ak, []):
            if tf.field_type == 'checkbox_choice':
                continue
            val = (typed_values.get(tf.id) or '').strip()
            if val and val.upper() != WIZARD_SKIP_NA:
                return True
    return False


def resolve_employment_employer_count(
    parts: dict[str, str],
    typed_fields: list,
    typed_values: dict[int, str],
) -> dict[str, str]:
    gate_key = f'{EMP_EMPLOYER_COUNT_PART_KEY}:{EMP_EMPLOYER_COUNT_ROLE}'
    if employment_employer_count(parts) is not None:
        return dict(parts)
    id_by_acro = emp_id_by_acro(typed_fields)
    highest = 0
    for idx, block in enumerate(EMP_EMPLOYER_BLOCKS):
        if _employer_block_has_real_data(block, parts, id_by_acro, typed_values):
            highest = max(highest, idx + 1)
    if not highest:
        return dict(parts)
    out = dict(parts)
    out[gate_key] = str(highest)
    return out


def clear_employer_block_not_applicable(
    block: dict,
    parts: dict,
    persist_fn,
    id_by_acro: dict[str, list],
) -> None:
    pk = _employer_part_key(block)
    seen: set[int] = set()
    for ak in (
        block['company'], block['phone'], block['address'],
        block['job_acro'], block['reason_acro'],
        block['supervisor_acro'], block['pay_acro'],
    ):
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            if tf.field_type == 'checkbox_choice':
                persist_fn(tf.id, '')
            else:
                persist_fn(tf.id, WIZARD_SKIP_NA)
    for role in ('date_from', 'date_to', 'supervisor_name', 'may_contact', 'pay_start', 'pay_end'):
        parts[f'{pk}:{role}'] = WIZARD_SKIP_NA


def clear_employers_beyond_count(
    count: int,
    parts: dict,
    persist_fn,
    id_by_acro: dict[str, list],
) -> None:
    for block in EMP_EMPLOYER_BLOCKS[count:]:
        clear_employer_block_not_applicable(block, parts, persist_fn, id_by_acro)


def clear_employer_block_values(
    block: dict,
    parts: dict,
    persist_fn,
    id_by_acro: dict[str, list],
) -> None:
    pk = _employer_part_key(block)
    seen: set[int] = set()
    for ak in (
        block['company'], block['phone'], block['address'],
        block['job_acro'], block['reason_acro'],
        block['supervisor_acro'], block['pay_acro'],
    ):
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            persist_fn(tf.id, '')
    for role in ('date_from', 'date_to', 'supervisor_name', 'may_contact', 'pay_start', 'pay_end'):
        parts.pop(f'{pk}:{role}', None)


def _apply_employer_date_overlays(
    overlays: dict[str, str],
    block: dict,
    date_from: str,
    date_to: str,
) -> None:
    df = (date_from or '').strip()
    dt = (date_to or '').strip()
    if df.upper() == WIZARD_SKIP_NA:
        df = ''
    if dt.upper() == WIZARD_SKIP_NA:
        dt = ''
    if df:
        overlays[block['dates_from_overlay_key']] = df
    if dt:
        overlays[block['dates_to_overlay_key']] = dt


def hydrate_employment_parts_from_overlays(
    overlay_values: dict[str, str],
    parts: dict[str, str],
) -> dict[str, str]:
    """Restore date_from/date_to wizard parts from saved PDF overlay strings."""
    out = dict(parts)
    for block in EMP_EMPLOYER_BLOCKS:
        pk = _employer_part_key(block)
        if (out.get(f'{pk}:date_from') or '').strip() or (out.get(f'{pk}:date_to') or '').strip():
            continue
        df = (overlay_values.get(block['dates_from_overlay_key']) or '').strip()
        dt = (overlay_values.get(block['dates_to_overlay_key']) or '').strip()
        if df and df.upper() != WIZARD_SKIP_NA:
            out[f'{pk}:date_from'] = df
        if dt and dt.upper() != WIZARD_SKIP_NA:
            out[f'{pk}:date_to'] = dt
        if df or dt:
            continue
        raw = (overlay_values.get(block['dates_overlay_key']) or '').strip()
        if not raw or raw.upper() == WIZARD_SKIP_NA:
            continue
        for sep in (' – ', ' - ', ' to ', '–'):
            if sep in raw:
                left, right = raw.split(sep, 1)
                out[f'{pk}:date_from'] = left.strip()
                out[f'{pk}:date_to'] = right.strip()
                break
        else:
            out[f'{pk}:date_from'] = raw
    return out


def build_employment_overlay_values(
    typed_fields: list,
    typed_values: dict[int, str],
    composite_parts: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Rebuild employer date overlays from saved typed values and composite parts."""
    from employment_pdf_field_map import EMP_EMPLOYER_BLOCKS

    overlays: dict[str, str] = {}
    parts = dict(composite_parts or {})
    hydrate_education_location_parts(typed_fields, typed_values, parts)
    for block in EMP_EMPLOYER_BLOCKS:
        pk = _employer_part_key(block)
        _apply_employer_date_overlays(
            overlays,
            block,
            parts.get(f'{pk}:date_from') or '',
            parts.get(f'{pk}:date_to') or '',
        )
    return overlays


def employment_wizard_parts_path(doc_id: int, username: str):
    from pathlib import Path
    return Path(__file__).resolve().parent / 'uploads' / 'wizard_parts' / f'{username}_doc{doc_id}.json'


def save_employment_wizard_parts(doc_id: int, username: str, parts: dict[str, str]) -> None:
    import json
    path = employment_wizard_parts_path(doc_id, username)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parts, indent=2), encoding='utf-8')


def load_employment_wizard_parts(doc_id: int, username: str) -> dict[str, str]:
    import json
    path = employment_wizard_parts_path(doc_id, username)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _parse_education_location(raw: str) -> dict[str, str]:
    text = (raw or '').strip()
    if not text or text.upper() == WIZARD_SKIP_NA:
        return {}
    pieces = [p.strip() for p in text.split(',') if p.strip()]
    if len(pieces) >= 3:
        return {
            'school_name': ', '.join(pieces[:-2]),
            'city': pieces[-2],
            'state': pieces[-1],
        }
    if len(pieces) == 2:
        return {'city': pieces[0], 'state': pieces[1]}
    return {'school_name': text}


def hydrate_education_name_from_overlays(
    overlay_values: dict[str, str],
    parts: dict[str, str],
) -> dict[str, str]:
    """Restore school_name wizard parts from saved overlay values (legacy)."""
    return dict(parts)


def resolve_education_section_gates(
    parts: dict[str, str],
    typed_fields: list,
    typed_values: dict[int, str],
) -> dict[str, str]:
    """Infer section Yes/No gates from saved answers when session has no gate value yet."""
    out = dict(parts)
    id_by_acro = emp_id_by_acro(typed_fields)
    for section_key, cfg in EMP_EDUCATION_SECTIONS.items():
        gate_key = f'{section_key}:attended'
        if (out.get(gate_key) or '').strip().lower() in ('yes', 'no'):
            continue
        values: list[str] = []
        for ak in cfg.get('typed_acros', ()):
            for tf in id_by_acro.get(ak, []):
                if tf.field_type == 'checkbox_choice':
                    continue
                val = (typed_values.get(tf.id) or '').strip()
                if val:
                    values.append(val)
        loc_pk = cfg.get('location_part_key')
        if loc_pk:
            for role in ('school_name', 'city', 'state'):
                val = (out.get(f'{loc_pk}:{role}') or '').strip()
                if val:
                    values.append(val)
        if not values:
            continue
        if all(v.upper() == WIZARD_SKIP_NA for v in values):
            out[gate_key] = 'no'
        else:
            out[gate_key] = 'yes'
    return out


def hydrate_education_location_parts(
    typed_fields: list,
    typed_values: dict[int, str],
    parts: dict[str, str],
) -> dict[str, str]:
    """Restore school_name/city/state parts from a combined PDF education location field."""
    out = dict(parts)
    id_by_acro = emp_id_by_acro(typed_fields)
    for block in EMP_EDUCATION_LOCATION_BLOCKS:
        pk = block['part_key']
        if any((out.get(f'{pk}:{role}') or '').strip() for role in ('school_name', 'city', 'state')):
            continue
        raw = ''
        for tf in id_by_acro.get(block['target_acro'], []):
            raw = (typed_values.get(tf.id) or '').strip()
            if raw:
                break
        if not raw:
            continue
        parsed = _parse_education_location(raw)
        for role, val in parsed.items():
            out[f'{pk}:{role}'] = val
    return out


def _html_date_value(raw: str) -> str:
    val = (raw or '').strip()
    if not val or val.upper() == WIZARD_SKIP_NA:
        return ''
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val):
        return val
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%m-%d-%Y'):
        try:
            return datetime.strptime(val, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


def _employment_yesno_ui_value(raw: str) -> str:
    val = (raw or '').strip().lower()
    if val in ('yes', 'y'):
        return 'yes'
    if val in ('no', 'n'):
        return 'no'
    return ''


def _employment_yesno_persist_value(raw: str) -> str:
    ui = _employment_yesno_ui_value(raw)
    if ui == 'yes':
        return 'Yes'
    if ui == 'no':
        return 'No'
    return ''


def emp_acro_key(placeholder: Optional[str]) -> str:
    """Raw Acrobat widget name — do not apply EE-form renames (e.g. undefined)."""
    ph = (placeholder or '').strip()
    if ph.startswith('acro:'):
        return ph[5:].strip()
    return ph


def is_employment_application_form(typed_fields: list) -> bool:
    keys = {emp_acro_key(getattr(tf, 'placeholder', None)) for tf in typed_fields}
    return EMP_FORM_MARKER_ACROS.issubset(keys)


def emp_id_by_acro(typed_fields: list) -> dict[str, list]:
    out: dict[str, list] = {}
    for tf in typed_fields:
        out.setdefault(emp_acro_key(tf.placeholder), []).append(tf)
    return out


def repair_employment_application_field_groups(typed_fields: list) -> bool:
    from employment_pdf_field_map import EMP_YESNO_TEXT_ACROS

    changed = False
    for tf in typed_fields:
        ak = emp_acro_key(tf.placeholder)
        if ak in EMP_YESNO_TEXT_ACROS or ak.startswith('GPA'):
            if tf.field_type != 'text':
                tf.field_type = 'text'
                changed = True
            if tf.choice_group:
                tf.choice_group = None
                changed = True
            continue
        expected = EMP_ACRO_TO_CHOICE_GROUP.get(ak)
        if not expected:
            continue
        if tf.choice_group != expected:
            tf.choice_group = expected
            changed = True
        if tf.field_type != 'checkbox_choice':
            tf.field_type = 'checkbox_choice'
            changed = True
        opt_label = EMP_ACRO_CHOICE_GROUPS.get(expected, {}).get(ak)
        if opt_label and (tf.field_label or '').strip() != opt_label:
            tf.field_label = opt_label
            changed = True

    # Radio pairs export two widgets with the same Acrobat name — normalize Yes/No labels.
    shared: dict[tuple[str, str], list] = {}
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice':
            continue
        ak = emp_acro_key(tf.placeholder)
        if ak not in EMP_RADIO_NO_SUFFIX:
            continue
        gid = (tf.choice_group or '').strip() or EMP_ACRO_TO_CHOICE_GROUP.get(ak, '')
        if not gid:
            continue
        shared.setdefault((gid, ak), []).append(tf)

    for widgets in shared.values():
        if len(widgets) < 2:
            continue
        widgets.sort(key=_field_sort_key)
        for idx, tf in enumerate(widgets):
            expected_label = 'Yes' if idx == 0 else 'No'
            if (tf.field_label or '').strip() != expected_label:
                tf.field_label = expected_label
                changed = True
    return changed


def _employment_template_pdf_path() -> Optional[str]:
    from pathlib import Path
    path = Path(__file__).resolve().parent / EMP_TRUTH_PDF_REL_PATH
    return str(path) if path.is_file() else None


def _sync_typed_field_to_radio_widget(tf, widget, page_height: float) -> bool:
    from pdf_form_wizard import pdf_rect_to_viewer_coords

    if not widget.rect or widget.rect.is_empty:
        return False
    x, y, width, height = pdf_rect_to_viewer_coords(list(widget.rect), page_height)
    changed = False
    for attr, val in (
        ('x_position', x),
        ('y_position', y),
        ('width', max(width, 20.0)),
        ('height', max(height, 16.0)),
    ):
        if abs(float(getattr(tf, attr, 0) or 0) - val) > 0.5:
            setattr(tf, attr, val)
            changed = True
    return changed


def ensure_employment_education_table_positions(typed_fields: list) -> bool:
    """
    Sync every education-table typed field to the live PDF widget rect.

    School-name cells have no row widget (only a header widget), so those use
    the measured name-column constants instead.
    """
    try:
        import fitz
        from pdf_form_wizard import pdf_rect_to_viewer_coords
    except ImportError:
        return False

    from employment_pdf_field_map import (
        EMP_EDU_NAME_COL_H,
        EMP_EDU_NAME_COL_W,
        EMP_EDU_NAME_COL_X,
        EMP_EDU_NAME_ROW_Y,
        EMP_EDUCATION_LOCATION_BLOCKS,
        EMP_HIGH_SCHOOL_NAME_ACRO,
    )

    pdf_path = _employment_template_pdf_path()
    if not pdf_path:
        return False

    changed = False
    id_by_acro = emp_id_by_acro(typed_fields)
    pdf = fitz.open(pdf_path)
    try:
        page = pdf[1]
        ph = page.rect.height
        for widget in page.widgets() or []:
            ak = (widget.field_name or '').strip()
            if ak == EMP_HIGH_SCHOOL_NAME_ACRO:
                continue
            if not (
                'Educational Institution' in ak
                or ak.startswith('Graduated YESNO')
                or ak.startswith('GPA')
                or ak.startswith('Major')
                or ak.startswith('Minor')
                or ak.startswith('Type of Degree or Degree Expected')
            ):
                continue
            rows = id_by_acro.get(ak, [])
            if not rows or not widget.rect or widget.rect.is_empty:
                continue
            x, y, w, h = pdf_rect_to_viewer_coords(list(widget.rect), ph)
            for tf in rows:
                for attr, val in (
                    ('x_position', x),
                    ('y_position', y),
                    ('width', max(w, 20.0)),
                    ('height', max(h, 16.0)),
                    ('page_number', 2),
                ):
                    if abs(float(getattr(tf, attr, 0) or 0) - val) > 0.5:
                        setattr(tf, attr, val)
                        changed = True

        def _sync_name_row(name_acro: str, row_y: float) -> None:
            nonlocal changed
            for tf in id_by_acro.get(name_acro, []):
                for attr, val in (
                    ('x_position', EMP_EDU_NAME_COL_X),
                    ('y_position', row_y),
                    ('width', EMP_EDU_NAME_COL_W),
                    ('height', EMP_EDU_NAME_COL_H),
                    ('page_number', 2),
                ):
                    if abs(float(getattr(tf, attr, 0) or 0) - val) > 0.5:
                        setattr(tf, attr, val)
                        changed = True

        _sync_name_row(EMP_HIGH_SCHOOL_NAME_ACRO, EMP_EDU_NAME_ROW_Y['high_school'])
        for block in EMP_EDUCATION_LOCATION_BLOCKS:
            name_acro = (block.get('name_acro') or '').strip()
            row_y = block.get('name_row_y')
            if name_acro and row_y is not None:
                _sync_name_row(name_acro, float(row_y))
    finally:
        pdf.close()
    return changed


def ensure_employment_education_name_field_positions(typed_fields: list) -> bool:
    """Backward-compatible alias."""
    return ensure_employment_education_table_positions(typed_fields)


def ensure_employment_radio_pair_fields(document, typed_fields: list) -> bool:
    """
    PDF Yes/No radios share one Acrobat name — ensure two typed_field rows exist
    (Yes + No) with positions matching each widget so the wizard and PDF embed agree.
    """
    try:
        import fitz
        from pdf_form_wizard import pdf_rect_to_viewer_coords
    except ImportError:
        return False

    from models import DocumentTypedField, db

    pdf_path = _employment_template_pdf_path()
    if not pdf_path:
        return False

    grouped: dict[tuple[str, str], list] = {}
    for tf in typed_fields:
        ak = emp_acro_key(tf.placeholder)
        if ak not in EMP_RADIO_NO_SUFFIX:
            continue
        gid = (tf.choice_group or '').strip() or EMP_ACRO_TO_CHOICE_GROUP.get(ak, '')
        if not gid:
            continue
        grouped.setdefault((gid, ak), []).append(tf)

    if not grouped:
        return False

    changed = False
    pdf = fitz.open(pdf_path)
    try:
        for (gid, ak), rows in grouped.items():
            page_num = min(int(tf.page_number or 2) for tf in rows)
            page_idx = page_num - 1
            if page_idx < 0 or page_idx >= len(pdf):
                continue
            page = pdf[page_idx]
            widgets = sorted(
                [
                    w for w in page.widgets() or []
                    if (w.field_name or '').strip() == ak and getattr(w, 'field_type', None) == 5
                ],
                key=lambda w: (w.rect.x0 if w.rect else 0.0),
            )
            if len(widgets) < 2:
                continue

            yes_w, no_w = widgets[0], widgets[1]
            page_h = page.rect.height
            rows.sort(key=lambda tf: float(tf.x_position or 0))

            if len(rows) == 1:
                yes_tf = rows[0]
                if (yes_tf.field_label or '').strip().lower() != 'yes':
                    yes_tf.field_label = 'Yes'
                    changed = True
                if _sync_typed_field_to_radio_widget(yes_tf, yes_w, page_h):
                    changed = True
                x, y, width, height = pdf_rect_to_viewer_coords(list(no_w.rect), page_h)
                no_tf = DocumentTypedField(
                    document_id=document.id,
                    page_number=page_num,
                    x_position=x,
                    y_position=y,
                    width=max(width, 20.0),
                    height=max(height, 16.0),
                    field_label='No',
                    field_type='checkbox_choice',
                    choice_group=gid,
                    placeholder=yes_tf.placeholder,
                    is_required=False,
                )
                db.session.add(no_tf)
                typed_fields.append(no_tf)
                changed = True
            else:
                yes_tf, no_tf = rows[0], rows[1]
                for tf, label in ((yes_tf, 'Yes'), (no_tf, 'No')):
                    if (tf.field_label or '').strip() != label:
                        tf.field_label = label
                        changed = True
                if _sync_typed_field_to_radio_widget(yes_tf, yes_w, page_h):
                    changed = True
                if _sync_typed_field_to_radio_widget(no_tf, no_w, page_h):
                    changed = True
    finally:
        pdf.close()
    return changed


def migrate_employment_applied_employed_values(
    document_id: int, username: str, typed_fields: list,
) -> bool:
    """
    Move saved X values after Check Box2/Check Box3 were mapped to the wrong rows.

    PDF layout (y positions):
      applied before  Yes=Check Box1  No=Check Box3  (y ~565)
      employed before Yes=Check Box2  No=Check Box4  (y ~593)
    """
    from app import DocumentTypedFieldValue, db

    id_by = emp_id_by_acro(typed_fields)

    def _field(ac):
        rows = id_by.get(ac) or []
        return rows[0] if rows else None

    def _row(tf):
        if not tf:
            return None
        return DocumentTypedFieldValue.query.filter_by(
            document_id=document_id,
            typed_field_id=tf.id,
            username=username,
        ).first()

    cb2, cb3 = _field('Check Box2'), _field('Check Box3')
    cb2_row, cb3_row = _row(cb2), _row(cb3)
    cb2_x = bool(cb2_row and (cb2_row.field_value or '').strip().upper() == 'X')
    cb3_x = bool(cb3_row and (cb3_row.field_value or '').strip().upper() == 'X')
    changed = False

    # Old mapping stored applied "No" on Check Box2; correct widget is Check Box3.
    if cb2_x and cb3 and not cb3_x:
        cb3_row = _row(cb3)
        if cb3_row:
            cb3_row.field_value = 'X'
        else:
            db.session.add(DocumentTypedFieldValue(
                document_id=document_id,
                typed_field_id=cb3.id,
                username=username,
                field_value='X',
                filled_at=datetime.utcnow(),
            ))
        if cb2_row:
            db.session.delete(cb2_row)
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
    'Job Applied for': ('Job applied for', EMP_PAGE1_SECTION, 'Enter the position title you are applying for.'),
    'Wage Expectation': ('Wage expectation', EMP_PAGE1_SECTION, 'Enter your expected pay (hourly or salary).'),
    'Date': ('Date', EMP_PAGE1_SECTION, 'Date you are completing this application.'),
    'Last Name': ('Last name', EMP_PAGE1_SECTION, ''),
    'First Name': ('First name', EMP_PAGE1_SECTION, ''),
    'Middle Initial': ('Middle initial', EMP_PAGE1_SECTION, 'Leave blank if none.'),
    'Telephone Number': ('Telephone number', EMP_PAGE1_SECTION, ''),
    'Street Address': ('Street address', EMP_PAGE1_SECTION, ''),
    'City': ('City', EMP_PAGE1_SECTION, ''),
    'State': ('State', EMP_PAGE1_SECTION, ''),
    'Zip Code': ('Zip code', EMP_PAGE1_SECTION, ''),
    'if no state your age for child labor law purposes only': (
        'If under 18, state your age', EMP_PAGE1_SECTION,
        'For child labor law purposes only.',
    ),
    'Other': ('Other start date', EMP_PAGE1_SECTION, 'Select the date you could start work.'),
    'If no please explain': (
        'If no, explain your availability', EMP_PAGE1_SECTION,
        'Describe which days, shifts, or hours you can work.',
    ),
    'Ad in': ('Ad in — where did you see the ad?', EMP_PAGE1_SECTION, 'Publication, website, or location of the ad.'),
    'Other_2': ('Other — where did you hear about us?', EMP_PAGE1_SECTION, 'Please specify.'),
    'If yes when': ('When did you apply here?', EMP_PAGE1_SECTION, 'Select the approximate date.'),
    'If yes when_2': ('When were you employed here?', EMP_PAGE1_SECTION, 'Select the approximate date.'),
    'State_2': ("Driver's license — state", EMP_PAGE2_SECTION, 'Required if you have a valid license.'),
    'Lic No': ("Driver's license — number", EMP_PAGE2_SECTION, 'Required if you have a valid license.'),
    'If yes please explain': ('If yes, please explain (tickets)', EMP_PAGE2_SECTION, ''),
    'If yes please explain_2': ('If yes, please explain (suspension/revocation)', EMP_PAGE2_SECTION, ''),
    'explain': ('If yes, when convicted and please explain (DUI/DWI)', EMP_PAGE2_SECTION, ''),
    'Name of Educational Institution': ('High school — name', EMP_PAGE2_SECTION, 'Leave blank if not applicable.'),
    'City and State of Educational InstitutionHigh School': ('High school — city and state', EMP_PAGE2_SECTION, ''),
    'Graduated YESNOHigh School': ('High school — did you graduate?', EMP_PAGE2_SECTION, ''),
    'Type of Degree or Degree ExpectedHigh School': ('High school — degree or degree expected', EMP_PAGE2_SECTION, ''),
    'MajorHigh School': ('High school — major', EMP_PAGE2_SECTION, ''),
    'MinorHigh School': ('High school — minor', EMP_PAGE2_SECTION, ''),
    'GPAHigh School': ('High school — GPA', EMP_PAGE2_SECTION, ''),
    'City and State of Educational InstitutionCollegeUniversity': (
        'College/university — name, city and state', EMP_PAGE2_SECTION,
        'Collected as separate steps in the wizard.',
    ),
    'Graduated YESNOCollegeUniversity': ('College/university — did you graduate?', EMP_PAGE2_SECTION, ''),
    'Type of Degree or Degree ExpectedCollegeUniversity': (
        'College/university — degree or degree expected', EMP_PAGE2_SECTION, '',
    ),
    'MajorCollegeUniversity': ('College/university — major', EMP_PAGE2_SECTION, ''),
    'MinorCollegeUniversity': ('College/university — minor', EMP_PAGE2_SECTION, ''),
    'GPACollegeUniversity': ('College/university — GPA', EMP_PAGE2_SECTION, ''),
    'City and State of Educational InstitutionTechnicalGED': (
        'Technical/GED — name, city and state', EMP_PAGE2_SECTION, '',
    ),
    'Graduated YESNOTechnicalGED': ('Technical/GED — did you graduate?', EMP_PAGE2_SECTION, ''),
    'Type of Degree or Degree ExpectedTechnicalGED': ('Technical/GED — degree or degree expected', EMP_PAGE2_SECTION, ''),
    'MajorTechnicalGED': ('Technical/GED — major', EMP_PAGE2_SECTION, ''),
    'MinorTechnicalGED': ('Technical/GED — minor', EMP_PAGE2_SECTION, ''),
    'GPATechnicalGED': ('Technical/GED — GPA', EMP_PAGE2_SECTION, ''),
    'City and State of Educational InstitutionOther': ('Other education — name, city and state', EMP_PAGE2_SECTION, ''),
    'Graduated YESNOOther': ('Other education — did you graduate?', EMP_PAGE2_SECTION, ''),
    'Type of Degree or Degree ExpectedOther': ('Other education — degree or degree expected', EMP_PAGE2_SECTION, ''),
    'MajorOther': ('Other education — major', EMP_PAGE2_SECTION, ''),
    'MinorOther': ('Other education — minor', EMP_PAGE2_SECTION, ''),
    'GPAOther': ('Other education — GPA', EMP_PAGE2_SECTION, ''),
    'What skills or additional training do you have that are related to the job for which you are applying': (
        'Skills or additional training related to this job', EMP_PAGE2_SECTION,
        'List certifications, courses, or training relevant to the position.',
    ),
    'What machinesequipmentcomputers etc can you operate that are related to the job for which you are applying': (
        'Machines, equipment, or computers you can operate', EMP_PAGE2_SECTION,
        'List tools, software, or equipment relevant to this job.',
    ),
    'Branch of Service': ('Military — branch of service', EMP_PAGE2_SECTION, ''),
    'Number of YearsMonths of Service': ('Military — years/months of service', EMP_PAGE2_SECTION, ''),
    'Rank at Discharge': ('Military — rank at discharge', EMP_PAGE2_SECTION, ''),
    'Discharge Date': ('Military — discharge date', EMP_PAGE2_SECTION, ''),
    'Reason for Leaving': ('Military — reason for leaving', EMP_PAGE2_SECTION, ''),
    'Describe any military skills training or experience you believe are relevant to the job applied for': (
        'Military skills, training, or experience relevant to this job', EMP_PAGE2_SECTION, '',
    ),
    'If yes whom do you suggest we contact': (
        'If presently employed, whom do you suggest we contact?', EMP_PAGE4_SECTION, '',
    ),
    'Please explain any gaps in your employment history 1': (
        'Explain any gaps in your employment history', EMP_PAGE4_SECTION,
        'Use the next step for additional space if needed.',
    ),
    'Please explain any gaps in your employment history 2': (
        'Optional: Why you are the best candidate and/or why you want to work here',
        EMP_PAGE4_SECTION,
        'This step is optional.',
    ),
    'Have you ever been discharged or forced to resign  If yes explain 1': (
        'Have you ever been discharged or forced to resign? If yes, explain',
        EMP_PAGE4_SECTION, 'Leave blank if not applicable.',
    ),
    'Have you ever been discharged or forced to resign  If yes explain 2': (
        'Discharged or forced to resign — additional explanation', EMP_PAGE4_SECTION,
        'Use if you need more space. Leave blank if not applicable.',
    ),
    'Did you receive any discipline in the last 12 months of active employment If yes please explain': (
        'Did you receive any discipline in the last 12 months of active employment? If yes, explain',
        EMP_PAGE4_SECTION, 'Leave blank if not applicable.',
    ),
    'range of scores used and what was your score': (
        'Performance evaluation in the last 12 months — score range used and your score',
        EMP_PAGE4_SECTION,
        'Were you given a performance evaluation within the last 12 months of active employment?',
    ),
    EMP_SIGNATURE_DATE_ACRO: ('Signature date', EMP_PAGE4_SECTION, ''),
}

EMP_CHOICE_GROUPS: dict[str, tuple[str, str, str]] = {
    'emp_age_18': ('Are you 18 years of age or older?', EMP_PAGE1_SECTION, ''),
    'emp_work_type': (
        'Are you seeking full-time, part-time, or temporary work?', EMP_PAGE1_SECTION, 'Select one.',
    ),
    'emp_overtime': ('Will you work overtime if required?', EMP_PAGE1_SECTION, ''),
    'emp_start_work': (
        'When could you start work?', EMP_PAGE1_SECTION, 'Now, two weeks, or other.',
    ),
    'emp_illegal_drugs': (
        'Have you taken any illegal drugs in the last 30 days?', EMP_PAGE1_SECTION, '',
    ),
    'emp_work_any_days': (
        'Can you work any days, shifts, or hours?', EMP_PAGE1_SECTION, '',
    ),
    'emp_heard_about': (
        'Where did you hear about us?', EMP_PAGE1_SECTION,
        'Walk-in, employee referral, ad, or other. If you pick Ad in or Other, the next step asks for details.',
    ),
    'emp_applied_before': ('Have you ever applied here before?', EMP_PAGE1_SECTION, ''),
    'emp_employed_before': ('Were you ever employed here?', EMP_PAGE1_SECTION, ''),
    'emp_work_eligible': (
        'If hired, can you furnish proof you are eligible to work in the U.S.?', EMP_PAGE1_SECTION,
        'Federal law requires documentation within 3 business days of starting work.',
    ),
    'emp_drivers_license': ("Do you have a valid driver's license?", EMP_PAGE2_SECTION, ''),
    'emp_had_tickets': ('Have you had any tickets?', EMP_PAGE2_SECTION, ''),
    'emp_license_suspended': (
        'Has your license ever been suspended or revoked?', EMP_PAGE2_SECTION, '',
    ),
    'emp_dui': ('Do you have any DUI or DWI convictions?', EMP_PAGE2_SECTION, ''),
    'emp_presently_employed': ('Are you presently employed?', EMP_PAGE4_SECTION, ''),
}

EMP_CONDITIONAL_ACROS: dict[str, dict] = {
    'if no state your age for child labor law purposes only': {'group': 'emp_age_18', 'acro': 'No', 'required': True},
    'Other': {'group': 'emp_start_work', 'acro': 'undefined', 'required': True},
    'If no please explain': {'group': 'emp_work_any_days', 'acro': 'No_4', 'required': True},
    'Ad in': {'group': 'emp_heard_about', 'acro': 'undefined_2', 'required': True},
    'Other_2': {'group': 'emp_heard_about', 'acro': 'undefined_3', 'required': True},
    'If yes when': {'group': 'emp_applied_before', 'label_yes': True, 'required': True},
    'If yes when_2': {'group': 'emp_employed_before', 'label_yes': True, 'required': True},
    'State_2': {'group': 'emp_drivers_license', 'label_yes': True, 'required': True},
    'Lic No': {'group': 'emp_drivers_license', 'label_yes': True, 'required': True},
    'If yes please explain': {'group': 'emp_had_tickets', 'label_yes': True, 'required': True},
    'If yes please explain_2': {'group': 'emp_license_suspended', 'label_yes': True, 'required': True},
    'explain': {'group': 'emp_dui', 'label_yes': True, 'required': True},
    'If yes whom do you suggest we contact': {'group': 'emp_presently_employed', 'label_yes': True},
}

# Shown inline on the same wizard step as the parent choice (not a separate step).
EMP_INLINE_CONDITIONAL_ACROS = frozenset({
    'Other',
    'Ad in',
    'Other_2',
})

# Inline on the Yes option of a yes/no choice (e.g. date when previously applied).
EMP_INLINE_YES_CONDITIONAL_ACROS = frozenset({
    'If yes when',
    'If yes when_2',
})

# Inline follow-ups that use a different wizard control than the PDF field type.
EMP_INLINE_FOLLOWUP_WIZARD_TYPES: dict[str, str] = {
    'Other': 'date',
    'If yes when': 'date',
    'If yes when_2': 'date',
}


def _field_in_choice_group(tf, group_id: str) -> bool:
    if (tf.choice_group or '') == group_id:
        return True
    ak = emp_acro_key(tf.placeholder)
    return ak in EMP_ACRO_CHOICE_GROUPS.get(group_id, {})


def _choice_selected_acro(typed_fields: list, typed_values: dict[int, str], group_id: str) -> Optional[str]:
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice':
            continue
        if not _field_in_choice_group(tf, group_id):
            continue
        if (typed_values.get(tf.id) or '').strip().upper() == 'X':
            return emp_acro_key(tf.placeholder)
    return None


def _employment_choice_option_label(
    group_id: str, tf, *, acro_count: int = 1, acro_index: int = 0,
) -> str:
    """Label for one checkbox/radio option; handles shared Acrobat names (Yes/No pairs)."""
    ak = emp_acro_key(tf.placeholder)
    fl = (tf.field_label or '').strip()
    mapped = EMP_ACRO_CHOICE_GROUPS.get(group_id, {}).get(ak, '')
    if acro_count > 1:
        if fl.lower() == 'yes':
            return 'Yes'
        if fl.lower() == 'no':
            return 'No'
        return 'Yes' if acro_index == 0 else 'No'
    if mapped:
        return mapped
    if fl and fl.lower() not in ('undefined', ''):
        return fl
    return ak or 'Option'


def _choice_is_yes(typed_fields: list, typed_values: dict[int, str], group_id: str) -> bool:
    opt_acros = EMP_ACRO_CHOICE_GROUPS.get(group_id, {})
    for tf in typed_fields:
        if tf.field_type != 'checkbox_choice':
            continue
        if not _field_in_choice_group(tf, group_id):
            continue
        if (typed_values.get(tf.id) or '').strip().upper() != 'X':
            continue
        ak = emp_acro_key(tf.placeholder)
        if opt_acros.get(ak, '').lower() != 'yes':
            continue
        if (tf.field_label or '').strip().lower() == 'no':
            continue
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
    emp_wizard_acks: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    acro_by_id = {tf.id: emp_acro_key(tf.placeholder) for tf in typed_fields}
    id_by_acro = emp_id_by_acro(typed_fields)
    overlay_values = overlay_values or {}
    composite_parts = composite_parts or {}
    emp_wizard_acks = emp_wizard_acks or {}
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _choice_option_label(group_id: str, tf, *, acro_count: int = 1, acro_index: int = 0) -> str:
        return _employment_choice_option_label(
            group_id, tf, acro_count=acro_count, acro_index=acro_index,
        )

    def _choice_step(group_id: str) -> Optional[dict[str, Any]]:
        if group_id in seen:
            return None
        cfg = EMP_CHOICE_GROUPS.get(group_id)
        if not cfg:
            return None
        label, section, hint = cfg
        opt_acros = EMP_ACRO_CHOICE_GROUPS.get(group_id, {})
        yes_acros = {a for a, lbl in opt_acros.items() if lbl.lower() == 'yes'}
        members_by_id: dict[int, Any] = {}
        for tf in typed_fields:
            ak = emp_acro_key(tf.placeholder)
            if ak in opt_acros:
                members_by_id[tf.id] = tf
            elif (tf.choice_group or '').strip() == group_id and ak in EMP_RADIO_NO_SUFFIX:
                members_by_id[tf.id] = tf
        members = list(members_by_id.values())
        if not members:
            return None
        # Stable order: PDF map order, then position on page
        acro_order = {a: i for i, a in enumerate(opt_acros)}
        members.sort(key=lambda tf: (
            acro_order.get(emp_acro_key(tf.placeholder), 99),
            0 if (tf.field_label or '').strip().lower() == 'yes' else (
                1 if (tf.field_label or '').strip().lower() == 'no' else 2
            ),
            tf.page_number or 1,
            tf.y_position or 0,
            tf.x_position or 0,
            tf.id or 0,
        ))
        acro_counts: dict[str, int] = {}
        acro_seen: dict[str, int] = {}
        for tf in members:
            ak = emp_acro_key(tf.placeholder)
            acro_counts[ak] = acro_counts.get(ak, 0) + 1
        options = []
        for tf in members:
            ak = emp_acro_key(tf.placeholder)
            acro_index = acro_seen.get(ak, 0)
            acro_seen[ak] = acro_index + 1
            options.append({
                'field_id': tf.id,
                'label': _choice_option_label(
                    group_id, tf,
                    acro_count=acro_counts.get(ak, 1),
                    acro_index=acro_index,
                ),
                'acro': ak,
            })
        selected_id = next((tf.id for tf in members if (typed_values.get(tf.id) or '').strip().upper() == 'X'), None)
        followups: list[dict[str, Any]] = []
        for cond_key, rule in EMP_CONDITIONAL_ACROS.items():
            if rule.get('group') != group_id or rule.get('label_yes'):
                continue
            if cond_key not in EMP_INLINE_CONDITIONAL_ACROS:
                continue
            trigger_acro = rule.get('acro')
            if not trigger_acro:
                continue
            for tf in id_by_acro.get(cond_key, []):
                if tf.field_type == 'checkbox_choice':
                    continue
                fu_step = _typed_step(tf, force_section=section, required_override=rule.get('required', False))
                fu_wtype = EMP_INLINE_FOLLOWUP_WIZARD_TYPES.get(cond_key, fu_step['wizard_type'])
                fu_value = fu_step['value']
                if fu_wtype == 'date':
                    fu_value = _html_date_value(fu_value)
                followups.append({
                    'trigger_acro': trigger_acro,
                    'field_id': tf.id,
                    'label': fu_step['label'],
                    'hint': fu_step.get('hint', ''),
                    'wizard_type': fu_wtype,
                    'value': fu_value,
                    'required': fu_step['required'],
                })
        for cond_key, rule in EMP_CONDITIONAL_ACROS.items():
            if rule.get('group') != group_id or not rule.get('label_yes'):
                continue
            if cond_key not in EMP_INLINE_YES_CONDITIONAL_ACROS:
                continue
            for tf in id_by_acro.get(cond_key, []):
                if tf.field_type == 'checkbox_choice':
                    continue
                fu_step = _typed_step(tf, force_section=section, required_override=rule.get('required', False))
                fu_wtype = EMP_INLINE_FOLLOWUP_WIZARD_TYPES.get(cond_key, fu_step['wizard_type'])
                fu_value = fu_step['value']
                if fu_wtype == 'date':
                    fu_value = _html_date_value(fu_value)
                fu = {
                    'trigger_yes': True,
                    'yes_acros': sorted(yes_acros),
                    'field_id': tf.id,
                    'label': fu_step['label'],
                    'hint': fu_step.get('hint', ''),
                    'wizard_type': fu_wtype,
                    'value': fu_value,
                    'required': fu_step['required'],
                }
                followups.append(fu)
                for opt in options:
                    if opt['acro'] in yes_acros:
                        opt['followup'] = fu
        for opt in options:
            if opt.get('followup'):
                continue
            opt_fu = next((fu for fu in followups if fu.get('trigger_acro') == opt['acro']), None)
            if opt_fu:
                opt['followup'] = opt_fu
        filled = selected_id is not None
        if filled and followups:
            selected_acro = _choice_selected_acro(typed_fields, typed_values, group_id)
            for fu in followups:
                show_fu = (
                    fu.get('trigger_acro') == selected_acro
                    or (fu.get('trigger_yes') and selected_acro in set(fu.get('yes_acros') or []))
                )
                if show_fu and fu['required'] and not wizard_value_counts_as_filled(
                    fu['value'], wizard_type=fu['wizard_type'],
                ):
                    filled = False
                    break
        seen.add(group_id)
        return {
            'wizard_id': f'choice:{group_id}', 'kind': 'choice_group', 'label': label, 'section': section,
            'page': min(tf.page_number for tf in members), 'required': emp_field_is_required(choice_group=group_id),
            'hint': hint, 'options': options, 'value': str(selected_id) if selected_id else '',
            'filled': filled,
            'followups': followups,
        }

    def _typed_step(tf, force_section: str = '', *, required_override: Optional[bool] = None) -> dict[str, Any]:
        ak = acro_by_id[tf.id]
        label, section, hint = EMP_TYPED_LABELS.get(ak, (tf.field_label or 'Field', '', ''))
        if force_section:
            section = force_section
        phone_like = ak in EMP_PHONE_ACROS or phone_like_fn(tf)
        if ak in EMP_YESNO_TEXT_ACROS:
            wtype = 'yes_no'
        elif ak in EMP_TEXTAREA_ACROS or 'Job Title and Job Duties' in ak:
            wtype = 'textarea'
        else:
            wtype = wizard_type_for_typed(tf.field_type, phone_like)
        val = (typed_values.get(tf.id) or '').strip()
        if wtype == 'yes_no':
            val = _employment_yesno_ui_value(val)
        elif not val and tf.field_type == 'date' and ak == EMP_SIGNATURE_DATE_ACRO:
            val = today_date
        required = required_override if required_override is not None else emp_field_is_required(acro=ak)
        step: dict[str, Any] = {
            'wizard_id': f'typed:{tf.id}', 'kind': 'typed', 'db_id': tf.id, 'field_type': tf.field_type,
            'wizard_type': wtype, 'label': label.strip(), 'section': section, 'page': tf.page_number or 1,
            'required': required, 'skip_value': wizard_skip_value_for_step({'required': required, 'wizard_type': wtype}),
            'hint': hint[:500], 'value': val, 'emp_acro': ak,
        }
        if wtype == 'yes_no':
            step['options'] = [{'value': 'yes', 'label': 'Yes'}, {'value': 'no', 'label': 'No'}]
            step['filled'] = val in ('yes', 'no')
        else:
            step['filled'] = wizard_value_counts_as_filled(val, wizard_type=wtype)
        return step

    def _policy_step() -> dict[str, Any]:
        return {
            'wizard_id': EMP_PAGE1_POLICY_ID,
            'kind': 'info',
            'label': 'Application for Employment',
            'section': EMP_PAGE1_SECTION,
            'page': 1,
            'required': True,
            'hint': 'Please read the policy message below, then tap Continue.',
            'policy_html': EMP_PAGE1_POLICY_HTML.strip(),
            'value': '',
            'filled': emp_wizard_acks.get(EMP_PAGE1_POLICY_ID) == '1',
        }

    def _edu_gate_step(section_key: str, gate_section: str, gate_page: int) -> dict[str, Any]:
        cfg = EMP_EDUCATION_SECTIONS[section_key]
        val = (composite_parts.get(f'{section_key}:attended') or '').strip().lower()
        return {
            'wizard_id': f'emp_edu_gate:{section_key}',
            'kind': 'gate',
            'edu_section_gate': True,
            'part_key': section_key,
            'part_role': 'attended',
            'wizard_type': 'yes_no',
            'label': cfg['gate_label'],
            'section': gate_section,
            'page': gate_page,
            'required': True,
            'skip_value': '',
            'hint': cfg.get('gate_hint', ''),
            'value': val,
            'filled': val in ('yes', 'no'),
            'options': [
                {'value': 'yes', 'label': 'Yes'},
                {'value': 'no', 'label': 'No, skip this section'},
            ],
        }

    def _append_flow_steps(flow: list, section: str, page: int) -> None:
        for kind, key in flow:
            if kind == 'info':
                if key == EMP_PAGE1_POLICY_ID:
                    steps.append(_policy_step())
                elif key == EMP_PAGE4_ACK_ID:
                    steps.append(_page4_ack_step())
                continue
            if kind == 'gate':
                if key in EMP_EDUCATION_SECTIONS:
                    steps.append(_edu_gate_step(key, section, page))
                continue
            if kind == 'choice':
                s = _choice_step(key)
                if s:
                    s['section'] = section
                    s['page'] = page
                    steps.append(s)
            elif kind == 'conditional':
                if key in EMP_INLINE_CONDITIONAL_ACROS or key in EMP_INLINE_YES_CONDITIONAL_ACROS:
                    continue
                if not _should_show_conditional(key, typed_fields, typed_values):
                    continue
                rule = EMP_CONDITIONAL_ACROS.get(key, {})
                req = rule.get('required', False)
                for tf in id_by_acro.get(key, []):
                    if tf.field_type == 'checkbox_choice':
                        continue
                    step = _typed_step(tf, force_section=section, required_override=req)
                    step['page'] = page
                    steps.append(step)
            elif kind == 'edu_location':
                block = next(
                    (b for b in EMP_EDUCATION_LOCATION_BLOCKS if b['part_key'] == key),
                    None,
                )
                if not block:
                    continue
                sec = block['label_prefix']
                prefix = block['label_prefix']
                steps.append(_part_text(
                    key, 'school_name', f'{prefix} — school name', sec, block['target_acro'], page=page,
                ))
                steps.append(_part_text(
                    key, 'city', f'{prefix} — city', sec, block['target_acro'], page=page,
                ))
                steps.append(_part_text(
                    key, 'state', f'{prefix} — state', sec, block['target_acro'], page=page,
                ))
            elif kind == 'typed':
                for tf in id_by_acro.get(key, []):
                    if tf.field_type == 'checkbox_choice':
                        continue
                    step = _typed_step(tf, force_section=section)
                    step['page'] = page
                    steps.append(step)

    def _page3_intro_step() -> dict[str, Any]:
        return {
            'wizard_id': EMP_PAGE3_INTRO_ID,
            'kind': 'info',
            'label': 'Employment history',
            'section': EMP_PAGE3_SECTION,
            'page': 3,
            'required': True,
            'hint': 'Read the instructions below, then tap Continue.',
            'policy_html': EMP_PAGE3_INTRO_HTML.strip(),
            'value': '',
            'filled': emp_wizard_acks.get(EMP_PAGE3_INTRO_ID) == '1',
        }

    def _page4_ack_step() -> dict[str, Any]:
        return {
            'wizard_id': EMP_PAGE4_ACK_ID,
            'kind': 'info',
            'label': "Applicant's acknowledgement",
            'section': EMP_PAGE4_SECTION,
            'page': 4,
            'required': True,
            'hint': 'Please read each statement carefully, then tap Continue to sign.',
            'policy_html': EMP_PAGE4_ACK_HTML.strip(),
            'value': '',
            'filled': emp_wizard_acks.get(EMP_PAGE4_ACK_ID) == '1',
        }

    def _employer_count_step() -> dict[str, Any]:
        val = (composite_parts.get(
            f'{EMP_EMPLOYER_COUNT_PART_KEY}:{EMP_EMPLOYER_COUNT_ROLE}',
        ) or '').strip()
        options = []
        for n in range(1, len(EMP_EMPLOYER_BLOCKS) + 1):
            label = '1 previous job' if n == 1 else f'{n} previous jobs'
            options.append({'value': str(n), 'label': label})
        return {
            'wizard_id': EMP_PAGE3_EMPLOYER_COUNT_ID,
            'kind': 'gate',
            'employer_count_gate': True,
            'part_key': EMP_EMPLOYER_COUNT_PART_KEY,
            'part_role': EMP_EMPLOYER_COUNT_ROLE,
            'wizard_type': 'choice',
            'label': 'How many previous jobs do you want to enter?',
            'section': EMP_PAGE3_SECTION,
            'page': 3,
            'required': True,
            'skip_value': '',
            'hint': (
                'Choose the number of employers you want to report, starting with your '
                'most recent job. Extra employer blocks will be skipped automatically.'
            ),
            'value': val,
            'filled': val.isdigit() and 1 <= int(val) <= len(EMP_EMPLOYER_BLOCKS),
            'options': options,
        }

    def _append_page3_steps() -> None:
        steps.append(_page3_intro_step())
        steps.append(_employer_count_step())
        for idx, block in enumerate(EMP_EMPLOYER_BLOCKS):
            n = idx + 1
            sec = f'Employer {n}' + (' (most recent)' if n == 1 else '')
            part_key = block['dates_overlay_key'].replace('_dates', '')
            for ak in (block['company'], block['phone'], block['address']):
                for tf in id_by_acro.get(ak, []):
                    if tf.field_type == 'checkbox_choice':
                        continue
                    step = _typed_step(tf, force_section=sec)
                    step['page'] = 3
                    if ak == block['company']:
                        step['label'] = 'Company name'
                    elif ak == block['phone']:
                        step['label'] = 'Telephone number'
                    elif ak == block['address']:
                        step['label'] = 'Address'
                    steps.append(step)
            steps.append(_part_text(
                part_key, 'date_from',
                'Date employed, start date', sec, block['supervisor_acro'],
            ))
            steps.append(_part_text(
                part_key, 'date_to',
                'Date employed, end date', sec, block['supervisor_acro'],
            ))
            steps.append(_part_text(
                part_key, 'supervisor_name', 'Name of supervisor', sec, block['supervisor_acro'],
            ))
            steps.append(_part_choice(
                part_key, 'may_contact', 'May we contact?', sec, block['supervisor_acro'],
            ))
            steps.append(_part_text(
                part_key, 'pay_start', 'Rate of pay — Start', sec, block['pay_acro'],
            ))
            steps.append(_part_text(
                part_key, 'pay_end', 'Rate of pay — Ending', sec, block['pay_acro'],
            ))
            for ak in (block['job_acro'], block['reason_acro']):
                for tf in id_by_acro.get(ak, []):
                    if tf.field_type == 'checkbox_choice':
                        continue
                    step = _typed_step(tf, force_section=sec)
                    step['page'] = 3
                    if 'Job Title' in ak:
                        step['label'] = 'Job title and job duties'
                    elif 'Reason for Leaving' in (tf.field_label or ak):
                        step['label'] = 'Reason for leaving'
                    steps.append(step)

    def _part_text(part_key, role, label, section, target_acro, required=False, page: int = 3):
        val = (composite_parts.get(f'{part_key}:{role}') or '').strip()
        return {
            'wizard_id': f'emp_part:{part_key}:{role}', 'kind': 'emp_part', 'part_key': part_key,
            'part_role': role, 'target_acro': target_acro, 'wizard_type': 'text', 'label': label,
            'section': section, 'page': page, 'required': required,
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

    def _append_signature_steps() -> None:
        sig_sorted = sorted(signature_fields, key=_field_sort_key)
        if sig_sorted:
            sf = sig_sorted[0]
            steps.append({
                'wizard_id': f'sig:{sf.id}', 'kind': 'signature', 'db_id': sf.id, 'wizard_type': 'signature',
                'label': 'Signature', 'section': EMP_PAGE4_SECTION, 'page': sf.page_number or 4, 'required': True,
                'filled': sf.id in signed_field_ids, 'hint': '', 'value': '', 'skip_value': '',
            })
        else:
            for tf in id_by_acro.get(EMP_SIGNATURE_ACRO, []):
                steps.append({
                    'wizard_id': f'typed:{tf.id}', 'kind': 'typed', 'db_id': tf.id, 'wizard_type': 'text',
                    'label': 'Signature (type your full name)', 'section': EMP_PAGE4_SECTION,
                    'page': tf.page_number or 4, 'required': True,
                    'hint': 'Type your full legal name as your signature.',
                    'value': (typed_values.get(tf.id) or user_display_name).strip(),
                    'filled': bool((typed_values.get(tf.id) or '').strip()), 'emp_acro': EMP_SIGNATURE_ACRO,
                    'skip_value': '',
                })

        for tf in id_by_acro.get(EMP_SIGNATURE_DATE_ACRO, []):
            step = _typed_step(tf, force_section=EMP_PAGE4_SECTION)
            step['page'] = tf.page_number or 4
            steps.append(step)

    _append_flow_steps(EMP_PAGE1_FLOW, EMP_PAGE1_SECTION, 1)
    _append_flow_steps(EMP_PAGE2_FLOW, EMP_PAGE2_SECTION, 2)
    _append_page3_steps()
    _append_flow_steps(EMP_PAGE4_FLOW, EMP_PAGE4_SECTION, 4)
    _append_signature_steps()

    return steps


def filter_employment_wizard_steps(steps, typed_fields, typed_values, composite_parts=None):
    parts = composite_parts or {}
    out = []
    for step in steps:
        edu_section = employment_edu_section_for_step(step)
        if edu_section and not education_section_is_active(edu_section, parts):
            continue
        if is_employment_employer_field_step(step) and not employment_employer_step_is_active(step, parts):
            continue
        ak = step.get('emp_acro')
        if ak and ak in EMP_CONDITIONAL_ACROS and not _should_show_conditional(ak, typed_fields, typed_values):
            continue
        out.append(step)
    return out


def apply_education_section_not_applicable(
    section_key: str,
    typed_fields: list,
    parts: dict,
    persist_fn,
    id_by_acro: dict[str, list],
) -> None:
    cfg = EMP_EDUCATION_SECTIONS.get(section_key)
    if not cfg:
        return
    seen: set[int] = set()
    for ak in cfg.get('typed_acros', ()):
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            if tf.field_type == 'checkbox_choice':
                persist_fn(tf.id, '')
            elif ak in EMP_YESNO_TEXT_ACROS:
                persist_fn(tf.id, '')
            else:
                persist_fn(tf.id, WIZARD_SKIP_NA)
    loc_pk = cfg.get('location_part_key')
    if loc_pk:
        for role in ('school_name', 'city', 'state'):
            parts[f'{loc_pk}:{role}'] = WIZARD_SKIP_NA


def clear_education_section_values(
    section_key: str,
    typed_fields: list,
    parts: dict,
    persist_fn,
    id_by_acro: dict[str, list],
) -> None:
    cfg = EMP_EDUCATION_SECTIONS.get(section_key)
    if not cfg:
        return
    seen: set[int] = set()
    for ak in cfg.get('typed_acros', ()):
        for tf in id_by_acro.get(ak, []):
            if tf.id in seen:
                continue
            seen.add(tf.id)
            persist_fn(tf.id, '')
    loc_pk = cfg.get('location_part_key')
    if loc_pk:
        for role in ('school_name', 'city', 'state'):
            parts.pop(f'{loc_pk}:{role}', None)


def sync_employment_date_overlays(session, doc_id: int, parts: dict) -> None:
    """Merge date_from/date_to parts into PDF overlay values for employment dates row."""
    overlay_key = f'doc_wizard_overlay_{doc_id}'
    overlays = dict(session.get(overlay_key) or {})
    for block in EMP_EMPLOYER_BLOCKS:
        pk = _employer_part_key(block)
        legacy_key = block['dates_overlay_key']
        overlays.pop(legacy_key, None)
        _apply_employer_date_overlays(
            overlays,
            block,
            parts.get(f'{pk}:date_from') or '',
            parts.get(f'{pk}:date_to') or '',
        )
    session[overlay_key] = overlays


def apply_education_location_composite_to_acro(typed_fields, typed_values, part_key, parts):
    block = next((b for b in EMP_EDUCATION_LOCATION_BLOCKS if b['part_key'] == part_key), None)
    if not block:
        return
    id_by_acro = emp_id_by_acro(typed_fields)
    city = (parts.get(f'{part_key}:city') or '').strip()
    state = (parts.get(f'{part_key}:state') or '').strip()
    if city.upper() == WIZARD_SKIP_NA and (not state or state.upper() == WIZARD_SKIP_NA):
        combined = 'N/A'
    elif state.upper() == WIZARD_SKIP_NA and not city:
        combined = 'N/A'
    elif city and state:
        combined = f'{city}, {state}'
    else:
        combined = city or state
    for tf in id_by_acro.get(block['target_acro'], []):
        typed_values[tf.id] = combined


def apply_education_name_composite_to_acro(typed_fields, typed_values, part_key, parts):
    block = next((b for b in EMP_EDUCATION_LOCATION_BLOCKS if b['part_key'] == part_key), None)
    if not block:
        return
    name_acro = (block.get('name_acro') or '').strip()
    if not name_acro:
        return
    name = (parts.get(f'{part_key}:school_name') or '').strip()
    for tf in emp_id_by_acro(typed_fields).get(name_acro, []):
        typed_values[tf.id] = name


def sync_education_name_overlays(session, doc_id: int, parts: dict) -> None:
    """School names are persisted to typed fields; no PDF overlay needed for college rows."""
    return


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
    if ps.upper() == WIZARD_SKIP_NA:
        ps = ''
    if pe.upper() == WIZARD_SKIP_NA:
        pe = ''
    if ps and pe:
        combined = f'{ps} – {pe}'
    elif ps:
        combined = ps
    elif pe:
        combined = pe
    else:
        combined = ''
    if combined:
        for tf in id_by_acro.get(block['pay_acro'], []):
            typed_values[tf.id] = combined


def persist_employment_composites_to_db(doc_id, typed_fields, parts, username, persist_fn):
    """Write merged composite employer and education values to DocumentTypedFieldValue rows."""
    merged: dict[int, str] = {}
    scratch: dict[int, str] = {}
    for block in EMP_EMPLOYER_BLOCKS:
        pk = block['dates_overlay_key'].replace('_dates', '')
        apply_employment_composite_to_acro(typed_fields, scratch, pk, parts)
    for block in EMP_EDUCATION_LOCATION_BLOCKS:
        apply_education_location_composite_to_acro(typed_fields, scratch, block['part_key'], parts)
        apply_education_name_composite_to_acro(typed_fields, scratch, block['part_key'], parts)
    for tf_id, val in scratch.items():
        if val:
            merged[tf_id] = val
    for tf_id, val in merged.items():
        tf = next((t for t in typed_fields if t.id == tf_id), None)
        if tf:
            persist_fn(doc_id, tf, val, username)
