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
        'undefined': 'Other — pick a date',
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
    'emp_applied_before': {'Check Box1': 'Yes', 'Check Box3': 'No'},
    'emp_employed_before': {'Check Box2': 'Yes', 'Check Box4': 'No'},
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

# Dates employed row — separate From / To input areas on page 3.
EMP_EMPLOYER_DATE_FROM_X = 341
EMP_EMPLOYER_DATE_FROM_W = 77
EMP_EMPLOYER_DATE_TO_X = 438
EMP_EMPLOYER_DATE_TO_W = 80
EMP_EMPLOYER_DATE_H = 14
EMP_EMPLOYER_DATE_FONT_BOOST = 2.0
EMP_EMPLOYER_DATE_BASELINE_UP = 2.0

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
        'dates_from_overlay_key': 'emp_employer_1_date_from',
        'dates_to_overlay_key': 'emp_employer_1_date_to',
        'dates_page': 3,
        'dates_from_rect': (EMP_EMPLOYER_DATE_FROM_X, 92, EMP_EMPLOYER_DATE_FROM_W, EMP_EMPLOYER_DATE_H),
        'dates_to_rect': (EMP_EMPLOYER_DATE_TO_X, 92, EMP_EMPLOYER_DATE_TO_W, EMP_EMPLOYER_DATE_H),
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
        'dates_from_overlay_key': 'emp_employer_2_date_from',
        'dates_to_overlay_key': 'emp_employer_2_date_to',
        'dates_page': 3,
        'dates_from_rect': (EMP_EMPLOYER_DATE_FROM_X, 233, EMP_EMPLOYER_DATE_FROM_W, EMP_EMPLOYER_DATE_H),
        'dates_to_rect': (EMP_EMPLOYER_DATE_TO_X, 233, EMP_EMPLOYER_DATE_TO_W, EMP_EMPLOYER_DATE_H),
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
        'dates_from_overlay_key': 'emp_employer_3_date_from',
        'dates_to_overlay_key': 'emp_employer_3_date_to',
        'dates_page': 3,
        'dates_from_rect': (EMP_EMPLOYER_DATE_FROM_X, 373, EMP_EMPLOYER_DATE_FROM_W, EMP_EMPLOYER_DATE_H),
        'dates_to_rect': (EMP_EMPLOYER_DATE_TO_X, 373, EMP_EMPLOYER_DATE_TO_W, EMP_EMPLOYER_DATE_H),
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
        'dates_from_overlay_key': 'emp_employer_4_date_from',
        'dates_to_overlay_key': 'emp_employer_4_date_to',
        'dates_page': 3,
        'dates_from_rect': (EMP_EMPLOYER_DATE_FROM_X, 514, EMP_EMPLOYER_DATE_FROM_W, EMP_EMPLOYER_DATE_H),
        'dates_to_rect': (EMP_EMPLOYER_DATE_TO_X, 514, EMP_EMPLOYER_DATE_TO_W, EMP_EMPLOYER_DATE_H),
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
        'dates_from_overlay_key': 'emp_employer_5_date_from',
        'dates_to_overlay_key': 'emp_employer_5_date_to',
        'dates_page': 3,
        'dates_from_rect': (EMP_EMPLOYER_DATE_FROM_X, 655, EMP_EMPLOYER_DATE_FROM_W, EMP_EMPLOYER_DATE_H),
        'dates_to_rect': (EMP_EMPLOYER_DATE_TO_X, 655, EMP_EMPLOYER_DATE_TO_W, EMP_EMPLOYER_DATE_H),
    },
]

# Name input uses the full column-1 cell (x≈49–148 in PDF points), with text on
# the underline at the bottom so row labels (High School, etc.) stay visible.
EMP_EDU_NAME_COL_X = 49.5
EMP_EDU_NAME_COL_W = 100.1
EMP_EDU_NAME_COL_H = 30.5
EMP_EDU_NAME_ROW_Y: dict[str, float] = {
    'high_school': 275.8,
    'college': 311.8,
    'technical': 347.8,
    'other': 383.9,
}

# High school name: the AcroForm widget sits in the column header; draw in the HS row instead.
EMP_HIGH_SCHOOL_NAME_ACRO = 'Name of Educational Institution'

