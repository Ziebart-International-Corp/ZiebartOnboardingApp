"""PDF path resolution, signed-copy build/persist, and completed-PDF viewers."""
from __future__ import annotations

import base64
import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import current_app, render_template, send_file, session
from werkzeug.utils import secure_filename

from config import BASE_DIR
from models import (
    Document, DocumentAssignment, DocumentSignature, DocumentSignatureField,
    DocumentTypedField, DocumentTypedFieldValue, SignatureAuditLog, UserTask, db,
)

try:
    import fitz
    FITZ_AVAILABLE = True
except Exception:
    fitz = None
    FITZ_AVAILABLE = False

ACRO_PLACEHOLDER_PREFIX = "acro:"


def _document_wizard_overlay_key(doc_id):
    import app as main
    return main._document_wizard_overlay_key(doc_id)


def document_fully_completed_for_user(document_id, username):
    import app as main
    return main.document_fully_completed_for_user(document_id, username)


def is_signature_field_signed(document_id, field, username):
    import app as main
    return main.is_signature_field_signed(document_id, field, username)


def is_typed_field_filled(document_id, field, username):
    import app as main
    return main.is_typed_field_filled(document_id, field, username)

def _signed_pdf_download_filename(document, username):
    base_name = os.path.splitext(document.original_filename)[0]
    ext = os.path.splitext(document.original_filename)[1] or '.pdf'
    return f"{base_name}_signed_{username}{ext}"


def _typed_signature_text_for_document(document_id, username):
    """Return typed signature text when a document has no image signature fields."""
    try:
        from employment_pdf_field_map import EMP_DOCUMENT_ID, EMP_SIGNATURE_ACRO
        if document_id == EMP_DOCUMENT_ID:
            for tf in DocumentTypedField.query.filter_by(document_id=document_id).all():
                if _pdf_field_name_from_placeholder(tf.placeholder) == EMP_SIGNATURE_ACRO:
                    val = DocumentTypedFieldValue.query.filter_by(
                        document_id=document_id,
                        typed_field_id=tf.id,
                        username=username,
                    ).first()
                    if val and (val.field_value or '').strip():
                        return val.field_value.strip()
    except ImportError:
        pass
    for tf in DocumentTypedField.query.filter_by(document_id=document_id).all():
        if tf.field_type != 'text':
            continue
        label = (tf.field_label or '').lower()
        if 'signature' not in label:
            continue
        val = DocumentTypedFieldValue.query.filter_by(
            document_id=document_id,
            typed_field_id=tf.id,
            username=username,
        ).first()
        if val and (val.field_value or '').strip():
            return val.field_value.strip()
    return ''


def _completed_document_cards_for_user(username):
    """
    Documents for the staff new-hire details page: image signatures plus
    completed assignments that only have typed signatures (e.g. employment application).
    """
    cards_by_doc_id: dict[int, dict] = {}

    def _ensure_card(doc_id, completed_at=None):
        if doc_id in cards_by_doc_id:
            card = cards_by_doc_id[doc_id]
            if completed_at and (
                not card.get('completed_at') or completed_at > card['completed_at']
            ):
                card['completed_at'] = completed_at
            return card
        doc = Document.query.get(doc_id)
        if not doc:
            return None
        card = {
            'document': doc,
            'signatures': [],
            'typed_signature': '',
            'completed_at': completed_at,
        }
        cards_by_doc_id[doc_id] = card
        return card

    for sig in DocumentSignature.query.filter_by(username=username).all():
        card = _ensure_card(sig.document_id, sig.signed_at)
        if card:
            card['signatures'].append(sig)

    for assignment in DocumentAssignment.query.filter_by(
        username=username, is_completed=True,
    ).all():
        _ensure_card(assignment.document_id, assignment.completed_at)

    for task in UserTask.query.filter_by(
        username=username, task_type='document', status='completed',
    ).all():
        if task.document_id:
            _ensure_card(task.document_id, task.completed_at)

    for card in cards_by_doc_id.values():
        if not card['signatures']:
            card['typed_signature'] = _typed_signature_text_for_document(
                card['document'].id, username,
            )

    return sorted(
        cards_by_doc_id.values(),
        key=lambda c: c.get('completed_at') or datetime.min,
        reverse=True,
    )


