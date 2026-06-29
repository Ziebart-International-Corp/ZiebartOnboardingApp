"""
Employee Information Form (doc 14) — canonical AcroForm field names and wizard config.

All PDF widgets use semantic names (e.g. Employee_Email, Dependent_1_Name).
Legacy Acrobat names are listed in EE_PDF_FIELD_RENAMES for PDF/DB migration.
"""
from __future__ import annotations

# old widget name -> canonical name (apply to PDF + DB placeholders)
EE_PDF_FIELD_RENAMES: dict[str, str] = {
    # Personal
    'Hire Date': 'Employee_Hire_Date',
    'Name3_es_:signer:fullname': 'Employee_Name',
    'Employee_Name_es_:signer:fullname': 'Employee_Name',
    'Text12': 'Employee_Phone_Number',
    'Text13': 'Employee_Address',
    'EMail8_es_:signer:email': 'Employee_Email',
    'Date9_es_:signer:date': 'Employee_Birthdate',
    'Text14': 'Employee_SSN_Last4',
    'SSN': 'Employee_SSN_Last4',
    # Marital / gender
    'Single': 'Employee_Marital_Status_Single',
    'Married': 'Employee_Marital_Status_Married',
    'Male': 'Employee_Gender_Male',
    'Female': 'Employee_Gender_Female',
    # Race / ethnicity
    'BlackAfrican American': 'Race_Black_African_American',
    'American Indian': 'Race_American_Indian',
    'Asian': 'Race_Asian',
    'Native HawaiianPacific Islanders': 'Race_Native_Hawaiian_Pacific_Islander',
    'HispanicSpanish': 'Race_Hispanic_Spanish',
    'White Caucasian': 'Race_White_Caucasian',
    # Emergency contacts
    'Name4_es_:signer:fullname': 'Emergency_Contact_1_Name',
    'Text15': 'Emergency_Contact_1_Relationship',
    'Text16': 'Emergency_Contact_1_Home_Phone',
    'Text17': 'Emergency_Contact_1_Cell_Phone',
    'Text18': 'Emergency_Contact_1_Work_Phone',
    'Text19': 'Emergency_Contact_2_Name',
    'Text23': 'Emergency_Contact_2_Relationship',
    'Text20': 'Emergency_Contact_2_Home_Phone',
    'Text21': 'Emergency_Contact_2_Cell_Phone',
    'Text22': 'Emergency_Contact_2_Work_Phone',
    # Medical yes/no
    'Yes': 'Tobacco_User_Yes',
    'No': 'Tobacco_User_No',
    'Yes_2': 'Medicare_Yes',
    'No_2': 'Medicare_No',
    'Check Box34': 'Medicaid_Yes',
    'Check Box35': 'Medicaid_No',
    'Check Box36': 'Other_Health_Plan_Yes',
    'Check Box37': 'Other_Health_Plan_No',
    'Check Box38': 'Other_Health_Plan_Relationship_Spouse',
    'Check Box39': 'Other_Health_Plan_Relationship_Child',
    # Other health plan text
    'Carrier Name': 'Other_Health_Plan_Carrier_Name',
    'Carrier Policy': 'Other_Health_Plan_Policy_Number',
    "Policy Holder's Name": 'Other_Health_Plan_Policyholder_Name',
    'undefined': 'Other_Health_Plan_Policyholder_Name',
    'Relationship': 'Other_Health_Plan_Relationship',
    # Dependent 1
    'Name5_es_:signer:fullname': 'Dependent_1_Name',
    'Date11_es_:signer:date': 'Dependent_1_Birthdate',
    'Text25': 'Dependent_1_Relationship',
    'Text24': 'Dependent_1_SSN_Last4',
    'Text26': 'Dependent_1_Address',
    'Male_2': 'Dependent_1_Gender_Male',
    'Check Box40': 'Dependent_1_Gender_Female',
    # Dependent 2
    'Name6_es_:signer:fullname': 'Dependent_2_Name',
    'Text27': 'Dependent_2_Birthdate',
    'Text28': 'Dependent_2_Relationship',
    'Text29': 'Dependent_2_SSN_Last4',
    'Text30': 'Dependent_2_Address',
    'Male_3': 'Dependent_2_Gender_Male',
    'Female_3': 'Dependent_2_Gender_Female',
    'Male_3.Dependent_2_Gender_Male': 'Dependent_2_Gender_Male',
    'Male_4.Dependent_3_Gender_Male': 'Dependent_3_Gender_Male',
    # Dependent 3
    'Name7_es_:signer:fullname': 'Dependent_3_Name',
    'Date10_es_:signer:date': 'Dependent_3_Birthdate',
    'Text31': 'Dependent_3_Relationship',
    'Text32': 'Dependent_3_SSN_Last4',
    'Text33': 'Dependent_3_Address',
    'Male_4': 'Dependent_3_Gender_Male',
    'Female_4': 'Dependent_3_Gender_Female',
    # Acknowledgements
    'Employee Handbook Received': 'Ack_Employee_Handbook',
    'Harassment Training Completed': 'Ack_Harassment_Training',
    'Technical Training Received': 'Ack_Technical_Training',
    'Hepatitis B Vaccine Declination': 'Ack_Hepatitis_B_Declination',
    'Safety Data SheetsSafety Handbook Reviewed': 'Ack_Safety_Handbook_Reviewed',
    'Urethane Liner Safety Received Rhino Technician only': 'Ack_Urethane_Liner_Safety',
    # Signatures
    'Signature1_es_:signer:signature': 'Employee_Signature',
    'Signature2_es_:signer:signature': 'Manager_Signature',
    'Date': 'Employee_Signature_Date',
    'Date_2': 'Manager_Signature_Date',
}

