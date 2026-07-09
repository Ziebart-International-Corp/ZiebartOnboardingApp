"""
Application for Employment — AcroForm field names and wizard config.

Document template:
  uploads/20260708_124125_Employment_Application.pdf
"""
from __future__ import annotations

EMP_DOCUMENT_ID = 15
EMP_TRUTH_PDF_FILENAME = '20260708_124125_Employment_Application.pdf'
EMP_TRUTH_PDF_REL_PATH = f'uploads/{EMP_TRUTH_PDF_FILENAME}'

# Canonical acro names that identify this form
EMP_FORM_MARKER_ACROS = frozenset({'Job Applied for', 'Wage Expectation'})

# Mutually exclusive choice groups: group_id -> {acro: option label}
EMP_ACRO_CHOICE_GROUPS: dict[str, dict[str, str]] = {
    'emp_age_18': {'Yes': 'Yes', 'No': 'No'},
    'emp_work_type': {
        'Full Time Work': 'Full-time',
        'Part Time Work': 'Part-time',
        'Temporary Work': 'Temporary',
    },
    'emp_overtime': {'Yes_2': 'Yes', 'No_2': 'No'},
    'emp_start_work': {
        'Now': 'Now',
        'Two Weeks': 'Two weeks',
        'undefined': 'Other',
    },
    'emp_illegal_drugs': {'Yes_6': 'Yes', 'No_3': 'No'},
    'emp_work_any_days': {
        'Can you work any days shifts hours': 'Yes',
        'No_4': 'No',
    },
    'emp_heard_about': {
        'Walk In': 'Walk-in',
        'Employee Referral': 'Employee referral',
        'undefined_2': 'Ad in',
        'undefined_3': 'Other',
    },
    'emp_applied_before': {'Check Box1': 'Yes', 'Check Box2': 'No'},
    'emp_employed_before': {'Check Box3': 'Yes', 'Check Box4': 'No'},
    'emp_work_eligible': {
        'If hired can you furnish proof you are eligible to work in the US': 'Yes',
    },
    'emp_drivers_license': {
        'Do you have a valid drivers license': 'Yes',
    },
    'emp_had_tickets': {'Have you had any tickets': 'Yes'},
    'emp_license_suspended': {'Has your license ever been suspended or revoked': 'Yes'},
    'emp_dui': {'Do you have any DUI or DWI convictions': 'Yes'},
    'emp_presently_employed': {'undefined_5': 'Yes'},
}

# Radio groups export two widgets with the same name — map No option by field order
EMP_RADIO_NO_SUFFIX = {
    'If hired can you furnish proof you are eligible to work in the US': 'No',
    'Do you have a valid drivers license': 'No',
    'Have you had any tickets': 'No',
    'Has your license ever been suspended or revoked': 'No',
    'Do you have any DUI or DWI convictions': 'No',
    'undefined_5': 'No',
}

EMP_ACRO_TO_CHOICE_GROUP: dict[str, str] = {}
for _gid, _opts in EMP_ACRO_CHOICE_GROUPS.items():
    for _a in _opts:
        EMP_ACRO_TO_CHOICE_GROUP[_a] = _gid

EMP_SIGNATURE_ACRO = 'Text1'
EMP_SIGNATURE_DATE_ACRO = 'Date_2'