def _send_built_user_pdf(document, username, *, as_attachment=False):
    """Build filled PDF for a user and return a Flask send_file response, or (None, error)."""
    from io import BytesIO

    ok, path_or_err = _build_signed_pdf_copy_for_user(document, username)
    if not ok:
        return None, path_or_err
    try:
        with open(path_or_err, 'rb') as f:
            data = f.read()
    finally:
        try:
            os.unlink(path_or_err)
        except OSError:
            pass
    if not data:
        return None, 'Built PDF was empty'
    buf = BytesIO(data)
    buf.seek(0)
    response = send_file(
        buf,
        as_attachment=as_attachment,
        download_name=_signed_pdf_download_filename(document, username),
        mimetype=document.file_type or 'application/pdf',
    )
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response, None


def _document_is_fillable_pdf(document) -> bool:
    if not document:
        return False
    ft = (document.file_type or '').lower()
    name = (document.original_filename or document.filename or '').lower()
    return ft == 'application/pdf' or name.endswith('.pdf')


def _document_pdf_path(document) -> str | None:
    if not document or not document.file_path:
        return None
    path = document.file_path
    if not os.path.isabs(path):
        path = str(BASE_DIR / path)
    return path if os.path.isfile(path) else None


def resolve_document_file_path(document, repair_db=True):
    """Return an existing filesystem path for a document file, or None if missing.

    Tries stored file_path (absolute or relative to BASE_DIR) and uploads/<filename>.
    When a file is found at a different path than stored, optionally updates the DB row.
    """
    if not document:
        return None
    try:
        from employment_pdf_field_map import (
            EMP_DOCUMENT_ID,
            EMP_TRUTH_PDF_FILENAME,
            EMP_TRUTH_PDF_REL_PATH,
        )
        if document.id == EMP_DOCUMENT_ID:
            truth_path = BASE_DIR / EMP_TRUTH_PDF_REL_PATH
            stored = (document.file_path or '').replace('\\', '/')
            if truth_path.is_file() and 'clean' in stored.lower():
                if repair_db:
                    try:
                        document.file_path = EMP_TRUTH_PDF_REL_PATH
                        document.filename = EMP_TRUTH_PDF_FILENAME
                        if not (document.original_filename or '').strip():
                            document.original_filename = 'Employment Application.pdf'
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                return str(truth_path)
    except ImportError:
        pass
    candidates = []
    if document.file_path:
        candidates.append(document.file_path)
        p = Path(document.file_path)
        if not p.is_absolute():
            candidates.append(str(BASE_DIR / document.file_path))
    if document.filename:
        candidates.append(str(current_app.config['UPLOAD_FOLDER'] / document.filename))
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path):
            if repair_db and getattr(document, 'file_path', None) != path:
                try:
                    document.file_path = path
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            return path
    return None


def _pdf_field_name_from_placeholder(placeholder):
    """Extract AcroForm widget name from placeholder acro:FieldName."""
    ph = (placeholder or '').strip()
    if ph.startswith(ACRO_PLACEHOLDER_PREFIX):
        return ph[len(ACRO_PLACEHOLDER_PREFIX):]
    return ''


def _render_completed_pdf_viewer(document, doc_id, *, pdf_url, download_url, print_url='', header_actions_html=''):
    """Shared PDF.js viewer for user and staff completed-document pages."""
    return render_template('documents/completed_pdf_viewer.html', document=document,
        doc_id=doc_id,
        pdf_url=pdf_url,
        download_url=download_url,
        print_url=print_url,
        header_actions_html=header_actions_html,)


def _render_completed_pdf_print_page(document, pdf_url):
    """Minimal page that embeds the built PDF and opens the browser print dialog."""
    return render_template('documents/completed_pdf_print.html', document=document, pdf_url=pdf_url)