# Canonical acro names that identify this form
EE_FORM_MARKER_ACROS = frozenset({'Employee_Name', 'Dependent_1_Name'})

# Choice groups: group_id -> list of canonical acro names
EE_ACRO_CHOICE_GROUPS: dict[str, list[str]] = {
    'ee_marital': ['Employee_Marital_Status_Single', 'Employee_Marital_Status_Married'],
    'ee_gender': ['Employee_Gender_Male', 'Employee_Gender_Female'],
    'ee_race': [
        'Race_Black_African_American', 'Race_American_Indian', 'Race_Asian',
        'Race_Native_Hawaiian_Pacific_Islander', 'Race_Hispanic_Spanish', 'Race_White_Caucasian',
    ],
    'ee_tobacco': ['Tobacco_User_Yes', 'Tobacco_User_No'],
    'ee_medicare': ['Medicare_Yes', 'Medicare_No'],
    'ee_medicaid': ['Medicaid_Yes', 'Medicaid_No'],
    'ee_group_health': ['Other_Health_Plan_Yes', 'Other_Health_Plan_No'],
    'ee_health_plan_relationship': [
        'Other_Health_Plan_Relationship_Spouse', 'Other_Health_Plan_Relationship_Child',
    ],
    'ee_dep1_gender': ['Dependent_1_Gender_Male', 'Dependent_1_Gender_Female'],
    'ee_dep2_gender': ['Dependent_2_Gender_Male', 'Dependent_2_Gender_Female'],
    'ee_dep3_gender': ['Dependent_3_Gender_Male', 'Dependent_3_Gender_Female'],
}

EE_ACRO_TO_CHOICE_GROUP: dict[str, str] = {}
for _gid, _acros in EE_ACRO_CHOICE_GROUPS.items():
    for _a in _acros:
        EE_ACRO_TO_CHOICE_GROUP[_a] = _gid

# Independent acknowledgement checkboxes (not mutually exclusive)
EE_ACK_ACROS = [
    'Ack_Employee_Handbook',
    'Ack_Harassment_Training',
    'Ack_Technical_Training',
    'Ack_Hepatitis_B_Declination',
    'Ack_Safety_Handbook_Reviewed',
    'Ack_Urethane_Liner_Safety',
]

EE_SIGNATURE_ACROS = {
    'employee': 'Employee_Signature',
    'manager': 'Manager_Signature',
}

# Reverse map: canonical -> any legacy (for value migration lookups)
EE_CANONICAL_FROM_LEGACY: dict[str, str] = {}
for _legacy, _canonical in EE_PDF_FIELD_RENAMES.items():
    EE_CANONICAL_FROM_LEGACY[_legacy] = _canonical


def canonical_acro(name: str) -> str:
    """Resolve legacy or partial name to canonical acro name."""
    n = (name or '').strip()
    if not n:
        return n
    return EE_PDF_FIELD_RENAMES.get(n, n)


def is_ee_form_acro_set(acro_keys: set[str]) -> bool:
    canonical = {canonical_acro(k) for k in acro_keys}
    return EE_FORM_MARKER_ACROS.issubset(canonical)