# Five employer blocks on page 3 (PDF uses combined fields for some rows)
EMP_EMPLOYER_BLOCKS: list[dict] = [
    {
        'label': 'Employer 1',
        'company': 'Company Name',
        'phone': 'Telephone Number_2',
        'address': 'Address',
        'supervisor_acro': 'Name of Supervisor May we contact Yes No',
        'pay_acro': 'Rate of Pay Start Ending',
        'job_acro': 'Job Title and Job Duties',
        'reason_acro': 'Reason for Leaving_2',
        'dates_overlay_key': 'emp_employer_1_dates',
        'dates_page': 3,
        'dates_rect': (49, 92, 280, 14),
    },
    {
        'label': 'Employer 2',
        'company': 'Company Name_2',
        'phone': 'Telephone Number_3',
        'address': 'Address_2',
        'supervisor_acro': 'Name of Supervisor May we contact Yes No_2',
        'pay_acro': 'Rate of Pay Start Ending_2',
        'job_acro': 'Job Title and Job Duties_2',
        'reason_acro': 'Reason for Leaving_3',
        'dates_overlay_key': 'emp_employer_2_dates',
        'dates_page': 3,
        'dates_rect': (49, 232, 280, 14),
    },
    {
        'label': 'Employer 3',
        'company': 'Company Name_3',
        'phone': 'Telephone Number_4',
        'address': 'Address_3',
        'supervisor_acro': 'Name of Supervisor May we contact Yes No_3',
        'pay_acro': 'Rate of Pay Start Ending_3',
        'job_acro': 'Job Title and Job Duties_3',
        'reason_acro': 'Reason for Leaving_4',
        'dates_overlay_key': 'emp_employer_3_dates',
        'dates_page': 3,
        'dates_rect': (49, 371, 280, 14),
    },
    {
        'label': 'Employer 4',
        'company': 'Company Name_4',
        'phone': 'Telephone Number_5',
        'address': 'Address_4',
        'supervisor_acro': 'Name of Supervisor May we contact Yes No_4',
        'pay_acro': 'Rate of Pay Start Ending_4',
        'job_acro': 'Job Title and Job Duties_4',
        'reason_acro': 'Reason for Leaving_5',
        'dates_overlay_key': 'emp_employer_4_dates',
        'dates_page': 3,
        'dates_rect': (49, 511, 280, 14),
    },
    {
        'label': 'Employer 5',
        'company': 'Company Name_5',
        'phone': 'Telephone Number_6',
        'address': 'Address_5',
        'supervisor_acro': 'Name of Supervisor May we contact Yes No_5',
        'pay_acro': 'Rate of Pay Start Ending_5',
        'job_acro': 'Job Title and Job Duties_5',
        'reason_acro': 'Reason for Leaving_6',
        'dates_overlay_key': 'emp_employer_5_dates',
        'dates_page': 3,
        'dates_rect': (49, 651, 280, 14),
    },
]

# Overlay-only keys (no AcroForm widget — drawn on PDF at completion)
EMP_OVERLAY_FIELDS: dict[str, tuple[int, tuple[float, float, float, float]]] = {}
for _block in EMP_EMPLOYER_BLOCKS:
    key = _block['dates_overlay_key']
    x, y, w, h = _block['dates_rect']
    EMP_OVERLAY_FIELDS[key] = (_block['dates_page'], (x, y, w, h))

EMP_PHONE_ACROS = frozenset({
    'Telephone Number',
    'Telephone Number_2', 'Telephone Number_3', 'Telephone Number_4',
    'Telephone Number_5', 'Telephone Number_6',
})

EMP_REQUIRED_ACROS = frozenset({
    'Job Applied for', 'Last Name', 'First Name', 'Telephone Number',
    'Street Address', 'City', 'State', 'Zip Code', 'Date',
    EMP_SIGNATURE_ACRO, EMP_SIGNATURE_DATE_ACRO,
})

EMP_REQUIRED_CHOICE_GROUPS = frozenset({
    'emp_age_18', 'emp_work_type', 'emp_overtime', 'emp_start_work',
    'emp_illegal_drugs', 'emp_work_any_days', 'emp_heard_about',
    'emp_applied_before', 'emp_employed_before', 'emp_work_eligible',
    'emp_drivers_license', 'emp_presently_employed',
})

EMP_OPTIONAL_STATEMENT_ACRO = 'Please explain any gaps in your employment history 2'


def canonical_emp_acro(name: str) -> str:
    return (name or '').strip()