def embed_signature_in_pdf(document, signature_field, signature_image_base64):
    """Embed a signature image directly into the PDF at the specified coordinates"""
    if not FITZ_AVAILABLE:
        return False, "PyMuPDF not available"
    
    try:
        from PIL import Image
        
        # Open the PDF
        pdf_doc = fitz.open(document.file_path)
        
        # Get the page (0-indexed)
        page_num = signature_field.page_number - 1
        if page_num < 0 or page_num >= len(pdf_doc):
            pdf_doc.close()
            return False, f"Invalid page number: {signature_field.page_number}"
        
        page = pdf_doc[page_num]
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        # Convert coordinates from browser pixels to PDF points
        # The admin page uses PDF.js to render the PDF at exactly 800px height
        # Coordinates are stored relative to the viewer container (after accounting for canvas offset)
        # We need to convert these pixel coordinates to PDF points
        
        # The PDF.js viewer renders at 800px height, maintaining aspect ratio
        viewer_height_px = 800.0
        
        # Calculate scale factor: PDF points per pixel
        # This matches the PDF.js rendering scale
        scale_y = page_height / viewer_height_px
        
        # Calculate viewer width at this scale (maintaining aspect ratio)
        viewer_width_px = viewer_height_px * (page_width / page_height)
        scale_x = page_width / viewer_width_px
        
        # Convert browser pixel coordinates to PDF points
        # Browser: (x, y) from top-left of canvas (stored directly from canvas click)
        # PyMuPDF: (x, y) from top-left of page (y increases downward)
        
        # Both use top-left origin, so direct conversion works!
        # X coordinate: direct conversion (both use left as origin)
        x_pdf = signature_field.x_position * scale_x
        
        # Y coordinate: direct conversion (both use top as origin, y increases downward)
        # signature_field.y_position is pixels from top of canvas (at 800px height scale)
        # This represents the TOP of the signature field
        # PyMuPDF also uses top-left origin, so no flipping needed!
        y_pdf = signature_field.y_position * scale_y
        
        # Convert width/height from pixels to PDF points
        width_pdf = (signature_field.width or 200) * scale_x
        height_pdf = (signature_field.height or 80) * scale_y
        
        # Clamp to page bounds (ensure signature fits on page)
        x_pdf = max(0, min(x_pdf, page_width - width_pdf))
        y_pdf = max(0, min(y_pdf, page_height - height_pdf))
        
        # Debug output
        print(f"\n=== Signature Embedding ===")
        print(f"Browser coords: x={signature_field.x_position:.1f}, y={signature_field.y_position:.1f}")
        print(f"PDF page: {page_width:.1f} x {page_height:.1f} points")
        print(f"Scale: x={scale_x:.6f}, y={scale_y:.6f}")
        print(f"PDF coords: x={x_pdf:.2f}, y={y_pdf:.2f}")
        print(f"Size: {width_pdf:.2f} x {height_pdf:.2f}")
        print(f"========================\n")
        
        # Decode signature image
        sig_image_data = base64.b64decode(signature_image_base64)
        sig_img = Image.open(BytesIO(sig_image_data))
        
        # Convert PIL image to bytes for PyMuPDF
        img_bytes = BytesIO()
        sig_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Create a PyMuPDF image rectangle
        # PyMuPDF Rect uses (x0, y0, x1, y1) where (x0,y0) is top-left and (x1,y1) is bottom-right
        # Origin is top-left, y increases downward
        # x_pdf and y_pdf are already in PDF points from top-left, so use directly
        img_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
        
        print(f"PyMuPDF rect: {img_rect}")
        
        # Insert the image into the PDF page
        page.insert_image(img_rect, stream=img_bytes.getvalue())
        
        # Save the modified PDF (incremental to preserve other data)
        pdf_doc.save(document.file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        pdf_doc.close()
        
        return True, "Signature embedded successfully"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error embedding signature: {str(e)}"


def calculate_pdf_hash(file_path):
    """Calculate SHA-256 hash of a PDF file for audit trail"""
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def sign_pdf_cryptographically(document, signature_field, username):
    """
    Sign a PDF cryptographically using pyHanko (PAdES compliant)
    This creates a legally binding, tamper-evident signature
    """
    if not PYHANKO_AVAILABLE:
        return False, "pyHanko library not available. Install with: pip install pyhanko[full]"
    
    try:
        # For now, we'll use a self-signed certificate for demonstration
        # In production, you MUST use a CA-issued document signing certificate
        # and store private keys securely (HSM/KMS)
        
        # TODO: Load certificate and key from secure storage (HSM/KMS)
        # For now, return an error indicating certificate setup is needed
        return False, "Cryptographic signing requires certificate setup. Please configure signing certificate and key in secure storage (HSM/KMS)."
        
        # Example implementation (commented out until certificates are configured):
        # signer = signers.SimpleSigner.load(
        #     key_file="path/to/private_key.pem",
        #     cert_file="path/to/signing_cert.pem",
        #     key_passphrase=b"password",  # In production, get from secure vault
        #     ca_chain_files=["path/to/intermediate_cert.pem"]
        # )
        # 
        # # Optional: Use trusted timestamp authority
        # tsa = HTTPTimeStamper("https://freetsa.org/tsr") if use_tsa else None
        # 
        # with open(document.file_path, "rb") as infile:
        #     writer = IncrementalPdfFileWriter(infile)
        #     
        #     # Convert browser pixel coordinates to PDF points
        #     # (Same conversion logic as embed_signature_in_pdf)
        #     pdf_doc = fitz.open(document.file_path)
        #     page = pdf_doc[signature_field.page_number - 1]
        #     page_rect = page.rect
        #     page_width = page_rect.width
        #     page_height = page_rect.height
        #     pdf_doc.close()
        #     
        #     viewer_height_px = 800.0
        #     scale_y = page_height / viewer_height_px
        #     viewer_width_px = viewer_height_px * (page_width / page_height)
        #     scale_x = page_width / viewer_width_px
        #     
        #     x_pdf = signature_field.x_position * scale_x
        #     y_from_top_pdf = signature_field.y_position * scale_y
        #     y_pdf = page_height - y_from_top_pdf - (signature_field.height * scale_y)
        #     width_pdf = signature_field.width * scale_x
        #     height_pdf = signature_field.height * scale_y
        #     
        #     # Create signature field in PDF
        #     sig_field = fields.SigFieldSpec(
        #         field_name=f"Signature_{signature_field.id}",
        #         box=(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf),
        #         on_page=signature_field.page_number - 1  # 0-indexed
        #     )
        #     
        #     signers.sign_pdf(
        #         writer,
        #         signers.PdfSignatureMetadata(
        #             field_name=f"Signature_{signature_field.id}",
        #             reason=f"Signed by {username}",
        #             location="Ziebart Onboarding System",
        #             use_pades_lta=True  # PAdES Long Term Availability
        #         ),
        #         signer=signer,
        #         timestamper=tsa,
        #         new_field_spec=sig_field,
        #         output=open(document.file_path, "wb")
        #     )
        # 
        # return True, "PDF signed cryptographically"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error signing PDF: {str(e)}"


def _build_signed_pdf_copy_for_user(document, username, output_path=None):
    """
    Build a signed PDF copy from stored signature/typed values without mutating original.
    Returns (success, path_or_error).
    """
    if not FITZ_AVAILABLE:
        return False, "PyMuPDF not available"
    pdf_source = resolve_document_file_path(document)
    if not pdf_source:
        return False, "Original document file not found"

    import tempfile
    import shutil

    try:
        try:
            user_signatures = DocumentSignature.query.filter_by(
                document_id=document.id,
                username=username
            ).all()
        except Exception:
            user_signatures = []

        try:
            user_typed_values = DocumentTypedFieldValue.query.filter_by(
                document_id=document.id,
                username=username
            ).all()
            typed_value_map = {val.typed_field_id: val.field_value for val in user_typed_values}
            typed_value_filled_at = {val.typed_field_id: val.filled_at for val in user_typed_values}
        except Exception:
            typed_value_map = {}
            typed_value_filled_at = {}

        # Build a copy even if no fields are filled (keeps copy semantics explicit).
        if output_path:
            work_path = str(output_path)
            Path(work_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_source, work_path)
        else:
            temp_fd, work_path = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)
            shutil.copy2(pdf_source, work_path)

        pdf_doc = fitz.open(work_path)

        typed_fields = DocumentTypedField.query.filter_by(document_id=document.id).all()
        signature_fields = DocumentSignatureField.query.filter_by(document_id=document.id).all()

        try:
            from employment_wizard_labels import (
                is_employment_application_form,
                migrate_employment_applied_employed_values,
                repair_employment_application_field_groups,
            )
            if is_employment_application_form(typed_fields):
                emp_changed = repair_employment_application_field_groups(typed_fields)
                from employment_wizard_labels import (
                    ensure_employment_education_table_positions,
                    ensure_employment_radio_pair_fields,
                )
                if ensure_employment_radio_pair_fields(document, typed_fields):
                    emp_changed = True
                    typed_fields = DocumentTypedField.query.filter_by(document_id=document.id).all()
                if ensure_employment_education_table_positions(typed_fields):
                    emp_changed = True
                if migrate_employment_applied_employed_values(document.id, username, typed_fields):
                    emp_changed = True
                if emp_changed:
                    db.session.commit()
                    user_typed_values = DocumentTypedFieldValue.query.filter_by(
                        document_id=document.id,
                        username=username,
                    ).all()
                    typed_value_map = {val.typed_field_id: val.field_value for val in user_typed_values}
                    typed_value_filled_at = {val.typed_field_id: val.filled_at for val in user_typed_values}
        except Exception:
            current_app.logger.exception('employment repair/migrate before PDF build doc_id=%s', document.id)

        embed_typed_field_values_in_pdf(
            pdf_doc, typed_fields, typed_value_map, typed_value_filled_at,
        )
        try:
            from flask import has_request_context
            from employment_wizard_labels import (
                build_employment_overlay_values,
                is_employment_application_form,
                load_employment_wizard_parts,
            )
            if is_employment_application_form(typed_fields):
                composite_parts = load_employment_wizard_parts(document.id, username)
                overlays = build_employment_overlay_values(
                    typed_fields, typed_value_map, composite_parts,
                )
                if has_request_context():
                    legacy_edu_overlay_keys = {
                        'edu_high_school_name',
                        'edu_college_name',
                        'edu_technical_name',
                        'edu_other_name',
                    }
                    legacy_emp_date_keys = {
                        f'emp_employer_{n}_dates' for n in range(1, 6)
                    }
                    session_overlays = {
                        k: v for k, v in (session.get(_document_wizard_overlay_key(document.id)) or {}).items()
                        if k not in legacy_edu_overlay_keys and k not in legacy_emp_date_keys
                    }
                    overlays = {**overlays, **session_overlays}
                embed_employment_overlay_values(pdf_doc, overlays)
        except Exception:
            pass
        embed_signatures_in_pdf(pdf_doc, user_signatures, signature_fields)
        flatten_pdf_form_widgets(pdf_doc)

        remaining_widgets = sum(len(list(p.widgets() or [])) for p in pdf_doc)
        if remaining_widgets:
            current_app.logger.warning(
                'completed PDF still has %s widget(s) after flatten doc_id=%s user=%s',
                remaining_widgets, document.id, username,
            )

        try:
            flat_doc = rasterize_pdf_pages(pdf_doc)
            pdf_doc.close()
            save_pdf_document_copy(flat_doc, work_path)
        except Exception as raster_err:
            current_app.logger.warning(
                'rasterize failed doc_id=%s user=%s, saving vector PDF: %s',
                document.id, username, raster_err,
            )
            save_pdf_document_copy(pdf_doc, work_path)
        return True, work_path
    except Exception as e:
        return False, str(e)


def _persist_signed_pdf_copy(document, username):
    """Persist a finalized signed PDF copy to uploads/signed_copies and return its relative path."""
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    base_name = secure_filename(f"{Path(document.original_filename).stem}_signed_{username}_{ts}.pdf")
    rel_path = Path('uploads') / 'signed_copies' / str(document.id) / base_name
    abs_path = BASE_DIR / rel_path
    ok, result = _build_signed_pdf_copy_for_user(document, username, output_path=abs_path)
    if not ok:
        raise RuntimeError(result)
    return str(rel_path).replace('\\', '/')


def _create_signature_audit_log(document_id, username, event_type, details='', used_saved_signature=False, signed_copy_path=None):
    """Best-effort audit logging for signature actions."""
    try:
        log = SignatureAuditLog(
            document_id=document_id,
            username=username,
            event_type=event_type,
            details=details,
            used_saved_signature=bool(used_saved_signature),
            signed_copy_path=signed_copy_path,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

