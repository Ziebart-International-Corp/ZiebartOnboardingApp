"""Admin console routes migrated from app.py."""
from __future__ import annotations

import traceback
from datetime import datetime

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, render_template_string,
    request, session, url_for, make_response, send_file,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from auth import admin_required, manager_required
from models import (
    Document, DocumentAssignment, DocumentSignature, DocumentSignatureField,
    NewHire, NewHireChecklist, Store, TrainingVideo, User as UserModel,
    UserTask, UserNotification, UserTrainingProgress, ChecklistItem,
    ManagerPermission, Role, Department, ExternalLink, QuizQuestion, QuizAnswer,
    db,
)


def register(app: Flask) -> None:
    """Register admin routes (endpoint names unchanged)."""
    import app as main
    from sqlalchemy import bindparam, text

    MANAGER_PERMISSION_KEYS = main.MANAGER_PERMISSION_KEYS
    DEFAULT_WELCOME_HEADLINE = main.DEFAULT_WELCOME_HEADLINE
    DEFAULT_WELCOME_BODY = main.DEFAULT_WELCOME_BODY
    DEFAULT_FINALE_MESSAGE = main.DEFAULT_FINALE_MESSAGE
    DEFAULT_ALL_TASKS_EMAIL_SUBJECT = main.DEFAULT_ALL_TASKS_EMAIL_SUBJECT
    DEFAULT_ALL_TASKS_EMAIL_BODY = main.DEFAULT_ALL_TASKS_EMAIL_BODY
    ONBOARDING_PORTAL_PAGES = main.ONBOARDING_PORTAL_PAGES
    normalize_legacy_onboarding_message = main.normalize_legacy_onboarding_message
    _ensure_stores_and_store_id = main._ensure_stores_and_store_id
    _ensure_departments_table = main._ensure_departments_table
    _attach_training_video_store_lists = main._attach_training_video_store_lists
    _access_revoke_calendar_date = main._access_revoke_calendar_date
    assign_task_link_context = main.assign_task_link_context
    _asana_is_connected = main._asana_is_connected
    _asana_redirect_uri = main._asana_redirect_uri
    _asana_oauth_configured = main._asana_oauth_configured
    _asana_env_token_configured = main._asana_env_token_configured
    _asana_feedback_ready = main._asana_feedback_ready
    ASANA_FEEDBACK_PROJECT_GID = main.ASANA_FEEDBACK_PROJECT_GID
    ASANA_SECTION_GID_COMMENT = main.ASANA_SECTION_GID_COMMENT
    ASANA_SECTION_GID_ISSUE = main.ASANA_SECTION_GID_ISSUE
    ASANA_SECTION_GID_SUGGESTION = main.ASANA_SECTION_GID_SUGGESTION
    ASANA_FEEDBACK_ASSIGNEE_GID = main.ASANA_FEEDBACK_ASSIGNEE_GID
    _document_has_assignable_fields_filter = main._document_has_assignable_fields_filter
    UserQuizResponse = main.UserQuizResponse
    generate_temporary_password = main.generate_temporary_password
    send_password_reset_email = main.send_password_reset_email
    send_onboarding_welcome_email = main.send_onboarding_welcome_email
    normalize_email = main.normalize_email
    email_in_use_by_other_user = main.email_in_use_by_other_user
    resolve_department_from_form = main.resolve_department_from_form
    _purge_training_video_dependencies = main._purge_training_video_dependencies
    _asana_store_tokens = main._asana_store_tokens
    _asana_clear_tokens = main._asana_clear_tokens
    training_video_visible_to_store = main.training_video_visible_to_store
    training_video_stores = main.training_video_stores
    import os
    from io import BytesIO
    from pdf_form_wizard import (
        TEST_FORM_SIG_PREFIX,
        analyze_pdf,
        build_filled_pdf,
        delete_wizard_state,
        is_test_form_signature_value,
        new_session_id,
        normalize_test_form_signature_value,
        save_uploaded_pdf,
        test_form_signature_b64,
    )
    PDF_WIZARD_FITZ_AVAILABLE = main.PDF_WIZARD_FITZ_AVAILABLE
    _test_form_wizard_state = main._test_form_wizard_state
    _test_form_wizard_save = main._test_form_wizard_save
    _test_form_field_is_last4 = main._test_form_field_is_last4
    _test_form_last4_digits = main._test_form_last4_digits
    _refresh_test_form_field_positions = main._refresh_test_form_field_positions
    normalize_last4_typed_value = main.normalize_last4_typed_value

    def _assign_task_redirect(staff_console):
        endpoint = (
            'manager_assign_task' if staff_console == 'manager' else 'admin_assign_task'
        )
        return redirect(url_for(endpoint, staff_console=staff_console))

    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin dashboard"""
        try:
            main.touch_staff_console_home('admin')
            return _admin_dashboard_impl()
        except Exception:
            app.logger.exception("admin_dashboard failed")
            db.session.rollback()
            return (
                f'<html><body><h1>Admin Dashboard Error</h1>'
                f'<pre>{traceback.format_exc()}</pre></body></html>'
            ), 500

    def _admin_dashboard_impl():
        """Admin dashboard: stores table → new hires list; nav via collapsible admin menu."""
        from collections import Counter
        from datetime import date as _date

        _admin_un = (current_user.username if current_user else '') or ''
        admin_name = main.staff_header_display_name(_admin_un) if _admin_un else 'Admin'
        pending_count = 0
        notifications = []
        all_stores = []
        store_dashboard_rows = []
        total_active_new_hires = 0
        hire_search_rows = []

        try:
            all_stores = Store.query.order_by(Store.name).all()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"admin_dashboard: all_stores failed: {e}")

        try:
            all_new_hires = NewHire.query.filter(NewHire.status != 'removed').order_by(NewHire.created_at.desc()).all()
            today = _date.today()
            eligible_pairs = []
            for nh in all_new_hires:
                user = UserModel.query.filter_by(username=nh.username).first()
                if not user:
                    continue
                revoked_at = getattr(user, 'access_revoked_at', None)
                if revoked_at is not None and today >= revoked_at:
                    continue
                eligible_pairs.append((nh, user))
            total_active_new_hires = len(eligible_pairs)
            by_store = Counter()
            for nh, user in eligible_pairs:
                by_store[nh.store_id] += 1
                fn = (nh.first_name or '').strip()
                ln = (nh.last_name or '').strip()
                display_name = f"{fn} {ln}".strip() or (nh.username or '')
                email = (getattr(user, 'email', None) or getattr(nh, 'email', None) or '') or ''
                store_name = 'No store assigned'
                list_url = url_for('view_all_new_hires', store_id='none', staff_console='admin')
                if nh.store_id:
                    st = Store.query.get(nh.store_id)
                    if st:
                        store_name = st.name
                        list_url = url_for('view_all_new_hires', store_id=st.id, staff_console='admin')
                    else:
                        store_name = 'Unknown store'
                parts = [display_name, nh.username or '', email, store_name]
                hire_search_rows.append({
                    'display_name': display_name,
                    'username': nh.username or '',
                    'email': email,
                    'store_name': store_name,
                    'list_url': list_url,
                    'search_text': ' '.join(p for p in parts if p).lower(),
                })
            for st in all_stores:
                store_dashboard_rows.append({
                    'store_name': st.name,
                    'store_code': (getattr(st, 'code', None) or '') or '—',
                    'new_hire_count': by_store.get(st.id, 0),
                    'list_url': url_for('view_all_new_hires', store_id=st.id, staff_console='admin'),
                })
            if by_store.get(None, 0) > 0:
                store_dashboard_rows.append({
                    'store_name': 'No store assigned',
                    'store_code': '—',
                    'new_hire_count': by_store.get(None, 0),
                    'list_url': url_for('view_all_new_hires', store_id='none', staff_console='admin'),
                })
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"admin_dashboard: store rows failed: {e}")

        try:
            admin_user = current_user
            notifications = []
            pending_count = len([n for n in notifications if not n['is_read']])
        except Exception as e:
            app.logger.exception('Error in admin_dashboard (notifications)')
            db.session.rollback()
            if not notifications:
                pending_count = 0

        return render_template(
            'admin/dashboard.html',
            admin_name=admin_name,
            pending_count=pending_count,
            notifications=notifications,
            store_dashboard_rows=store_dashboard_rows,
            total_active_new_hires=total_active_new_hires,
            hire_search_rows=hire_search_rows,
        )

    @app.route('/admin/stores/<int:store_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def manage_store_edit(store_id):
        """Edit store name and code."""
        store = Store.query.get(store_id)
        if not store:
            flash('Store not found.', 'error')
            return redirect(url_for('manage_stores'))
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            if not name:
                flash('Store name is required.', 'error')
                return redirect(url_for('manage_store_edit', store_id=store_id))
            code = (request.form.get('code') or '').strip() or None
            try:
                store.name = name
                store.code = code
                db.session.commit()
                flash(f'Store "{name}" updated.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error updating store. Please try again.', 'error')
            return redirect(url_for('manage_stores'))
        return render_template('staff/store_edit.html', store=store)


    @app.route('/admin/settings/stores/<int:store_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def manage_store_edit_legacy(store_id):
        """Legacy URL alias — canonical path is /admin/stores/<id>/edit."""
        if request.method == 'GET':
            return redirect(url_for('manage_store_edit', store_id=store_id), code=301)
        return manage_store_edit(store_id)

    def _assign_task_impl(force_manager=False):
        """Assign a one-off UserTask. Admins: any user; managers: store-scoped users only."""
        if not main.can_assign_extra_tasks():
            abort(403)

        scope_store_id = main.staff_store_scope_id() if (force_manager or main.uses_manager_console_scope()) else None
        if force_manager and scope_store_id is None and main.is_pure_manager():
            scope_store_id = main.get_current_user_store_id()

        all_users, user_display_names, user_store_ids = main.build_user_display_and_store_maps()
        if scope_store_id is not None:
            all_users = [u for u in all_users if user_store_ids.get(u.username) == scope_store_id]

        try:
            if scope_store_id is not None:
                all_stores = Store.query.filter_by(id=scope_store_id).order_by(Store.name).all()
            else:
                all_stores = Store.query.order_by(Store.name).all()
        except Exception:
            all_stores = []

        try:
            # Assignment lists include Not in library forms (is_visible only affects the user library)
            if scope_store_id is not None:
                all_documents = main.documents_assignable_to_store_query(scope_store_id).order_by(Document.original_filename).all()
            else:
                all_documents = Document.query.order_by(Document.original_filename).all()
        except Exception:
            all_documents = []

        try:
            all_training_videos = main.training_videos_visible_to_store_query(
                scope_store_id,
                base_filter=(TrainingVideo.is_active == True),
            ).order_by(TrainingVideo.title).all()
        except Exception:
            all_training_videos = []

        default_sc = 'manager' if force_manager or main.uses_manager_console_scope() else 'admin'

        if request.method == 'POST':
            sc = (request.form.get('staff_console') or request.args.get('staff_console') or default_sc).strip()
            username = (request.form.get('username') or '').strip()
            task_title = (request.form.get('task_title') or '').strip()
            task_description = (request.form.get('task_description') or '').strip() or None
            priority = (request.form.get('priority') or 'normal').strip().lower()
            notes = (request.form.get('notes') or '').strip() or None
            due_date_str = (request.form.get('due_date') or '').strip()
            document_id_str = (request.form.get('document_id') or '').strip()
            video_id_str = (request.form.get('video_id') or '').strip()

            if priority not in ('low', 'normal', 'high', 'urgent'):
                priority = 'normal'

            if not username:
                flash('Please select a user.', 'error')
                return _assign_task_redirect(sc)

            if not current_user.is_admin() and not main._manager_can_act_on_new_hire(username):
                flash('You can only assign tasks to new hires at your store.', 'error')
                return _assign_task_redirect(sc)

            document_id = None
            document = None
            if document_id_str.isdigit():
                document = Document.query.get(int(document_id_str))
                if not document:
                    flash('Selected document was not found.', 'error')
                    return _assign_task_redirect(sc)
                document_id = document.id

            video = None
            video_id = None
            if video_id_str.isdigit():
                video = TrainingVideo.query.get(int(video_id_str))
                if not video or not video.is_active:
                    flash('Selected training video was not found or is inactive.', 'error')
                    return _assign_task_redirect(sc)
                video_id = video.id

            if document and video:
                flash('Please select either a document or a training video, not both.', 'error')
                return _assign_task_redirect(sc)

            if not task_title and not document and not video:
                flash('Please enter a task title or select a document or training video.', 'error')
                return _assign_task_redirect(sc)
            if not task_title and document:
                task_title = f"Sign Document: {document.name_for_users}"
            if not task_title and video:
                task_title = f"Complete Training: {video.title}"
            if len(task_title) > 200:
                task_title = task_title[:200]

            assignee = UserModel.query.filter_by(username=username).first()
            if not assignee:
                flash('Selected user was not found.', 'error')
                return _assign_task_redirect(sc)

            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                except Exception:
                    pass

            try:
                if document is not None:
                    existing_assignment = DocumentAssignment.query.filter_by(
                        document_id=document_id, username=username
                    ).first()
                    if not existing_assignment:
                        db.session.add(DocumentAssignment(
                            document_id=document_id,
                            username=username,
                            assigned_by=current_user.username,
                            due_date=due_date,
                            notes=notes,
                        ))
                    else:
                        if due_date:
                            existing_assignment.due_date = due_date
                        if notes:
                            existing_assignment.notes = notes

                    if not task_description:
                        task_description = (
                            f"Please review and sign the document: "
                            f"{document.description or document.name_for_users}"
                        )

                if video is not None:
                    existing_training_task = UserTask.query.filter_by(
                        username=username,
                        task_type='training',
                        status='pending',
                    ).filter(UserTask.notes.like(f'video_id:{video_id}%')).first()
                    if existing_training_task:
                        display_name = user_display_names.get(username, username)
                        flash(
                            f'{display_name} already has a pending training task for "{video.title}".',
                            'error',
                        )
                        return _assign_task_redirect(sc)

                    if not task_description:
                        task_description = f"Please watch and complete the training video: {video.title}"

                task_notes = notes
                if video is not None:
                    task_notes = f'video_id:{video_id}'

                task = UserTask(
                    username=username,
                    task_title=task_title,
                    task_description=task_description,
                    task_type='document' if document else ('training' if video else 'general'),
                    document_id=document_id,
                    priority=priority,
                    status='pending',
                    due_date=due_date,
                    assigned_by=current_user.username,
                    notes=task_notes,
                    display_order=5000,
                    depends_on_task_id=None,
                )
                db.session.add(task)
                db.session.commit()
                main.reset_onboarding_completion_state(username)

                display_name = user_display_names.get(username, username)
                if document is not None:
                    flash(
                        f'Document "{document.name_for_users}" assigned to {display_name}. '
                        f'They will see a sign-document task on their Tasks page.',
                        'success'
                    )
                elif video is not None:
                    flash(
                        f'Training video "{video.title}" assigned to {display_name}. '
                        f'They will see a watch-and-quiz task on their Tasks page.',
                        'success'
                    )
                else:
                    flash(f'Task assigned to {display_name}.', 'success')
            except Exception as e:
                db.session.rollback()
                app.logger.exception('admin_assign_task failed')
                flash('Could not assign task. Please try again.', 'error')

            return _assign_task_redirect(sc)

        prefill_username = (request.args.get('username') or '').strip()
        staff_console_redirect = (request.args.get('staff_console') or default_sc).strip()
        prefill_document_id = (request.args.get('document_id') or '').strip()
        prefill_video_id = (request.args.get('video_id') or '').strip()
        store_scope_locked = scope_store_id is not None
        prefill_store_id = str(scope_store_id) if scope_store_id is not None else ''
        if not prefill_store_id and prefill_username in user_store_ids:
            sid = user_store_ids[prefill_username]
            prefill_store_id = str(sid) if sid is not None else 'none'

        return render_template(
            'staff/assign_task.html',
            all_users=all_users,
            user_display_names=user_display_names,
            user_store_ids=user_store_ids,
            all_stores=all_stores,
            prefill_username=prefill_username,
            prefill_store_id=prefill_store_id,
            store_scope_locked=store_scope_locked,
            staff_console_redirect=staff_console_redirect,
            all_documents=all_documents,
            all_training_videos=all_training_videos,
            prefill_document_id=prefill_document_id,
            prefill_video_id=prefill_video_id,
            assign_task_form_endpoint='manager_assign_task' if force_manager else 'admin_assign_task',
        )

    @app.route('/admin/assign-task', methods=['GET', 'POST'])
    @login_required
    def admin_assign_task():
        if not current_user.is_admin():
            abort(403)
        sc = (
            request.args.get('staff_console')
            or request.form.get('staff_console')
            or session.get(main.STAFF_CONSOLE_HOME_KEY)
            or ''
        ).strip().lower()
        if sc == 'manager' and current_user.is_manager():
            if request.method == 'GET':
                return redirect(url_for('manager_assign_task', **request.args))
            main.touch_staff_console_home('manager')
            return _assign_task_impl(force_manager=True)
        return _assign_task_impl()


    @app.route('/manager/assign-task', methods=['GET', 'POST'])
    @manager_required
    def manager_assign_task():
        main.touch_staff_console_home('manager')
        return _assign_task_impl(force_manager=True)

    @app.route('/admin/stores/add', methods=['POST'])
    @admin_required
    def manage_stores_add():
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Store name is required.', 'error')
            return redirect(url_for('manage_stores'))
        code = (request.form.get('code') or '').strip() or None
        try:
            store = Store(name=name, code=code)
            db.session.add(store)
            db.session.commit()
            flash(f'Store "{name}" added.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding store. Please try again.', 'error')
        return redirect(url_for('manage_stores'))


    @app.route('/admin/settings/stores/add', methods=['POST'])
    @admin_required
    def manage_stores_add_legacy():
        """Legacy URL alias — canonical path is /admin/stores/add."""
        return manage_stores_add()


    @app.route('/admin/stores/<int:store_id>/delete', methods=['POST'])
    @admin_required
    def manage_store_delete(store_id):
        store = Store.query.get(store_id)
        if not store:
            flash('Store not found.', 'error')
            return redirect(url_for('manage_stores'))
        try:
            UserModel.query.filter_by(store_id=store_id).update({UserModel.store_id: None})
            NewHire.query.filter_by(store_id=store_id).update({NewHire.store_id: None})
            Document.query.filter_by(store_id=store_id).update({Document.store_id: None})
            db.session.delete(store)
            db.session.commit()
            flash('Store deleted. User and document store links were cleared.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error. Please try again.', 'error')
        return redirect(url_for('manage_stores'))


    @app.route('/admin/settings/stores/<int:store_id>/delete', methods=['POST'])
    @admin_required
    def manage_store_delete_legacy(store_id):
        """Legacy URL alias — canonical path is /admin/stores/<id>/delete."""
        return manage_store_delete(store_id)


    @app.route('/admin/stores')
    @admin_required
    def manage_stores():
        """List all stores with counts of managers, users, and store-scoped forms. Link to store detail."""
        stores = Store.query.order_by(Store.name).all()
        store_stats = []
        for store in stores:
            managers_count = UserModel.query.filter_by(store_id=store.id, role='manager').count()
            users_count = UserModel.query.filter_by(store_id=store.id, role='user').count()
            forms_count = Document.query.filter_by(store_id=store.id).count()
            store_stats.append({
                'store': store,
                'managers_count': managers_count,
                'users_count': users_count,
                'forms_count': forms_count,
            })
        return render_template('admin/stores.html', store_stats=store_stats)


    @app.route('/admin/stores/<int:store_id>')
    @admin_required
    def store_detail(store_id):
        """One store: managers, users, and forms visible only for this store."""
        store = Store.query.get(store_id)
        if not store:
            flash('Store not found.', 'error')
            return redirect(url_for('manage_stores'))
        managers = UserModel.query.filter_by(store_id=store_id, role='manager').order_by(UserModel.username).all()
        users = UserModel.query.filter_by(store_id=store_id, role='user').order_by(UserModel.username).all()
        forms = Document.query.filter_by(store_id=store_id).order_by(Document.original_filename).all()
        store_training_videos = main.training_videos_for_store_detail(store_id)
        return render_template(
            'admin/store_detail.html',
            store=store,
            managers=managers,
            users=users,
            forms=forms,
            store_training_videos=store_training_videos,
        )



    @app.route('/admin/checklist')
    @login_required
    def manage_checklist():
        """Manage new hire checklist items. Admin or manager with manage_checklist permission."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_checklist'):
            abort(403)
        checklist_items = ChecklistItem.query.order_by(ChecklistItem.order, ChecklistItem.id).all()

        return render_template('admin/checklist.html', checklist_items=checklist_items)



    @app.route('/admin/users')
    @admin_required
    def manage_users():
        """Manage users and managers: edit store, role, permissions; reset password; revoke. Admins are on Manage Admins."""
        try:
            _ensure_stores_and_store_id()
            users = []
            try:
                users = UserModel.query.filter(UserModel.role.in_(['user', 'manager'])).order_by(UserModel.username).all()
            except Exception as e:
                db.session.rollback()
                try:
                    users = UserModel.query.filter(UserModel.role.in_(['user', 'manager'])).order_by(UserModel.username).all()
                except Exception:
                    db.session.rollback()
                    users = []
            stores = Store.query.order_by(Store.name).all()
            store_by_id = {s.id: s.name for s in stores}
            user_store_name = {}
            user_manager_permissions = {}
            for u in users:
                sid = getattr(u, 'store_id', None)
                user_store_name[u.id] = store_by_id.get(sid, '-') if sid else '-'
                if getattr(u, 'role', None) == 'manager':
                    perms = ManagerPermission.query.filter_by(user_id=u.id).all()
                    user_manager_permissions[u.id] = [p.permission_key for p in perms]
                else:
                    user_manager_permissions[u.id] = []
            today = datetime.utcnow().date()
            for u in users:
                revoked_at = getattr(u, 'access_revoked_at', None)
                try:
                    u.is_revoked = bool(revoked_at is not None and today >= revoked_at)
                except (TypeError, ValueError):
                    u.is_revoked = False
            users = [u for u in users if not getattr(u, 'is_revoked', False)]
            _admin_un = (current_user.username if current_user else '') or ''
            admin_name = main.staff_header_display_name(_admin_un) if _admin_un else 'Admin'
            return render_template('admin/users.html', users=users, stores=stores, manager_permission_keys=MANAGER_PERMISSION_KEYS, user_store_name=user_store_name, user_manager_permissions=user_manager_permissions)
        except Exception as e:
            import traceback
            app.logger.error(f'Error in manage_users: {str(e)}')
            app.logger.error(traceback.format_exc())
            db.session.rollback()
            flash('Unable to load users list. Please try again.', 'error')
            return redirect(url_for('admin_dashboard'))



    @app.route('/admin/training')
    @login_required
    def manage_training():
        """Manage harassment training videos and quizzes. Admin: full edit. Manager: view only, watch videos, see who watched and scores."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_training'):
            abort(403)
        _ensure_stores_and_store_id()
        stores = Store.query.order_by(Store.name).all()
        is_manager_view = main.uses_manager_console_scope()
        manager_store_id = main.get_current_user_store_id() if is_manager_view else None
        if is_manager_view:
            videos = main.training_videos_visible_to_store_query(
                manager_store_id,
                base_filter=(TrainingVideo.is_active == True),
            ).order_by(TrainingVideo.created_at.desc()).all()
        else:
            videos = TrainingVideo.query.order_by(TrainingVideo.created_at.desc()).all()
            _attach_training_video_store_lists(videos)
        videos_with_progress = []  # used for manager view only
        if is_manager_view:
            store_id = manager_store_id
            store_usernames = None
            if store_id is not None:
                store_usernames = set(nh.username for nh in NewHire.query.filter_by(store_id=store_id).all())
            for video in videos:
                progress_records = UserTrainingProgress.query.filter_by(video_id=video.id).order_by(
                    UserTrainingProgress.username, UserTrainingProgress.attempt_number.desc()
                ).all()
                # Latest attempt per user; filter by store if manager has store
                seen = set()
                progress_list = []
                for p in progress_records:
                    if store_usernames is not None and p.username not in store_usernames:
                        continue
                    if p.username in seen:
                        continue
                    seen.add(p.username)
                    progress_list.append({
                        'username': p.username,
                        'time_watched': p.time_watched or 0,
                        'score': p.score,
                        'is_passed': p.is_passed,
                        'is_completed': p.is_completed,
                        'completed_at': p.completed_at,
                    })
                videos_with_progress.append({'video': video, 'progress_list': progress_list})

        return render_template('admin/training.html', videos=videos, is_manager_view=is_manager_view, videos_with_progress=videos_with_progress, stores=stores)



    @app.route('/admin/roles')
    @admin_required
    def manage_roles():
        """List job roles and link to manage default documents"""
        try:
            roles = Role.query.order_by(Role.name).all()
        except Exception:
            db.session.rollback()
            try:
                db.create_all()
                roles = Role.query.order_by(Role.name).all()
            except Exception as e:
                flash(f'Database setup needed for roles. Run: CREATE TABLE roles (id INT PRIMARY KEY IDENTITY(1,1), name NVARCHAR(150) NOT NULL UNIQUE, description NVARCHAR(500), created_at DATETIME); CREATE TABLE role_documents (role_id INT NOT NULL, document_id INT NOT NULL, PRIMARY KEY (role_id, document_id)); ALTER TABLE new_hires ADD role_id INT NULL;', 'error')
                roles = []
        return render_template('admin/roles.html', roles=roles)



    @app.route('/admin/departments')
    @admin_required
    def manage_departments():
        """List departments for new hire onboarding."""
        try:
            departments = Department.query.order_by(Department.name).all()
            dept_rows = []
            for dept in departments:
                nh_count = NewHire.query.filter_by(department_id=dept.id).count()
                dept_rows.append({'department': dept, 'new_hire_count': nh_count})
        except Exception:
            db.session.rollback()
            _ensure_departments_table()
            departments = Department.query.order_by(Department.name).all()
            dept_rows = [{'department': d, 'new_hire_count': NewHire.query.filter_by(department_id=d.id).count()} for d in departments]
        return render_template('admin/departments.html', dept_rows=dept_rows)



    @app.route('/admin/manage-admins')
    @admin_required
    def manage_admins():
        """Manage admin users: add, update, delete, change password"""
        admins = UserModel.query.filter_by(role='admin').order_by(UserModel.username).all()
        return render_template('admin/admins.html', admins=admins)



    @app.route('/admin/external-links')
    @admin_required
    def manage_external_links():
        """Admin page to manage external links"""
        try:
            links = ExternalLink.query.order_by(ExternalLink.order, ExternalLink.created_at).all()
        except Exception as e:
            import traceback
            print(f"Error in manage_external_links: {e}")
            print(traceback.format_exc())
            flash('Error loading links. Please try again.', 'error')
            links = []

        return render_template('admin/external_links.html', links=links)



    @app.route('/admin/onboarding-messages', methods=['GET', 'POST'])
    @admin_required
    def manage_onboarding_messages():
        """Configure welcome screen and all-tasks-completed messages for new hires."""
        documents = Document.query.order_by(Document.original_filename).all()
        try:
            external_links = ExternalLink.query.filter_by(is_active=True).order_by(
                ExternalLink.order, ExternalLink.created_at
            ).all()
        except Exception:
            external_links = []
        if request.method == 'POST':
            section = (request.form.get('section') or '').strip().lower()
            try:
                if section == 'welcome':
                    welcome_headline = (request.form.get('welcome_headline') or '').strip().replace('{name}', '')
                    welcome_include_name = '1' if request.form.get('welcome_include_name') else '0'
                    welcome_body = (request.form.get('welcome_body') or '').strip()
                    if not welcome_headline or not welcome_body:
                        flash('Welcome headline and body are required.', 'error')
                        return redirect(url_for('manage_onboarding_messages'))
                    main.set_admin_setting('welcome_headline', welcome_headline)
                    main.set_admin_setting('welcome_include_name', welcome_include_name)
                    main.set_admin_setting('welcome_body', welcome_body)
                    db.session.commit()
                    flash('Welcome message saved.', 'success')
                elif section == 'finale':
                    default_finale_message = (request.form.get('default_finale_message') or '').strip()
                    default_finale_document_id = (request.form.get('default_finale_document_id') or '').strip()
                    if not default_finale_message:
                        flash('Completion dashboard message is required.', 'error')
                        return redirect(url_for('manage_onboarding_messages'))
                    if default_finale_document_id and not default_finale_document_id.isdigit():
                        flash('Invalid document selection.', 'error')
                        return redirect(url_for('manage_onboarding_messages'))
                    main.set_admin_setting('default_finale_message', default_finale_message)
                    main.set_admin_setting(
                        'default_finale_document_id',
                        default_finale_document_id if default_finale_document_id.isdigit() else '',
                    )
                    db.session.commit()
                    flash('Dashboard message saved.', 'success')
                elif section == 'email':
                    email_subject = (request.form.get('all_tasks_completed_email_subject') or '').strip()
                    email_body = (request.form.get('all_tasks_completed_email_body') or '').strip()
                    if not email_subject or not email_body:
                        flash('Completion email subject and body are required.', 'error')
                        return redirect(url_for('manage_onboarding_messages'))
                    main.set_admin_setting('all_tasks_completed_email_subject', email_subject)
                    main.set_admin_setting('all_tasks_completed_email_body', email_body)
                    db.session.commit()
                    flash('Completion email saved.', 'success')
                else:
                    flash('Could not save — unknown section.', 'error')
            except Exception as e:
                db.session.rollback()
                flash('Could not save messages. Please try again.', 'error')
            return redirect(url_for('manage_onboarding_messages'))

        welcome_headline_raw = main.get_admin_setting('welcome_headline', DEFAULT_WELCOME_HEADLINE)
        welcome_include_name = main.get_admin_setting('welcome_include_name', '1') == '1'
        if '{name}' in welcome_headline_raw:
            welcome_include_name = True
            welcome_headline_raw = welcome_headline_raw.replace('{name}', '')
        settings = {
            'welcome_headline': welcome_headline_raw,
            'welcome_include_name': welcome_include_name,
            'welcome_body': normalize_legacy_onboarding_message(
                main.get_admin_setting('welcome_body', DEFAULT_WELCOME_BODY)
            ),
            'default_finale_message': normalize_legacy_onboarding_message(
                main.get_admin_setting('default_finale_message', DEFAULT_FINALE_MESSAGE)
            ),
            'default_finale_document_id': main.get_admin_setting('default_finale_document_id', ''),
            'all_tasks_completed_email_subject': main.get_admin_setting(
                'all_tasks_completed_email_subject', DEFAULT_ALL_TASKS_EMAIL_SUBJECT
            ),
            'all_tasks_completed_email_body': normalize_legacy_onboarding_message(
                main.get_admin_setting('all_tasks_completed_email_body', DEFAULT_ALL_TASKS_EMAIL_BODY)
            ),
        }
        portal_links = [
            {'key': key, 'label': label, 'token': f'[link:portal:{key}|{label}]'}
            for key, label in ONBOARDING_PORTAL_PAGES
        ]
        external_link_items = [
            {
                'id': link.id,
                'label': link.title,
                'token': f'[link:external:{link.id}|{link.title}]',
            }
            for link in external_links
        ]
        return render_template('admin/onboarding_messages.html', settings=settings, documents=documents, portal_links=portal_links, external_link_items=external_link_items)



    @app.route('/admin/reports')
    @admin_required
    def admin_reports():
        """Admin reports page with comprehensive statistics"""
        try:
            # Overall statistics (exclude removed new hires)
            try:
                total_new_hires = NewHire.query.filter(NewHire.status != 'removed').count()
                total_users = UserModel.query.count()
                total_documents = Document.query.count()
                total_training_videos = TrainingVideo.query.filter_by(is_active=True).count()
                total_checklist_items = ChecklistItem.query.filter_by(is_active=True).count()
            except Exception as e:
                total_new_hires = 0
                total_users = 0
                total_documents = 0
                total_training_videos = 0
                total_checklist_items = 0

            # Training statistics
            try:
                total_training_progress = UserTrainingProgress.query.count()
                completed_trainings = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=True).count()
                failed_trainings = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=False).count()
                in_progress_trainings = UserTrainingProgress.query.filter_by(is_completed=False).count()
            except Exception as e:
                total_training_progress = 0
                completed_trainings = 0
                failed_trainings = 0
                in_progress_trainings = 0

            # Document statistics
            try:
                visible_documents = Document.query.filter_by(is_visible=True).count()
                documents_with_signatures = Document.query.join(DocumentSignatureField).distinct().count()
                total_signatures = DocumentSignature.query.count()
                unique_signed_users = db.session.query(DocumentSignature.username).distinct().count()
            except Exception as e:
                visible_documents = 0
                documents_with_signatures = 0
                total_signatures = 0
                unique_signed_users = 0

            # Checklist statistics
            try:
                total_checklist_completions = NewHireChecklist.query.filter_by(is_completed=True).count()
            except Exception as e:
                total_checklist_completions = 0

            # User progress statistics (exclude removed new hires)
            try:
                all_new_hires = NewHire.query.filter(NewHire.status != 'removed').all()
            except Exception as e:
                all_new_hires = []

            user_progress_stats = []
            for new_hire in all_new_hires:
                try:
                    # Training progress
                    try:
                        required_videos = list(new_hire.required_training_videos)
                        completed_videos = 0
                        for video in required_videos:
                            try:
                                progress = UserTrainingProgress.query.filter_by(
                                    username=new_hire.username,
                                    video_id=video.id,
                                    is_completed=True,
                                    is_passed=True
                                ).first()
                                if progress:
                                    completed_videos += 1
                            except Exception as e:
                                continue
                    except Exception as e:
                        required_videos = []
                        completed_videos = 0

                    # Task progress
                    try:
                        user_tasks = UserTask.query.filter_by(username=new_hire.username).all()
                        completed_tasks = len([t for t in user_tasks if t.status == 'completed'])
                        total_tasks = len(user_tasks)
                    except Exception as e:
                        completed_tasks = 0
                        total_tasks = 0

                    # Checklist progress
                    try:
                        checklist_completed = NewHireChecklist.query.filter_by(
                            new_hire_id=new_hire.id,
                            is_completed=True
                        ).count()
                        checklist_total = ChecklistItem.query.filter_by(is_active=True).count()
                    except Exception as e:
                        checklist_completed = 0
                        checklist_total = 0

                    # Calculate overall progress
                    total_items = len(required_videos) + total_tasks + checklist_total
                    completed_items = completed_videos + completed_tasks + checklist_completed
                    overall_progress = int((completed_items / total_items * 100)) if total_items > 0 else 0

                    user_progress_stats.append({
                        'new_hire': new_hire,
                        'training': {'completed': completed_videos, 'total': len(required_videos)},
                        'tasks': {'completed': completed_tasks, 'total': total_tasks},
                        'checklist': {'completed': checklist_completed, 'total': checklist_total},
                        'overall_progress': overall_progress
                    })
                except Exception as e:
                    # If there's an error processing this new hire, skip it
                    continue

            # Sort by overall progress
            try:
                user_progress_stats.sort(key=lambda x: x['overall_progress'], reverse=True)
            except Exception as e:
                pass

            # Department statistics
            department_stats = {}
            try:
                for new_hire in all_new_hires:
                    try:
                        dept = new_hire.department or 'Unassigned'
                        if dept not in department_stats:
                            department_stats[dept] = {'count': 0, 'completed': 0}
                        department_stats[dept]['count'] += 1
                        # Count completed users in this department
                        user_stats = next((s for s in user_progress_stats if s['new_hire'].id == new_hire.id), None)
                        if user_stats and user_stats['overall_progress'] == 100:
                            department_stats[dept]['completed'] += 1
                    except Exception as e:
                        continue
            except Exception as e:
                department_stats = {}

            # Detailed Training Information - per user and video
            training_details = []
            try:
                all_videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.title).all()
            except Exception as e:
                all_videos = []

            for new_hire in all_new_hires:
                for video in all_videos:
                    try:
                        # Get the latest progress record for this user and video
                        try:
                            progress = UserTrainingProgress.query.filter_by(
                                username=new_hire.username,
                                video_id=video.id
                            ).order_by(UserTrainingProgress.attempt_number.desc()).first()
                        except Exception as e:
                            progress = None

                        if progress:
                            try:
                                # Calculate watch percentage if video has duration
                                watch_percentage = 0
                                if video.duration and video.duration > 0:
                                    watch_percentage = min(100, (progress.time_watched / video.duration) * 100)

                                # Format time watched
                                time_watched_min = int(progress.time_watched // 60)
                                time_watched_sec = int(progress.time_watched % 60)
                                time_watched_str = f"{time_watched_min}m {time_watched_sec}s"

                                # Format video duration
                                video_duration_min = int(video.duration // 60) if video.duration else 0
                                video_duration_sec = int(video.duration % 60) if video.duration else 0
                                video_duration_str = f"{video_duration_min}m {video_duration_sec}s" if video.duration else "N/A"

                                training_details.append({
                                    'user': new_hire,
                                    'video': video,
                                    'progress': progress,
                                    'watched': True,
                                    'score': progress.score,
                                    'watch_percentage': watch_percentage,
                                    'time_watched': time_watched_str,
                                    'video_duration': video_duration_str,
                                    'is_passed': progress.is_passed,
                                    'is_completed': progress.is_completed,
                                    'attempt_number': progress.attempt_number,
                                    'started_at': progress.started_at,
                                    'completed_at': progress.completed_at
                                })
                            except Exception as e:
                                # If there's an error processing progress, skip it
                                continue
                        else:
                            # User hasn't watched this video yet
                            try:
                                video_duration_min = int(video.duration // 60) if video.duration else 0
                                video_duration_sec = int(video.duration % 60) if video.duration else 0
                                video_duration_str = f"{video_duration_min}m {video_duration_sec}s" if video.duration else "N/A"

                                training_details.append({
                                    'user': new_hire,
                                    'video': video,
                                    'progress': None,
                                    'watched': False,
                                    'score': None,
                                    'watch_percentage': 0,
                                    'time_watched': '0m 0s',
                                    'video_duration': video_duration_str,
                                    'is_passed': False,
                                    'is_completed': False,
                                    'attempt_number': 0,
                                    'started_at': None,
                                    'completed_at': None
                                })
                            except Exception as e:
                                continue
                    except Exception as e:
                        # If there's an error processing this user/video combination, skip it
                        continue

            # Sort training details by user name, then video title
            try:
                training_details.sort(key=lambda x: (x['user'].last_name, x['user'].first_name, x['video'].title))
            except Exception as e:
                pass

            return render_template('admin/reports.html', total_new_hires=total_new_hires, total_users=total_users, total_documents=total_documents,
             total_training_videos=total_training_videos, total_checklist_items=total_checklist_items,
             completed_trainings=completed_trainings, failed_trainings=failed_trainings,
             in_progress_trainings=in_progress_trainings, total_training_progress=total_training_progress,
             visible_documents=visible_documents, documents_with_signatures=documents_with_signatures,
             total_signatures=total_signatures, unique_signed_users=unique_signed_users,
             total_checklist_completions=total_checklist_completions,
             user_progress_stats=user_progress_stats, department_stats=department_stats,
             training_details=training_details)
        except Exception as e:
            # Log the error for debugging
            import traceback
            app.logger.error(f'Error in admin_reports: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Set defaults to prevent template errors
            total_new_hires = 0
            total_users = 0
            total_documents = 0
            total_training_videos = 0
            total_checklist_items = 0
            total_training_progress = 0
            completed_trainings = 0
            failed_trainings = 0
            in_progress_trainings = 0
            visible_documents = 0
            documents_with_signatures = 0
            total_signatures = 0
            unique_signed_users = 0
            total_checklist_completions = 0
            user_progress_stats = []
            department_stats = {}
            training_details = []

            # Return a basic reports page with error message
            app.logger.exception('Error loading reports')
            flash('Error loading reports. Some data may be missing.', 'error')

            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Reports - Onboarding App</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: 'URW Form', Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                    .error-box { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                    .error-box strong { color: #856404; }
                {{ global_theme_css|safe }}
            </style>
            </head>
            <body>
                <div class="error-box">
                    <strong>⚠️ Reports Page Error</strong>
                    <p>There was an error loading the reports. Please refresh the page or contact support if the problem persists.</p>
                </div>
                <p><a href="{{ url_for('admin_reports') }}">Refresh Reports</a> | <a href="{{ url_for('admin_dashboard') }}">Back to Dashboard</a></p>
            </body>
            </html>
            ''')



    @app.route('/admin/jobs')
    @admin_required
    def admin_jobs():
        """List recent background jobs (signed PDF builds, etc.)."""
        from services.jobs import list_recent_jobs, recover_stuck_jobs
        try:
            recover_stuck_jobs()
            jobs = list_recent_jobs(100)
        except Exception as exc:
            app.logger.exception('admin_jobs failed')
            flash(f'Could not load jobs: {exc}', 'error')
            jobs = []
        return render_template(
            'admin/jobs.html',
            jobs=jobs,
            back_url=main.staff_console_home_url(),
        )

    @app.route('/admin/jobs/<int:job_id>/requeue', methods=['POST'])
    @admin_required
    def admin_jobs_requeue(job_id):
        from services.jobs import requeue_job
        job = requeue_job(job_id)
        if job:
            flash(f'Job #{job_id} requeued.', 'success')
        else:
            flash(f'Could not requeue job #{job_id} (done, missing, or max attempts).', 'error')
        return redirect(url_for('admin_jobs'))



    @app.route('/admin/user-checklists')
    @login_required
    def view_user_checklists():
        """List active users and their checklist progress. Admin sees all; managers see their store only."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_user_checklists') and not main.manager_has_permission('manage_checklist'):
            abort(403)
        from datetime import date as _date
        today = _date.today()
        store_id = main.get_current_user_store_id()
        q = NewHire.query.filter(NewHire.status != 'removed')
        if current_user.is_manager() and store_id is not None:
            q = q.filter(NewHire.store_id == store_id)
        candidates = q.order_by(NewHire.first_name, NewHire.last_name).all()
        # Exclude new hires whose user was revoked or deleted (same as dashboard / manage users)
        all_new_hires = []
        for nh in candidates:
            user = UserModel.query.filter_by(username=nh.username).first()
            if not user:
                continue
            revoked_at = getattr(user, 'access_revoked_at', None)
            if revoked_at is not None and today >= revoked_at:
                continue
            all_new_hires.append(nh)

        # Re-fetch display fields with a fresh query so names are always current (bypasses ORM/session cache)
        from types import SimpleNamespace
        if all_new_hires:
            usernames = [nh.username for nh in all_new_hires]
            try:
                stmt = text(
                    "SELECT username, first_name, last_name, department FROM new_hires WHERE status != 'removed' AND username IN :usernames ORDER BY first_name, last_name"
                ).bindparams(bindparam("usernames", expanding=True))
                result = db.session.execute(stmt, {"usernames": usernames})
                rows = result.fetchall()
                all_new_hires = [SimpleNamespace(username=r[0], first_name=r[1] or '', last_name=r[2] or '', department=r[3]) for r in rows]
            except Exception:
                pass  # keep original all_new_hires if raw query fails (e.g. dialect)
        resp = render_template('admin/user_checklists.html', all_new_hires=all_new_hires)
        resp = make_response(resp)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
        return resp



    @app.route('/admin/new-hire/add')
    @login_required
    def add_new_hire():
        """Add a new hire with step-by-step onboarding wizard. Admin or manager with start_onboarding permission."""
        if not current_user.is_admin() and not main.manager_has_permission('start_onboarding'):
            abort(403)
        store_id = main.staff_store_scope_id()
        videos = main.training_videos_visible_to_store_query(
            store_id,
            base_filter=(TrainingVideo.is_active == True),
        ).order_by(TrainingVideo.title).all()
        # Assignable forms for this store (or all for admin) — includes Not in library
        documents = main.documents_assignable_to_store_query(
            store_id,
            base_filter=_document_has_assignable_fields_filter(),
        ).order_by(Document.original_filename).all()
        checklist_items = ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order).all()
        # Roles for default-document pre-selection
        try:
            roles = Role.query.order_by(Role.name).all()
            role_default_documents = {str(r.id): [d.id for d in r.default_documents.all()] for r in roles}
        except Exception:
            roles = []
            role_default_documents = {}
        stores = Store.query.order_by(Store.name).all()
        default_store_id = main.staff_store_scope_id()
        default_store_code = ''
        if default_store_id:
            store = Store.query.get(default_store_id)
            default_store_code = (store.code or '').strip().lower() if store else ''
        try:
            departments = Department.query.order_by(Department.name).all()
        except Exception:
            db.session.rollback()
            _ensure_departments_table()
            departments = Department.query.order_by(Department.name).all()
        return render_template('admin/add_new_hire.html', videos=videos, documents=documents, checklist_items=checklist_items, roles=roles, role_default_documents=role_default_documents, stores=stores, departments=departments, default_store_id=default_store_id, default_store_code=default_store_code)



    def _view_all_new_hires_impl(force_staff_console_manager=False):
        """Implementation for admin/manager new-hires list. Managers (non-admin) see only their store; admins see all or filter by ?store_id=."""
        q = NewHire.query.filter(NewHire.status != 'removed')
        _sc = (request.args.get(main.STAFF_CONSOLE_QUERY_KEY) or '').strip().lower()
        if force_staff_console_manager:
            _sc = 'manager'
        _mgr_uri = _sc == 'manager'
        _sid_user = main.get_current_user_store_id()
        sp = (request.args.get('store_id') or '').strip()

        if main.is_pure_manager():
            if _sid_user is not None:
                q = q.filter(NewHire.store_id == _sid_user)
        elif current_user.is_admin():
            # Admins acting from Manager Console (?staff_console=manager) must stay store-scoped like managers.
            if _mgr_uri and sp.isdigit():
                q = q.filter(NewHire.store_id == int(sp))
            elif _mgr_uri and _sid_user is not None:
                q = q.filter(NewHire.store_id == _sid_user)
            elif sp == 'none':
                q = q.filter(NewHire.store_id.is_(None))
            elif sp.isdigit():
                q = q.filter(NewHire.store_id == int(sp))
        all_new_hires = q.order_by(NewHire.created_at.desc()).all()
        new_hires_with_progress = []
        try:
            role_name_by_id = {r.id: r.name for r in Role.query.all()}
        except Exception:
            role_name_by_id = {}
        from datetime import date as _nh_list_date
        _nh_today = _nh_list_date.today()
        # Fresh reads for users.access_revoked_at (avoid stale identity map; matches login after cancel-access).
        try:
            db.session.expire_all()
        except Exception:
            db.session.rollback()

        for new_hire in all_new_hires:
            # Training videos progress
            required_videos = list(new_hire.required_training_videos)
            total_videos = len(required_videos)
            completed_videos = 0

            for video in required_videos:
                progress = UserTrainingProgress.query.filter_by(
                    username=new_hire.username,
                    video_id=video.id,
                    is_completed=True,
                    is_passed=True
                ).first()
                if progress:
                    completed_videos += 1

            # User tasks progress
            all_user_tasks = UserTask.query.filter_by(username=new_hire.username).all()
            total_user_tasks = len(all_user_tasks)
            completed_user_tasks = len([t for t in all_user_tasks if t.status == 'completed'])

            # Checklist progress
            checklist_completed = NewHireChecklist.query.filter_by(
                new_hire_id=new_hire.id,
                is_completed=True
            ).count()
            checklist_total = ChecklistItem.query.filter_by(is_active=True).count()

            # Calculate overall progress (training videos + user tasks + checklist items)
            total_items = total_videos + total_user_tasks + checklist_total
            completed_items = completed_videos + completed_user_tasks + checklist_completed
            progress_percentage = int((completed_items / total_items * 100)) if total_items > 0 else 0

            _nh_user = UserModel.query.filter_by(username=new_hire.username).first()
            _ur = _access_revoke_calendar_date(getattr(_nh_user, 'access_revoked_at', None)) if _nh_user else None
            # Same rule as authenticate_by_email_password: revoked when today >= revoke calendar date.
            login_active = bool(_nh_user) and not (_ur is not None and _nh_today >= _ur)

            new_hires_with_progress.append({
                'new_hire': new_hire,
                'progress': progress_percentage,
                'completed': completed_items,
                'total': total_items,
                'training': {'completed': completed_videos, 'total': total_videos},
                'tasks': {'completed': completed_user_tasks, 'total': total_user_tasks},
                'checklist': {'completed': checklist_completed, 'total': checklist_total},
                'login_active': login_active,
            })

        _nh_list_un = (current_user.username if current_user else '') or ''
        admin_name = main.staff_header_display_name(_nh_list_un) if _nh_list_un else 'Admin'
        new_hires_list_heading = 'New Hires List'
        if main.is_pure_manager():
            _msid = main.get_current_user_store_id()
            if _msid is not None:
                _mst = Store.query.get(_msid)
                if _mst and (_mst.name or '').strip():
                    new_hires_list_heading = _mst.name.strip()
        elif current_user.is_admin():
            _asp = sp
            if _mgr_uri and _asp.isdigit():
                _ast = Store.query.get(int(_asp))
                new_hires_list_heading = (_ast.name.strip() if _ast and (_ast.name or '').strip() else f'Store #{_asp}')
            elif _mgr_uri and _sid_user is not None:
                _mst = Store.query.get(_sid_user)
                if _mst and (_mst.name or '').strip():
                    new_hires_list_heading = _mst.name.strip()
            elif _asp == 'none':
                new_hires_list_heading = 'No store assigned'
            elif _asp.isdigit():
                _ast = Store.query.get(int(_asp))
                new_hires_list_heading = (_ast.name.strip() if _ast and (_ast.name or '').strip() else f'Store #{_asp}')

        _nh_list_html = render_template('admin/new_hires.html', new_hires_with_progress=new_hires_with_progress, admin_name=admin_name,
             new_hires_list_heading=new_hires_list_heading, role_name_by_id=role_name_by_id)
        _nh_list_resp = make_response(_nh_list_html)
        _nh_list_resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        _nh_list_resp.headers['Pragma'] = 'no-cache'
        return _nh_list_resp



    def _view_new_hire_details_impl(username, force_manager_console=False):
        """Implementation for admin/manager new-hire details pages."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        manager_view = force_manager_console or main.uses_manager_console_scope()
        try:
            new_hire = NewHire.query.filter_by(username=username).first()
            if not new_hire:
                flash('New hire not found.', 'error')
                return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(main.staff_console_home_url())
            if manager_view or main.is_pure_manager():
                store_id = main.get_current_user_store_id()
                if store_id is None:
                    flash('You can only view new hires at your store.', 'error')
                    return redirect(main.manager_new_hires_list_url())
                allowed = NewHire.query.filter(
                    NewHire.status != 'removed',
                    NewHire.store_id == store_id,
                    NewHire.username == username
                ).first()
                if not allowed:
                    flash('You can only view new hires at your store.', 'error')
                    return redirect(main.manager_new_hires_list_url())

            # Get training video progress and quiz results
            required_videos = list(new_hire.required_training_videos)
            video_progress = []

            for video in required_videos:
                try:
                    progress = UserTrainingProgress.query.filter_by(
                        username=username,
                        video_id=video.id
                    ).order_by(UserTrainingProgress.attempt_number.desc()).first()

                    # Get quiz responses for this video
                    quiz_responses = []
                    if progress:
                        responses = UserQuizResponse.query.filter_by(
                            progress_id=progress.id
                        ).all()
                        quiz_responses = responses

                    video_progress.append({
                        'video': video,
                        'progress': progress,
                        'quiz_responses': quiz_responses
                    })
                except Exception as e:
                    # If there's an error with a specific video, skip it
                    video_progress.append({
                        'video': video,
                        'progress': None,
                        'quiz_responses': []
                    })

            # Get signed / completed documents (image signatures and typed-signature forms)
            signed_documents = []
            try:
                signed_documents = main._completed_document_cards_for_user(username)
            except Exception:
                signed_documents = []

            # Get user tasks
            try:
                user_tasks = UserTask.query.filter_by(username=username).all()
            except Exception as e:
                # If there's an error getting tasks, use empty list
                user_tasks = []

            # Get user account (for Cancel / Restore access); revoke date normalized like login check
            user_record = None
            user_is_revoked = False
            try:
                user_record = UserModel.query.filter_by(username=username).first()
                if user_record:
                    from datetime import date as _detail_today
                    _ur = _access_revoke_calendar_date(getattr(user_record, 'access_revoked_at', None))
                    user_is_revoked = bool(_ur is not None and _detail_today.today() >= _ur)
            except Exception:
                pass

            all_stores = []
            try:
                scope_sid = main.get_current_user_store_id() if manager_view else None
                if scope_sid is not None:
                    all_stores = Store.query.filter_by(id=scope_sid).order_by(Store.name).all()
                else:
                    all_stores = Store.query.order_by(Store.name).all()
            except Exception:
                all_stores = []

            all_roles = []
            try:
                all_roles = Role.query.order_by(Role.name).all()
            except Exception:
                all_roles = []
            try:
                all_departments = Department.query.order_by(Department.name).all()
            except Exception:
                db.session.rollback()
                _ensure_departments_table()
                all_departments = Department.query.order_by(Department.name).all()

            can_assign_extra_task = current_user.is_admin() or main._manager_can_act_on_new_hire(username)
            assign_task_endpoint, assign_task_staff_console = assign_task_link_context()

            return render_template('admin/new_hire_details.html', new_hire=new_hire, video_progress=video_progress, signed_documents=signed_documents, 
             user_tasks=user_tasks, username=username, user_record=user_record, user_is_revoked=user_is_revoked,
             all_stores=all_stores, all_roles=all_roles, all_departments=all_departments,
             can_assign_extra_task=can_assign_extra_task, assign_task_endpoint=assign_task_endpoint,
             assign_task_staff_console=assign_task_staff_console, manager_view=manager_view)
        except Exception as e:
            # Log the error for debugging
            import traceback
            app.logger.error(f'Error in view_new_hire_details for {username}: {str(e)}')
            app.logger.error(traceback.format_exc())
            flash('Error loading new hire details. Please try again.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(main.staff_console_home_url())

    @app.route('/admin/new-hires')
    @login_required
    def view_all_new_hires():
        """View all new hires with progress information. Admin sees all; managers see their store only."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        try:
            return _view_all_new_hires_impl()
        except Exception:
            app.logger.exception("view_all_new_hires failed")
            db.session.rollback()
            import traceback
            return (
                f'<html><body><h1>New Hires Page Error</h1>'
                f'<pre>{traceback.format_exc()}</pre></body></html>'
            ), 500

    @app.route('/manager/new-hires')
    @manager_required
    def manager_new_hires():
        """New hires list at a manager URL (same data as /admin/new-hires with staff_console=manager)."""
        try:
            main.touch_staff_console_home('manager')
            return _view_all_new_hires_impl(force_staff_console_manager=True)
        except Exception:
            app.logger.exception("manager_new_hires failed")
            db.session.rollback()
            import traceback
            return (
                f'<html><body><h1>New Hires Page Error</h1>'
                f'<pre>{traceback.format_exc()}</pre></body></html>'
            ), 500

    @app.route('/manager/new-hire/<username>/details')
    @manager_required
    def manager_view_new_hire_details(username):
        """New hire details at a manager URL (store-scoped UI, not org-wide admin)."""
        main.touch_staff_console_home('manager')
        return _view_new_hire_details_impl(username, force_manager_console=True)

    @app.route('/admin/new-hire/<username>/details')
    @login_required
    def view_new_hire_details(username):
        """View detailed information about a new hire including quiz results and signed forms."""
        sc = (request.args.get(main.STAFF_CONSOLE_QUERY_KEY) or '').strip().lower()
        if sc != 'admin' and main.uses_manager_console_scope():
            return redirect(url_for('manager_view_new_hire_details', username=username))
        return _view_new_hire_details_impl(username, force_manager_console=False)



    @app.route('/admin/asana/feedback')
    @admin_required
    def admin_asana_feedback():
        """Asana feedback integration status (.env access token or optional OAuth)."""
        connected = _asana_is_connected()
        connected_user = main.get_admin_setting('asana_connected_user')
        redirect_uri = _asana_redirect_uri()
        oauth_available = _asana_oauth_configured()
        env_token = _asana_env_token_configured()
        feedback_ready = _asana_feedback_ready()
        project_gid = ASANA_FEEDBACK_PROJECT_GID
        return render_template('admin/asana_feedback.html', connected=connected,
            connected_user=connected_user,
            redirect_uri=redirect_uri,
            oauth_available=oauth_available,
            env_token=env_token,
            feedback_ready=feedback_ready,
            project_gid=project_gid,
            section_gid_comment=ASANA_SECTION_GID_COMMENT,
            section_gid_issue=ASANA_SECTION_GID_ISSUE,
            section_gid_suggestion=ASANA_SECTION_GID_SUGGESTION,
            assignee_gid=ASANA_FEEDBACK_ASSIGNEE_GID,)



    @app.route('/admin/view-checklist')
    @admin_required
    def view_checklist():
        """View checklist and check off completed tasks"""
        checklist_items = ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order, ChecklistItem.id).all()

        # Get completion status for each item (for now, we'll track globally or per admin)
        # For simplicity, we'll create a simple completion tracking
        completed_items = request.args.getlist('completed')  # Get completed items from query params

        return render_template('admin/view_checklist.html', checklist_items=checklist_items)



    @app.route('/admin/training/<int:video_id>/quiz')
    @admin_required
    def manage_video_quiz(video_id):
        """Manage quiz questions for a training video"""
        video = TrainingVideo.query.get(video_id)

        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('manage_training'))

        # Get questions ordered by type and timestamp/order
        mid_questions = [q for q in video.questions if q.question_type == 'mid']
        mid_questions.sort(key=lambda x: x.video_timestamp or 0)
        end_questions = [q for q in video.questions if q.question_type == 'end']
        end_questions.sort(key=lambda x: x.order)

        return render_template('admin/video_quiz.html', video=video, mid_questions=mid_questions, end_questions=end_questions)

    @app.route('/admin/new-hire/create', methods=['POST'])
    @login_required
    def create_new_hire():
        """Create a new hire with required training videos and documents. Admin or manager with start_onboarding."""
        if not current_user.is_admin() and not main.manager_has_permission('start_onboarding'):
            abort(403)
        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = normalize_email(request.form.get('email'))
        email_provided_by_staff = bool(email)
        password = request.form.get('password', '').strip()
        department_id_raw = request.form.get('department_id', '').strip()
        dept_id, dept_name = resolve_department_from_form(department_id_raw)
        start_date_str = request.form.get('start_date', '').strip()
        access_revoked_at_str = request.form.get('access_revoked_at', '').strip()
        required_videos = request.form.getlist('required_videos')
        required_documents = request.form.getlist('required_documents')
        role_id_str = request.form.get('role_id', '').strip()

        if not username or not first_name or not last_name:
            flash('Username, first name, and last name are required.', 'error')
            return redirect(url_for('add_new_hire'))
        if not password or len(password) < 6:
            flash('Password is required and must be at least 6 characters.', 'error')
            return redirect(url_for('add_new_hire'))

        if not required_videos:
            flash('At least one training video must be selected.', 'error')
            return redirect(url_for('add_new_hire'))

        try:
            _ensure_user_task_order_columns()
            # Ensure access_revoked_at column exists (for existing databases)
            try:
                db.session.execute(text("SELECT access_revoked_at FROM new_hires WHERE 1=0"))
            except Exception:
                db.session.rollback()
                try:
                    db.session.execute(text("ALTER TABLE new_hires ADD access_revoked_at DATE NULL"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            try:
                db.session.execute(text("SELECT role_id FROM new_hires WHERE 1=0"))
            except Exception:
                db.session.rollback()
                try:
                    db.session.execute(text("ALTER TABLE new_hires ADD role_id INT NULL"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Generate a default email if not provided (model requires email)
            if not email:
                import config
                email_domain = config.EMAIL_DOMAIN if hasattr(config, 'EMAIL_DOMAIN') else 'ziebart.com'
                email = normalize_email(f"{username}@{email_domain}")
            existing_user = UserModel.query.filter_by(username=username).first()
            existing_user_email = normalize_email(getattr(existing_user, 'email', None)) if existing_user else None
            if existing_user and existing_user_email and email != existing_user_email:
                flash(
                    f'Email cannot be changed for existing user "{username}". '
                    f'Current login email is "{existing_user.email}".',
                    'error'
                )
                return redirect(url_for('add_new_hire'))
            if existing_user_email:
                email = existing_user_email
            if email_in_use_by_other_user(email, exclude_user_id=existing_user.id if existing_user else None):
                flash(f'Email "{email}" is already in use by another account.', 'error')
                return redirect(url_for('add_new_hire'))

            # Parse start date
            start_date = None
            if start_date_str:
                try:
                    from datetime import datetime
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except Exception:
                    pass

            # Parse access revoke date
            access_revoked_at = None
            if access_revoked_at_str:
                try:
                    from datetime import datetime
                    access_revoked_at = datetime.strptime(access_revoked_at_str, '%Y-%m-%d').date()
                except Exception:
                    pass

            role_id = None
            if role_id_str:
                try:
                    role_id = int(role_id_str)
                    if Role.query.get(role_id) is None:
                        role_id = None
                except (ValueError, TypeError):
                    role_id = None

            # Store: admins pick from form; managers use hidden field or dropdown (must honor POST when DB store is unset)
            store_id = None
            mgr_db_store = main.get_current_user_store_id() if not current_user.is_admin() else None
            store_id_raw = (request.form.get('store_id') or '').strip()
            if store_id_raw.isdigit():
                try:
                    cand = int(store_id_raw)
                    if Store.query.get(cand) is not None:
                        if current_user.is_admin():
                            store_id = cand
                        elif mgr_db_store is None:
                            store_id = cand
                        elif cand == mgr_db_store:
                            store_id = cand
                except (ValueError, TypeError):
                    pass
            if store_id is None and not current_user.is_admin():
                store_id = mgr_db_store

            # Create new hire
            new_hire = NewHire(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                department=dept_name,
                start_date=start_date,
                access_revoked_at=access_revoked_at,
                created_by=current_user.username
            )
            if role_id is not None and hasattr(NewHire, 'role_id'):
                new_hire.role_id = role_id
            if hasattr(NewHire, 'department_id'):
                new_hire.department_id = dept_id
            if hasattr(NewHire, 'store_id'):
                new_hire.store_id = store_id
            db.session.add(new_hire)
            db.session.flush()  # Get the ID

            # Ensure User exists with email and password so new hire can log in (email + password)
            user = existing_user
            if not user:
                user = UserModel(
                    username=username,
                    email=email,
                    role='user',
                    password_hash=generate_password_hash(password)
                )
                db.session.add(user)
            else:
                # Existing users keep their original login email; only reset password for onboarding.
                user.password_hash = generate_password_hash(password)
            if hasattr(user, 'store_id'):
                user.store_id = store_id

            # Add required training videos and create tasks with display_order and dependencies
            training_tasks_created = []
            display_order = 0
            for video_id in required_videos:
                video = TrainingVideo.query.get(int(video_id))
                if video:
                    new_hire.required_training_videos.append(video)

                    existing_task = UserTask.query.filter_by(
                        username=username,
                        task_type='training',
                        status='pending'
                    ).filter(UserTask.notes.like(f'video_id:{video_id}%')).first()

                    if not existing_task:
                        task = UserTask(
                            username=username,
                            task_title=f"Complete Training: {video.title}",
                            task_description=f"Please watch and complete the training video: {video.title}",
                            task_type='training',
                            priority='normal',
                            status='pending',
                            assigned_by=current_user.username,
                            notes=f'video_id:{video_id}',
                            display_order=display_order,
                            depends_on_task_id=training_tasks_created[-1].id if training_tasks_created else None
                        )
                        db.session.add(task)
                        db.session.flush()
                        training_tasks_created.append(task)
                        display_order += 1

            # Assign documents if selected; each doc task depends on the previous task (training or doc)
            prev_task = training_tasks_created[-1] if training_tasks_created else None
            for doc_id in required_documents:
                document = Document.query.get(int(doc_id))
                if document:
                    existing = DocumentAssignment.query.filter_by(
                        document_id=doc_id,
                        username=username
                    ).first()

                    if not existing:
                        assignment = DocumentAssignment(
                            document_id=doc_id,
                            username=username,
                            assigned_by=current_user.username
                        )
                        db.session.add(assignment)

                        task = UserTask(
                            username=username,
                            task_title=f"Sign Document: {document.name_for_users}",
                            task_description=f"Please review and sign the document: {document.description or document.name_for_users}",
                            task_type='document',
                            document_id=doc_id,
                            priority='normal',
                            status='pending',
                            assigned_by=current_user.username,
                            display_order=display_order,
                            depends_on_task_id=prev_task.id if prev_task else None
                        )
                        db.session.add(task)
                        db.session.flush()
                        prev_task = task
                        display_order += 1

            db.session.commit()

            # Build success message
            msg_parts = [f'Onboarding started for "{first_name} {last_name}" ({username})']
            msg_parts.append(f'with {len(required_videos)} training video(s)')
            if required_documents:
                msg_parts.append(f'and {len(required_documents)} document(s) to sign')
            msg_parts.append('.')

            # Send get-started email with login link (best-effort; hire creation already succeeded)
            if email_provided_by_staff and send_onboarding_welcome_email(first_name, last_name, email, password):
                msg_parts.append(f'Welcome email sent to {email}.')
            elif email_provided_by_staff:
                msg_parts.append(f'Could not send welcome email to {email} — share the login link manually.')
            else:
                msg_parts.append('No email entered — welcome link was not sent.')

            flash(' '.join(msg_parts), 'success')
            if main.uses_manager_new_hires_home():
                return redirect(main.manager_new_hires_list_url())
            return redirect(url_for('admin_dashboard', staff_console='admin'))
        except Exception as e:
            db.session.rollback()
            flash('Error starting onboarding. Please try again.', 'error')
            return redirect(url_for('add_new_hire'))

    @app.route('/admin/asana/connect')
    @admin_required
    def asana_oauth_connect():
        if not _asana_oauth_configured():
            flash('Set ASANA_CLIENT_ID and ASANA_CLIENT_SECRET in .env first.', 'error')
            return redirect(url_for('admin_asana_feedback'))
        verifier, challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(24)
        session['asana_oauth_state'] = state
        session['asana_oauth_code_verifier'] = verifier
        auth_url = build_authorization_url(
            ASANA_CLIENT_ID,
            _asana_redirect_uri(),
            state,
            challenge,
        )
        return redirect(auth_url)

    @app.route('/admin/asana/callback')
    @admin_required
    def asana_oauth_callback():
        error = request.args.get('error')
        if error:
            flash(f'Asana authorization was denied or failed ({error}).', 'error')
            return redirect(url_for('admin_asana_feedback'))
        state = request.args.get('state') or ''
        code = request.args.get('code') or ''
        expected_state = session.pop('asana_oauth_state', None)
        code_verifier = session.pop('asana_oauth_code_verifier', None)
        if not code or not code_verifier or not expected_state or state != expected_state:
            flash('Invalid Asana OAuth response. Please try connecting again.', 'error')
            return redirect(url_for('admin_asana_feedback'))
        try:
            token_payload = exchange_authorization_code(
                ASANA_CLIENT_ID,
                ASANA_CLIENT_SECRET,
                _asana_redirect_uri(),
                code,
                code_verifier,
            )
            _asana_store_tokens(token_payload)
            flash('Asana connected successfully. Feedback will now create tasks in your project.', 'success')
        except AsanaError as exc:
            flash(f'Could not complete Asana authorization: {exc}', 'error')
        return redirect(url_for('admin_asana_feedback'))

    @app.route('/admin/asana/disconnect', methods=['POST'])
    @admin_required
    def asana_oauth_disconnect():
        _asana_clear_tokens()
        flash('Asana disconnected.', 'success')
        return redirect(url_for('admin_asana_feedback'))

    @app.route('/admin/users/add', methods=['POST'])
    @admin_required
    def users_add():
        """User creation is disabled; users are only created when starting onboarding (add new hire)."""
        flash('Users cannot be added here. Add a new hire from the New Hires / onboarding flow to create a user.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/<int:user_id>/update', methods=['POST'])
    @admin_required
    def users_update(user_id):
        """Update user email, full name, store, role, and manager permissions."""
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))
        email = normalize_email(request.form.get('email'))
        full_name = (request.form.get('full_name') or '').strip()
        store_id_raw = request.form.get('store_id') or ''
        role = (request.form.get('role') or 'user').strip().lower()
        if role not in ('user', 'manager'):
            role = 'user'
        current_email = normalize_email(getattr(user, 'email', None))
        if email != current_email:
            flash('Email is locked after account creation. Use username/password reset only.', 'error')
            return redirect(url_for('manage_users'))
        user.full_name = full_name or None
        try:
            user.store_id = int(store_id_raw) if store_id_raw.isdigit() else None
        except (ValueError, TypeError):
            user.store_id = None
        user.role = role
        if role == 'manager':
            ManagerPermission.query.filter_by(user_id=user.id).delete()
            for key, _label in MANAGER_PERMISSION_KEYS:
                if request.form.get('perm_' + key) == '1':
                    db.session.add(ManagerPermission(user_id=user.id, permission_key=key))
        else:
            ManagerPermission.query.filter_by(user_id=user.id).delete()
        try:
            db.session.commit()
            flash(f'User "{user.username}" updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating. Please try again.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
    @admin_required
    def users_reset_password(user_id):
        """Reset a user's password."""
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))
        new_password = (request.form.get('new_password') or '').strip()
        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('manage_users'))
        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        try:
            db.session.commit()
            flash(f'Password updated for "{user.username}".', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating password. Please try again.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/<int:user_id>/send-password-reset-email', methods=['POST'])
    @admin_required
    def users_send_password_reset_email(user_id):
        """Generate a temporary password, email it to the user, and require password change on next login."""
        _ensure_users_must_change_password_column()
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))
        to_email = normalize_email(getattr(user, 'email', None))
        if not to_email:
            flash(f'User "{user.username}" has no email address.', 'error')
            return redirect(url_for('manage_users'))
        temporary_password = generate_temporary_password()
        user.password_hash = generate_password_hash(temporary_password)
        user.must_change_password = True
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Could not update password. Please try again.', 'error')
            return redirect(url_for('manage_users'))
        if send_password_reset_email(user, temporary_password):
            flash(f'Password reset email sent to {to_email}.', 'success')
        else:
            flash('Temporary password was set, but the email could not be sent. Check mail configuration.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/<int:user_id>/revoke', methods=['POST'])
    @admin_required
    def users_revoke(user_id):
        """Remove user permanently (delete account and mark new hire as removed). They will no longer appear in the list."""
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))
        if user.username == current_user.username:
            flash('You cannot remove your own account.', 'error')
            return redirect(url_for('manage_users'))
        if getattr(user, 'role', None) == 'admin':
            flash('Cannot remove an admin. Remove admin role first from Manage Admins.', 'error')
            return redirect(url_for('manage_users'))
        username = user.username
        try:
            # Mark new hire as removed if they have a record
            new_hire = NewHire.query.filter_by(username=username).first()
            if new_hire:
                new_hire.status = 'removed'
            # Delete the user account
            db.session.delete(user)
            db.session.commit()
            flash(f'User "{username}" has been removed.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.exception('users_revoke failed')
            flash('Error removing user. Please try again.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/<int:user_id>/restore', methods=['POST'])
    @admin_required
    def users_restore(user_id):
        """Restore user access (clear revoke date)."""
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))
        user.access_revoked_at = None
        try:
            db.session.commit()
            flash(f'Access restored for "{user.username}".', 'success')
        except Exception as e:
            db.session.rollback()
            err_str = (str(e) or '').lower()
            if 'access_revoked_at' in err_str or 'invalid column' in err_str:
                try:
                    db.session.execute(text("ALTER TABLE users ADD access_revoked_at DATE NULL"))
                    db.session.commit()
                    user.access_revoked_at = None
                    db.session.commit()
                    flash(f'Access restored for "{user.username}".', 'success')
                except Exception:
                    db.session.rollback()
                    flash('Error. Please try again.', 'error')
            else:
                flash('Error. Please try again.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/roles/add', methods=['POST'])
    @admin_required
    def add_role():
        """Create a new role"""
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Position/Title name is required.', 'error')
            return redirect(url_for('manage_roles'))
        existing = Role.query.filter(db.func.lower(Role.name) == name.lower()).first()
        if existing:
            flash(f'Position/Title "{name}" already exists.', 'error')
            return redirect(url_for('manage_roles'))
        try:
            role = Role(name=name)
            db.session.add(role)
            db.session.commit()
            flash(f'Position/Title "{name}" added.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding Position/Title. Please try again.', 'error')
        return redirect(url_for('manage_roles'))

    @app.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
    @admin_required
    def delete_role(role_id):
        """Delete a role"""
        role = Role.query.get(role_id)
        if not role:
            flash('Position/Title not found.', 'error')
            return redirect(url_for('manage_roles'))
        try:
            # Clear default_documents and new hires' role_id
            NewHire.query.filter_by(role_id=role_id).update({NewHire.role_id: None})
            db.session.delete(role)
            db.session.commit()
            flash(f'Position/Title "{role.name}" deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting Position/Title. Please try again.', 'error')
        return redirect(url_for('manage_roles'))

    @app.route('/admin/departments/add', methods=['POST'])
    @admin_required
    def add_department():
        """Create a new department. Supports JSON for wizard inline add."""
        if request.is_json:
            data = request.get_json(silent=True) or {}
            name = (data.get('name') or '').strip()
        else:
            name = (request.form.get('name') or '').strip()
        if not name:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': False, 'error': 'Department name is required.'}), 400
            flash('Department name is required.', 'error')
            return redirect(url_for('manage_departments'))
        existing = Department.query.filter(func.lower(Department.name) == name.lower()).first()
        if existing:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': False, 'error': f'Department "{name}" already exists.'}), 400
            flash(f'Department "{name}" already exists.', 'error')
            return redirect(url_for('manage_departments'))
        try:
            dept = Department(name=name)
            db.session.add(dept)
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': True, 'id': dept.id, 'name': dept.name})
            flash(f'Department "{name}" added.', 'success')
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500
            flash('Error adding department. Please try again.', 'error')
        return redirect(url_for('manage_departments'))

    @app.route('/admin/departments/<int:department_id>/delete', methods=['POST'])
    @admin_required
    def delete_department(department_id):
        """Delete a department if no new hires reference it."""
        dept = Department.query.get(department_id)
        if not dept:
            flash('Department not found.', 'error')
            return redirect(url_for('manage_departments'))
        nh_count = NewHire.query.filter_by(department_id=department_id).count()
        if nh_count > 0:
            flash(f'Cannot delete "{dept.name}": {nh_count} new hire(s) still use it. Change their department first.', 'error')
            return redirect(url_for('manage_departments'))
        try:
            db.session.delete(dept)
            db.session.commit()
            flash(f'Department "{dept.name}" deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting department. Please try again.', 'error')
        return redirect(url_for('manage_departments'))



    @app.route('/admin/assign-admin', methods=['POST'])
    @admin_required
    def assign_admin():
        """Assign admin role to a user"""
        username = request.form.get('username', '').strip()

        if not username:
            flash('Username is required.', 'error')
            return redirect(url_for('manage_users'))

        # Find user by username
        user = UserModel.query.filter_by(username=username).first()

        if not user:
            # Create new user if doesn't exist
            user = UserModel(
                username=username,
                role='admin'
            )
            db.session.add(user)
            flash(f'User {username} created and assigned admin role.', 'success')
        else:
            user.role = 'admin'
            flash(f'Admin role assigned to {username}.', 'success')

        db.session.commit()
        return redirect(url_for('manage_users'))

    @app.route('/admin/remove-admin', methods=['POST'])
    @admin_required
    def remove_admin():
        """Remove admin role from a user"""
        user_id = request.form.get('user_id')

        if not user_id:
            flash('User ID is required.', 'error')
            return redirect(url_for('manage_users'))

        user = UserModel.query.get(user_id)

        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_users'))

        if user.username == current_user.username:
            flash('You cannot remove your own admin role.', 'error')
            return redirect(url_for('manage_users'))

        user.role = 'user'
        db.session.commit()
        flash(f'Admin role removed from {user.username}.', 'success')
        return redirect(url_for('manage_users'))

    @app.route('/admin/manage-admins/add', methods=['POST'])
    @admin_required
    def manage_admins_add():
        """Add a new admin user"""
        username = (request.form.get('username') or '').strip()
        email = normalize_email(request.form.get('email'))
        password = (request.form.get('password') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()

        if not username:
            flash('Username is required.', 'error')
            return redirect(url_for('manage_admins'))
        if not password or len(password) < 6:
            flash('Password is required and must be at least 6 characters.', 'error')
            return redirect(url_for('manage_admins'))

        existing = UserModel.query.filter_by(username=username).first()
        if existing:
            flash(f'User "{username}" already exists. Use Edit or Make Admin from Manage Users.', 'error')
            return redirect(url_for('manage_admins'))
        if email_in_use_by_other_user(email):
            flash(f'Email "{email}" is already in use by another account.', 'error')
            return redirect(url_for('manage_admins'))

        try:
            user = UserModel(
                username=username,
                email=email or None,
                full_name=full_name or None,
                password_hash=generate_password_hash(password),
                role='admin'
            )
            db.session.add(user)
            db.session.commit()
            flash(f'Admin "{username}" added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding admin. Please try again.', 'error')
        return redirect(url_for('manage_admins'))

    @app.route('/admin/manage-admins/<int:user_id>/update', methods=['POST'])
    @admin_required
    def manage_admins_update(user_id):
        """Update admin email and full name"""
        user = UserModel.query.get(user_id)
        if not user or user.role != 'admin':
            flash('Admin not found.', 'error')
            return redirect(url_for('manage_admins'))

        email = normalize_email(request.form.get('email'))
        full_name = (request.form.get('full_name') or '').strip()
        current_email = normalize_email(getattr(user, 'email', None))
        if email != current_email:
            flash('Email is locked after account creation. Use username/password reset only.', 'error')
            return redirect(url_for('manage_admins'))
        user.full_name = full_name or None
        try:
            db.session.commit()
            flash(f'Admin "{user.username}" updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating. Please try again.', 'error')
        return redirect(url_for('manage_admins'))

    @app.route('/admin/manage-admins/<int:user_id>/change-password', methods=['POST'])
    @admin_required
    def manage_admins_change_password(user_id):
        """Change an admin's password"""
        user = UserModel.query.get(user_id)
        if not user or user.role != 'admin':
            flash('Admin not found.', 'error')
            return redirect(url_for('manage_admins'))

        new_password = (request.form.get('new_password') or '').strip()
        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('manage_admins'))

        user.password_hash = generate_password_hash(new_password)
        try:
            db.session.commit()
            flash(f'Password updated for "{user.username}".', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating password. Please try again.', 'error')
        return redirect(url_for('manage_admins'))

    @app.route('/admin/manage-admins/<int:user_id>/remove', methods=['POST'])
    @admin_required
    def manage_admins_remove(user_id):
        """Remove admin role from user (they become a regular user)"""
        user = UserModel.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('manage_admins'))
        if user.username == current_user.username:
            flash('You cannot remove your own admin role.', 'error')
            return redirect(url_for('manage_admins'))

        user.role = 'user'
        try:
            db.session.commit()
            flash(f'Admin role removed from "{user.username}".', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error. Please try again.', 'error')
        return redirect(url_for('manage_admins'))

    @app.route('/admin/tasks/<int:task_id>/remove', methods=['POST'])
    @admin_required
    def remove_user_task(task_id):
        """Remove a required task for a user (admin only)."""
        task = UserTask.query.get(task_id)
        if not task:
            flash('Task not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        username = task.username
        task_title = task.task_title
        try:
            db.session.delete(task)
            db.session.commit()
            flash(f'Task "{task_title}" has been removed for {username}.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.exception('remove_user_task failed')
            flash('Could not remove task. Please try again.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))



    @app.route('/admin/new-hire/<username>/nudge-task/<int:task_id>', methods=['POST'])
    @login_required
    def nudge_user_task(username, task_id):
        """Send an email nudge to the user reminding them to complete the task. Admin or manager (store) only. Only for pending tasks."""
        if not main._manager_can_act_on_new_hire(username):
            flash('You do not have permission to nudge this user.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(main.staff_console_home_url())
        task = UserTask.query.filter_by(id=task_id, username=username).first()
        if not task:
            flash('Task not found.', 'error')
            return main.redirect_new_hire_details(username)
        if task.status == 'completed':
            flash('Cannot nudge a completed task.', 'info')
            return main.redirect_new_hire_details(username)
        # Get user email: NewHire first, then User
        to_email = None
        new_hire = NewHire.query.filter_by(username=username).first()
        if new_hire and getattr(new_hire, 'email', None) and str(new_hire.email).strip():
            to_email = str(new_hire.email).strip()
        if not to_email:
            user_record = UserModel.query.filter_by(username=username).first()
            if user_record and getattr(user_record, 'email', None) and str(user_record.email).strip():
                to_email = str(user_record.email).strip()
        if not to_email:
            flash(f'No email address for {username}. Cannot send nudge.', 'error')
            return main.redirect_new_hire_details(username)
        task_title = task.task_title or 'Your assigned task'
        subject = f'Reminder: Complete your onboarding task – {task_title}'
        tasks_link = main.onboarding_tasks_url()
        body_html = f'''
        <p>Hello,</p>
        <p>This is a reminder that the following task <strong>needs to be completed to continue onboarding</strong>:</p>
        <p><strong>{task_title}</strong></p>
        <p>Please log in to the onboarding portal and complete this task at your earliest convenience.</p>
        <p><a href="{tasks_link}">Open your onboarding tasks</a></p>
        <p>If the button does not work, copy and paste this link into your browser:<br>{tasks_link}</p>
        <p>Thank you,<br>Onboarding Team</p>
        '''
        body_text = (
            "Hello,\n\n"
            "This is a reminder that the following task needs to be completed to continue onboarding:\n"
            f"{task_title}\n\n"
            "Open your onboarding tasks here:\n"
            f"{tasks_link}\n\n"
            "Thank you,\n"
            "Onboarding Team"
        )
        if main.send_email(to_email, subject, body_html, body_text=body_text):
            flash(f'Nudge email sent to {to_email} for task "{task_title}".', 'success')
        else:
            flash('Email could not be sent. Check mail configuration.', 'error')
        return main.redirect_new_hire_details(username)



    @app.route('/admin/new-hire/<username>/update', methods=['POST'])
    @login_required
    def update_new_hire_details(username):
        """Update new hire details. Managers can only update new hires at their store."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('New hire not found.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(main.staff_console_home_url())
        if not main._manager_can_act_on_new_hire(username):
            flash('You can only update new hires at your store.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(url_for('view_all_new_hires', staff_console='admin'))

        try:
            store_raw = (request.form.get('store_id') or '').strip()
            new_store_id = None
            if store_raw.isdigit():
                sid_int = int(store_raw)
                if Store.query.get(sid_int):
                    new_store_id = sid_int
            if not current_user.is_admin() or main.uses_manager_console_scope():
                mgr_sid = main.get_current_user_store_id()
                if mgr_sid is not None and new_store_id is not None and new_store_id != mgr_sid:
                    flash('Managers can only assign this employee to their own store or leave store unset.', 'error')
                    return main.redirect_new_hire_details(username)

            # Update first name and last name (required on model; keep existing if blank)
            first_name = request.form.get('first_name', '').strip() or (new_hire.first_name or '')
            last_name = request.form.get('last_name', '').strip() or (new_hire.last_name or '')
            if first_name:
                new_hire.first_name = first_name
            if last_name:
                new_hire.last_name = last_name

            # Email is immutable after account creation.
            submitted_email = normalize_email(request.form.get('email'))
            current_new_hire_email = normalize_email(getattr(new_hire, 'email', None))
            if submitted_email != current_new_hire_email:
                flash('Email is locked after account creation. Use password reset for access issues.', 'error')
                return main.redirect_new_hire_details(username)

            # Update department
            dept_id, dept_name = resolve_department_from_form(request.form.get('department_id', ''))
            new_hire.department_id = dept_id
            new_hire.department = dept_name

            # Update position/title (role_id dropdown)
            role_id_raw = (request.form.get('role_id') or '').strip()
            new_role_id = None
            if role_id_raw.isdigit():
                try:
                    cand = int(role_id_raw)
                    if Role.query.get(cand) is not None:
                        new_role_id = cand
                except (ValueError, TypeError):
                    pass
            if hasattr(NewHire, 'role_id'):
                new_hire.role_id = new_role_id

            # Update start date
            start_date_str = request.form.get('start_date', '').strip()
            if start_date_str:
                try:
                    from datetime import datetime
                    new_hire.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                new_hire.start_date = None

            # Update status
            status = request.form.get('status', 'pending').strip()
            allowed_statuses = ['pending', 'active', 'completed']
            if not main.uses_manager_console_scope():
                allowed_statuses.append('removed')
            if status in allowed_statuses:
                new_hire.status = status

            if main.uses_manager_console_scope():
                mgr_sid = main.get_current_user_store_id()
                if mgr_sid is not None:
                    new_store_id = mgr_sid
            new_hire.store_id = new_store_id
            user_row = UserModel.query.filter_by(username=username).first()
            if user_row is not None:
                user_row.store_id = new_store_id

            db.session.commit()
            flash('New hire details updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating new hire details. Please try again.', 'error')

        return main.redirect_new_hire_details(username)

    @app.route('/admin/new-hire/<username>/cancel-access', methods=['POST'])
    @login_required
    def new_hire_cancel_access(username):
        """Cancel (revoke) access for this new hire so they can no longer log in. Managers can only for their store."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        if not main._manager_can_act_on_new_hire(username):
            flash('You can only revoke access for new hires at your store.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(url_for('view_all_new_hires', staff_console='admin'))
        user = UserModel.query.filter_by(username=username).first()
        if not user:
            flash('No login account found for this user.', 'error')
            return main.redirect_new_hire_details(username)
        if getattr(user, 'role', None) == 'admin':
            flash('Cannot cancel access for an admin.', 'error')
            return main.redirect_new_hire_details(username)
        if user.username == current_user.username:
            flash('You cannot revoke your own access.', 'error')
            return main.redirect_new_hire_details(username)
        from datetime import date
        _already = _access_revoke_calendar_date(getattr(user, 'access_revoked_at', None))
        if _already is not None and date.today() >= _already:
            flash('Access is already cancelled for this user. Use Restore access if you want them to log in again.', 'info')
            return main.redirect_new_hire_details(username)
        try:
            user.access_revoked_at = date.today()
            db.session.commit()
            flash(f'Access cancelled for {username}. They can no longer log in. Use "Restore access" to allow login again.', 'success')
        except Exception as e:
            db.session.rollback()
            err_str = (str(e) or '').lower()
            if 'access_revoked_at' in err_str or 'invalid column' in err_str:
                try:
                    db.session.execute(text("ALTER TABLE users ADD access_revoked_at DATE NULL"))
                    db.session.commit()
                    user.access_revoked_at = date.today()
                    db.session.commit()
                    flash(f'Access cancelled for {username}. They can no longer log in.', 'success')
                except Exception:
                    db.session.rollback()
                    flash('Error. Please try again.', 'error')
            else:
                flash('Error. Please try again.', 'error')
        return main.redirect_new_hire_details(username)

    @app.route('/admin/new-hire/<username>/restore-access', methods=['POST'])
    @login_required
    def new_hire_restore_access(username):
        """Restore access for this new hire so they can log in again. Managers can only for their store."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        if not main._manager_can_act_on_new_hire(username):
            flash('You can only restore access for new hires at your store.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(url_for('view_all_new_hires', staff_console='admin'))
        user = UserModel.query.filter_by(username=username).first()
        if not user:
            flash('No login account found for this user.', 'error')
            return main.redirect_new_hire_details(username)
        try:
            user.access_revoked_at = None
            db.session.commit()
            flash(f'Access restored for {username}. They can log in again.', 'success')
        except Exception as e:
            db.session.rollback()
            err_str = (str(e) or '').lower()
            if 'access_revoked_at' in err_str or 'invalid column' in err_str:
                try:
                    db.session.execute(text("ALTER TABLE users ADD access_revoked_at DATE NULL"))
                    db.session.commit()
                    user.access_revoked_at = None
                    db.session.commit()
                    flash(f'Access restored for {username}.', 'success')
                except Exception:
                    db.session.rollback()
                    flash('Error. Please try again.', 'error')
            else:
                flash('Error. Please try again.', 'error')
        return main.redirect_new_hire_details(username)

    @app.route('/admin/checklist/add', methods=['POST'])
    @admin_required
    def add_checklist_item():
        """Add a new checklist item"""
        task_name = request.form.get('task_name', '').strip()
        description = request.form.get('description', '').strip() or None
        assigned_to = request.form.get('assigned_to', '').strip() or None
        order = int(request.form.get('order', 0) or 0)
        is_active = request.form.get('is_active') == '1'

        if not task_name:
            flash('Task name is required.', 'error')
            return redirect(url_for('manage_checklist'))

        try:
            item = ChecklistItem(
                task_name=task_name,
                description=description,
                assigned_to=assigned_to,
                order=order,
                is_active=is_active,
                created_by=current_user.username
            )
            db.session.add(item)
            db.session.commit()
            flash(f'Checklist item "{task_name}" added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding checklist item. Please try again.', 'error')

        return redirect(url_for('manage_checklist'))



    @app.route('/admin/checklist/<int:item_id>/update', methods=['POST'])
    @admin_required
    def update_checklist_item(item_id):
        """Update a checklist item"""
        item = ChecklistItem.query.get(item_id)

        if not item:
            flash('Checklist item not found.', 'error')
            return redirect(url_for('manage_checklist'))

        task_name = request.form.get('task_name', '').strip()
        description = request.form.get('description', '').strip() or None
        assigned_to = request.form.get('assigned_to', '').strip() or None
        order = int(request.form.get('order', 0) or 0)
        is_active = request.form.get('is_active') == '1'

        if not task_name:
            flash('Task name is required.', 'error')
            return redirect(url_for('edit_checklist_item', item_id=item_id))

        try:
            item.task_name = task_name
            item.description = description
            item.assigned_to = assigned_to
            item.order = order
            item.is_active = is_active
            item.updated_at = datetime.utcnow()

            db.session.commit()
            flash(f'Checklist item "{task_name}" updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating checklist item. Please try again.', 'error')

        return redirect(url_for('manage_checklist'))

    @app.route('/admin/checklist/delete', methods=['POST'])
    @admin_required
    def delete_checklist_item():
        """Delete a checklist item"""
        item_id = request.form.get('item_id')

        if not item_id:
            flash('Item ID is required.', 'error')
            return redirect(url_for('manage_checklist'))

        item = ChecklistItem.query.get(item_id)
        if not item:
            flash('Checklist item not found.', 'error')
            return redirect(url_for('manage_checklist'))

        try:
            db.session.delete(item)
            db.session.commit()
            flash(f'Checklist item "{item.task_name}" deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting checklist item. Please try again.', 'error')

        return redirect(url_for('manage_checklist'))

    @app.route('/admin/checklist/move', methods=['POST'])
    @admin_required
    def move_checklist_item():
        """Move a checklist item up or down in order"""
        item_id = request.form.get('item_id')
        direction = request.form.get('direction')  # 'up' or 'down'

        if not item_id or not direction:
            flash('Invalid request.', 'error')
            return redirect(url_for('manage_checklist'))

        item = ChecklistItem.query.get(item_id)
        if not item:
            flash('Checklist item not found.', 'error')
            return redirect(url_for('manage_checklist'))

        try:
            if direction == 'up':
                # Find item with order one less
                prev_item = ChecklistItem.query.filter(
                    ChecklistItem.order < item.order
                ).order_by(ChecklistItem.order.desc()).first()

                if prev_item:
                    # Swap orders
                    temp_order = item.order
                    item.order = prev_item.order
                    prev_item.order = temp_order
            else:  # down
                # Find item with order one more
                next_item = ChecklistItem.query.filter(
                    ChecklistItem.order > item.order
                ).order_by(ChecklistItem.order).first()

                if next_item:
                    # Swap orders
                    temp_order = item.order
                    item.order = next_item.order
                    next_item.order = temp_order

            db.session.commit()
            flash('Checklist item order updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating order. Please try again.', 'error')

        return redirect(url_for('manage_checklist'))

    @app.route('/admin/checklist/update-completion', methods=['POST'])
    @admin_required
    def update_checklist_completion():
        """Update checklist completion status"""
        completed_items = request.form.getlist('completed_items')

        # For now, we'll just acknowledge the save
        # In the future, this could be stored in the database per new hire
        flash(f'Checklist status saved. {len(completed_items)} items marked as completed.', 'success')

        return redirect(url_for('view_checklist'))

    @app.route('/admin/sync-new-hires', methods=['POST'])
    @login_required
    def sync_new_hires_from_users():
        """Create missing NewHire records for Users so they appear on the checklist list. Admin only."""
        if not current_user.is_admin():
            abort(403)
        created = 0
        restored = 0
        default_store_id = None
        try:
            first_store = Store.query.first()
            if first_store:
                default_store_id = first_store.id
        except Exception:
            pass
        for user in UserModel.query.filter(UserModel.role == 'user').all():
            nh = NewHire.query.filter_by(username=user.username).first()
            if nh:
                if nh.status != 'removed':
                    continue
                nh.status = 'pending'
                nh.email = getattr(user, 'email', None) or nh.email
                if hasattr(user, 'full_name') and user.full_name:
                    parts = (user.full_name or '').strip().split(None, 1)
                    nh.first_name = parts[0] or nh.first_name
                    nh.last_name = (parts[1] if len(parts) > 1 else '') or nh.last_name
                if getattr(nh, 'store_id', None) is None and default_store_id is not None:
                    nh.store_id = default_store_id
                restored += 1
                continue
            full = (getattr(user, 'full_name', None) or '').strip() or user.username
            parts = full.split(None, 1)
            first = parts[0] or user.username
            last = (parts[1] if len(parts) > 1 else '') or ''
            email = getattr(user, 'email', None) or f'{user.username}@example.com'
            store_id = getattr(user, 'store_id', None)
            if store_id is None:
                store_id = default_store_id
            db.session.add(NewHire(
                username=user.username,
                first_name=first,
                last_name=last,
                email=email,
                status='pending',
                created_by=current_user.username,
                store_id=store_id,
            ))
            created += 1
        if created or restored:
            db.session.commit()
            flash(f'Synced new hires: {created} created, {restored} restored. User checklist list updated.', 'success')
        else:
            flash('All users already have a new hire record. No changes made.', 'info')
        return redirect(url_for('view_user_checklists'))



    @app.route('/admin/user-checklists/<username>/send-finale', methods=['POST'])
    @login_required
    def send_finale_message(username):
        """Save and send finale message to the new hire (shown on their dashboard). Managers only for their store."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_user_checklists') and not main.manager_has_permission('manage_checklist'):
            abort(403)
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('User not found.', 'error')
            return redirect(url_for('view_user_checklists'))
        # Managers can only send finale to new hires at their store (same as list)
        if current_user.is_manager():
            store_id = main.get_current_user_store_id()
            if store_id is None:
                flash('You can only send finale to new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))
            allowed = NewHire.query.filter(
                NewHire.status != 'removed',
                NewHire.store_id == store_id,
                NewHire.username == username
            ).first()
            if not allowed:
                flash('You can only send finale to new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))
        message = (request.form.get('finale_message') or '').strip()
        if not message:
            flash('Please enter a message.', 'error')
            return redirect(url_for('view_user_checklist', username=username))
        doc_id = request.form.get('finale_document_id', '').strip()
        new_hire.finale_message = message
        new_hire.finale_message_sent_at = datetime.utcnow()
        new_hire.finale_document_id = int(doc_id) if doc_id and doc_id.isdigit() else None
        new_hire.finale_message_dismissed_at = None  # so user sees it again

        try:
            db.session.commit()
            flash(f'Finale message sent to {new_hire.first_name} {new_hire.last_name}. They will see it on their next visit.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error saving message. Please try again.', 'error')
            return redirect(url_for('view_user_checklist', username=username))

        # Optionally save as default for future finale messages (after commit so message send is not rolled back)
        if request.form.get('save_as_default'):
            try:
                doc_val = doc_id if doc_id and doc_id.isdigit() else ''
                main.set_admin_setting('default_finale_message', message)
                main.set_admin_setting('default_finale_document_id', doc_val)
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash('Message was sent, but saving as default failed. You can set a default again next time.', 'warning')
        return redirect(url_for('view_user_checklist', username=username))

    @app.route('/admin/user-checklists/<username>/update', methods=['POST'])
    @login_required
    def update_user_checklist(username):
        """Update checklist completion status for a specific user. Managers only for their store."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_user_checklists') and not main.manager_has_permission('manage_checklist'):
            abort(403)
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('User not found.', 'error')
            return redirect(url_for('view_user_checklists'))
        # Managers can only update checklists for new hires at their store (same as list)
        if current_user.is_manager():
            store_id = main.get_current_user_store_id()
            if store_id is None:
                flash('You can only update checklists for new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))
            allowed = NewHire.query.filter(
                NewHire.status != 'removed',
                NewHire.store_id == store_id,
                NewHire.username == username
            ).first()
            if not allowed:
                flash('You can only update checklists for new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))

        completed_item_ids = [int(id) for id in request.form.getlist('completed_items')]

        try:
            # Get all checklist items
            all_items = ChecklistItem.query.filter_by(is_active=True).all()

            # Update or create completion records
            for item in all_items:
                completion = NewHireChecklist.query.filter_by(
                    new_hire_id=new_hire.id,
                    checklist_item_id=item.id
                ).first()

                is_completed = item.id in completed_item_ids

                if is_completed:
                    if not completion:
                        # Create new completion record
                        completion = NewHireChecklist(
                            new_hire_id=new_hire.id,
                            checklist_item_id=item.id,
                            is_completed=True,
                            completed_by=current_user.username,
                            completed_at=datetime.utcnow()
                        )
                        db.session.add(completion)
                    elif not completion.is_completed:
                        # Update existing record
                        completion.is_completed = True
                        completion.completed_by = current_user.username
                        completion.completed_at = datetime.utcnow()
                else:
                    if completion and completion.is_completed:
                        # Mark as not completed
                        completion.is_completed = False
                        completion.completed_at = None

            db.session.commit()
            flash(f'Checklist updated successfully. {len(completed_item_ids)} items marked as completed.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating checklist. Please try again.', 'error')

        return redirect(url_for('view_user_checklist', username=username))

    @app.route('/admin/external-links/add', methods=['POST'])
    @admin_required
    def add_external_link():
        """Add a new external link"""
        title = request.form.get('title', '').strip()
        url = request.form.get('url', '').strip()
        description = request.form.get('description', '').strip() or None
        icon = request.form.get('icon', '🔗').strip() or '🔗'
        order = int(request.form.get('order', 0) or 0)

        if not title or not url:
            flash('Title and URL are required.', 'error')
            return redirect(url_for('manage_external_links'))

        image_filename = None
        # Handle cropped image (preferred) or regular image upload
        cropped_image_data = request.form.get('cropped_image', '').strip()

        if cropped_image_data:
            # Process cropped image (base64 data)
            try:
                from PIL import Image
                import base64
                from io import BytesIO

                # Remove data URL prefix if present
                if ',' in cropped_image_data:
                    cropped_image_data = cropped_image_data.split(',')[1]

                # Decode base64 image
                image_data = base64.b64decode(cropped_image_data)
                img = Image.open(BytesIO(image_data))

                # Convert to RGBA for processing
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                # Detect and remove background color (check corners for background color)
                width, height = img.size
                corner_pixels = [
                    img.getpixel((0, 0)),  # Top-left
                    img.getpixel((width-1, 0)),  # Top-right
                    img.getpixel((0, height-1)),  # Bottom-left
                    img.getpixel((width-1, height-1))  # Bottom-right
                ]

                # Find the most common corner color (likely the background)
                from collections import Counter
                corner_colors = [pixel[:3] for pixel in corner_pixels]  # Get RGB, ignore alpha
                bg_color = Counter(corner_colors).most_common(1)[0][0]

                # Create a mask for background pixels (with tolerance for slight variations)
                tolerance = 30  # Allow some variation in color matching
                data = img.getdata()
                new_data = []
                for item in data:
                    r, g, b, a = item
                    # Check if pixel matches background color (within tolerance)
                    if (abs(r - bg_color[0]) < tolerance and 
                        abs(g - bg_color[1]) < tolerance and 
                        abs(b - bg_color[2]) < tolerance):
                        # Make transparent
                        new_data.append((255, 255, 255, 0))
                    else:
                        # Keep original pixel
                        new_data.append(item)

                # Apply the mask
                img.putdata(new_data)

                # Create white background and paste image
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                img = background

                # Resize to square if needed (200x200)
                if img.size[0] != img.size[1]:
                    size = min(img.size)
                    img = img.crop((0, 0, size, size))
                img = img.resize((200, 200), Image.Resampling.LANCZOS)

                # Generate filename
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + 'cropped_logo.png'

                # Create quick_links folder if it doesn't exist
                quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                quick_links_folder.mkdir(exist_ok=True)

                # Save file
                file_path = quick_links_folder / filename
                img.save(str(file_path), 'PNG', optimize=True)
                image_filename = filename
            except Exception as e:
                print(f"Error processing cropped image: {e}")
                import traceback
                app.logger.exception('request failed')
                flash('Error processing cropped image. Please try again.', 'error')
                # Fall through to regular image upload
                cropped_image_data = None

        # Handle regular image upload if no cropped image (only if cropped_image is empty)
        if not image_filename and not cropped_image_data and 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Check if it's an allowed image type
                if image_file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg')):
                    # Secure the filename
                    original_filename = image_file.filename
                    filename = secure_filename(original_filename)

                    # Add timestamp to avoid conflicts
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                    filename = timestamp + filename

                    # Create quick_links folder if it doesn't exist
                    quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                    quick_links_folder.mkdir(exist_ok=True)

                    # Save file
                    file_path = quick_links_folder / filename
                    image_file.save(str(file_path))
                    image_filename = filename
                else:
                    flash('Invalid image format. Allowed: JPG, PNG, GIF, SVG', 'error')
                    return redirect(url_for('manage_external_links'))

        try:
            link = ExternalLink(
                title=title,
                url=url,
                description=description,
                icon=icon,
                image_filename=image_filename,
                order=order,
                is_active=True,
                created_by=current_user.username
            )
            db.session.add(link)
            db.session.commit()
            flash(f'External link "{title}" added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding link. Please try again.', 'error')

        return redirect(url_for('manage_external_links'))



    @app.route('/admin/external-links/<int:link_id>/update', methods=['POST'])
    @admin_required
    def update_external_link(link_id):
        """Update an external link"""
        link = ExternalLink.query.get(link_id)
        if not link:
            flash('Link not found.', 'error')
            return redirect(url_for('manage_external_links'))

        title = request.form.get('title', '').strip()
        url = request.form.get('url', '').strip()
        description = request.form.get('description', '').strip() or None
        icon = request.form.get('icon', '🔗').strip() or '🔗'
        order = int(request.form.get('order', 0) or 0)
        remove_image = request.form.get('remove_image') == '1'

        if not title or not url:
            flash('Title and URL are required.', 'error')
            return redirect(url_for('edit_external_link', link_id=link_id))

        # Handle image removal
        if remove_image and link.image_filename:
            try:
                quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                old_file_path = quick_links_folder / link.image_filename
                if old_file_path.exists():
                    old_file_path.unlink()
            except Exception as e:
                print(f"Error removing old image: {e}")
            link.image_filename = None

        # Handle cropped image (preferred) or regular image upload
        cropped_image_data = request.form.get('cropped_image', '').strip()

        if cropped_image_data:
            # Process cropped image (base64 data)
            try:
                from PIL import Image
                import base64
                from io import BytesIO

                # Remove old image if exists
                if link.image_filename:
                    try:
                        quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                        old_file_path = quick_links_folder / link.image_filename
                        if old_file_path.exists():
                            old_file_path.unlink()
                    except Exception as e:
                        print(f"Error removing old image: {e}")

                # Remove data URL prefix if present
                if ',' in cropped_image_data:
                    cropped_image_data = cropped_image_data.split(',')[1]

                # Decode base64 image
                image_data = base64.b64decode(cropped_image_data)
                img = Image.open(BytesIO(image_data))

                # Convert to RGBA for processing
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                # Detect and remove background color (check corners for background color)
                width, height = img.size
                corner_pixels = [
                    img.getpixel((0, 0)),  # Top-left
                    img.getpixel((width-1, 0)),  # Top-right
                    img.getpixel((0, height-1)),  # Bottom-left
                    img.getpixel((width-1, height-1))  # Bottom-right
                ]

                # Find the most common corner color (likely the background)
                from collections import Counter
                corner_colors = [pixel[:3] for pixel in corner_pixels]  # Get RGB, ignore alpha
                bg_color = Counter(corner_colors).most_common(1)[0][0]

                # Create a mask for background pixels (with tolerance for slight variations)
                tolerance = 30  # Allow some variation in color matching
                data = img.getdata()
                new_data = []
                for item in data:
                    r, g, b, a = item
                    # Check if pixel matches background color (within tolerance)
                    if (abs(r - bg_color[0]) < tolerance and 
                        abs(g - bg_color[1]) < tolerance and 
                        abs(b - bg_color[2]) < tolerance):
                        # Make transparent
                        new_data.append((255, 255, 255, 0))
                    else:
                        # Keep original pixel
                        new_data.append(item)

                # Apply the mask
                img.putdata(new_data)

                # Create white background and paste image
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                img = background

                # Resize to square if needed (200x200)
                if img.size[0] != img.size[1]:
                    size = min(img.size)
                    img = img.crop((0, 0, size, size))
                img = img.resize((200, 200), Image.Resampling.LANCZOS)

                # Generate filename
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + 'cropped_logo.png'

                # Create quick_links folder if it doesn't exist
                quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                quick_links_folder.mkdir(exist_ok=True)

                # Save file
                file_path = quick_links_folder / filename
                img.save(str(file_path), 'PNG', optimize=True)
                link.image_filename = filename
            except Exception as e:
                print(f"Error processing cropped image: {e}")
                import traceback
                app.logger.exception('request failed')
                flash('Error processing cropped image. Please try again.', 'error')
                # Fall through to regular image upload
                cropped_image_data = None

        # Handle regular image upload if no cropped image (only if cropped_image is empty)
        if not link.image_filename and not cropped_image_data and 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Check if it's an allowed image type
                if image_file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg')):
                    # Remove old image if exists
                    if link.image_filename:
                        try:
                            quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                            old_file_path = quick_links_folder / link.image_filename
                            if old_file_path.exists():
                                old_file_path.unlink()
                        except Exception as e:
                            print(f"Error removing old image: {e}")

                    # Secure the filename
                    original_filename = image_file.filename
                    filename = secure_filename(original_filename)

                    # Add timestamp to avoid conflicts
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                    filename = timestamp + filename

                    # Create quick_links folder if it doesn't exist
                    quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                    quick_links_folder.mkdir(exist_ok=True)

                    # Save file
                    file_path = quick_links_folder / filename
                    image_file.save(str(file_path))
                    link.image_filename = filename
                else:
                    flash('Invalid image format. Allowed: JPG, PNG, GIF, SVG', 'error')
                    return redirect(url_for('edit_external_link', link_id=link_id))

        try:
            link.title = title
            link.url = url
            link.description = description
            link.icon = icon
            link.order = order
            link.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f'External link "{title}" updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating link. Please try again.', 'error')

        return redirect(url_for('manage_external_links'))

    @app.route('/admin/external-links/<int:link_id>/toggle', methods=['POST'])
    @admin_required
    def toggle_external_link(link_id):
        """Toggle external link active status"""
        link = ExternalLink.query.get(link_id)
        if not link:
            flash('Link not found.', 'error')
            return redirect(url_for('manage_external_links'))

        try:
            link.is_active = not link.is_active
            link.updated_at = datetime.utcnow()
            db.session.commit()
            status = 'activated' if link.is_active else 'deactivated'
            flash(f'Link "{link.title}" {status} successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error toggling link. Please try again.', 'error')

        return redirect(url_for('manage_external_links'))

    @app.route('/admin/external-links/<int:link_id>/delete', methods=['POST'])
    @admin_required
    def delete_external_link(link_id):
        """Delete an external link"""
        link = ExternalLink.query.get(link_id)
        if not link:
            flash('Link not found.', 'error')
            return redirect(url_for('manage_external_links'))

        try:
            title = link.title
            # Delete associated image file if it exists
            if link.image_filename:
                try:
                    quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
                    image_path = quick_links_folder / link.image_filename
                    if image_path.exists():
                        image_path.unlink()
                except Exception as e:
                    print(f"Error deleting image file: {e}")

            db.session.delete(link)
            db.session.commit()
            flash(f'External link "{title}" deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting link. Please try again.', 'error')

        return redirect(url_for('manage_external_links'))

    @app.route('/admin/training/upload', methods=['POST'])
    @admin_required
    def upload_training_video():
        """Upload a training video"""
        if 'video_file' not in request.files:
            flash('No video file selected.', 'error')
            return redirect(url_for('manage_training'))

        file = request.files['video_file']
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip() or None
        passing_score = int(request.form.get('passing_score', 80) or 80)

        if file.filename == '':
            flash('No video file selected.', 'error')
            return redirect(url_for('manage_training'))

        if not title:
            flash('Video title is required.', 'error')
            return redirect(url_for('manage_training'))

        if not main.allowed_video_file(file.filename):
            flash('Video file type not allowed. Allowed: MP4, WebM, OGG, MOV, AVI', 'error')
            return redirect(url_for('manage_training'))

        try:
            # Secure the filename
            original_filename = file.filename
            filename = secure_filename(original_filename)

            # Add timestamp to avoid conflicts
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename

            # Save file
            upload_folder = app.config['VIDEO_UPLOAD_FOLDER']
            upload_folder.mkdir(parents=True, exist_ok=True)
            file_path = upload_folder / filename
            file.save(str(file_path))

            # Get file size
            file_size = file_path.stat().st_size

            # Create video record
            video = TrainingVideo(
                title=title,
                description=description,
                filename=filename,
                original_filename=original_filename,
                file_path=str(file_path),
                file_size=file_size,
                passing_score=passing_score,
                uploaded_by=current_user.username
            )

            db.session.add(video)
            db.session.commit()

            flash(f'Training video "{title}" uploaded successfully. Now add quiz questions.', 'success')
            return redirect(url_for('manage_video_quiz', video_id=video.id))
        except Exception as e:
            db.session.rollback()
            flash('Error uploading video. Please try again.', 'error')

        return redirect(url_for('manage_training'))

    @app.route('/admin/training/<int:video_id>/quiz/add', methods=['POST'])
    @admin_required
    def add_quiz_question(video_id):
        """Add a quiz question to a training video"""
        video = TrainingVideo.query.get(video_id)

        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('manage_training'))

        question_text = request.form.get('question_text', '').strip()
        question_type = request.form.get('question_type', 'mid')
        video_timestamp = request.form.get('video_timestamp')
        answer_texts = request.form.getlist('answer_text[]')
        correct_answer_index = int(request.form.get('correct_answer', 0) or 0)

        if not question_text or len(answer_texts) < 2:
            flash('Question text and at least 2 answers are required.', 'error')
            return redirect(url_for('manage_video_quiz', video_id=video_id))

        if question_type == 'mid' and not video_timestamp:
            flash('Video timestamp is required for mid-video questions.', 'error')
            return redirect(url_for('manage_video_quiz', video_id=video_id))

        try:
            # Create question
            question = QuizQuestion(
                video_id=video_id,
                question_text=question_text,
                question_type=question_type,
                video_timestamp=float(video_timestamp) if video_timestamp else None,
                order=len([q for q in video.questions if q.question_type == 'end']) if question_type == 'end' else 0
            )
            db.session.add(question)
            db.session.flush()  # Get question ID

            # Create answers
            for idx, answer_text in enumerate(answer_texts):
                if answer_text.strip():
                    answer = QuizAnswer(
                        question_id=question.id,
                        answer_text=answer_text.strip(),
                        is_correct=(idx == correct_answer_index),
                        order=idx
                    )
                    db.session.add(answer)

            db.session.commit()
            flash('Quiz question added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error adding question. Please try again.', 'error')

        return redirect(url_for('manage_video_quiz', video_id=video_id))

    @app.route('/admin/training/question/<int:question_id>/delete')
    @admin_required
    def delete_quiz_question(question_id):
        """Delete a quiz question"""
        question = QuizQuestion.query.get(question_id)

        if not question:
            flash('Question not found.', 'error')
            return redirect(url_for('manage_training'))

        video_id = question.video_id

        try:
            # Delete answers first
            QuizAnswer.query.filter_by(question_id=question_id).delete()
            # Delete question
            db.session.delete(question)
            db.session.commit()
            flash('Question deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting question. Please try again.', 'error')

        return redirect(url_for('manage_video_quiz', video_id=video_id))



    @app.route('/admin/training/<int:video_id>/update-stores', methods=['POST'])
    @admin_required
    def training_video_update_stores(video_id):
        """Update which stores can see a training video. Form: all=1 for all stores, or store_ids list."""
        video = TrainingVideo.query.get(video_id)
        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('manage_training'))
        try:
            _ensure_stores_and_store_id()
            db.session.execute(
                training_video_stores.delete().where(training_video_stores.c.video_id == video_id)
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
                    if Store.query.get(sid):
                        seen.add(sid)
                        db.session.execute(
                            training_video_stores.insert().values(video_id=video_id, store_id=sid)
                        )
            db.session.commit()
            flash(f'Store visibility updated for "{video.title}".', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating store visibility. Please try again.', 'error')
        return redirect(url_for('manage_training'))

    @app.route('/admin/training/toggle-active', methods=['POST'])
    @admin_required
    def toggle_training_video_active():
        """Hide or show a training video for users without deleting it."""
        video_id = request.form.get('video_id')
        if not video_id:
            flash('Video ID is required.', 'error')
            return redirect(url_for('manage_training'))

        video = TrainingVideo.query.get(video_id)
        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('manage_training'))

        try:
            video.is_active = not video.is_active
            db.session.commit()
            if video.is_active:
                flash(f'"{video.title}" is now visible to users.', 'success')
            else:
                flash(f'"{video.title}" is hidden from users. You can show it again anytime.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating video status. Please try again.', 'error')

        return redirect(url_for('manage_training'))

    @app.route('/admin/training/delete', methods=['POST'])
    @admin_required
    def delete_training_video():
        """Delete a training video"""
        video_id = request.form.get('video_id')

        if not video_id:
            flash('Video ID is required.', 'error')
            return redirect(url_for('manage_training'))

        video = TrainingVideo.query.get(video_id)

        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('manage_training'))

        try:
            title = video.title
            file_path = video.file_path

            _purge_training_video_dependencies(video_id)

            db.session.delete(video)
            db.session.commit()

            if file_path and os.path.exists(file_path):
                os.remove(file_path)

            flash(f'Training video "{title}" deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error deleting video. Please try again.', 'error')

        return redirect(url_for('manage_training'))

    @app.route('/training/<int:video_id>/video')
    @login_required
    def serve_training_video(video_id):
        """Serve training video file"""
        video = TrainingVideo.query.get(video_id)

        if not video:
            return "Video not found", 404

        # Check permissions
        if not video.is_active:
            return "Video not available", 403

        user_store_id = main.get_current_user_store_id()
        if not training_video_visible_to_store(video, user_store_id):
            return "Video not available for your store", 403

        if not os.path.exists(video.file_path):
            return "Video file not found", 404

        return send_file(video.file_path, mimetype='video/mp4', conditional=True)



    @app.route('/api/training/save-answer', methods=['POST'])
    @login_required
    def save_quiz_answer():
        """Save user's quiz answer"""
        data = request.json
        progress_id = data.get('progress_id')
        question_id = data.get('question_id')
        answer_id = data.get('answer_id')
        is_correct = data.get('is_correct', False)

        try:
            response = UserQuizResponse(
                progress_id=progress_id,
                question_id=question_id,
                answer_id=answer_id,
                is_correct=is_correct
            )
            db.session.add(response)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500

    @app.route('/api/training/update-watch-time', methods=['POST'])
    @login_required
    def update_watch_time():
        """Update user's watch time"""
        data = request.json
        progress_id = data.get('progress_id')
        time_watched = data.get('time_watched', 0)

        try:
            progress = UserTrainingProgress.query.get(progress_id)
            if progress and progress.username == current_user.username:
                progress.time_watched = max(progress.time_watched or 0, time_watched)
                progress.last_updated = datetime.utcnow()
                db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500

    @app.route('/api/training/save-score', methods=['POST'])
    @login_required
    def save_training_score():
        """Save final training score"""
        data = request.json
        progress_id = data.get('progress_id')
        score = data.get('score', 0)
        total_questions = data.get('total_questions', 0)
        correct_answers = data.get('correct_answers', 0)
        is_passed = data.get('is_passed', False)

        try:
            progress = UserTrainingProgress.query.get(progress_id)
            if progress and progress.username == current_user.username:
                progress.score = score
                progress.total_questions = total_questions
                progress.correct_answers = correct_answers
                progress.is_passed = is_passed
                progress.is_completed = True
                progress.completed_at = datetime.utcnow()
                progress.last_updated = datetime.utcnow()

                # If training is passed, mark corresponding task as completed
                if is_passed and progress.is_completed:
                    # Find the task for this training video
                    video_id = progress.video_id
                    task = UserTask.query.filter_by(
                        username=current_user.username,
                        task_type='training',
                        status='pending'
                    ).filter(UserTask.notes.like(f'video_id:{video_id}%')).first()

                    if task:
                        task.status = 'completed'
                        task.completed_at = datetime.utcnow()

                db.session.commit()
                if is_passed and progress.is_completed:
                    try:
                        maybe_send_all_tasks_completed_email(current_user.username)
                    except Exception as e:
                        app.logger.warning(f"All-tasks-completed email check failed: {e}")
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500

    @app.route('/api/notifications/count')
    @login_required
    def get_notification_count():
        """Get count of unread notifications for current user"""
        # Get required training videos
        user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
        incomplete_training = []
        if user_new_hire:
            required_videos = list(user_new_hire.required_training_videos)
            for video in required_videos:
                progress = UserTrainingProgress.query.filter_by(
                    username=current_user.username,
                    video_id=video.id,
                    is_completed=True,
                    is_passed=True
                ).first()
                if not progress:
                    # Check if notification is read
                    notification = UserNotification.query.filter_by(
                        username=current_user.username,
                        notification_type='training',
                        notification_id=str(video.id)
                    ).first()
                    if not notification or not notification.is_read:
                        incomplete_training.append(video)

        # Get incomplete user tasks
        all_user_tasks = UserTask.query.filter_by(username=current_user.username).all()
        incomplete_tasks = [t for t in all_user_tasks if t.status != 'completed']

        # Count unread notifications
        unread_count = 0

        for video in incomplete_training:
            notification = UserNotification.query.filter_by(
                username=current_user.username,
                notification_type='training',
                notification_id=str(video.id)
            ).first()
            if not notification or not notification.is_read:
                unread_count += 1

        for task in incomplete_tasks:
            notification = UserNotification.query.filter_by(
                username=current_user.username,
                notification_type='task',
                notification_id=str(task.id)
            ).first()
            if not notification or not notification.is_read:
                unread_count += 1

        return jsonify({'count': unread_count})

    @app.route('/api/notifications/mark-read', methods=['POST'])
    @login_required
    def mark_notification_read():
        """Mark a specific notification as read"""
        data = request.json
        notification_type = data.get('notification_type')
        notification_id = data.get('notification_id')

        try:
            notification = UserNotification.query.filter_by(
                username=current_user.username,
                notification_type=notification_type,
                notification_id=str(notification_id)
            ).first()

            if notification:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
            else:
                # Create new notification record
                notification = UserNotification(
                    username=current_user.username,
                    notification_type=notification_type,
                    notification_id=str(notification_id),
                    is_read=True,
                    read_at=datetime.utcnow()
                )
                db.session.add(notification)

            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500

    @app.route('/api/notifications/mark-all-read', methods=['POST'])
    @login_required
    def mark_all_notifications_read():
        """Mark all notifications as read for current user"""
        try:
            # Get all incomplete training videos
            user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
            if user_new_hire:
                required_videos = list(user_new_hire.required_training_videos)
                for video in required_videos:
                    progress = UserTrainingProgress.query.filter_by(
                        username=current_user.username,
                        video_id=video.id,
                        is_completed=True,
                        is_passed=True
                    ).first()
                    if not progress:
                        notification = UserNotification.query.filter_by(
                            username=current_user.username,
                            notification_type='training',
                            notification_id=str(video.id)
                        ).first()
                        if notification:
                            notification.is_read = True
                            notification.read_at = datetime.utcnow()
                        else:
                            notification = UserNotification(
                                username=current_user.username,
                                notification_type='training',
                                notification_id=str(video.id),
                                is_read=True,
                                read_at=datetime.utcnow()
                            )
                            db.session.add(notification)

            # Get all incomplete tasks
            all_user_tasks = UserTask.query.filter_by(username=current_user.username).all()
            incomplete_tasks = [t for t in all_user_tasks if t.status != 'completed']

            for task in incomplete_tasks:
                notification = UserNotification.query.filter_by(
                    username=current_user.username,
                    notification_type='task',
                    notification_id=str(task.id)
                ).first()
                if notification:
                    notification.is_read = True
                    notification.read_at = datetime.utcnow()
                else:
                    notification = UserNotification(
                        username=current_user.username,
                        notification_type='task',
                        notification_id=str(task.id),
                        is_read=True,
                        read_at=datetime.utcnow()
                    )
                    db.session.add(notification)

            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500

    @app.route('/admin/settings')
    @admin_required
    def settings_page():
        """Legacy URL — store management lives on Manage Stores."""
        return redirect(url_for('manage_stores'))

    @app.route('/admin/roles/<int:role_id>/documents', methods=['GET', 'POST'])
    @admin_required
    def role_default_documents(role_id):
        """Manage default documents for a role"""
        role = Role.query.get(role_id)
        if not role:
            flash('Position/Title not found.', 'error')
            return redirect(url_for('manage_roles'))
        # Assignable forms for this store (or all for admin) — includes Not in library
        store_id = main.staff_store_scope_id()
        documents = main.documents_assignable_to_store_query(
            store_id,
            base_filter=_document_has_assignable_fields_filter(),
        ).order_by(Document.original_filename).all()
        default_doc_ids = set(d.id for d in role.default_documents.all())
        if request.method == 'POST':
            selected = request.form.getlist('document_id')
            try:
                role.default_documents = []
                for doc_id in selected:
                    try:
                        doc = Document.query.get(int(doc_id))
                        if doc:
                            role.default_documents.append(doc)
                    except (ValueError, TypeError):
                        pass
                db.session.commit()
                flash(f'Default documents updated for "{role.name}".', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error. Please try again.', 'error')
            return redirect(url_for('manage_roles'))
        return render_template('admin/role_default_documents.html', role=role, documents=documents, default_doc_ids=default_doc_ids)

    @app.route('/admin/new-hire/<username>/remove-user', methods=['GET', 'POST'])
    @login_required
    def remove_new_hire_user(username):
        """GET: show confirmation. POST: remove new hire's user account. Managers can only for new hires at their store."""
        if not current_user.is_admin() and not current_user.is_manager():
            abort(403)
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('New hire not found.', 'error')
            return redirect(url_for('view_all_new_hires'))
        if not main._manager_can_act_on_new_hire(username):
            flash('You can only remove new hires at your store.', 'error')
            return redirect(url_for('view_all_new_hires'))
        if new_hire.status == 'removed':
            flash('This user has already been removed.', 'info')
            return redirect(url_for('view_all_new_hires'))
        user_record = UserModel.query.filter_by(username=username).first()
        if user_record and getattr(user_record, 'role', None) == 'admin':
            flash('Cannot remove an admin user.', 'error')
            return main.redirect_new_hire_details(username)

        if request.method == 'POST':
            try:
                if user_record:
                    db.session.delete(user_record)
                new_hire.status = 'removed'
                db.session.commit()
                flash(f'User removed. {new_hire.first_name} {new_hire.last_name} can no longer log in and has been removed from the active list.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error removing user. Please try again.', 'error')
            return redirect(main.manager_new_hires_list_url()) if main.uses_manager_new_hires_home() else redirect(url_for('view_all_new_hires', staff_console='admin'))

        # GET: show confirmation page
        no_account_msg = 'No login account exists for this new hire. You may still mark their record as removed.' if not user_record else ''
        return render_template('admin/remove_new_hire_user.html', new_hire=new_hire, username=username, no_account_msg=no_account_msg)

    @app.route('/admin/checklist/<int:item_id>/edit')
    @admin_required
    def edit_checklist_item(item_id):
        """Edit checklist item page"""
        item = ChecklistItem.query.get(item_id)

        if not item:
            flash('Checklist item not found.', 'error')
            return redirect(url_for('manage_checklist'))

        return render_template('admin/edit_checklist_item.html', item=item)

    @app.route('/admin/user-checklists/<username>')
    @login_required
    def view_user_checklist(username):
        """View and update checklist for a specific user. Managers can only access new hires at their store."""
        if not current_user.is_admin() and not main.manager_has_permission('manage_user_checklists') and not main.manager_has_permission('manage_checklist'):
            abort(403)
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('User not found.', 'error')
            return redirect(url_for('view_user_checklists'))
        # Managers can only access new hires that appear on their store's list (same filter as view_user_checklists)
        if current_user.is_manager():
            store_id = main.get_current_user_store_id()
            if store_id is None:
                flash('You can only view checklists for new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))
            allowed = NewHire.query.filter(
                NewHire.status != 'removed',
                NewHire.store_id == store_id,
                NewHire.username == username
            ).first()
            if not allowed:
                flash('You can only view checklists for new hires at your store.', 'error')
                return redirect(url_for('view_user_checklists'))

        # Get all active checklist items
        checklist_items = ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order, ChecklistItem.id).all()

        # Get completion status for this user
        user_completions = {}
        for completion in NewHireChecklist.query.filter_by(new_hire_id=new_hire.id).all():
            user_completions[completion.checklist_item_id] = completion

        # Documents for optional attachment to finale message
        documents = Document.query.order_by(Document.original_filename).all()

        # Default finale message (and optional document) for pre-filling the modal
        default_finale_message = main.get_admin_setting('default_finale_message', DEFAULT_FINALE_MESSAGE).strip()
        default_finale_document_id = main.get_admin_setting('default_finale_document_id', '').strip()

        return render_template('admin/view_user_checklist.html', new_hire=new_hire, checklist_items=checklist_items, user_completions=user_completions, username=username, documents=documents, default_finale_message=default_finale_message, default_finale_document_id=default_finale_document_id)

    @app.route('/admin/external-links/<int:link_id>/edit')
    @admin_required
    def edit_external_link(link_id):
        """Edit an external link"""
        link = ExternalLink.query.get(link_id)
        if not link:
            flash('Link not found.', 'error')
            return redirect(url_for('manage_external_links'))

        return render_template('admin/edit_external_link.html', link=link)



    @app.route('/admin/test-form')
    @admin_required
    def admin_test_form():
        """Upload a PDF to convert into a step-by-step digital form (admin test tool)."""
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        state = _test_form_wizard_state()
        resume_url = None
        if state and state.get('fields'):
            if state.get('completed'):
                resume_url = url_for('admin_test_form_review')
            else:
                resume_url = url_for('admin_test_form_fill')
        ai_configured = bool((os.getenv('OPENAI_API_KEY') or '').strip())
        return render_template('admin/test_form.html', resume_url=resume_url, ai_configured=ai_configured, pdf_wizard_available=PDF_WIZARD_FITZ_AVAILABLE)

    @app.route('/admin/test-form/analyze', methods=['POST'])
    @admin_required
    def admin_test_form_analyze():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        if not PDF_WIZARD_FITZ_AVAILABLE:
            flash('PyMuPDF is not installed on the server.', 'error')
            return redirect(url_for('admin_test_form'))
        f = request.files.get('pdf_file')
        if not f or not f.filename:
            flash('Please choose a PDF file.', 'error')
            return redirect(url_for('admin_test_form'))
        if not main.allowed_file(f.filename) or not f.filename.lower().endswith('.pdf'):
            flash('Only PDF files are supported.', 'error')
            return redirect(url_for('admin_test_form'))

        old_sid = session.get('test_form_wizard_id')
        if old_sid:
            delete_wizard_state(app.config['UPLOAD_FOLDER'], old_sid)

        sid = new_session_id()
        try:
            pdf_path, original_name = save_uploaded_pdf(app.config['UPLOAD_FOLDER'], f, sid)
            result = analyze_pdf(pdf_path)
            fields = result.get('fields') or []
            if not fields:
                delete_wizard_state(app.config['UPLOAD_FOLDER'], sid)
                flash(result.get('message') or 'No fields detected.', 'error')
                return redirect(url_for('admin_test_form'))

            state = {
                'session_id': sid,
                'original_name': original_name,
                'pdf_path': pdf_path,
                'source': result.get('source', ''),
                'message': result.get('message', ''),
                'ai_used': bool(result.get('ai_used')),
                'fields': fields,
                'values': {},
                'index': 0,
                'completed': False,
                'created_at': datetime.utcnow().isoformat() + 'Z',
            }
            _test_form_wizard_save(state)
            flash(result.get('message', f'Found {len(fields)} fields.'), 'success')
            return redirect(url_for('admin_test_form_fill'))
        except Exception as e:
            app.logger.exception('admin_test_form_analyze failed')
            delete_wizard_state(app.config['UPLOAD_FOLDER'], sid)
            flash('Could not analyze PDF. Please try again.', 'error')
            return redirect(url_for('admin_test_form'))

    @app.route('/admin/test-form/reset', methods=['POST'])
    @admin_required
    def admin_test_form_reset():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        sid = session.pop('test_form_wizard_id', None)
        if sid:
            delete_wizard_state(app.config['UPLOAD_FOLDER'], sid)
        flash('Test form cleared.', 'success')
        return redirect(url_for('admin_test_form'))

    @app.route('/admin/test-form/fill')
    @admin_required
    def admin_test_form_fill():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        state = _test_form_wizard_state()
        if not state or not state.get('fields'):
            flash('Upload a PDF first.', 'error')
            return redirect(url_for('admin_test_form'))
        if request.args.get('edit') == '1':
            state['completed'] = False
            state['index'] = 0
            _test_form_wizard_save(state)
        elif state.get('completed'):
            return redirect(url_for('admin_test_form_review'))

        fields = state['fields']
        idx = int(state.get('index') or 0)
        if idx >= len(fields):
            idx = len(fields) - 1
        field = fields[idx]
        values = state.get('values') or {}
        current_val = values.get(field['id'], '')
        is_last4 = _test_form_field_is_last4(field)
        last4_digits = _test_form_last4_digits(current_val) if is_last4 else ''
        is_signature = field.get('type') == 'signature'
        sig_b64_existing = test_form_signature_b64(current_val) if is_signature and is_test_form_signature_value(current_val) else ''

        return render_template('admin/test_form_fill.html', field=field,
            idx=idx,
            total=len(fields),
            progress_pct=int(100 * (idx + 1) / max(len(fields), 1)),
            current_val=current_val,
            doc_name=state.get('original_name', 'Form'),
            is_last4=is_last4,
            last4_digits=last4_digits,
            is_signature=is_signature,
            sig_b64_existing=sig_b64_existing,
            TEST_FORM_SIG_PREFIX=TEST_FORM_SIG_PREFIX,)

    @app.route('/admin/test-form/save-field', methods=['POST'])
    @admin_required
    def admin_test_form_save_field():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        state = _test_form_wizard_state()
        if not state:
            return redirect(url_for('admin_test_form'))
        field_id = (request.form.get('field_id') or '').strip()
        direction = (request.form.get('direction') or 'next').strip()
        value = (request.form.get('value') or '').strip()
        fields = state.get('fields') or []
        field_map = {f['id']: f for f in fields}
        if field_id not in field_map:
            flash('Invalid field.', 'error')
            return redirect(url_for('admin_test_form_fill'))

        fdef = field_map[field_id]
        if direction != 'back':
            if fdef.get('type') == 'checkbox':
                value = 'yes' if request.form.get('value') == 'yes' else ''
            elif _test_form_field_is_last4(fdef):
                value = normalize_last4_typed_value(value)
            elif fdef.get('type') == 'signature':
                value = normalize_test_form_signature_value(value)
            if direction != 'skip' and fdef.get('required') and not value:
                if fdef.get('type') == 'signature':
                    flash('Please draw your signature before continuing.', 'error')
                elif fdef.get('type') == 'choice':
                    flash('Please select one option.', 'error')
                elif _test_form_field_is_last4(fdef):
                    flash('Please enter the last 4 digits of your SSN (XXX-XX-####).', 'error')
                else:
                    flash('This field is required.', 'error')
                state['index'] = next(i for i, x in enumerate(fields) if x['id'] == field_id)
                _test_form_wizard_save(state)
                return redirect(url_for('admin_test_form_fill'))
            if direction != 'skip':
                state.setdefault('values', {})[field_id] = value
            elif field_id in state.get('values', {}):
                del state['values'][field_id]

        idx = next((i for i, x in enumerate(fields) if x['id'] == field_id), 0)
        if direction == 'back':
            state['index'] = max(0, idx - 1)
        elif direction == 'skip' or direction == 'next':
            if idx + 1 >= len(fields):
                state['completed'] = True
                state['index'] = idx
                _test_form_wizard_save(state)
                return redirect(url_for('admin_test_form_review'))
            state['index'] = idx + 1
        _test_form_wizard_save(state)
        return redirect(url_for('admin_test_form_fill'))

    @app.route('/admin/test-form/review')
    @admin_required
    def admin_test_form_review():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        state = _test_form_wizard_state()
        if not state or not state.get('fields'):
            return redirect(url_for('admin_test_form'))
        if not state.get('completed') and not (state.get('values')):
            return redirect(url_for('admin_test_form_fill'))

        fields = state['fields']
        values = state.get('values') or {}
        rows = []
        for f in fields:
            val = values.get(f['id'], '')
            sig_b64 = ''
            if f.get('type') == 'checkbox':
                val = 'Yes' if val else 'No'
            elif f.get('type') == 'signature' and is_test_form_signature_value(val):
                sig_b64 = test_form_signature_b64(val)
                val = 'Signed'
            rows.append({
                'label': f['label'],
                'value': val or '—',
                'page': f.get('page', 1),
                'sig_b64': sig_b64,
            })

        return render_template('admin/test_form_review.html', rows=rows,
            doc_name=state.get('original_name', 'Form'),
            detect_message=state.get('message', ''),)

    @app.route('/admin/test-form/download')
    @admin_required
    def admin_test_form_download():
        if not app.config.get('ENABLE_TEST_FORM_WIZARD'):
            flash('Test Form Wizard is disabled on this server.', 'error')
            return redirect(url_for('admin_dashboard'))
        state = _test_form_wizard_state()
        if not state or not state.get('pdf_path'):
            abort(404)
        state = _refresh_test_form_field_positions(state)
        try:
            pdf_bytes = build_filled_pdf(
                state['pdf_path'],
                state.get('fields') or [],
                state.get('values') or {},
            )
            name = (state.get('original_name') or 'form').rsplit('.', 1)[0] + '_filled.pdf'
            return send_file(
                BytesIO(pdf_bytes),
                mimetype='application/pdf',
                as_attachment=False,
                download_name=name,
            )
        except Exception as e:
            app.logger.exception('admin_test_form_download failed')
            flash('Could not build PDF. Please try again.', 'error')
            return redirect(url_for('admin_test_form_review'))