# City/state PDF field holds only city + state; school name uses name_acro typed fields.
EMP_EDUCATION_LOCATION_BLOCKS: list[dict] = [
    {
        'part_key': 'edu_college',
        'target_acro': 'City and State of Educational InstitutionCollegeUniversity',
        'label_prefix': 'College/university',
        'name_acro': 'Name of Educational InstitutionCollegeUniversity',
        'name_row_y': EMP_EDU_NAME_ROW_Y['college'],
    },
    {
        'part_key': 'edu_technical',
        'target_acro': 'City and State of Educational InstitutionTechnicalGED',
        'label_prefix': 'Technical/GED',
        'name_acro': 'Name of Educational InstitutionTechnicalGED',
        'name_row_y': EMP_EDU_NAME_ROW_Y['technical'],
    },
    {
        'part_key': 'edu_other',
        'target_acro': 'City and State of Educational InstitutionOther',
        'label_prefix': 'Other education',
        'name_acro': 'Name of Educational InstitutionOther',
        'name_row_y': EMP_EDU_NAME_ROW_Y['other'],
    },
]

# Narrow name column — clip/wrap text so it cannot bleed into city/state.
EMP_EDUCATION_NAME_ACROS = frozenset({
    EMP_HIGH_SCHOOL_NAME_ACRO,
    *(b['name_acro'] for b in EMP_EDUCATION_LOCATION_BLOCKS),
})

# Overlay-only keys (no AcroForm widget — drawn on PDF at completion)
EMP_OVERLAY_FIELDS: dict[str, tuple[int, tuple[float, float, float, float]]] = {}
_emp_date_overlay_keys: set[str] = set()
for _block in EMP_EMPLOYER_BLOCKS:
    page = _block['dates_page']
    for _key, _rect in (
        (_block['dates_from_overlay_key'], _block['dates_from_rect']),
        (_block['dates_to_overlay_key'], _block['dates_to_rect']),
    ):
        x, y, w, h = _rect
        EMP_OVERLAY_FIELDS[_key] = (page, (x, y, w, h))
        _emp_date_overlay_keys.add(_key)
EMP_EMPLOYER_DATE_OVERLAY_KEYS = frozenset(_emp_date_overlay_keys)

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
    'emp_drivers_license', 'emp_had_tickets', 'emp_license_suspended', 'emp_dui',
    'emp_presently_employed',
})

EMP_OPTIONAL_STATEMENT_ACRO = 'Please explain any gaps in your employment history 2'

# Text fields on the PDF that collect Yes/No answers (render as radio buttons in the wizard).
EMP_YESNO_TEXT_ACROS = frozenset({
    'Graduated YESNOHigh School',
    'Graduated YESNOCollegeUniversity',
    'Graduated YESNOTechnicalGED',
    'Graduated YESNOOther',
})

EMP_PAGE1_SECTION = 'Page 1 — Application'
EMP_PAGE1_POLICY_ID = 'emp:page1_policy'
EMP_PAGE2_SECTION = 'Page 2 — Education & background'
EMP_PAGE3_SECTION = 'Page 3 — Employment history'
EMP_PAGE3_INTRO_ID = 'emp:page3_intro'
EMP_PAGE4_SECTION = 'Page 4 — Final questions & signature'
EMP_PAGE4_ACK_ID = 'emp:page4_ack'

# Long text fields — use multi-line input in the wizard
EMP_TEXTAREA_ACROS = frozenset({
    'What skills or additional training do you have that are related to the job for which you are applying',
    'What machinesequipmentcomputers etc can you operate that are related to the job for which you are applying',
    'Describe any military skills training or experience you believe are relevant to the job applied for',
    'If yes please explain',
    'If yes please explain_2',
    'explain',
    'Please explain any gaps in your employment history 1',
    'Please explain any gaps in your employment history 2',
    'Have you ever been discharged or forced to resign  If yes explain 1',
    'Have you ever been discharged or forced to resign  If yes explain 2',
    'Did you receive any discipline in the last 12 months of active employment If yes please explain',
})


def canonical_emp_acro(name: str) -> str:
    return (name or '').strip()
