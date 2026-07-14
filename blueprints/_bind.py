"""Bind names from the main app module into a register() locals dict for closures."""
from __future__ import annotations

from typing import Any


# Models / symbols imported on app.py that route bodies commonly reference
COMMON_MODEL_NAMES = (
    "Store",
    "Department",
    "UserModel",
    "NewHire",
    "Document",
    "Role",
    "ChecklistItem",
    "NewHireChecklist",
    "TrainingVideo",
    "QuizQuestion",
    "QuizAnswer",
    "UserTrainingProgress",
    "UserQuizResponse",
    "UserTask",
    "DocumentSignatureField",
    "DocumentSignature",
    "DocumentTypedField",
    "DocumentTypedFieldValue",
    "DocumentAssignment",
    "ExternalLink",
    "UserNotification",
    "ManagerPermission",
    "AdminSetting",
    "SignatureAuditLog",
)

# PDF / document helpers still defined on app.py
DOCUMENT_HELPER_NAMES = (
    "_drop_field_editor_noise_flashes",
    "_document_is_fillable_pdf",
    "_document_pdf_path",
    "_ensure_stores_and_store_id",
    "_attach_document_store_lists",
    "count_orphaned_document_user_tasks",
    "count_pdf_acroform_widgets",
    "PDF_WIZARD_FITZ_AVAILABLE",
    "FITZ_AVAILABLE",
    "allowed_file",
    "allowed_video_file",
)


def bind_from_main(main: Any, *extra_names: str) -> dict[str, Any]:
    """Return {name: value} for names that exist on the main app module."""
    names = COMMON_MODEL_NAMES + DOCUMENT_HELPER_NAMES + extra_names
    out: dict[str, Any] = {}
    for name in names:
        if hasattr(main, name):
            out[name] = getattr(main, name)
    return out
