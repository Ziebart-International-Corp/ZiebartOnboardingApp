"""Document library and admin document management routes."""
from __future__ import annotations

from datetime import datetime

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request,
    session, url_for, send_file, send_from_directory,
)
from flask_login import current_user
from sqlalchemy import text

from auth import admin_required, manager_required, login_required
from blueprints._bind import bind_from_main
from models import (
    Document, DocumentAssignment, DocumentSignature, DocumentSignatureField,
    DocumentTypedField, NewHire, Store, db,
)


def register(app: Flask) -> None:
    """Register document routes (endpoint names unchanged)."""
    import app as main

    # Enclosing-scope bindings so nested views can use helpers still on app.py
    locals().update(bind_from_main(main))
    # Explicit locals for reliable closures (update() alone is not enough for nested defs)
    _b = bind_from_main(main)
    _drop_field_editor_noise_flashes = _b["_drop_field_editor_noise_flashes"]
    _document_is_fillable_pdf = _b["_document_is_fillable_pdf"]
    _document_pdf_path = _b["_document_pdf_path"]
    _ensure_stores_and_store_id = _b["_ensure_stores_and_store_id"]
    _attach_document_store_lists = _b["_attach_document_store_lists"]
    count_orphaned_document_user_tasks = _b["count_orphaned_document_user_tasks"]
    count_pdf_acroform_widgets = _b["count_pdf_acroform_widgets"]
    PDF_WIZARD_FITZ_AVAILABLE = _b["PDF_WIZARD_FITZ_AVAILABLE"]
    documents_for_user_files = main.documents_for_user_files
    document_fully_completed_for_user = main.document_fully_completed_for_user
    _user_can_fill_document = main._user_can_fill_document
    _send_built_user_pdf = main._send_built_user_pdf
    _render_completed_pdf_viewer = main._render_completed_pdf_viewer
    _render_completed_pdf_print_page = main._render_completed_pdf_print_page
    _persist_signed_pdf_copy = main._persist_signed_pdf_copy
    _mark_document_assignment_complete_if_ready = main._mark_document_assignment_complete_if_ready
    _create_signature_audit_log = main._create_signature_audit_log
    _document_configured_field_count = main._document_configured_field_count
    _ensure_document_typed_field_columns = main._ensure_document_typed_field_columns
    _pdf_field_name_from_placeholder = main._pdf_field_name_from_placeholder
    _try_auto_import_acroform_fields = main._try_auto_import_acroform_fields
    document_uses_step_wizard = main.document_uses_step_wizard
    document_visible_to_store = main.document_visible_to_store
    is_signature_field_signed = main.is_signature_field_signed
    maybe_send_all_tasks_completed_email = main.maybe_send_all_tasks_completed_email
    resolve_document_file_path = main.resolve_document_file_path
    typed_field_is_phone_like = main.typed_field_is_phone_like
    ACRO_PLACEHOLDER_PREFIX = main.ACRO_PLACEHOLDER_PREFIX
    DOCUMENT_WIZARD_MIN_FIELDS = main.DOCUMENT_WIZARD_MIN_FIELDS
    FIELD_EDITOR_TYPE_CHOICES = main.FIELD_EDITOR_TYPE_CHOICES
    FITZ_AVAILABLE = main.FITZ_AVAILABLE
    TYPED_FIELD_LAST4_REGEX_JS = main.TYPED_FIELD_LAST4_REGEX_JS
    TYPED_FIELD_PHONE_PATTERN_HTML = main.TYPED_FIELD_PHONE_PATTERN_HTML
    TYPED_FIELD_PHONE_REGEX_JS = main.TYPED_FIELD_PHONE_REGEX_JS
    TYPED_FIELD_TYPE_CHOICES = main.TYPED_FIELD_TYPE_CHOICES
    UserModel = main.UserModel
    from werkzeug.utils import secure_filename
    fitz = getattr(main, "fitz", None)
    allowed_file = main.allowed_file
    DocumentTypedFieldValue = main.DocumentTypedFieldValue
    cleanup_orphaned_document_user_tasks = main.cleanup_orphaned_document_user_tasks
    _signature_fields_redirect = main._signature_fields_redirect
    _delete_user_tasks_for_document = main._delete_user_tasks_for_document
    normalize_typed_field_type = main.normalize_typed_field_type
    validate_typed_field_value = main.validate_typed_field_value
    clear_choice_group_selections_except = main.clear_choice_group_selections_except
    _staff_can_view_user_documents = main._staff_can_view_user_documents
    _staff_new_hire_details_url = main._staff_new_hire_details_url
    SignatureAuditLog = main.SignatureAuditLog
    import os

    @app.route('/admin/documents')
    @login_required
    def manage_documents():
        """Manage documents - upload and manage new hire paperwork. Admin or manager with manage_documents permission. Managers see only forms for their store, view/download only."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_documents'):
            abort(403)
        # Field-editor success flashes aren't shown on that page, so purge leftovers here
        _drop_field_editor_noise_flashes()
        is_manager_view = main.uses_manager_console_scope()
        try:
            store_id = main.get_current_user_store_id()
            if is_manager_view and store_id is not None:
                # Only documents visible to this store (is_visible and assigned to this store or all stores)
                q = main.documents_visible_to_store_query(store_id).order_by(Document.created_at.desc())
                documents = q.all()
            elif is_manager_view:
                documents = []
            else:
                documents = Document.query.order_by(Document.created_at.desc()).all()
        except Exception as e:
            # If display_name column is missing (existing DBs), add it and retry
            db.session.rollback()
            err_str = (str(e) or '').lower()
            if 'display_name' in err_str or 'invalid column' in err_str or 'unknown column' in err_str:
                try:
                    db.session.execute(text("ALTER TABLE documents ADD display_name NVARCHAR(255) NULL"))
                    db.session.commit()
                except Exception as alter_e:
                    db.session.rollback()
                    flash('Database update needed. Run this SQL on your database: ALTER TABLE documents ADD display_name NVARCHAR(255) NULL;', 'error')
                    return redirect(main.staff_console_home_url())
                if is_manager_view and main.get_current_user_store_id() is not None:
                    sid = main.get_current_user_store_id()
                    documents = main.documents_visible_to_store_query(sid).order_by(Document.created_at.desc()).all()
                elif is_manager_view:
                    documents = []
                else:
                    documents = Document.query.order_by(Document.created_at.desc()).all()
            else:
                raise
        # For managers: only count signatures from users at their store
        store_usernames = None
        if is_manager_view and store_id is not None:
            store_usernames = set(nh.username for nh in NewHire.query.filter_by(store_id=store_id).all())
        try:
            # Get signature status for each document
            for doc in documents:
                signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
                doc.signature_fields_count = len(signature_fields)
                try:
                    doc.typed_fields_count = DocumentTypedField.query.filter_by(document_id=doc.id).count()
                except Exception:
                    doc.typed_fields_count = 0
                doc.configured_fields_count = doc.signature_fields_count + doc.typed_fields_count
                doc.acro_widget_count = 0
                if _document_is_fillable_pdf(doc) and PDF_WIZARD_FITZ_AVAILABLE:
                    pdf_path = _document_pdf_path(doc)
                    if pdf_path:
                        try:
                            doc.acro_widget_count = count_pdf_acroform_widgets(pdf_path)
                        except Exception:
                            doc.acro_widget_count = 0
                # Count how many users have signed (for managers: only users at their store)
                try:
                    signatures = DocumentSignature.query.filter_by(document_id=doc.id).all()
                    if store_usernames is not None:
                        signatures = [s for s in signatures if s.username in store_usernames]
                    doc.signatures_count = len(signatures)
                    # Get unique users who signed
                    signed_users = set(sig.username for sig in signatures)
                    doc.signed_users_count = len(signed_users)
                except Exception as e:
                    # If query fails (columns don't exist), use defaults
                    doc.signatures_count = 0
                    doc.signed_users_count = 0
        except Exception as e:
            # If anything fails, provide default values
            if is_manager_view and main.get_current_user_store_id() is not None:
                sid = main.get_current_user_store_id()
                documents = main.documents_visible_to_store_query(sid).order_by(Document.created_at.desc()).all()
            elif is_manager_view:
                documents = []
            else:
                documents = Document.query.order_by(Document.created_at.desc()).all()
            for doc in documents:
                doc.signature_fields_count = 0
                doc.typed_fields_count = 0
                doc.configured_fields_count = 0
                doc.acro_widget_count = 0
                doc.signatures_count = 0
                doc.signed_users_count = 0
                doc.store_ids = []
        _ensure_stores_and_store_id()
        _attach_document_store_lists(documents)
        stores = Store.query.order_by(Store.name).all()
        store_by_id = {s.id: s.name for s in stores}
        orphaned_document_task_count = 0
        if not is_manager_view:
            orphaned_document_task_count = count_orphaned_document_user_tasks()
        return render_template('documents/manage.html', documents=documents, stores=stores, store_by_id=store_by_id, is_manager_view=is_manager_view,
             orphaned_document_task_count=orphaned_document_task_count)

    @app.route('/documents')
    @login_required
    def view_documents():
        """View assigned documents (regular users) or all documents (admins). Supports ?sign=<doc_id> or ?wizard=<doc_id>."""
        wizard_id = request.args.get('wizard')
        if wizard_id:
            try:
                doc_id = int(wizard_id)
                return main._serve_document_wizard_page(doc_id)
            except (ValueError, TypeError):
                pass
        sign_id = request.args.get('sign')
        if sign_id:
            try:
                doc_id = int(sign_id)
                return _serve_sign_document_page(doc_id)
            except (ValueError, TypeError):
                pass
        return _view_documents_impl()

    def _view_documents_impl():
        """Implementation of view_documents. Renders Files page with empty list on error instead of redirecting."""
        documents = []
        is_admin = current_user.is_admin() if current_user else False
        user_first_name = (current_user.username if current_user else 'User') or 'User'
        user_full_name = (current_user.username if current_user else 'User') or 'User'
        assigned_documents = []
        assigned_doc_ids = set()

        try:
            documents, assigned_documents = documents_for_user_files(current_user.username)
            assigned_doc_ids = set(a.document_id for a in assigned_documents)

            # Check signature / typed field completion for each document
            for doc in documents:
                signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
                try:
                    typed_count = DocumentTypedField.query.filter_by(document_id=doc.id).count()
                except Exception:
                    typed_count = 0
                doc.has_signature_fields = len(signature_fields) > 0
                doc.has_form_fields = len(signature_fields) > 0 or typed_count > 0
                try:
                    doc.all_signed = document_fully_completed_for_user(doc.id, current_user.username)
                except Exception:
                    doc.all_signed = False
                doc.is_assigned = doc.id in assigned_doc_ids
                doc.needs_signature = doc.is_assigned and doc.has_form_fields and not doc.all_signed
                if doc.is_assigned:
                    doc.assignment = next((a for a in assigned_documents if a.document_id == doc.id), None)

            is_admin = current_user.is_admin()
            user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
            if user_new_hire:
                user_first_name = (user_new_hire.first_name or '').strip() or current_user.username
                _ln = (user_new_hire.last_name or '').strip()
                user_full_name = f"{user_first_name} {_ln}".strip() if _ln else (user_first_name or current_user.username)
            else:
                user_first_name = current_user.username
                user_full_name = current_user.username
            if not user_first_name:
                user_first_name = current_user.username
            if not user_full_name:
                user_full_name = current_user.username
        except Exception as e:
            db.session.rollback()
            err_str = (str(e) or '').lower()
            if 'display_name' in err_str or 'invalid column' in err_str:
                try:
                    db.session.execute(text("ALTER TABLE documents ADD display_name NVARCHAR(255) NULL"))
                    db.session.commit()
                    documents, assigned_documents = documents_for_user_files(current_user.username)
                    assigned_doc_ids = set(a.document_id for a in assigned_documents)
                    for doc in documents:
                        signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
                        try:
                            typed_count = DocumentTypedField.query.filter_by(document_id=doc.id).count()
                        except Exception:
                            typed_count = 0
                        doc.has_signature_fields = len(signature_fields) > 0
                        doc.has_form_fields = len(signature_fields) > 0 or typed_count > 0
                        try:
                            doc.all_signed = document_fully_completed_for_user(doc.id, current_user.username)
                        except Exception:
                            doc.all_signed = False
                        doc.is_assigned = doc.id in assigned_doc_ids
                        doc.needs_signature = doc.is_assigned and doc.has_form_fields and not doc.all_signed
                        if doc.is_assigned:
                            doc.assignment = next((a for a in assigned_documents if a.document_id == doc.id), None)
                except Exception:
                    db.session.rollback()
                    import traceback
                    app.logger.error(f'Error in view_documents for {current_user.username}: {e}')
                    app.logger.error(traceback.format_exc())
                    flash('Unable to load document list. Showing empty list.', 'error')
                    documents = []
            else:
                import traceback
                app.logger.error(f'Error in view_documents for {current_user.username if current_user else "unknown"}: {str(e)}')
                app.logger.error(traceback.format_exc())
                flash('Unable to load document list. Showing empty list.', 'error')
                documents = []

        return render_template('documents/library.html', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name, documents=documents)



    @app.route('/admin/documents/<int:doc_id>/assign')
    @admin_required
    def assign_document(doc_id):
        """Assign a document to specific users for signing"""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        # Get all users (both regular users and admins) for assignment
        all_users = UserModel.query.order_by(UserModel.username).all()

        # Build display names: NewHire first+last name, else User.full_name, else username
        user_display_names = {}
        for u in all_users:
            new_hire = NewHire.query.filter_by(username=u.username).first()
            if new_hire:
                user_display_names[u.username] = f"{new_hire.first_name} {new_hire.last_name}".strip() or u.username
            elif getattr(u, 'full_name', None) and u.full_name.strip():
                user_display_names[u.username] = u.full_name.strip()
            else:
                user_display_names[u.username] = u.username

        # Get current assignments for this document
        current_assignments = DocumentAssignment.query.filter_by(document_id=doc_id).all()
        assigned_usernames = set(a.username for a in current_assignments)

        return render_template('documents/assign.html', document=document, all_users=all_users, assigned_usernames=assigned_usernames, current_assignments=current_assignments, user_display_names=user_display_names)



    @app.route('/admin/documents/<int:doc_id>/signature-fields')
    @admin_required
    def set_signature_fields(doc_id):
        """Admin interface to set signature field locations on a document"""
        _ensure_document_typed_field_columns()
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        # Get existing signature fields
        existing_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()

        # Get existing typed fields (handle case where table might not exist yet)
        try:
            existing_typed_fields = DocumentTypedField.query.filter_by(document_id=doc_id).all()
        except Exception as e:
            # Table doesn't exist yet, return empty list
            existing_typed_fields = []

        # Check if document is a PDF (for now, we'll support PDFs primarily)
        is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
        try:
            initial_page = max(1, int(request.args.get('page', 1)))
        except (TypeError, ValueError):
            initial_page = 1

        configured_field_count = len(existing_fields) + len(existing_typed_fields)
        acro_widget_count = 0
        pdf_path = _document_pdf_path(document)
        if is_pdf and pdf_path and PDF_WIZARD_FITZ_AVAILABLE:
            acro_widget_count = count_pdf_acroform_widgets(pdf_path)

        field_inventory = []
        for f in existing_fields:
            field_inventory.append({
                'kind': 'signature',
                'id': f.id,
                'pdf_name': '',
                'label': f.field_label or 'Signature',
                'field_type': 'signature',
                'page': f.page_number,
            })
        for f in existing_typed_fields:
            field_inventory.append({
                'kind': 'typed',
                'id': f.id,
                'pdf_name': _pdf_field_name_from_placeholder(f.placeholder),
                'label': f.field_label or 'Typed Field',
                'field_type': f.field_type or 'text',
                'choice_group': f.choice_group,
                'is_required': f.is_required,
                'page': f.page_number,
            })
        field_inventory.sort(key=lambda x: (x['page'], x['kind'], x['label'].lower()))

        return render_template('documents/signature_fields.html', document=document, existing_fields=existing_fields, existing_typed_fields=existing_typed_fields,
             is_pdf=is_pdf, initial_page=initial_page, acro_widget_count=acro_widget_count,
             configured_field_count=configured_field_count, field_inventory=field_inventory,
             typed_field_type_choices=TYPED_FIELD_TYPE_CHOICES,
             field_editor_type_choices=FIELD_EDITOR_TYPE_CHOICES)



    @app.route('/documents/<int:doc_id>/sign/submit', methods=['POST'])
    @login_required
    def submit_signature(doc_id):
        """Submit a signature for a document"""
        document = Document.query.get(doc_id)
        if not document:
            return jsonify({'success': False, 'error': 'Document not found'}), 404

        # Check permissions - only allow if document is assigned to user (unless admin)
        if not current_user.is_admin():
            assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
            if not assignment:
                return jsonify({'success': False, 'error': 'This document has not been assigned to you.'}), 403

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'error': 'Invalid or missing JSON in request'}), 400
        signature_field_id = data.get('signature_field_id')
        signature_image = data.get('signature_image')  # Base64 encoded (for image type)
        consent_given = data.get('consent_given', False)  # User consent for electronic signing
        used_saved_signature = bool(data.get('used_saved_signature', False))

        if not signature_field_id:
            return jsonify({'success': False, 'error': 'Missing signature field ID'}), 400

        # Verify signature field exists and belongs to this document
        signature_field = DocumentSignatureField.query.get(signature_field_id)
        if not signature_field or signature_field.document_id != doc_id:
            return jsonify({'success': False, 'error': 'Invalid signature field'}), 400

        if not signature_image:
            return jsonify({'success': False, 'error': 'Missing signature image'}), 400
        if not consent_given:
            return jsonify({'success': False, 'error': 'Intent confirmation is required before applying a signature'}), 400

        try:
            # Check if user already signed this field (by ID or by location for orphaned signatures)
            existing_signature = DocumentSignature.query.filter_by(
                document_id=doc_id,
                signature_field_id=signature_field_id,
                username=current_user.username
            ).first()

            # Also check for orphaned signatures at the same location
            if not existing_signature:
                try:
                    tolerance = 10.0
                    orphaned_sigs = DocumentSignature.query.filter_by(
                        document_id=doc_id,
                        username=current_user.username
                    ).filter(DocumentSignature.signature_field_id.is_(None)).all()

                    for sig in orphaned_sigs:
                        # Safely access new fields (may not exist if database not migrated)
                        field_page = getattr(sig, 'field_page_number', None)
                        field_x = getattr(sig, 'field_x_position', None)
                        field_y = getattr(sig, 'field_y_position', None)

                        if (field_page == signature_field.page_number and
                            field_x is not None and field_y is not None and
                            abs(field_x - signature_field.x_position) <= tolerance and
                            abs(field_y - signature_field.y_position) <= tolerance):
                            existing_signature = sig
                            # Reconnect orphaned signature to the new field
                            existing_signature.signature_field_id = signature_field_id
                            break
                except Exception:
                    # If new columns don't exist yet, skip orphaned signature matching
                    pass

            if existing_signature:
                # Update existing signature
                existing_signature.signature_image = signature_image
                existing_signature.signed_at = datetime.utcnow()
                existing_signature.ip_address = request.remote_addr
                existing_signature.user_agent = request.headers.get('User-Agent', '')
                existing_signature.consent_given = consent_given
                existing_signature.used_saved_signature = used_saved_signature
                # Update stored field metadata in case field was recreated
                # Safely set new fields (may not exist if database not migrated yet)
                try:
                    existing_signature.field_page_number = signature_field.page_number
                    existing_signature.field_x_position = signature_field.x_position
                    existing_signature.field_y_position = signature_field.y_position
                    existing_signature.field_width = signature_field.width
                    existing_signature.field_height = signature_field.height
                    existing_signature.field_label = signature_field.field_label
                except AttributeError:
                    # New columns don't exist yet, skip metadata storage
                    pass
                sig_to_embed = existing_signature
            else:
                # Create new signature record with stored field metadata
                # Build signature with basic fields first
                new_signature = DocumentSignature(
                    document_id=doc_id,
                    signature_field_id=signature_field_id,
                    username=current_user.username,
                    signature_image=signature_image,
                    signature_type='image',
                    signed_at=datetime.utcnow(),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', ''),
                    consent_given=consent_given,
                    used_saved_signature=used_saved_signature
                )

                # Add field metadata if columns exist (handle case where database hasn't been migrated)
                try:
                    new_signature.field_page_number = signature_field.page_number
                    new_signature.field_x_position = signature_field.x_position
                    new_signature.field_y_position = signature_field.y_position
                    new_signature.field_width = signature_field.width
                    new_signature.field_height = signature_field.height
                    new_signature.field_label = signature_field.field_label
                except (AttributeError, Exception):
                    # Columns don't exist yet, skip metadata (signature will still work)
                    pass
                db.session.add(new_signature)
                sig_to_embed = new_signature

            # Keep original documents immutable:
            # - Save signature/typed data in DB
            # - Generate signed copies on demand for preview/download
            #   (do NOT write image signatures into document.file_path)
            # Image signature: stored in DB; signed PDF copies generated on demand.
            success, message = True, "Signature saved to database"

            if not success:
                db.session.rollback()
                return jsonify({'success': False, 'error': message}), 500

            db.session.commit()
            _create_signature_audit_log(
                document_id=doc_id,
                username=current_user.username,
                event_type='apply_signature',
                details=f'Applied signature to field_id={signature_field_id}',
                used_saved_signature=used_saved_signature
            )

            all_complete = document_fully_completed_for_user(doc_id, current_user.username)

            # Update task completion if all fields signed and typed
            if all_complete:
                signed_copy_rel_path = None
                _mark_document_assignment_complete_if_ready(doc_id, current_user.username)

                # Persist a finalized signed PDF copy (async job, sync fallback).
                try:
                    from services.jobs import enqueue_or_persist_signed_pdf
                    _job, signed_copy_rel_path = enqueue_or_persist_signed_pdf(
                        document, current_user.username
                    )
                except Exception as e:
                    app.logger.warning(f"Failed to persist signed PDF copy: {e}")
                    main._log_exception_to_file(e)

                db.session.commit()
                any_saved_used = DocumentSignature.query.filter_by(
                    document_id=doc_id,
                    username=current_user.username,
                    used_saved_signature=True
                ).first() is not None
                _create_signature_audit_log(
                    document_id=doc_id,
                    username=current_user.username,
                    event_type='complete_document',
                    details='All required signature fields completed',
                    used_saved_signature=any_saved_used,
                    signed_copy_path=signed_copy_rel_path
                )
                try:
                    maybe_send_all_tasks_completed_email(current_user.username)
                except Exception as e:
                    app.logger.warning(f"All-tasks-completed email check failed: {e}")

            return jsonify({'success': True, 'message': 'Signature saved and embedded in PDF'})

        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500



    @app.route('/admin/upload-document', methods=['POST'])
    @login_required
    def upload_document():
        """Upload a new document. Admin or manager with manage_documents permission."""
        if not current_user.is_admin() and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            abort(403)
        if main.uses_manager_console_scope():
            abort(403)
        if 'file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('manage_documents'))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('manage_documents'))

        if not main.allowed_file(file.filename):
            flash('File type not allowed. Allowed types: PDF, DOC, DOCX, XLS, XLSX, TXT, JPG, PNG, GIF', 'error')
            return redirect(url_for('manage_documents'))

        try:
            # Secure the filename
            original_filename = file.filename
            filename = secure_filename(original_filename)

            # Add timestamp to avoid conflicts
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename

            # Save file
            upload_folder = app.config['UPLOAD_FOLDER']
            upload_folder.mkdir(exist_ok=True)  # Create directory if it doesn't exist
            file_path = upload_folder / filename
            file.save(str(file_path))

            # Get file size
            file_size = file_path.stat().st_size

            # Store: who can see this document (null = all stores)
            store_id = None
            store_id_raw = (request.form.get('store_id') or '').strip()
            if store_id_raw and store_id_raw.isdigit():
                sid = int(store_id_raw)
                if Store.query.get(sid):
                    if main.document_manage_requires_store_scope():
                        my_sid = main.get_current_user_store_id()
                        if my_sid is not None and sid != my_sid:
                            sid = my_sid  # managers can only assign their store or all
                    store_id = sid
            # Create document record
            display_name = request.form.get('display_name', '').strip() or None
            document = Document(
                filename=filename,
                original_filename=original_filename,
                display_name=display_name,
                file_path=str(file_path),
                file_size=file_size,
                file_type=file.content_type or 'application/octet-stream',
                description=request.form.get('description', '').strip() or None,
                is_visible=request.form.get('is_visible') == '1',
                uploaded_by=current_user.username
            )
            if hasattr(Document, 'store_id'):
                document.store_id = store_id
            db.session.add(document)
            db.session.commit()

            import_note = ''
            if filename.lower().endswith('.pdf'):
                ok, msg = _try_auto_import_acroform_fields(document, current_user.username)
                if ok:
                    import_note = f' {msg}'

            flash(f'Document "{original_filename}" uploaded successfully.{import_note}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error uploading file: {str(e)}', 'error')

        return redirect(url_for('manage_documents'))



    def _serve_sign_document_page(doc_id):
        """Build and return the sign document page (or a redirect if not allowed). Used by both /documents/<id>/sign and /documents?sign=<id>."""
        try:
            document = Document.query.get(doc_id)
            if not document:
                flash('Document not found.', 'error')
                return redirect(url_for('view_documents'))

            # Check permissions - only allow if document is assigned to user (unless admin)
            if not current_user.is_admin():
                assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
                if not assignment:
                    flash('This document has not been assigned to you.', 'error')
                    return redirect(url_for('view_documents'))

            # Get signature fields for this document
            signature_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).order_by(DocumentSignatureField.page_number, DocumentSignatureField.id).all()

            # Get typed fields for this document (handle case where table might not exist yet)
            try:
                typed_fields = DocumentTypedField.query.filter_by(document_id=doc_id).order_by(DocumentTypedField.page_number, DocumentTypedField.id).all()
            except Exception:
                typed_fields = []

            if not signature_fields and not typed_fields:
                if _document_is_fillable_pdf(document):
                    _try_auto_import_acroform_fields(document, current_user.username)
                    signature_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).order_by(
                        DocumentSignatureField.page_number, DocumentSignatureField.id
                    ).all()
                    try:
                        typed_fields = DocumentTypedField.query.filter_by(document_id=doc_id).order_by(
                            DocumentTypedField.page_number, DocumentTypedField.id
                        ).all()
                    except Exception:
                        typed_fields = []
            if not signature_fields and not typed_fields:
                flash(
                    'This document does not have any fields configured. '
                    'For fillable PDFs from Adobe, open Set Signature Fields and click Import fields from PDF.',
                    'error',
                )
                return redirect(url_for('view_documents'))

            if document_uses_step_wizard(len(signature_fields) + len(typed_fields), typed_fields) and not request.args.get('classic'):
                return redirect(url_for('view_documents', wizard=doc_id))

            # Get existing signatures by current user
            try:
                user_signatures = DocumentSignature.query.filter_by(document_id=doc_id, username=current_user.username).all()
            except Exception:
                user_signatures = []
            # Mark each field as signed or not (using helper to handle deleted fields)
            # Also find the matching signature for each field
            for field in signature_fields:
                try:
                    field.is_signed = is_signature_field_signed(doc_id, field, current_user.username)
                except Exception:
                    field.is_signed = False
                # Find the matching signature for this field
                field.matching_signature = None
                if field.id:
                    field.matching_signature = next((sig for sig in user_signatures if sig.signature_field_id == field.id), None)
                if not field.matching_signature:
                    try:
                        tolerance = 10.0
                        for sig in user_signatures:
                            sig_field_page = getattr(sig, 'field_page_number', None)
                            sig_field_x = getattr(sig, 'field_x_position', None)
                            sig_field_y = getattr(sig, 'field_y_position', None)
                            if (not sig.signature_field_id and
                                sig_field_page == field.page_number and
                                sig_field_x is not None and sig_field_y is not None and
                                abs(sig_field_x - field.x_position) <= tolerance and
                                abs(sig_field_y - field.y_position) <= tolerance):
                                field.matching_signature = sig
                                break
                    except Exception:
                        pass
            # Set of signed field ids (only include non-None ids)
            signed_field_ids = set(f.id for f in signature_fields if f.is_signed and f.id is not None)

            # Get existing typed field values by current user
            try:
                user_typed_values = DocumentTypedFieldValue.query.filter_by(document_id=doc_id, username=current_user.username).all()
                filled_typed_field_ids = {val.typed_field_id: val.field_value for val in user_typed_values}
            except Exception:
                filled_typed_field_ids = {}

            # Check if document is a PDF (handle None file_type/original_filename)
            fn = (document.original_filename or '').strip()
            ft = (document.file_type or '').strip()
            is_pdf = ft == 'application/pdf' or fn.lower().endswith('.pdf')

            # User display name and initials for typed_name / typed_initials fields
            user_display_name = current_user.username
            user_initials = (current_user.username[:2] if len(current_user.username) >= 2 else current_user.username).upper()
            try:
                nh = NewHire.query.filter_by(username=current_user.username).first()
                if nh:
                    first = (nh.first_name or '').strip()
                    last = (nh.last_name or '').strip()
                    user_display_name = f"{first} {last}".strip() or current_user.username
                    user_initials = ((first[:1] if first else '') + (last[:1] if last else '')).upper() or user_initials
                elif getattr(current_user, 'full_name', None) and (current_user.full_name or '').strip():
                    parts = (current_user.full_name or '').strip().split()
                    user_display_name = current_user.full_name.strip()
                    user_initials = (parts[0][:1] + (parts[1][:1] if len(parts) > 1 else '')).upper() if parts else user_initials
            except Exception:
                pass

            # Today's date for auto-filling date typed fields (YYYY-MM-DD for HTML date input)
            from datetime import date
            today_date = date.today().isoformat()
            saved_signature_image = None
            saved_signature_kind = None
            try:
                user_row = UserModel.query.filter_by(username=current_user.username).first()
                if user_row:
                    saved_signature_image = (getattr(user_row, 'saved_signature_image', None) or '').strip() or None
                    saved_signature_kind = (getattr(user_row, 'saved_signature_kind', None) or '').strip() or None
            except Exception:
                db.session.rollback()

            document_file_path = resolve_document_file_path(document)
            document_file_missing = bool(is_pdf and not document_file_path)

            import json as _json
            sign_overlay_fields = []
            for field in signature_fields:
                sig_img = None
                if field.is_signed and field.matching_signature and field.matching_signature.signature_image:
                    sig_img = field.matching_signature.signature_image
                sign_overlay_fields.append({
                    'id': field.id,
                    'kind': 'signature',
                    'field_type': 'signature',
                    'label': field.field_label or 'Signature',
                    'page': field.page_number,
                    'x': float(field.x_position),
                    'y': float(field.y_position),
                    'width': float(field.width or 200),
                    'height': float(field.height or 80),
                    'filled': bool(field.is_signed),
                    'value': None,
                    'signature_image': sig_img,
                    'phone_like': False,
                    'choice_group': '',
                    'is_required': True,
                })
            for field in typed_fields:
                phone_like = typed_field_is_phone_like(field)
                filled = field.id in filled_typed_field_ids
                val = filled_typed_field_ids.get(field.id, '') if filled else ''
                if not filled and field.field_type == 'typed_name':
                    val = user_display_name
                elif not filled and field.field_type == 'typed_initials':
                    val = user_initials
                elif not filled and field.field_type == 'date':
                    val = today_date
                ph = (field.placeholder or '').strip()
                if ph.startswith(ACRO_PLACEHOLDER_PREFIX):
                    input_hint = ''
                else:
                    input_hint = ph[:200]
                if not input_hint:
                    if phone_like:
                        input_hint = '(555) 123-4567'
                    elif field.field_type == 'last4':
                        input_hint = '1234'
                    elif field.field_type == 'number':
                        input_hint = 'Enter number'
                    else:
                        lbl = (field.field_label or '').strip()
                        input_hint = f'Enter {lbl}' if lbl else ''
                sign_overlay_fields.append({
                    'id': field.id,
                    'kind': 'typed',
                    'field_type': field.field_type,
                    'label': field.field_label or 'Typed Field',
                    'page': field.page_number,
                    'x': float(field.x_position),
                    'y': float(field.y_position),
                    'width': float(field.width or 200),
                    'height': float(field.height or 30),
                    'filled': filled,
                    'value': val if filled or field.field_type in ('typed_name', 'typed_initials', 'date') else '',
                    'signature_image': None,
                    'phone_like': phone_like,
                    'choice_group': (field.choice_group or '').strip(),
                    'is_required': field.field_type != 'checkbox_choice',
                    'input_hint': input_hint,
                })
            sign_overlay_fields_json = _json.dumps(sign_overlay_fields)

            return render_template('documents/sign.html', document=document, signature_fields=signature_fields, signed_field_ids=signed_field_ids, 
             user_signatures=user_signatures, typed_fields=typed_fields, filled_typed_field_ids=filled_typed_field_ids, is_pdf=is_pdf,
             user_display_name=user_display_name, user_initials=user_initials, today_date=today_date,
             saved_signature_image=saved_signature_image, saved_signature_kind=saved_signature_kind,
             document_file_missing=document_file_missing,
             typed_field_phone_pattern_html=TYPED_FIELD_PHONE_PATTERN_HTML,
             typed_field_phone_regex_js=TYPED_FIELD_PHONE_REGEX_JS,
             typed_field_last4_regex_js=TYPED_FIELD_LAST4_REGEX_JS,
             sign_overlay_fields_json=sign_overlay_fields_json,
             sign_overlay_fields=sign_overlay_fields,
             wizard_min_fields=DOCUMENT_WIZARD_MIN_FIELDS)
        except Exception as e:
            import traceback
            traceback.print_exc()
            app.logger.error(f'Error in sign_document (doc_id={doc_id}): {e}')
            flash('Unable to load the sign document page. Please try again or contact support.', 'error')
            return redirect(url_for('view_documents'))

    @app.route('/documents/<int:doc_id>/sign')
    @login_required
    def sign_document(doc_id):
        """Redirect to /documents?sign= for reliable routing behind IIS."""
        return redirect(url_for('view_documents', sign=doc_id))



    @app.route('/documents/<int:doc_id>/completed')
    @login_required
    def view_document_completed(doc_id):
        """Clean read-only view of the employee's completed PDF (no field overlays)."""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('view_documents'))
        if not _user_can_fill_document(document, current_user.username):
            flash('This document has not been assigned to you.', 'error')
            return redirect(url_for('view_documents'))
        if not os.path.exists(document.file_path):
            flash('Document file not found on server.', 'error')
            return redirect(url_for('view_documents'))

        is_pdf = (
            document.file_type == 'application/pdf'
            or (document.original_filename or '').lower().endswith('.pdf')
        )
        if not is_pdf:
            flash('Preview is only available for PDF documents.', 'error')
            return redirect(url_for('view_documents'))

        pdf_url = url_for('document_completed_pdf', doc_id=doc_id)
        download_url = url_for('document_completed_pdf', doc_id=doc_id, download=1)
        print_url = url_for('print_document_completed', doc_id=doc_id)
        header_actions_html = (
            f'<a href="{url_for("view_documents", wizard=doc_id)}" class="btn btn-ghost">Edit form</a>'
            f'<a href="{url_for("view_documents")}" class="btn btn-ghost">← Files</a>'
        )
        return _render_completed_pdf_viewer(
            document, doc_id,
            pdf_url=pdf_url, download_url=download_url, print_url=print_url,
            header_actions_html=header_actions_html,
        )



    @app.route('/documents/<int:doc_id>/print-completed')
    @login_required
    def print_document_completed(doc_id):
        """Open the built PDF in a print-ready page for the current user."""
        document = Document.query.get(doc_id)
        if not document:
            abort(404)
        if not _user_can_fill_document(document, current_user.username):
            abort(403)
        if not resolve_document_file_path(document):
            abort(404)
        pdf_url = url_for('document_completed_pdf', doc_id=doc_id)
        return _render_completed_pdf_print_page(document, pdf_url)



    @app.route('/documents/<int:doc_id>/completed-pdf')
    @login_required
    def document_completed_pdf(doc_id):
        """Stream the user's completed PDF inline (values baked in, no UI overlays)."""
        document = Document.query.get(doc_id)
        if not document:
            abort(404)
        if not _user_can_fill_document(document, current_user.username):
            abort(403)
        if not resolve_document_file_path(document):
            abort(404)

        as_attachment = request.args.get('download', '').lower() in ('1', 'true', 'yes')
        response, err = _send_built_user_pdf(
            document, current_user.username, as_attachment=as_attachment,
        )
        if not response:
            app.logger.warning(
                'completed PDF stream failed doc_id=%s user=%s: %s',
                doc_id, current_user.username, err,
            )
            abort(500)
        return response

    @app.route('/documents/<int:doc_id>/download')
    @login_required
    def download_document(doc_id):
        """Download a document - for users, download their signed version; for admins, download original"""
        document = Document.query.get(doc_id)

        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('dashboard'))

        # Check permissions: admin can download all; manager with manage_documents can download store-visible docs; others need assignment
        if main.document_manage_requires_store_scope():
            user_store_id = main.get_current_user_store_id()
            _attach_document_store_lists([document])
            if not document_visible_to_store(document, user_store_id):
                flash('This document is not available.', 'error')
                return redirect(url_for('manage_documents'))
        elif not current_user.is_admin():
            assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
            if not assignment:
                flash('This document has not been assigned to you.', 'error')
                return redirect(url_for('dashboard'))
            user_store_id = main.get_current_user_store_id()
            if not document_visible_to_store(document, user_store_id):
                flash('This document is not available.', 'error')
                return redirect(url_for('dashboard'))

        # Check if file exists
        if not resolve_document_file_path(document):
            flash('Document not found on server.', 'error')
            return redirect(url_for('dashboard'))

        # For regular users, generate and download their signed version; for admins and managers (viewing from forms page), download original
        admin_full_doc_access = current_user.is_admin() and not main.document_manage_requires_store_scope()
        if not admin_full_doc_access and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            # Generate signed PDF for this user
            try:
                # Get user's signatures for this document
                user_signatures = DocumentSignature.query.filter_by(
                    document_id=doc_id,
                    username=current_user.username
                ).all()

                # Get typed field values for this user (handle case where table might not exist yet)
                try:
                    user_typed_values = DocumentTypedFieldValue.query.filter_by(
                        document_id=doc_id,
                        username=current_user.username
                    ).all()
                    typed_value_map = {val.typed_field_id: val.field_value for val in user_typed_values}
                except Exception:
                    typed_value_map = {}

                has_form_fields = _document_configured_field_count(doc_id) > 0
                if FITZ_AVAILABLE and (has_form_fields or user_signatures or typed_value_map):
                    response, err = _send_built_user_pdf(
                        document, current_user.username, as_attachment=True,
                    )
                    if response:
                        return response
                    app.logger.error(
                        'download signed PDF failed doc_id=%s user=%s: %s',
                        doc_id, current_user.username, err,
                    )
                    flash('Could not generate your filled PDF. Please try again or use View PDF from the form.', 'error')
                    return redirect(url_for('view_documents'))
                return send_file(
                    resolve_document_file_path(document),
                    as_attachment=True,
                    download_name=document.original_filename,
                    mimetype=document.file_type or 'application/octet-stream'
                )
            except Exception as e:
                app.logger.exception(
                    'Error generating signed PDF doc_id=%s user=%s: %s',
                    doc_id, current_user.username, e,
                )
                flash('Could not generate your filled PDF. Please try again or use View PDF from the form.', 'error')
                return redirect(url_for('view_documents'))
        else:
            # Admin downloads original document
            return send_file(
                document.file_path,
                as_attachment=True,
                download_name=document.original_filename,
                mimetype=document.file_type or 'application/octet-stream'
            )

    @app.route('/documents/<int:doc_id>/view')
    @login_required
    def view_document(doc_id):
        """View a document in the browser (admin can view all, users can only view visible ones)"""
        document = Document.query.get(doc_id)

        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('dashboard'))

        # Check permissions - only allow if document is assigned to user (unless admin)
        if not current_user.is_admin():
            assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
            if not assignment:
                flash('This document has not been assigned to you.', 'error')
                return redirect(url_for('dashboard'))
            # Document must be visible and (if user has a store) visible to that store
            user_store_id = main.get_current_user_store_id()
            if not document_visible_to_store(document, user_store_id):
                flash('This document is not available.', 'error')
                return redirect(url_for('dashboard'))

        file_path = resolve_document_file_path(document)
        if not file_path:
            flash('File not found on server. Ask an administrator to re-upload the document file.', 'error')
            return redirect(url_for('dashboard'))

        # Determine if file can be viewed in browser
        viewable_types = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'text/plain']
        file_type = document.file_type or 'application/octet-stream'

        # Check file extension as fallback
        file_ext = document.original_filename.rsplit('.', 1)[-1].lower() if '.' in document.original_filename else ''
        viewable_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'gif', 'txt']

        if file_type in viewable_types or file_ext in viewable_extensions:
            # Serve file for viewing in browser
            return send_file(
                file_path,
                as_attachment=False,
                mimetype=file_type or 'application/octet-stream'
            )
        else:
            # For non-viewable types, redirect to download
            flash('This file type cannot be viewed in browser. Please download it.', 'info')
            return redirect(url_for('download_document', doc_id=doc_id))

    @app.route('/documents/<int:doc_id>/embed')
    @app.route('/documents/<int:doc_id>/embed/<username>')
    @login_required
    def view_document_embed(doc_id, username=None):
        """Embed a document for viewing in modal (admin can view all, users can only view visible ones)

        If username is provided, show that user's signed version with signatures.
        Otherwise, show the original blank document.
        """
        document = Document.query.get(doc_id)

        if not document:
            return "Document not found.", 404

        # Check permissions: admin can view all; manager with manage_documents can view store-visible docs; others need assignment
        if main.document_manage_requires_store_scope():
            user_store_id = main.get_current_user_store_id()
            _attach_document_store_lists([document])
            if not document_visible_to_store(document, user_store_id):
                return "This document is not available.", 403
        elif not current_user.is_admin():
            assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
            if not assignment:
                return "This document has not been assigned to you.", 403
            user_store_id = main.get_current_user_store_id()
            if not document_visible_to_store(document, user_store_id):
                return "This document is not available.", 403

        file_path = resolve_document_file_path(document)
        if not file_path:
            app.logger.warning(
                'Document file missing on disk: doc_id=%s path=%s filename=%s',
                doc_id, document.file_path, document.filename,
            )
            return "File not found on server.", 404

        # If username is provided and current user is admin OR it's their own username, show signed version
        # Otherwise, show original blank document
        show_signed = False
        if username:
            if current_user.is_admin() or username == current_user.username:
                show_signed = True

        if show_signed and FITZ_AVAILABLE:
            response, err = _send_built_user_pdf(document, username, as_attachment=False)
            if response:
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
                return response
            app.logger.warning(
                'signed embed build failed doc_id=%s user=%s: %s', doc_id, username, err,
            )

        # Serve original blank document (file_path resolved above)
        file_type = document.file_type or 'application/octet-stream'

        response = send_file(
            file_path,
            as_attachment=False,
            mimetype=file_type
        )

        # Allow iframe embedding
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"

        return response

    @app.route('/documents/<int:doc_id>/render-with-signatures')
    @login_required
    def render_document_with_signatures(doc_id):
        """Render a PDF page as an image with signatures overlaid at exact coordinates"""
        document = Document.query.get(doc_id)

        if not document:
            return "Document not found.", 404

        # Check permissions - only allow if document is assigned to user (unless admin)
        if not current_user.is_admin():
            assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
            if not assignment:
                return "This document has not been assigned to you.", 403

        # Check if file exists
        if not os.path.exists(document.file_path):
            return "File not found on server.", 404

        # Check if document is a PDF
        is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
        if not is_pdf:
            return "Only PDF documents can be rendered with signatures.", 400

        # Get page number (default to 1)
        try:
            page_num = int(request.args.get('page', 1)) - 1  # PyMuPDF uses 0-based indexing
        except ValueError:
            page_num = 0

        # Get signature fields for this page
        signature_fields = DocumentSignatureField.query.filter_by(
            document_id=doc_id, 
            page_number=page_num + 1
        ).all()

        # Get existing signatures by current user for these fields
        field_ids = [f.id for f in signature_fields]
        user_signatures = DocumentSignature.query.filter_by(
            document_id=doc_id, 
            username=current_user.username
        ).filter(DocumentSignature.signature_field_id.in_(field_ids)).all() if field_ids else []

        # Also get orphaned signatures (where field was deleted) that match these fields by location
        # Safely handle case where new columns don't exist yet
        try:
            orphaned_sigs = DocumentSignature.query.filter_by(
                document_id=doc_id,
                username=current_user.username
            ).filter(DocumentSignature.signature_field_id.is_(None)).all()

            # Match orphaned signatures to fields by location
            tolerance = 10.0
            for field in signature_fields:
                for sig in orphaned_sigs:
                    # Safely access new fields (may not exist if database not migrated)
                    sig_field_page = getattr(sig, 'field_page_number', None)
                    sig_field_x = getattr(sig, 'field_x_position', None)
                    sig_field_y = getattr(sig, 'field_y_position', None)

                    if (sig_field_page == field.page_number and
                        sig_field_x is not None and sig_field_y is not None and
                        abs(sig_field_x - field.x_position) <= tolerance and
                        abs(sig_field_y - field.y_position) <= tolerance):
                        # Add to user_signatures if not already there
                        if sig not in user_signatures:
                            user_signatures.append(sig)
                        break

            # Create a map of field_id -> signature (including orphaned signatures matched by location)
            sig_map = {}
            for sig in user_signatures:
                if sig.signature_field_id:
                    sig_map[sig.signature_field_id] = sig
                else:
                    # For orphaned signatures, find matching field by location
                    for field in signature_fields:
                        sig_field_page = getattr(sig, 'field_page_number', None)
                        sig_field_x = getattr(sig, 'field_x_position', None)
                        sig_field_y = getattr(sig, 'field_y_position', None)

                        if (sig_field_page == field.page_number and
                            sig_field_x is not None and sig_field_y is not None and
                            abs(sig_field_x - field.x_position) <= tolerance and
                            abs(sig_field_y - field.y_position) <= tolerance):
                            sig_map[field.id] = sig
                            break
        except Exception:
            # If new columns don't exist yet, just use the basic sig_map
            sig_map = {sig.signature_field_id: sig for sig in user_signatures if sig.signature_field_id}

        try:
            from PIL import Image

            # Use PyMuPDF (fitz) - it's already installed and works reliably
            if not FITZ_AVAILABLE:
                return "PDF rendering library (PyMuPDF) not available. Please install pymupdf.", 500

            # Open PDF
            pdf_doc = fitz.open(document.file_path)

            # Validate page number
            if page_num < 0 or page_num >= len(pdf_doc):
                pdf_doc.close()
                return f"Page not found. Document has {len(pdf_doc)} page(s).", 404

            # Get the page
            page = pdf_doc[page_num]
            page_rect = page.rect
            page_height = page_rect.height

            if page_height <= 0:
                pdf_doc.close()
                return "Invalid page dimensions.", 500

            # Render page to image - scale to match viewer height (800px)
            # This ensures coordinates stored from the viewer match the image
            viewer_height = 800.0
            scale = viewer_height / page_height
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image for signature overlay
            img_data = pix.tobytes("png")
            img = Image.open(BytesIO(img_data))

            # Clean up
            pix = None
            pdf_doc.close()

            # Overlay signatures at exact coordinates
            for field in signature_fields:
                if field.id in sig_map:
                    sig = sig_map[field.id]
                    try:
                        # Decode signature image
                        sig_image_data = base64.b64decode(sig.signature_image)
                        sig_img = Image.open(BytesIO(sig_image_data))

                        # Use coordinates directly (they're already in pixels matching the image)
                        # The image is rendered at the same scale as the viewer (800px height)
                        x = int(field.x_position)
                        y = int(field.y_position)
                        width = int(field.width or 200)
                        height = int(field.height or 80)

                        # Ensure coordinates are within image bounds
                        x = max(0, min(x, img.width - 1))
                        y = max(0, min(y, img.height - 1))
                        width = min(width, img.width - x)
                        height = min(height, img.height - y)

                        if width <= 0 or height <= 0:
                            continue

                        # Resize signature to fit the field
                        sig_img_resized = sig_img.resize((width, height), Image.Resampling.LANCZOS)

                        # Paste signature onto the page image
                        # Use alpha composite if signature has transparency
                        if sig_img_resized.mode == 'RGBA':
                            img.paste(sig_img_resized, (x, y), sig_img_resized)
                        else:
                            img.paste(sig_img_resized, (x, y))

                    except Exception as e:
                        print(f"Error overlaying signature for field {field.id}: {e}")
                        continue

            # Convert back to bytes
            output = BytesIO()
            img.save(output, format='PNG')
            output.seek(0)

            pdf_doc.close()

            return send_file(output, mimetype='image/png')

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error rendering document: {str(e)}", 500

    @app.route('/admin/documents/cleanup-orphaned-tasks', methods=['POST'])
    @admin_required
    def cleanup_orphaned_document_tasks_route():
        """One-time style cleanup for document tasks left when forms were deleted under the old logic."""
        try:
            removed = cleanup_orphaned_document_user_tasks()
            db.session.commit()
            if removed:
                flash(
                    f'Removed {removed} orphaned document task(s) from users\' Tasks lists.',
                    'success',
                )
            else:
                flash('No orphaned document tasks found.', 'info')
        except Exception as e:
            db.session.rollback()
            app.logger.exception('cleanup_orphaned_document_tasks failed')
            flash(f'Cleanup failed: {e}', 'error')
        return redirect(url_for('manage_documents'))

    @app.route('/admin/documents/<int:doc_id>/replace-file', methods=['POST'])
    @login_required
    def replace_document_file(doc_id):
        """Replace a document's underlying PDF file with a clean re-uploaded copy.

        Use this when an old PDF has stale embedded signatures from before signatures
        were stored only in the database. The Document record (id, name, signature
        fields, assignments, signatures in DB) is preserved; only `file_path` /
        `filename` / `file_size` / `file_type` are swapped to point at the new file.
        The previous file is renamed to `<name>.replaced-<timestamp>.bak` so it can
        still be recovered if needed.
        """
        if not current_user.is_admin() and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            abort(403)
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        if 'file' not in request.files:
            flash('No replacement file selected.', 'error')
            return redirect(url_for('manage_documents'))

        file = request.files['file']
        if not file or file.filename == '':
            flash('No replacement file selected.', 'error')
            return redirect(url_for('manage_documents'))
        if not main.allowed_file(file.filename):
            flash('File type not allowed for replacement.', 'error')
            return redirect(url_for('manage_documents'))

        try:
            upload_folder = app.config['UPLOAD_FOLDER']
            upload_folder.mkdir(exist_ok=True)

            original_filename = file.filename
            new_safe_name = secure_filename(original_filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
            new_filename = timestamp + new_safe_name
            new_file_path = upload_folder / new_filename
            file.save(str(new_file_path))
            new_size = new_file_path.stat().st_size

            old_path = document.file_path
            if old_path and os.path.exists(old_path):
                try:
                    bak_path = f"{old_path}.replaced-{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.bak"
                    os.rename(old_path, bak_path)
                except Exception:
                    app.logger.exception('Could not back up old document file at %s', old_path)

            document.filename = new_filename
            document.original_filename = original_filename
            document.file_path = str(new_file_path)
            document.file_size = new_size
            document.file_type = file.content_type or document.file_type or 'application/pdf'

            db.session.commit()
            import_note = ''
            if new_filename.lower().endswith('.pdf'):
                sig_count = DocumentSignatureField.query.filter_by(document_id=document.id).count()
                typed_count = DocumentTypedField.query.filter_by(document_id=document.id).count()
                if not sig_count and not typed_count:
                    ok, msg = _try_auto_import_acroform_fields(document, current_user.username)
                    if ok:
                        import_note = f' {msg}'
            flash(
                f'Document file replaced. The original file was kept as a .bak next to it. '
                f'Existing signature fields, assignments, and DB signatures are preserved.{import_note}',
                'success'
            )
        except Exception as e:
            db.session.rollback()
            app.logger.exception('replace_document_file failed for doc_id=%s', doc_id)
            flash(f'Error replacing file: {str(e)}', 'error')

        return redirect(url_for('manage_documents'))

    @app.route('/admin/documents/<int:doc_id>/import-acroform-fields', methods=['POST'])
    @admin_required
    def import_acroform_fields_route(doc_id):
        """Import fillable PDF (AcroForm) field positions from Adobe/Acrobat into signature/typed field records."""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))
        replace = request.form.get('replace') == '1'
        ok, msg = _import_acroform_fields_for_document(
            document, current_user.username, replace_existing=replace,
        )
        flash(msg, 'success' if ok else 'error')
        return redirect(url_for('set_signature_fields', doc_id=doc_id))

    @app.route('/admin/documents/<int:doc_id>/update-stores', methods=['POST'])
    @login_required
    def document_update_stores(doc_id):
        """Update which stores can see this document. Form: all=1 for all stores, or store_ids list."""
        if not current_user.is_admin() and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            abort(403)
        is_manager_scoped = main.document_manage_requires_store_scope()
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))
        if is_manager_scoped:
            my_sid = main.get_current_user_store_id()
            if my_sid is None:
                flash('You must be assigned to a store to change document library settings.', 'error')
                return redirect(url_for('manage_documents'))
            _attach_document_store_lists([document])
            if not document_visible_to_store(document, my_sid):
                abort(403)
        try:
            _ensure_stores_and_store_id()
            db.session.execute(
                document_stores.delete().where(document_stores.c.document_id == doc_id)
            )
            if request.form.get('all') != '1':
                ids_raw = request.form.getlist('store_ids')
                seen = set()
                for sid in ids_raw:
                    try:
                        sid = int(sid)
                    except (ValueError, TypeError):
                        continue
                    if sid in seen:
                        continue
                    if is_manager_scoped and sid != my_sid:
                        continue
                    if Store.query.get(sid):
                        seen.add(sid)
                        db.session.execute(
                            document_stores.insert().values(document_id=doc_id, store_id=sid)
                        )
            document.store_id = None
            db.session.commit()
            flash('Document library store scope updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating: {str(e)}', 'error')
        return redirect(url_for('manage_documents'))

    @app.route('/admin/toggle-document-visibility', methods=['POST'])
    @login_required
    def toggle_document_visibility():
        """Toggle whether document appears in the optional user document library (is_visible). Does not affect assignments."""
        if not current_user.is_admin() and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            abort(403)
        doc_id = request.form.get('doc_id')

        if not doc_id:
            flash('Document ID is required.', 'error')
            return redirect(url_for('manage_documents'))

        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        document.is_visible = not document.is_visible
        document.updated_at = datetime.utcnow()
        db.session.commit()

        if document.is_visible:
            flash('Document will appear in the optional document library (for selected stores). Assigned users are unchanged.', 'success')
        else:
            flash('Document removed from the optional document library. Assigned users can still sign via Files and Tasks.', 'success')
        return redirect(url_for('manage_documents'))



    @app.route('/admin/delete-document', methods=['POST'])
    @admin_required
    def delete_document():
        """Delete a document and all related records (signatures, assignments, etc.)"""
        doc_id = request.form.get('doc_id')

        if not doc_id:
            flash('Document ID is required.', 'error')
            return redirect(url_for('manage_documents'))

        try:
            doc_id = int(doc_id)
        except (TypeError, ValueError):
            flash('Invalid document ID.', 'error')
            return redirect(url_for('manage_documents'))

        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        original_filename = document.original_filename
        file_path = document.file_path

        try:
            # Delete related records first (foreign keys would block document delete)
            DocumentSignature.query.filter_by(document_id=doc_id).delete()
            DocumentTypedFieldValue.query.filter_by(document_id=doc_id).delete()
            DocumentSignatureField.query.filter_by(document_id=doc_id).delete()
            DocumentTypedField.query.filter_by(document_id=doc_id).delete()
            DocumentAssignment.query.filter_by(document_id=doc_id).delete()
            tasks_removed = _delete_user_tasks_for_document(document)
            try:
                SignatureAuditLog.query.filter_by(document_id=doc_id).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                db.session.execute(
                    document_stores.delete().where(document_stores.c.document_id == doc_id)
                )
            except Exception:
                pass
            try:
                db.session.execute(
                    role_documents.delete().where(role_documents.c.document_id == doc_id)
                )
            except Exception:
                pass
            try:
                NewHire.query.filter_by(finale_document_id=doc_id).update(
                    {NewHire.finale_document_id: None},
                    synchronize_session=False,
                )
            except Exception:
                pass

            # Delete file from filesystem
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # continue even if file already gone

            # Delete document
            db.session.delete(document)
            db.session.commit()

            msg = f'Document "{original_filename}" deleted successfully.'
            if tasks_removed:
                msg += f' Removed {tasks_removed} task(s) from users\' Tasks lists.'
            flash(msg, 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting document: {str(e)}', 'error')

        return redirect(url_for('manage_documents'))



    @app.route('/admin/documents/<int:doc_id>/signature-fields/add', methods=['POST'])
    @admin_required
    def add_signature_field(doc_id):
        """Add a signature field to a document"""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        try:
            signature_type = 'image'
            signature_field = DocumentSignatureField(
                document_id=doc_id,
                page_number=int(request.form.get('page_number', 1)),
                x_position=float(request.form.get('x_position', 0)),
                y_position=float(request.form.get('y_position', 0)),
                width=float(request.form.get('width', 200)),
                height=float(request.form.get('height', 80)),
                field_label=request.form.get('field_label', '').strip() or None,
                signature_type=signature_type,
                is_required=True,
                created_by=current_user.username
            )

            db.session.add(signature_field)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding signature field: {str(e)}', 'error')

        return _signature_fields_redirect(doc_id, request.form.get('page_number') or request.form.get('return_page'))

    @app.route('/admin/documents/<int:doc_id>/typed-fields/add', methods=['POST'])
    @admin_required
    def add_typed_field(doc_id):
        """Add a typed field to a document"""
        document = Document.query.get(doc_id)
        if not document:
            error_msg = 'Document not found.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg}), 404
            flash(error_msg, 'error')
            return redirect(url_for('manage_documents'))

        try:
            _ensure_document_typed_field_columns()
            # Check if table exists by trying to query it
            try:
                DocumentTypedField.query.first()
            except Exception as e:
                error_msg = 'Typed fields feature requires database tables to be created. Please run init_db.py first.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                return redirect(url_for('set_signature_fields', doc_id=doc_id))

            field_type = normalize_typed_field_type(request.form.get('field_type'))
            choice_group = (request.form.get('choice_group') or '').strip() or None
            if field_type == 'checkbox_choice':
                if not choice_group:
                    error_msg = 'Choice group name is required for checkbox fields.'
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'success': False, 'message': error_msg}), 400
                    flash(error_msg, 'error')
                    return _signature_fields_redirect(doc_id, request.form.get('page_number'))

            # Get and validate required fields
            x_pos = request.form.get('x_position')
            y_pos = request.form.get('y_position')
            width = request.form.get('width')
            height = request.form.get('height')
            field_label = request.form.get('field_label', '').strip()

            if not x_pos or not y_pos or not width or not height:
                error_msg = 'Missing position or size data. Please try placing the field again.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                return redirect(url_for('set_signature_fields', doc_id=doc_id))

            if not field_label:
                error_msg = 'Field label is required.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                return redirect(url_for('set_signature_fields', doc_id=doc_id))

            typed_field = DocumentTypedField(
                document_id=doc_id,
                page_number=int(request.form.get('page_number', 1)),
                x_position=float(x_pos),
                y_position=float(y_pos),
                width=float(width),
                height=float(height),
                field_label=field_label,
                field_type=field_type,
                choice_group=choice_group if field_type == 'checkbox_choice' else None,
                placeholder=request.form.get('placeholder', '').strip() or None,
                is_required=False if field_type == 'checkbox_choice' else True,
                created_by=current_user.username
            )

            db.session.add(typed_field)
            db.session.commit()

            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': 'Typed field added successfully.', 
                    'field_id': typed_field.id,
                    'field': {
                        'id': typed_field.id,
                        'label': typed_field.field_label,
                        'type': typed_field.field_type,
                        'x': typed_field.x_position,
                        'y': typed_field.y_position,
                        'width': typed_field.width,
                        'height': typed_field.height,
                        'page': typed_field.page_number
                    }
                })

        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            error_msg = f'Error adding typed field: {str(e)}'

            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg}), 500

            flash(error_msg, 'error')

        return _signature_fields_redirect(doc_id, request.form.get('page_number') or request.form.get('return_page'))

    @app.route('/admin/documents/typed-fields/<int:field_id>/update', methods=['POST'])
    @admin_required
    def update_typed_field(field_id):
        """Update an existing typed field's label, input type, and options."""
        typed_field = DocumentTypedField.query.get(field_id)
        if not typed_field:
            flash('Typed field not found.', 'error')
            return redirect(url_for('manage_documents'))

        doc_id = typed_field.document_id
        try:
            _ensure_document_typed_field_columns()
            requested_field_type = (request.form.get('field_type') or 'text').strip().lower()
            field_label = (request.form.get('field_label') or '').strip()
            choice_group = (request.form.get('choice_group') or '').strip() or None

            if requested_field_type == 'signature':
                signature_field = DocumentSignatureField(
                    document_id=doc_id,
                    page_number=typed_field.page_number,
                    x_position=typed_field.x_position,
                    y_position=typed_field.y_position,
                    width=max(float(typed_field.width or 200), 120.0),
                    height=max(float(typed_field.height or 30), 50.0),
                    field_label=field_label or typed_field.field_label or 'Signature',
                    signature_type='image',
                    is_required=True,
                    created_by=current_user.username,
                )
                db.session.add(signature_field)
                DocumentTypedFieldValue.query.filter_by(typed_field_id=field_id).delete()
                db.session.delete(typed_field)
                db.session.commit()
                return _signature_fields_redirect(doc_id, request.form.get('return_page'))

            field_type = normalize_typed_field_type(requested_field_type)
            if field_type == 'checkbox_choice':
                if not choice_group:
                    flash('Choice group name is required for checkbox fields.', 'error')
                    return _signature_fields_redirect(doc_id, request.form.get('return_page'))
                typed_field.choice_group = choice_group
                typed_field.is_required = False
            else:
                typed_field.choice_group = None
                typed_field.is_required = True

            if field_label:
                typed_field.field_label = field_label
            typed_field.field_type = field_type
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating field: {str(e)}', 'error')

        return _signature_fields_redirect(doc_id, request.form.get('return_page'))

    @app.route('/admin/documents/typed-fields/<int:field_id>/delete', methods=['POST'])
    @admin_required
    def delete_typed_field(field_id):
        """Delete a typed field"""
        try:
            typed_field = DocumentTypedField.query.get(field_id)
            if not typed_field:
                flash('Typed field not found.', 'error')
                return redirect(url_for('manage_documents'))

            doc_id = typed_field.document_id

            try:
                # Delete all values for this field
                DocumentTypedFieldValue.query.filter_by(typed_field_id=field_id).delete()
                db.session.delete(typed_field)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(f'Error deleting typed field: {str(e)}', 'error')

            return _signature_fields_redirect(doc_id, request.form.get('return_page'))
        except Exception as e:
            flash(f'Error: {str(e)}. Typed fields feature may not be available.', 'error')
            return redirect(url_for('manage_documents'))

    @app.route('/admin/documents/signature-fields/<int:field_id>/geometry', methods=['POST'])
    @admin_required
    def update_signature_field_geometry(field_id):
        """Update position/size of an existing signature field (drag/resize on editor)."""
        field = DocumentSignatureField.query.get(field_id)
        if not field:
            return jsonify({'success': False, 'message': 'Signature field not found.'}), 404
        try:
            data = request.get_json(silent=True) or {}
            field.x_position = float(data.get('x_position', field.x_position) or 0)
            field.y_position = float(data.get('y_position', field.y_position) or 0)
            field.width = float(data.get('width', field.width) or 200)
            field.height = float(data.get('height', field.height) or 80)
            if data.get('page_number') is not None:
                field.page_number = max(1, int(data.get('page_number')))
            db.session.commit()
            return jsonify({
                'success': True,
                'x_position': field.x_position,
                'y_position': field.y_position,
                'width': field.width,
                'height': field.height,
                'page_number': field.page_number,
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/admin/documents/typed-fields/<int:field_id>/geometry', methods=['POST'])
    @admin_required
    def update_typed_field_geometry(field_id):
        """Update position/size of an existing typed field (drag/resize on editor)."""
        field = DocumentTypedField.query.get(field_id)
        if not field:
            return jsonify({'success': False, 'message': 'Typed field not found.'}), 404
        try:
            data = request.get_json(silent=True) or {}
            field.x_position = float(data.get('x_position', field.x_position) or 0)
            field.y_position = float(data.get('y_position', field.y_position) or 0)
            field.width = float(data.get('width', field.width) or 200)
            field.height = float(data.get('height', field.height) or 30)
            if data.get('page_number') is not None:
                field.page_number = max(1, int(data.get('page_number')))
            db.session.commit()
            return jsonify({
                'success': True,
                'x_position': field.x_position,
                'y_position': field.y_position,
                'width': field.width,
                'height': field.height,
                'page_number': field.page_number,
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/admin/documents/signature-fields/<int:field_id>/delete', methods=['POST'])
    @admin_required
    def delete_signature_field(field_id):
        """Delete a signature field - preserves existing signatures by setting signature_field_id to null"""
        field = DocumentSignatureField.query.get(field_id)
        if not field:
            flash('Signature field not found.', 'error')
            return redirect(url_for('manage_documents'))

        doc_id = field.document_id

        try:
            # Preserve existing signatures by setting signature_field_id to null
            # The signatures retain their stored field metadata (page_number, x_position, etc.)
            # so they can still be embedded in PDFs even if the field is deleted
            signatures = DocumentSignature.query.filter_by(signature_field_id=field_id).all()
            for sig in signatures:
                # Ensure field metadata is stored (in case it wasn't stored when signature was created)
                # Safely set new fields (may not exist if database not migrated yet)
                try:
                    if not getattr(sig, 'field_page_number', None) and field:
                        sig.field_page_number = field.page_number
                        sig.field_x_position = field.x_position
                        sig.field_y_position = field.y_position
                        sig.field_width = field.width
                        sig.field_height = field.height
                        sig.field_label = field.field_label
                except AttributeError:
                    # New columns don't exist yet, skip metadata storage
                    pass
                sig.signature_field_id = None  # Disconnect from deleted field

            # Delete the field
            db.session.delete(field)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting signature field: {str(e)}', 'error')

        return _signature_fields_redirect(doc_id, request.form.get('return_page'))

    @app.route('/admin/documents/<int:doc_id>/assign/submit', methods=['POST'])
    @admin_required
    def assign_document_submit(doc_id):
        """Submit document assignment to users"""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        selected_usernames = request.form.getlist('usernames')
        due_date_str = request.form.get('due_date', '').strip()
        notes = request.form.get('notes', '').strip() or None

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except:
                pass

        try:
            assigned_count = 0
            newly_assigned_usernames = []
            for username in selected_usernames:
                # Check if assignment already exists
                existing = DocumentAssignment.query.filter_by(document_id=doc_id, username=username).first()

                if not existing:
                    # Create new assignment
                    assignment = DocumentAssignment(
                        document_id=doc_id,
                        username=username,
                        assigned_by=current_user.username,
                        due_date=due_date,
                        notes=notes
                    )
                    db.session.add(assignment)

                    # Create a UserTask for this document assignment (display_order high so it appears after any ordered onboarding tasks)
                    task = UserTask(
                        username=username,
                        task_title=f"Sign Document: {document.name_for_users}",
                        task_description=f"Please review and sign the document: {document.description or document.name_for_users}",
                        task_type='document',
                        document_id=doc_id,
                        priority='normal',
                        status='pending',
                        due_date=due_date,
                        assigned_by=current_user.username,
                        notes=notes,
                        display_order=9999,
                        depends_on_task_id=None
                    )
                    db.session.add(task)
                    assigned_count += 1
                    newly_assigned_usernames.append(username)
                else:
                    # Update existing assignment
                    if due_date:
                        existing.due_date = due_date
                    if notes:
                        existing.notes = notes
                    assigned_count += 1

            db.session.commit()

            for username in newly_assigned_usernames:
                main.reset_onboarding_completion_state(username)

            flash(f'Document assigned to {assigned_count} user(s).', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error assigning document: {str(e)}', 'error')

        return redirect(url_for('assign_document', doc_id=doc_id))

    @app.route('/admin/documents/assignments/<int:assignment_id>/remove', methods=['POST'])
    @admin_required
    def remove_document_assignment(assignment_id):
        """Remove a document assignment"""
        assignment = DocumentAssignment.query.get(assignment_id)
        if not assignment:
            flash('Assignment not found.', 'error')
            return redirect(url_for('manage_documents'))

        doc_id = assignment.document_id

        try:
            # Remove related UserTask if exists
            UserTask.query.filter_by(
                username=assignment.username,
                task_type='document',
                document_id=doc_id
            ).delete()

            # Remove assignment
            db.session.delete(assignment)
            db.session.commit()

            flash('Assignment removed successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error removing assignment: {str(e)}', 'error')

        return redirect(url_for('assign_document', doc_id=doc_id))

    @app.route('/documents/<int:doc_id>/typed-field/delete', methods=['POST'])
    @login_required
    def delete_typed_field_value(doc_id):
        """Delete a typed field value to allow redo"""
        try:
            document = Document.query.get(doc_id)
            if not document:
                return jsonify({'success': False, 'error': 'Document not found'}), 404

            # Check permissions - only allow if document is assigned to user (unless admin)
            if not current_user.is_admin():
                assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
                if not assignment:
                    return jsonify({'success': False, 'error': 'This document has not been assigned to you.'}), 403

            data = request.get_json()
            typed_field_id = data.get('typed_field_id')

            if not typed_field_id:
                return jsonify({'success': False, 'error': 'Missing typed field ID'}), 400

            try:
                # Find and delete the typed field value
                typed_field_value = DocumentTypedFieldValue.query.filter_by(
                    document_id=doc_id,
                    typed_field_id=typed_field_id,
                    username=current_user.username
                ).first()

                if typed_field_value:
                    db.session.delete(typed_field_value)
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'Typed field value deleted successfully'})
                else:
                    return jsonify({'success': False, 'error': 'Typed field value not found'}), 404
            except Exception as e:
                db.session.rollback()
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Error deleting typed field value: {str(e)}'}), 500
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

    @app.route('/documents/<int:doc_id>/signature/delete', methods=['POST'])
    @login_required
    def delete_signature(doc_id):
        """Delete a signature to allow redo"""
        try:
            document = Document.query.get(doc_id)
            if not document:
                return jsonify({'success': False, 'error': 'Document not found'}), 404

            # Check permissions - only allow if document is assigned to user (unless admin)
            if not current_user.is_admin():
                assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
                if not assignment:
                    return jsonify({'success': False, 'error': 'This document has not been assigned to you.'}), 403

            data = request.get_json()
            signature_field_id = data.get('signature_field_id')

            if not signature_field_id:
                return jsonify({'success': False, 'error': 'Missing signature field ID'}), 400

            try:
                # Get the signature field to check location
                field = DocumentSignatureField.query.get(signature_field_id)
                if not field:
                    return jsonify({'success': False, 'error': 'Signature field not found'}), 404

                # First try to find signature by field ID
                signature = DocumentSignature.query.filter_by(
                    document_id=doc_id,
                    signature_field_id=signature_field_id,
                    username=current_user.username
                ).first()

                # If not found by ID, try to find by location (for orphaned signatures)
                if not signature:
                    try:
                        tolerance = 10.0
                        orphaned_sigs = DocumentSignature.query.filter_by(
                            document_id=doc_id,
                            username=current_user.username
                        ).filter(DocumentSignature.signature_field_id.is_(None)).all()

                        for sig in orphaned_sigs:
                            # Safely access new fields (may not exist if database not migrated)
                            field_page = getattr(sig, 'field_page_number', None)
                            field_x = getattr(sig, 'field_x_position', None)
                            field_y = getattr(sig, 'field_y_position', None)

                            if (field_page == field.page_number and
                                field_x is not None and field_y is not None and
                                abs(field_x - field.x_position) <= tolerance and
                                abs(field_y - field.y_position) <= tolerance):
                                signature = sig
                                break
                    except Exception:
                        # If new columns don't exist yet, skip orphaned signature matching
                        pass

                if signature:
                    db.session.delete(signature)
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'Signature deleted successfully'})
                else:
                    return jsonify({'success': False, 'error': 'Signature not found'}), 404
            except Exception as e:
                db.session.rollback()
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Error deleting signature: {str(e)}'}), 500
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

    @app.route('/documents/<int:doc_id>/typed-field/submit', methods=['POST'])
    @login_required
    def submit_typed_field(doc_id):
        """Submit a typed field value for a document"""
        try:
            document = Document.query.get(doc_id)
            if not document:
                return jsonify({'success': False, 'error': 'Document not found'}), 404

            # Check permissions - only allow if document is assigned to user (unless admin)
            if not current_user.is_admin():
                assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
                if not assignment:
                    return jsonify({'success': False, 'error': 'This document has not been assigned to you.'}), 403

            data = request.get_json()
            typed_field_id = data.get('typed_field_id')
            field_value = data.get('field_value', '').strip()

            if not typed_field_id:
                return jsonify({'success': False, 'error': 'Missing typed field ID'}), 400

            # Verify typed field exists and belongs to this document
            try:
                typed_field = DocumentTypedField.query.get(typed_field_id)
            except Exception:
                return jsonify({'success': False, 'error': 'Typed fields feature is not available. Please contact administrator.'}), 500

            if not typed_field or typed_field.document_id != doc_id:
                return jsonify({'success': False, 'error': 'Invalid typed field'}), 400

            if typed_field.field_type == 'checkbox_choice':
                field_value = (field_value or '').strip()
                if field_value.upper() == 'X':
                    field_value = 'X'
                else:
                    field_value = ''
            elif typed_field.field_type == 'last4':
                field_value = normalize_last4_typed_value(field_value)
            elif not field_value:
                return jsonify({'success': False, 'error': 'Field value is required'}), 400

            # For typed_name/typed_initials, allow server-side default if client sent empty
            if not field_value and typed_field.field_type in ('typed_name', 'typed_initials'):
                try:
                    nh = NewHire.query.filter_by(username=current_user.username).first()
                    if nh:
                        first = (nh.first_name or '').strip()
                        last = (nh.last_name or '').strip()
                        if typed_field.field_type == 'typed_name':
                            field_value = f"{first} {last}".strip() or current_user.username
                        else:
                            field_value = ((first[:1] if first else '') + (last[:1] if last else '')).upper() or (current_user.username[:2] if len(current_user.username) >= 2 else current_user.username).upper()
                    elif getattr(current_user, 'full_name', None) and (current_user.full_name or '').strip():
                        parts = (current_user.full_name or '').strip().split()
                        if typed_field.field_type == 'typed_name':
                            field_value = current_user.full_name.strip()
                        else:
                            field_value = (parts[0][:1] + (parts[1][:1] if len(parts) > 1 else '')).upper() if parts else (current_user.username[:2] if len(current_user.username) >= 2 else current_user.username).upper()
                    else:
                        field_value = current_user.username if typed_field.field_type == 'typed_name' else (current_user.username[:2] if len(current_user.username) >= 2 else current_user.username).upper()
                except Exception:
                    field_value = current_user.username if typed_field.field_type == 'typed_name' else (current_user.username[:2] if len(current_user.username) >= 2 else current_user.username).upper()

            if typed_field.field_type != 'checkbox_choice' and not field_value:
                return jsonify({'success': False, 'error': 'Field value is required'}), 400

            ok, validation_error = validate_typed_field_value(
                typed_field.field_type,
                field_value,
                typed_field.field_label,
                placeholder=typed_field.placeholder,
            )
            if not ok:
                return jsonify({'success': False, 'error': validation_error}), 400

            try:
                _ensure_document_typed_field_columns()
                cleared_field_ids = []
                if typed_field.field_type == 'checkbox_choice' and field_value == 'X':
                    cleared_field_ids = clear_choice_group_selections_except(
                        doc_id, current_user.username, typed_field.choice_group, typed_field_id
                    )

                # Check if user already filled this field
                try:
                    existing_value = DocumentTypedFieldValue.query.filter_by(
                        document_id=doc_id,
                        typed_field_id=typed_field_id,
                        username=current_user.username
                    ).first()
                except Exception as table_error:
                    # Table might not exist yet
                    import traceback
                    traceback.print_exc()
                    return jsonify({'success': False, 'error': 'Database table not available. Please contact administrator.'}), 500

                if field_value == '' and existing_value:
                    db.session.delete(existing_value)
                elif field_value == '':
                    pass
                elif existing_value:
                    existing_value.field_value = field_value
                    existing_value.filled_at = datetime.utcnow()
                    existing_value.ip_address = request.remote_addr
                    existing_value.user_agent = request.headers.get('User-Agent', '')
                else:
                    new_value = DocumentTypedFieldValue(
                        document_id=doc_id,
                        typed_field_id=typed_field_id,
                        username=current_user.username,
                        field_value=field_value,
                        filled_at=datetime.utcnow(),
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent', '')
                    )
                    db.session.add(new_value)

                db.session.commit()

                all_complete = document_fully_completed_for_user(doc_id, current_user.username)
                if all_complete:
                    _mark_document_assignment_complete_if_ready(doc_id, current_user.username)
                    try:
                        document = Document.query.get(doc_id)
                        if document:
                            from services.jobs import enqueue_or_persist_signed_pdf
                            enqueue_or_persist_signed_pdf(document, current_user.username)
                    except Exception as e:
                        app.logger.warning('Failed to persist signed PDF after typed fields: %s', e)
                    db.session.commit()

                return jsonify({
                    'success': True,
                    'message': 'Typed field value saved successfully',
                    'field_value': field_value,
                    'cleared_field_ids': cleared_field_ids,
                    'selected_field_id': typed_field_id if field_value == 'X' else None,
                    'document_complete': all_complete,
                })
            except Exception as e:
                db.session.rollback()
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Error saving typed field: {str(e)}'}), 500
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

    @app.route('/admin/documents/<int:doc_id>/user/<username>/completed-pdf')
    @manager_required
    def staff_user_document_completed_pdf(doc_id, username):
        """Stream a user's completed PDF for staff (inline view or download)."""
        document = Document.query.get(doc_id)
        if not document:
            abort(404)
        if not _staff_can_view_user_documents(username):
            abort(403)
        if not resolve_document_file_path(document):
            abort(404)

        as_attachment = request.args.get('download', '').lower() in ('1', 'true', 'yes')
        response, err = _send_built_user_pdf(document, username, as_attachment=as_attachment)
        if not response:
            app.logger.warning(
                'staff completed PDF failed doc_id=%s user=%s: %s',
                doc_id, username, err,
            )
            abort(500)
        return response



    @app.route('/admin/documents/<int:doc_id>/signed-copy/<username>')
    @manager_required
    def download_signed_document(doc_id, username):
        """Download a signed copy of a document for a specific user (staff or self)."""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        if not _staff_can_view_user_documents(username):
            abort(403)

        def _error_redirect():
            if _staff_can_view_user_documents(username):
                return redirect(_staff_new_hire_details_url(username))
            if request.args.get('inline'):
                return redirect(url_for('view_form_signatures', doc_id=doc_id))
            return redirect(url_for('view_signed_documents', doc_id=doc_id))

        if not resolve_document_file_path(document):
            flash('File not found on server.', 'error')
            return _error_redirect()

        is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
        if not is_pdf:
            flash('Signed copies can only be generated for PDF documents.', 'error')
            return _error_redirect()

        if not FITZ_AVAILABLE:
            flash('PDF processing library not available. Please install PyMuPDF.', 'error')
            return _error_redirect()

        as_attachment = not request.args.get('inline')
        response, err = _send_built_user_pdf(document, username, as_attachment=as_attachment)
        if not response:
            app.logger.error(
                'download signed PDF failed doc_id=%s user=%s: %s',
                doc_id, username, err,
            )
            flash('Could not generate signed PDF. Please try again.', 'error')
            return _error_redirect()
        return response

    @app.route('/admin/documents/<int:doc_id>/rename', methods=['GET', 'POST'])
    @login_required
    def rename_document(doc_id):
        """Rename a document and set store visibility. Admin or manager with manage_documents."""
        if not current_user.is_admin() and not (current_user.is_manager() and main.manager_has_permission('manage_documents')):
            abort(403)
        is_manager_scoped = main.document_manage_requires_store_scope()
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))
        if is_manager_scoped:
            sid = main.get_current_user_store_id()
            _attach_document_store_lists([document])
            if sid is None or not document_visible_to_store(document, sid):
                abort(403)
        current_name = document.display_name or document.original_filename or ''
        stores = Store.query.order_by(Store.name).all()

        if request.method == 'POST':
            new_name = (request.form.get('display_name') or '').strip()
            store_id_raw = (request.form.get('store_id') or '').strip()
            try:
                if not new_name or new_name == document.original_filename:
                    document.display_name = None
                else:
                    document.display_name = new_name
                # Update store visibility
                if hasattr(document, 'store_id'):
                    if not store_id_raw or not store_id_raw.isdigit():
                        document.store_id = None
                    else:
                        sid = int(store_id_raw)
                        if is_manager_scoped:
                            my_sid = main.get_current_user_store_id()
                            if my_sid is not None and sid != my_sid:
                                document.store_id = my_sid
                            else:
                                document.store_id = sid if Store.query.get(sid) else None
                        else:
                            document.store_id = sid if Store.query.get(sid) else None
                db.session.commit()
                flash('Document updated.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating: {str(e)}', 'error')
            return redirect(url_for('manage_documents'))

        return render_template('documents/rename_document.html', document=document, current_name=current_name, stores=stores)

    @app.route('/admin/documents/<int:doc_id>/user/<username>/completed')
    @manager_required
    def staff_view_user_document_completed(doc_id, username):
        """Staff read-only view of a user's completed PDF (same flat filled copy as the employee sees)."""
        document = Document.query.get(doc_id)
        if not document:
            abort(404)
        if not _staff_can_view_user_documents(username):
            abort(403)
        if not resolve_document_file_path(document):
            abort(404)

        is_pdf = (
            document.file_type == 'application/pdf'
            or (document.original_filename or '').lower().endswith('.pdf')
        )
        if not is_pdf:
            flash('Preview is only available for PDF documents.', 'error')
            return redirect(_staff_new_hire_details_url(username))

        pdf_url = url_for('staff_user_document_completed_pdf', doc_id=doc_id, username=username)
        download_url = url_for(
            'staff_user_document_completed_pdf', doc_id=doc_id, username=username, download=1,
        )
        print_url = url_for('staff_print_user_document_completed', doc_id=doc_id, username=username)
        header_actions_html = (
            f'<a href="{_staff_new_hire_details_url(username)}" class="btn btn-ghost">← Back to {username}</a>'
        )
        return _render_completed_pdf_viewer(
            document, doc_id,
            pdf_url=pdf_url, download_url=download_url, print_url=print_url,
            header_actions_html=header_actions_html,
        )

    @app.route('/admin/documents/<int:doc_id>/user/<username>/print')
    @manager_required
    def staff_print_user_document_completed(doc_id, username):
        """Open the built PDF in a print-ready page for staff."""
        document = Document.query.get(doc_id)
        if not document:
            abort(404)
        if not _staff_can_view_user_documents(username):
            abort(403)
        if not resolve_document_file_path(document):
            abort(404)
        pdf_url = url_for('staff_user_document_completed_pdf', doc_id=doc_id, username=username)
        return _render_completed_pdf_print_page(document, pdf_url)

    @app.route('/admin/documents/<int:doc_id>/signed-copies')
    @admin_required
    def view_signed_documents(doc_id):
        """View and download signed copies of a document"""
        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return redirect(url_for('manage_documents'))

        try:
            # Get all users who have signed this document
            signatures = DocumentSignature.query.filter_by(document_id=doc_id).all()

            # Group signatures by username
            signed_users = {}
            for sig in signatures:
                if sig.username not in signed_users:
                    signed_users[sig.username] = []
                signed_users[sig.username].append(sig)
        except Exception as e:
            # If query fails (columns don't exist), use empty dict
            signed_users = {}

        # All signature fields are required; checkbox/radio groups are handled by document completion logic elsewhere.
        signature_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()
        required_fields = signature_fields

        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Signed Copies - {{ document.name_for_users }}</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'URW Form', Arial, sans-serif;
                    background: #f5f5f5;
                }
                .header {
                    background: #000000;
                    color: white;
                    padding: 12px 30px;
                    overflow: visible;
                    position: relative;
                    z-index: 100;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    min-height: 60px;
                }
                .header-content {
                    max-width: 1600px;
                    margin: 0 auto;
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    flex: 1;
                }
                .header-content h1 {
                    font-family: 'URW Form', Arial, sans-serif;
                    font-weight: 800;
                    margin: 0;
                }
                .back-btn {
                    background: rgba(255,255,255,0.2);
                    color: #FFFFFF;
                    padding: 8px 16px;
                    border-radius: 0.5rem;
                    text-decoration: none;
                    font-family: 'URW Form', Arial, sans-serif;
                    font-size: 0.95em;
                    font-weight: 500;
                    transition: all 0.2s;
                    border: 1px solid rgba(255,255,255,0.3);
                    white-space: nowrap;
                }
                .back-btn:hover {
                    background: rgba(255,255,255,0.3);
                    color: #FFFFFF;
                }
                .container {
                    max-width: 1600px;
                    margin: 30px auto;
                    padding: 0 20px;
                }
                .btn {
                    display: inline-block;
                    padding: 10px 20px;
                    background: #FE0100;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 5px;
                }
                .btn-success {
                    background: #28a745;
                }
                .admin-panel {
                    background: white;
                    padding: 25px;
                    border-radius: 0.5rem;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    overflow: visible;
                }
                .admin-panel h2 {
                    font-family: 'URW Form', Arial, sans-serif;
                    font-weight: 800;
                    color: #000000;
                }
                .signed-user-item {
                    background: #f8f9fa;
                    padding: 20px;
                    margin-bottom: 15px;
                    border-radius: 0.5rem;
                    border-left: 4px solid #28a745;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .user-info h3 {
                    margin-bottom: 5px;
                    color: #000000;
                }
                .user-info p {
                    color: #808080;
                    font-size: 0.9em;
                }
                .signature-preview {
                    display: flex;
                    gap: 10px;
                    margin-top: 10px;
                    flex-wrap: wrap;
                }
                .signature-preview img {
                    max-width: 150px;
                    max-height: 60px;
                    border: 1px solid #ddd;
                    border-radius: 0.5rem;
                    padding: 5px;
                    background: white;
                }
                .empty-state {
                    text-align: center;
                    padding: 40px;
                    color: #999;
                }

                /* Mobile Responsive Styles */
                @media (max-width: 768px) {
                    .header {
                        padding: 12px 15px;
                        flex-wrap: wrap;
                    }
                    .header-content h1 {
                        font-size: 1.2em;
                    }
                    .back-btn {
                        font-size: 0.85em;
                        padding: 6px 12px;
                    }
                    .container {
                        padding: 15px;
                    }
                    .admin-panel {
                        padding: 15px;
                    }
                    .signed-user-item {
                        flex-direction: column;
                        align-items: flex-start;
                        gap: 15px;
                    }
                    .btn {
                        min-height: 44px;
                        padding: 12px 20px;
                        font-size: 1em;
                        width: 100%;
                    }
                }

                @media (max-width: 480px) {
                    .header-content h1 {
                        font-size: 1em;
                    }
                    .admin-panel {
                        padding: 12px;
                    }
                    .signed-user-item {
                        padding: 15px;
                    }
                }
            {{ global_theme_css|safe }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="header-content">
                    <h1>📥 Signed Copies - {{ document.name_for_users }}</h1>
                </div>
                <div class="header-actions"><a href="{{ url_for('manage_documents') }}" class="back-btn">← Back to Documents</a></div>
            </div>

            <div class="container">

                <div class="admin-panel">
                    <h2>Users Who Have Signed This Document</h2>
                    {% if signed_users %}
                        {% for username, user_signatures in signed_users.items() %}
                        <div class="signed-user-item">
                            <div class="user-info">
                                <h3>{{ username }}</h3>
                                <p>Signed {{ user_signatures|length }} field(s) on {{ user_signatures[0].signed_at.strftime('%B %d, %Y at %I:%M %p') if user_signatures[0].signed_at else 'Unknown date' }}</p>
                                <div class="signature-preview">
                                    {% for sig in user_signatures %}
                                    <img src="data:image/png;base64,{{ sig.signature_image }}" alt="Signature">
                                    {% endfor %}
                                </div>
                            </div>
                            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <a href="{{ url_for('download_signed_document', doc_id=document.id, username=username) }}" class="btn btn-success">
                                    📥 Download Signed Copy
                                </a>
                                <a href="{{ url_for('download_signed_document', doc_id=document.id, username=username) }}?inline=1" class="btn" style="background: #333; color: white;" target="_blank" title="Opens PDF in new tab for printing">
                                    🖨️ Print
                                </a>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="empty-state">
                            <p>No users have signed this document yet.</p>
                        </div>
                    {% endif %}
                </div>
            </div>
        </body>
        </html>
        ''', document=document, signed_users=signed_users, required_fields=required_fields)

    @app.route('/admin/documents/<int:doc_id>/signatures')
    @admin_required
    def view_form_signatures(doc_id):
        """View which users have signed a form and which haven't"""
        try:
            document = Document.query.get(doc_id)
            if not document:
                flash('Document not found.', 'error')
                return redirect(url_for('admin_dashboard'))

            # All signature fields are required for document completion.
            required_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()

            if not required_fields:
                flash('This document has no signature fields.', 'error')
                return redirect(url_for('admin_dashboard'))

            # Get only users who have been assigned this document
            assignments = DocumentAssignment.query.filter_by(document_id=doc_id).all()
            assigned_usernames = set(a.username for a in assignments)

            if not assigned_usernames:
                # If no assignments, show message
                signed_users = []
                unsigned_users = []
            else:
                # Get user records for assigned users only
                assigned_users = UserModel.query.filter(UserModel.username.in_(assigned_usernames)).all()

                # Check signing status for each assigned user
                users_status = []
                for user in assigned_users:
                    try:
                        # Check if user has signed all required fields (using helper to handle deleted fields)
                        all_signed = all(is_signature_field_signed(doc_id, f, user.username) for f in required_fields)
                        signed_count = len([f for f in required_fields if is_signature_field_signed(doc_id, f, user.username)])
                    except Exception as e:
                        # If checking signatures fails, assume not signed
                        all_signed = False
                        signed_count = 0

                    # Get user's new hire record if exists
                    new_hire = NewHire.query.filter_by(username=user.username).first()
                    try:
                        if new_hire:
                            first_name = new_hire.first_name or ''
                            last_name = new_hire.last_name or ''
                            user_name = f"{first_name} {last_name}".strip() or user.username
                            user_email = getattr(new_hire, 'email', None) or getattr(user, 'email', None) or '-'
                            user_department = getattr(new_hire, 'department', None) or '-'
                        else:
                            user_name = user.username
                            user_email = getattr(user, 'email', None) or '-'
                            user_department = '-'
                    except Exception as e:
                        # Fallback if there's any error accessing attributes
                        user_name = user.username
                        user_email = '-'
                        user_department = '-'

                    users_status.append({
                        'username': user.username,
                        'name': user_name,
                        'email': user_email,
                        'department': user_department,
                        'signed': all_signed,
                        'signed_count': signed_count,
                        'total_required': len(required_fields)
                    })

                # Sort: signed users first, then by name
                users_status.sort(key=lambda x: (not x['signed'], x['name']))

                signed_users = [u for u in users_status if u['signed']]
                unsigned_users = [u for u in users_status if not u['signed']]
        except Exception as e:
            # If anything fails, provide default values
            flash(f'Error loading signature data: {str(e)}', 'error')
            signed_users = []
            unsigned_users = []
            required_fields = []
            document = Document.query.get(doc_id)
            if not document:
                return redirect(url_for('admin_dashboard'))

        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Form Signatures - {{ document.original_filename }}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
                body {
                    font-family: 'URW Form', Arial, sans-serif;
                    background: #FFFFFF;
                    color: #000000;
                }
                p, span, div, td, th, label, input, textarea, select, button, a {
                    font-family: 'URW Form', Arial, sans-serif;
                }
                .top-header {
                    background: #000000;
                    padding: 12px 30px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    overflow: visible;
                    position: relative;
                    z-index: 100;
                    min-height: 60px;
                }
                .back-btn {
                    background: rgba(255,255,255,0.2);
                    color: #FFFFFF;
                    padding: 8px 16px;
                    border-radius: 0.5rem;
                    text-decoration: none;
                    font-family: 'URW Form', Arial, sans-serif;
                    font-size: 0.95em;
                    font-weight: 500;
                    transition: all 0.2s;
                    border: 1px solid rgba(255,255,255,0.3);
                }
                .back-btn:hover {
                    background: rgba(255,255,255,0.3);
                    color: #FFFFFF;
                }
                .logo-section {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    font-size: 1.4em;
                    font-weight: 800;
                    font-family: 'URW Form', Arial, sans-serif;
                    color: #ffffff;
                    position: relative;
                    z-index: 101;
                    height: 100%;
                }
                .logo-section img {
                    height: 80px;
                    width: auto;
                    align-self: flex-end;
                    margin-bottom: -40px;
                }
                .btn {
                    display: inline-block;
                    padding: 10px 20px;
                    background: #FE0100;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 5px;
                }
                .btn:hover {
                    background: #FE0100;
                }
                .container {
                    max-width: 1600px;
                    margin: 30px auto;
                    padding: 0 20px;
                }
                .section {
                    background: #FFFFFF;
                    border-radius: 1rem;
                    border: 1px solid #E0E0E0;
                    padding: 2rem;
                    margin-bottom: 30px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                }
                .section-title {
                    font-size: 1.6em;
                    font-weight: 800;
                    margin-bottom: 20px;
                    color: #000000;
                    border-bottom: 2px solid #dc3545;
                    padding-bottom: 10px;
                }
                .document-header {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 0.5rem;
                    margin-bottom: 20px;
                }
                .document-header h2 {
                    font-size: 1.4em;
                    margin-bottom: 5px;
                    color: #000000;
                }
                .document-header p {
                    color: #808080;
                    font-size: 0.9em;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }
                th, td {
                    padding: 14px 16px;
                    text-align: left;
                    border-bottom: 1px solid #e5e5e5;
                }
                th {
                    background: #2d2d2d;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 0.9em;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                tbody tr {
                    transition: background-color 0.2s;
                }
                tbody tr:hover {
                    background-color: #f8f9fa;
                }
                tbody tr:last-child td {
                    border-bottom: none;
                }
                .status-badge {
                    padding: 6px 12px;
                    border-radius: 12px;
                    font-size: 0.85em;
                    font-weight: 600;
                    display: inline-block;
                }
                .status-signed {
                    background: #d4edda;
                    color: #155724;
                }
                .status-unsigned {
                    background: #f8d7da;
                    color: #842029;
                }
                .progress-info {
                    font-size: 0.85em;
                    color: #808080;
                }
                .form-actions {
                    display: flex;
                    gap: 12px;
                    flex-wrap: wrap;
                    margin-top: 12px;
                }
                .form-actions a {
                    display: inline-block;
                    padding: 8px 16px;
                    border-radius: 0.5rem;
                    font-size: 0.9em;
                    font-weight: 600;
                    text-decoration: none;
                    transition: all 0.2s;
                }
                .form-actions a.btn-download {
                    background: #FE0100;
                    color: white;
                    border: 1px solid #FE0100;
                }
                .form-actions a.btn-download:hover {
                    background: #c00;
                    color: white;
                }
                .form-actions a.btn-print {
                    background: #333;
                    color: white;
                    border: 1px solid #333;
                }
                .form-actions a.btn-print:hover {
                    background: #000;
                    color: white;
                }
                .form-actions a.btn-outline {
                    background: transparent;
                    color: #333;
                    border: 1px solid #666;
                }
                .form-actions a.btn-outline:hover {
                    background: #f0f0f0;
                }
                .stats-summary {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 20px;
                    margin-bottom: 30px;
                }
                .stat-card {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 0.5rem;
                    text-align: center;
                }
                .stat-number {
                    font-size: 2.5em;
                    font-weight: bold;
                    color: #FE0100;
                    margin-bottom: 5px;
                }
                .stat-label {
                    color: #808080;
                    font-size: 0.9em;
                }

                /* Mobile Responsive Styles */
                @media (max-width: 768px) {
                    .top-header {
                        padding: 12px 15px;
                        flex-wrap: wrap;
                    }
                    .logo-section {
                        font-size: 1.1em;
                    }
                    .logo-section img {
                        height: 60px;
                        margin-bottom: -30px;
                    }
                    .back-btn {
                        font-size: 0.85em;
                        padding: 6px 12px;
                    }
                    .container {
                        padding: 15px;
                    }
                    .document-header {
                        padding: 15px;
                    }
                    .document-header h2 {
                        font-size: 1.2em;
                    }
                    .stats-summary {
                        grid-template-columns: 1fr;
                        gap: 15px;
                    }
                    .section {
                        padding: 20px;
                    }
                    .section-title {
                        font-size: 1.3em;
                    }
                    table {
                        display: block;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                    }
                    th, td {
                        padding: 10px 8px;
                        font-size: 0.85em;
                        white-space: nowrap;
                    }
                    .btn {
                        min-height: 44px;
                        padding: 12px 20px;
                        font-size: 1em;
                    }
                }

                @media (max-width: 480px) {
                    .top-header {
                        padding: 10px 12px;
                    }
                    .logo-section {
                        font-size: 1em;
                    }
                    .logo-section img {
                        height: 50px;
                        margin-bottom: -25px;
                    }
                    .section {
                        padding: 15px;
                    }
                    .section-title {
                        font-size: 1.2em;
                    }
                    th, td {
                        padding: 8px 6px;
                        font-size: 0.8em;
                    }
                }
            {{ global_theme_css|safe }}
            </style>
        </head>
        <body>
            <div class="top-header">
                <div class="logo-section">
                    <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                    <span class="logo-text">Ziebart Onboarding</span>
                </div>
                <div class="header-actions"><a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a></div>
            </div>

            <div class="container">
                <div class="document-header">
                    <h2>{{ document.name_for_users }}</h2>
                    <p>Form Signature Status - {{ required_fields|length }} required signature field(s)</p>
                    <div class="form-actions">
                        <a href="{{ url_for('download_document', doc_id=document.id) }}" class="btn-download" target="_blank">⬇️ Download unsigned form</a>
                        <a href="{{ url_for('view_document_embed', doc_id=document.id) }}" class="btn-print" target="_blank">🖨️ Print unsigned form</a>
                    </div>
                </div>

                <div class="stats-summary">
                    <div class="stat-card">
                        <div class="stat-number">{{ users_status|length }}</div>
                        <div class="stat-label">Total Users</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" style="color: #28a745;">{{ signed_users|length }}</div>
                        <div class="stat-label">Signed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" style="color: #FE0100;">{{ unsigned_users|length }}</div>
                        <div class="stat-label">Not Signed</div>
                    </div>
                </div>

                {% if signed_users %}
                <div class="section">
                    <h2 class="section-title">✓ Users Who Have Signed</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Username</th>
                                <th>Email</th>
                                <th>Department</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user in signed_users %}
                            <tr>
                                <td><strong>{{ user.name }}</strong></td>
                                <td>{{ user.username }}</td>
                                <td>{{ user.email }}</td>
                                <td>{{ user.department }}</td>
                                <td>
                                    <span class="status-badge status-signed">✓ Signed</span>
                                </td>
                                <td>
                                    <div class="form-actions" style="margin-top: 0;">
                                        <a href="{{ url_for('download_signed_document', doc_id=document.id, username=user.username) }}" class="btn-outline" style="padding: 6px 12px; font-size: 0.85em;">⬇️ Download</a>
                                        <a href="{{ url_for('download_signed_document', doc_id=document.id, username=user.username) }}?inline=1" class="btn-outline" style="padding: 6px 12px; font-size: 0.85em;" target="_blank">🖨️ Print</a>
                                    </div>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}

                {% if unsigned_users %}
                <div class="section">
                    <h2 class="section-title">✗ Users Who Have Not Signed</h2>
                    <p style="margin-bottom: 12px; color: #666; font-size: 0.95em;">Download or print the blank form: <a href="{{ url_for('download_document', doc_id=document.id) }}" class="btn-outline" style="padding: 6px 12px; font-size: 0.85em;">⬇️ Download unsigned form</a> <a href="{{ url_for('view_document_embed', doc_id=document.id) }}" class="btn-outline" style="padding: 6px 12px; font-size: 0.85em;" target="_blank">🖨️ Print unsigned form</a></p>
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Username</th>
                                <th>Email</th>
                                <th>Department</th>
                                <th>Progress</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user in unsigned_users %}
                            <tr>
                                <td><strong>{{ user.name }}</strong></td>
                                <td>{{ user.username }}</td>
                                <td>{{ user.email }}</td>
                                <td>{{ user.department }}</td>
                                <td>
                                    <div class="progress-info">
                                        {{ user.signed_count }}/{{ user.total_required }} fields signed
                                    </div>
                                </td>
                                <td>
                                    <span class="status-badge status-unsigned">Not Complete</span>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}

                {% if not signed_users and not unsigned_users %}
                <div class="section">
                    <p style="color: #666; text-align: center; padding: 40px;">No users found.</p>
                </div>
                {% endif %}
            </div>
        </body>
        </html>
        ''', document=document, required_fields=required_fields, users_status=users_status if assigned_usernames else [],
             signed_users=signed_users, unsigned_users=unsigned_users, assigned_usernames=assigned_usernames)

