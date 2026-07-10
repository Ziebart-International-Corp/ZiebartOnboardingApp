"""Conditional Offer Letter — AcroForm names and wizard config."""
from __future__ import annotations

COL_OFFER_DOCUMENT_ID = 16
COL_OFFER_PDF_FILENAME = '20260708_124404_Conditional_Letter_-_FT.pdf'

# Unique acro names on this template (not shared with Employment Application markers).
COL_OFFER_FORM_MARKER_ACROS = frozenset({
    'undefined_2',
    'This letter shall confirm our conditional offer of employment to you as a nonexempt',
})

COL_OFFER_LOCATION_ACRO = (
    'This letter shall confirm our conditional offer of employment to you as a nonexempt'
)
COL_OFFER_APPLICANT_NAME_ACRO = 'undefined_2'
COL_OFFER_POSITION_ACRO = 'Text1'
COL_OFFER_STORE_MANAGER_DATE_ACRO = 'Employee_Signature_Date'
COL_OFFER_APPLICANT_DATE_ACRO = 'Manager_Signature_Date'

COL_OFFER_SECTION_OFFER = 'Offer details'
COL_OFFER_SECTION_MANAGER = 'Store manager'
COL_OFFER_SECTION_APPLICANT = 'Your signature'

# Wizard step order: kind, key (acro or signature role)
COL_OFFER_FLOW: list[tuple[str, str]] = [
    ('typed', COL_OFFER_APPLICANT_NAME_ACRO),
    ('typed', COL_OFFER_POSITION_ACRO),
    ('typed', COL_OFFER_LOCATION_ACRO),
    ('sig', 'store_manager'),
    ('typed', COL_OFFER_STORE_MANAGER_DATE_ACRO),
    ('sig', 'applicant'),
    ('typed', COL_OFFER_APPLICANT_DATE_ACRO),
]

COL_OFFER_TYPED_ACROS = frozenset({
    COL_OFFER_APPLICANT_NAME_ACRO,
    COL_OFFER_POSITION_ACRO,
    COL_OFFER_LOCATION_ACRO,
    COL_OFFER_STORE_MANAGER_DATE_ACRO,
    COL_OFFER_APPLICANT_DATE_ACRO,
})

COL_OFFER_SIGNATURE_ROLES = frozenset({'store_manager', 'applicant'})
