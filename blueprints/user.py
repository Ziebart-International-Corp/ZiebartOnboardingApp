"""User portal routes migrated from app.py."""
from __future__ import annotations

from datetime import datetime

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, render_template_string,
    request, session, url_for,
)
from flask_login import current_user
from markupsafe import Markup

from auth import login_required
from models import (
    Document, DocumentAssignment, ExternalLink, NewHire, Role, TrainingVideo,
    User as UserModel, UserNotification, UserTask, UserTrainingProgress, db,
)


def register(app: Flask) -> None:
    """Register user portal routes (endpoint names unchanged)."""
    import app as main

    documents_for_user_files = main.documents_for_user_files
    document_fully_completed_for_user = main.document_fully_completed_for_user
    dashboard_onboarding_work = main.dashboard_onboarding_work
    get_visible_ordered_user_tasks = main.get_visible_ordered_user_tasks
    attach_training_video_ids_to_tasks = main.attach_training_video_ids_to_tasks
    _ensure_user_task_order_columns = main._ensure_user_task_order_columns
    maybe_apply_default_finale_message = main.maybe_apply_default_finale_message
    render_onboarding_message_html = main.render_onboarding_message_html
    user_sign_document_url = main.user_sign_document_url
    user_document_completed_view_url = main.user_document_completed_view_url
    user_document_completed_print_url = main.user_document_completed_print_url
    _completed_document_cards_for_user = main._completed_document_cards_for_user
    user_mobile_bottom_nav_markup = main.user_mobile_bottom_nav_markup
    _feedback_header_button_html = main._feedback_header_button_html
    maybe_send_all_tasks_completed_email = main.maybe_send_all_tasks_completed_email
    training_video_visible_to_store = main.training_video_visible_to_store

    @app.route('/welcome')
    @login_required
    def welcome():
        """Welcome page shown after login; user clicks Continue to go to dashboard."""
        from services.security import safe_redirect_url
        next_url = safe_redirect_url(request.args.get('next'), url_for('dashboard'))
        full_name = current_user.username
        try:
            nh = NewHire.query.filter_by(username=current_user.username).first()
            if nh:
                first = (nh.first_name or '').strip()
                last = (nh.last_name or '').strip()
                full_name = f"{first} {last}".strip() if last else (first or current_user.username)
                if not full_name:
                    full_name = current_user.username
        except Exception:
            pass
        user_record = UserModel.query.filter_by(username=current_user.username).first()
        if user_record and getattr(user_record, 'full_name', None) and (not full_name or full_name == current_user.username):
            full_name = (user_record.full_name or '').strip() or full_name
        welcome_headline, welcome_body = main.get_welcome_messages(full_name)
        welcome_body_html = main.render_onboarding_message_html(welcome_body)
        return render_template('user/welcome.html', full_name=full_name, next_url=next_url, welcome_headline=welcome_headline, welcome_body_html=welcome_body_html)

    @app.route('/profile')
    @login_required
    def profile():
        """User profile page showing name, position, email, and start date. Renders with safe defaults on error."""
        is_admin = current_user.is_admin() if current_user else False
        user_name = (current_user.username if current_user else 'User') or 'User'
        user_email = 'Not set'
        user_position = None
        user_start_date = None

        try:
            user_record = UserModel.query.filter_by(username=current_user.username).first()
            user_name = user_record.full_name if user_record and user_record.full_name else current_user.username
            user_email = user_record.email if user_record and user_record.email else 'Not set'

            user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
            if user_new_hire:
                _fn = (user_new_hire.first_name or '').strip()
                _ln = (user_new_hire.last_name or '').strip()
                user_name = f"{_fn} {_ln}".strip() or current_user.username
                if not user_email or user_email == 'Not set':
                    user_email = user_new_hire.email or 'Not set'
                user_position = None
                if getattr(user_new_hire, 'role_id', None):
                    try:
                        _role_obj = Role.query.get(user_new_hire.role_id)
                        user_position = _role_obj.name if _role_obj else None
                    except Exception:
                        user_position = None
                user_start_date = user_new_hire.start_date
            if not user_name:
                user_name = current_user.username
        except Exception as e:
            import traceback
            app.logger.error(f'Error in profile for {current_user.username if current_user else "unknown"}: {str(e)}')
            app.logger.error(traceback.format_exc())
            db.session.rollback()
            flash('Some profile information could not be loaded.', 'error')
            is_admin = current_user.is_admin() if current_user else False
            user_name = (current_user.username if current_user else 'User') or 'User'
            user_email = user_email or 'Not set'

        return render_template('user/profile.html', is_admin=is_admin, user_name=user_name, user_email=user_email,
             user_position=user_position, user_start_date=user_start_date)

    @app.route('/profile/signature', methods=['GET', 'POST'])
    @login_required
    def manage_signature():
        """Create/update a default reusable signature for current user."""
        user_record = UserModel.query.filter_by(username=current_user.username).first()
        if not user_record:
            flash('User profile not found.', 'error')
            return redirect(url_for('profile'))

        if request.method == 'POST':
            mode = (request.form.get('signature_mode') or '').strip().lower()
            signature_image = (request.form.get('signature_image') or '').strip()
            if signature_image.startswith('data:image'):
                signature_image = signature_image.split(',', 1)[1] if ',' in signature_image else signature_image

            if mode not in ('drawn', 'typed'):
                flash('Please choose how to create your signature.', 'error')
                return redirect(url_for('manage_signature'))
            if not signature_image:
                flash('Please provide a signature before saving.', 'error')
                return redirect(url_for('manage_signature'))

            try:
                user_record.saved_signature_image = signature_image
                user_record.saved_signature_kind = mode
                user_record.saved_signature_updated_at = datetime.utcnow()
                db.session.commit()
                flash('Default signature saved. You can now apply it intentionally on each document field.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error saving signature. Please try again.', 'error')
            return redirect(url_for('manage_signature'))

        if request.args.get('clear') == '1':
            try:
                user_record.saved_signature_image = None
                user_record.saved_signature_kind = None
                user_record.saved_signature_updated_at = None
                db.session.commit()
                flash('Saved signature removed.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error clearing signature. Please try again.', 'error')
            return redirect(url_for('manage_signature'))

        return render_template('user/signature.html', user_record=user_record)



    @app.route('/training')
    @login_required
    def list_training_videos():
        """List available training videos for users. Renders with empty list on error to avoid 500."""
        videos = []
        user_progress = {}
        is_admin = current_user.is_admin() if current_user else False
        user_first_name = (current_user.username if current_user else 'User') or 'User'
        user_full_name = (current_user.username if current_user else 'User') or 'User'

        try:
            user_store_id = main.get_current_user_store_id()
            videos = main.training_videos_visible_to_store_query(
                user_store_id,
                base_filter=(TrainingVideo.is_active == True),
            ).order_by(TrainingVideo.created_at.desc()).all()

            # Get user progress for each video
            for video in videos:
                progress = UserTrainingProgress.query.filter_by(
                    username=current_user.username,
                    video_id=video.id
                ).order_by(UserTrainingProgress.attempt_number.desc()).first()
                user_progress[video.id] = progress

            # Get user info for header (guard against None first/last name)
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
            import traceback
            app.logger.error(f'Error in list_training_videos for {current_user.username if current_user else "unknown"}: {str(e)}')
            app.logger.error(traceback.format_exc())
            db.session.rollback()
            flash('Unable to load training list. Showing available videos below.', 'error')
            videos = videos if videos else []
            user_progress = user_progress if user_progress else {}
            is_admin = current_user.is_admin() if current_user else False
            user_first_name = (current_user.username if current_user else 'User') or 'User'
            user_full_name = (current_user.username if current_user else 'User') or 'User'

        return render_template('user/training_list.html', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name, videos=videos, user_progress=user_progress)

    @app.route('/dashboard/dismiss-finale', methods=['POST'])
    @login_required
    def dismiss_finale_message():
        """Mark the current user's finale message as dismissed so it is no longer shown."""
        new_hire = NewHire.query.filter_by(username=current_user.username).first()
        if new_hire:
            new_hire.finale_message_dismissed_at = datetime.utcnow()
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return redirect(url_for('dashboard'))




    @app.route('/dashboard')
    @login_required
    def dashboard():
        """User dashboard"""
        try:
            is_admin = current_user.is_admin()

            # Get new hire record for current user (guard None first/last name)
            try:
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
                user_new_hire = None
                user_first_name = current_user.username
                user_full_name = current_user.username

            # Get required training videos for current user
            required_videos = []
            completed_required_videos = []

            if user_new_hire:
                try:
                    required_videos = list(user_new_hire.required_training_videos)
                    # Check which ones are completed
                    for video in required_videos:
                        try:
                            progress = UserTrainingProgress.query.filter_by(
                                username=current_user.username,
                                video_id=video.id,
                                is_completed=True,
                                is_passed=True
                            ).first()
                            if progress:
                                completed_required_videos.append(video.id)
                        except Exception as e:
                            # Skip this video if there's an error
                            continue
                except Exception as e:
                    # If there's an error getting videos, use empty list
                    required_videos = []

            # Ensure task order/dependency columns exist (for display_order, depends_on_task_id)
            try:
                _ensure_user_task_order_columns()
            except Exception:
                pass
            # Get user tasks assigned to current user
            try:
                all_user_tasks = UserTask.query.filter_by(username=current_user.username).all()
            except Exception as e:
                all_user_tasks = []

            # Check document tasks and update completion status
            for task in all_user_tasks:
                try:
                    if task.task_type == 'document' and task.document_id:
                        document = Document.query.get(task.document_id)
                        if document:
                            # Check if all document fields are complete: every non-checkbox field and one per checkbox group.
                            try:
                                all_complete = document_fully_completed_for_user(task.document_id, current_user.username)
                                if all_complete and task.status != 'completed':
                                    # Auto-complete the task
                                    task.status = 'completed'
                                    task.completed_at = datetime.utcnow()
                                    db.session.commit()

                                # Update assignment completion status
                                assignment = DocumentAssignment.query.filter_by(
                                    document_id=task.document_id,
                                    username=current_user.username
                                ).first()
                                if assignment:
                                    assignment.is_completed = all_complete
                                    if all_complete and not assignment.completed_at:
                                        assignment.completed_at = datetime.utcnow()
                                    db.session.commit()
                            except Exception as e:
                                # If checking document completion fails, skip this task
                                continue
                except Exception as e:
                    # If processing this task fails, skip it
                    continue

            # Re-query tasks so we have fresh objects (commit() above expires session objects;
            # using expired objects in template/notifications can cause 500 on "Back to Dashboard").
            try:
                all_user_tasks = UserTask.query.filter_by(username=current_user.username).all()
            except Exception as e:
                all_user_tasks = []
            # Actionable now: dependency unlocked. Upcoming: still blocked so Home matches total progress count.
            visible_ordered = get_visible_ordered_user_tasks(all_user_tasks)
            user_tasks = [t for t in visible_ordered if t.status != 'completed']
            attach_training_video_ids_to_tasks(user_tasks)
            incomplete_ids = {t.id for t in user_tasks}
            upcoming_tasks = [
                t for t in sorted(
                    all_user_tasks,
                    key=lambda x: (getattr(x, 'display_order', None) is None, getattr(x, 'display_order', 0) or 0, x.id or 0),
                )
                if t.status != 'completed' and t.id not in incomplete_ids
            ]
            attach_training_video_ids_to_tasks(upcoming_tasks)

            work = dashboard_onboarding_work(required_videos, all_user_tasks, completed_required_videos)
            incomplete_training = work['incomplete_standalone_training']
            total_tasks = work['total_tasks']
            completed_tasks = work['completed_tasks']
            progress_percentage = work['progress_percentage']

            # Check if all tasks are completed (include locked upcoming so progress denom matches Home)
            all_tasks_completed = (
                len(incomplete_training) == 0 and len(user_tasks) == 0 and len(upcoming_tasks) == 0
            ) if (required_videos or all_user_tasks) else False

            # Build notifications list
            notifications = []

            # Add incomplete training videos as notifications
            for video in incomplete_training:
                try:
                    # Check if user has viewed this notification
                    notification = UserNotification.query.filter_by(
                        username=current_user.username,
                        notification_type='training',
                        notification_id=str(video.id)
                    ).first()

                    if not notification or not notification.is_read:
                        notifications.append({
                            'type': 'training',
                            'id': video.id,
                            'title': video.title,
                            'message': f'Complete required training: {video.title}',
                            'url': url_for('view_training_video', video_id=video.id),
                            'is_read': notification.is_read if notification else False
                        })
                except Exception as e:
                    # Skip this notification if there's an error
                    continue

            # Add incomplete user tasks as notifications
            for task in user_tasks:
                try:
                    notification = UserNotification.query.filter_by(
                        username=current_user.username,
                        notification_type='task',
                        notification_id=str(task.id)
                    ).first()

                    if not notification or not notification.is_read:
                        task_url = main.user_sign_document_url(task.document_id) if (task.task_type == 'document' and task.document_id) else url_for('user_tasks')
                        notifications.append({
                            'type': 'task',
                            'id': task.id,
                            'title': task.task_title,
                            'message': task.task_description or f'Complete task: {task.task_title}',
                            'url': task_url,
                            'is_read': notification.is_read if notification else False
                        })
                except Exception as e:
                    # Skip this notification if there's an error
                    continue

            # Count unread notifications
            unread_count = len([n for n in notifications if not n['is_read']])
            pending_count = unread_count

            # Get training videos for the user's store (for the training videos section)
            try:
                _user_store_id = main.get_current_user_store_id()
                all_videos = main.training_videos_visible_to_store_query(
                    _user_store_id,
                    base_filter=(TrainingVideo.is_active == True),
                ).order_by(TrainingVideo.created_at.desc()).limit(6).all()
            except Exception as e:
                all_videos = []

            # Dashboard document preview: assigned + visible + store-scoped (same rules as Files tab)
            try:
                visible_documents, _ = documents_for_user_files(current_user.username)
                visible_documents = visible_documents[:3]
            except Exception:
                visible_documents = []

            # Get active external links for the dashboard
            try:
                external_links = ExternalLink.query.filter_by(is_active=True).order_by(ExternalLink.order, ExternalLink.created_at).all()
            except Exception as e:
                external_links = []

            # Optional hero animation: look in uploads/dashboard_hero/ for confetti.gif, hero.gif, etc.
            # For a sharper gold confetti: use a high-res GIF (e.g. from Freepik/Vecteezy) and replace confetti.gif in that folder.
            hero_media_url = None
            hero_media_type = None
            try:
                hero_dir = app.config['UPLOAD_FOLDER'] / 'dashboard_hero'
                if hero_dir.exists():
                    for f in ['adjusting confetti density for readability.gif', 'confetti.gif', 'hero.gif', 'animation.gif', 'hero.mp4', 'hero.webm', 'animation.mp4']:
                        p = hero_dir / f
                        if p.exists():
                            hero_media_url = url_for('serve_dashboard_hero', filename=f)
                            hero_media_type = 'video' if f.endswith(('.mp4', '.webm')) else 'gif'
                            break
            except Exception:
                pass

            # Finale message from admin (only when all work is done; tasks panel otherwise)
            show_finale = False
            finale_message = ''
            finale_message_html = Markup('')
            finale_document = None
            has_new_assigned_work = False
            if user_new_hire and all_tasks_completed:
                main.maybe_apply_default_finale_message(current_user.username)
                try:
                    db.session.refresh(user_new_hire)
                except Exception:
                    pass
            if user_new_hire:
                msg = getattr(user_new_hire, 'finale_message', None)
                sent_at = getattr(user_new_hire, 'finale_message_sent_at', None)
                dismissed_at = getattr(user_new_hire, 'finale_message_dismissed_at', None)
                if msg and sent_at:
                    finale_message = msg
                    finale_message_html = main.render_onboarding_message_html(msg)
                    doc_id = getattr(user_new_hire, 'finale_document_id', None)
                    if doc_id:
                        try:
                            finale_document = Document.query.get(int(doc_id))
                        except Exception:
                            finale_document = None
                show_finale = bool(
                    all_tasks_completed and msg and sent_at and not dismissed_at
                )
                has_new_assigned_work = bool(
                    sent_at and (incomplete_training or user_tasks)
                )

            return render_template('user/dashboard.html', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name,
             required_videos=required_videos, completed_required_videos=completed_required_videos,
             incomplete_training=incomplete_training, all_tasks_completed=all_tasks_completed,
             progress_percentage=progress_percentage, all_videos=all_videos, visible_documents=visible_documents,
             user_tasks=user_tasks, upcoming_tasks=upcoming_tasks, total_tasks=total_tasks, completed_tasks=completed_tasks,
             pending_count=pending_count, notifications=notifications, external_links=external_links,
             hero_media_url=hero_media_url, hero_media_type=hero_media_type,
             show_finale=show_finale, finale_message=finale_message, finale_message_html=finale_message_html, finale_document=finale_document,
             has_new_assigned_work=has_new_assigned_work)
        except Exception as e:
            # Log the error for debugging
            import traceback
            app.logger.error(f'Error in dashboard for {current_user.username if current_user else "unknown"}: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Set defaults to prevent template errors
            is_admin = current_user.is_admin() if current_user else False
            user_first_name = current_user.username if current_user else "User"
            user_full_name = current_user.username if current_user else "User"
            required_videos = []
            completed_required_videos = []
            incomplete_training = []
            all_tasks_completed = False
            progress_percentage = 0
            all_videos = []
            visible_documents = []
            user_tasks = []
            total_tasks = 0
            completed_tasks = 0
            pending_count = 0
            notifications = []
            external_links = []

            # Return a basic dashboard with error message
            app.logger.exception('Error loading dashboard')
            flash('Error loading dashboard. Some data may be missing.', 'error')

            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Dashboard - Onboarding App</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
                <style>
                    body { font-family: 'URW Form', Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                    .error-box { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                    .error-box strong { color: #856404; }
                {{ global_theme_css|safe }}
            </style>
            </head>
            <body>
                <div class="error-box">
                    <strong>⚠️ Dashboard Error</strong>
                    <p>There was an error loading your dashboard. Please refresh the page or contact support if the problem persists.</p>
                </div>
                <p><a href="{{ url_for('dashboard') }}">Refresh Dashboard</a></p>
            </body>
            </html>
            ''')



    @app.route('/tasks')
    @login_required
    def user_tasks():
        """User tasks page - shows tasks assigned to the current user. Tasks are ordered by display_order and only visible when their dependency is completed."""
        try:
            is_admin = current_user.is_admin()
            _ensure_user_task_order_columns()

            # Get tasks assigned to current user (order by display_order then priority/due_date)
            try:
                user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                    UserTask.display_order.asc(),
                    UserTask.priority.desc(),
                    UserTask.due_date.asc(),
                    UserTask.created_at.desc()
                ).all()
            except Exception as e:
                err_str = (str(e) or '').lower()
                if 'display_order' in err_str or 'invalid column' in err_str or 'unknown column' in err_str:
                    _ensure_user_task_order_columns()
                    user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                        UserTask.priority.desc(),
                        UserTask.due_date.asc(),
                        UserTask.created_at.desc()
                    ).all()
                else:
                    user_tasks = []

            # Get new hire record for current user
            try:
                user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
            except Exception as e:
                user_new_hire = None

            # Ensure tasks exist for incomplete training videos
            if user_new_hire:
                try:
                    required_videos = list(user_new_hire.required_training_videos)
                    for video in required_videos:
                        try:
                            # Check if video is completed
                            progress = UserTrainingProgress.query.filter_by(
                                username=current_user.username,
                                video_id=video.id,
                                is_completed=True,
                                is_passed=True
                            ).first()

                            # Only create task if video is not completed
                            if not progress:
                                # Check if task already exists for this video
                                existing_task = UserTask.query.filter_by(
                                    username=current_user.username,
                                    task_type='training',
                                    status='pending'
                                ).filter(UserTask.notes.like(f'video_id:{video.id}%')).first()

                                if not existing_task:
                                    # Create task for incomplete training video
                                    task = UserTask(
                                        username=current_user.username,
                                        task_title=f"Complete Training: {video.title}",
                                        task_description=f"Please watch and complete the training video: {video.title}",
                                        task_type='training',
                                        priority='normal',
                                        status='pending',
                                        assigned_by=user_new_hire.created_by or 'system',
                                        notes=f'video_id:{video.id}'
                                    )
                                    db.session.add(task)
                                    db.session.commit()
                        except Exception as e:
                            # Skip this video if there's an error
                            continue
                except Exception as e:
                    # If there's an error getting videos, continue without creating tasks
                    pass

            # Refresh tasks list after potential additions
            try:
                user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                    UserTask.display_order.asc(),
                    UserTask.priority.desc(),
                    UserTask.due_date.asc(),
                    UserTask.created_at.desc()
                ).all()
            except Exception as e:
                try:
                    user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                        UserTask.priority.desc(),
                        UserTask.due_date.asc(),
                        UserTask.created_at.desc()
                    ).all()
                except Exception:
                    user_tasks = []

            # Check document tasks and update completion status
            for task in user_tasks:
                try:
                    if task.task_type == 'document' and task.document_id:
                        try:
                            document = Document.query.get(task.document_id)
                            if document:
                                # Check if all document fields are complete: every non-checkbox field and one per checkbox group.
                                try:
                                    all_complete = document_fully_completed_for_user(task.document_id, current_user.username)
                                    if all_complete and task.status != 'completed':
                                        # Auto-complete the task
                                        task.status = 'completed'
                                        task.completed_at = datetime.utcnow()
                                        db.session.commit()

                                    # Update assignment completion status
                                    assignment = DocumentAssignment.query.filter_by(
                                        document_id=task.document_id,
                                        username=current_user.username
                                    ).first()
                                    if assignment:
                                        assignment.is_completed = all_complete
                                        if all_complete and not assignment.completed_at:
                                            assignment.completed_at = datetime.utcnow()
                                        db.session.commit()
                                except Exception as e:
                                    # If checking document completion fails, skip this task
                                    continue
                        except Exception as e:
                            # If getting document fails, skip this task
                            continue

                    # Check training video tasks and update completion status
                    elif task.task_type == 'training' and task.notes:
                        # Extract video_id from notes (format: "video_id:123")
                        if task.notes.startswith('video_id:'):
                            try:
                                video_id = int(task.notes.split(':')[1])
                                # Check if video is completed
                                progress = UserTrainingProgress.query.filter_by(
                                    username=current_user.username,
                                    video_id=video_id,
                                    is_completed=True,
                                    is_passed=True
                                ).first()

                                if progress and task.status != 'completed':
                                    # Auto-complete the task
                                    task.status = 'completed'
                                    task.completed_at = datetime.utcnow()
                                    db.session.commit()
                            except (ValueError, IndexError, Exception):
                                # Skip if there's an error parsing or querying
                                pass
                except Exception as e:
                    # If processing this task fails, skip it
                    continue

            # Re-query tasks so we have fresh objects (commit() above expires session objects)
            try:
                user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                    UserTask.display_order.asc(),
                    UserTask.priority.desc(),
                    UserTask.due_date.asc(),
                    UserTask.created_at.desc()
                ).all()
            except Exception as e:
                try:
                    user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                        UserTask.priority.desc(),
                        UserTask.due_date.asc(),
                        UserTask.created_at.desc()
                    ).all()
                except Exception:
                    user_tasks = []
            # Only show tasks that are visible (dependency satisfied); order by display_order so next task appears after previous is done
            user_tasks = get_visible_ordered_user_tasks(user_tasks)

            # Safe user display names (guard None first/last name from NewHire)
            try:
                if user_new_hire:
                    user_first_name = (user_new_hire.first_name or '').strip() or current_user.username
                    _ln = (user_new_hire.last_name or '').strip()
                    user_full_name = f"{user_first_name} {_ln}".strip() if _ln else (user_first_name or current_user.username)
                else:
                    user_first_name = current_user.username
                    user_full_name = current_user.username
            except Exception as e:
                user_first_name = current_user.username
                user_full_name = current_user.username
            if not user_first_name:
                user_first_name = current_user.username
            if not user_full_name:
                user_full_name = current_user.username

            # Count tasks by status
            pending_tasks = [t for t in user_tasks if t.status == 'pending']
            in_progress_tasks = [t for t in user_tasks if t.status == 'in_progress']
            completed_tasks = [t for t in user_tasks if t.status == 'completed']

            # Extract video_id from training tasks for easier template access
            for task in user_tasks:
                try:
                    if task.task_type == 'training' and task.notes and task.notes.startswith('video_id:'):
                        try:
                            task.video_id = int(task.notes.split(':')[1])
                        except (ValueError, IndexError):
                            task.video_id = None
                    else:
                        task.video_id = None
                except Exception as e:
                    task.video_id = None

            # Fallback: document tasks missing document_id - try to resolve from user's incomplete assignments
            try:
                doc_tasks_missing_id = [t for t in user_tasks if t.task_type == 'document' and not t.document_id]
                if doc_tasks_missing_id:
                    incomplete = DocumentAssignment.query.filter_by(
                        username=current_user.username, is_completed=False
                    ).all()
                    for task in doc_tasks_missing_id:
                        if task.document_id:
                            continue
                        # Match by task title: "Sign Document: handbook.pdf" or "Sign Document: Ziebart Handbook"
                        title_suffix = (task.task_title or '').split(':', 1)[-1].strip().lower()
                        title_key = title_suffix.replace('.pdf', '').strip() or title_suffix  # e.g. "handbook"
                        for a in incomplete:
                            doc = Document.query.get(a.document_id) if a.document_id else None
                            if not doc:
                                continue
                            doc_name = (getattr(doc, 'name_for_users', None) or doc.original_filename or '').lower()
                            doc_key = (doc.original_filename or '').lower().replace('.pdf', '').strip()
                            if (title_suffix in doc_name or (doc_name and doc_name in title_suffix) or
                                    (title_key and title_key in doc_name) or (doc_key and title_key in doc_key)):
                                task.document_id = a.document_id
                                break
                        if not task.document_id and len(incomplete) == 1:
                            task.document_id = incomplete[0].document_id
            except Exception:
                pass

            return render_template('user/tasks.html', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name,
             user_tasks=user_tasks, pending_tasks=pending_tasks, in_progress_tasks=in_progress_tasks, completed_tasks=completed_tasks)
        except Exception as e:
            # Log the error for debugging
            import traceback
            app.logger.error(f'Error in user_tasks for {current_user.username if current_user else "unknown"}: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Set defaults to prevent template errors
            is_admin = current_user.is_admin() if current_user else False
            user_first_name = current_user.username if current_user else "User"
            user_full_name = current_user.username if current_user else "User"
            user_tasks = []
            pending_tasks = []
            in_progress_tasks = []
            completed_tasks = []

            # Return a basic tasks page with error message
            app.logger.exception('Error loading tasks')
            flash('Error loading tasks. Some data may be missing.', 'error')

            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>My Tasks - Onboarding App</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
                <style>
                    body { font-family: 'URW Form', Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                    .error-box { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                    .error-box strong { color: #856404; }
                {{ global_theme_css|safe }}
            </style>
            </head>
            <body>
                <div class="error-box">
                    <strong>⚠️ Tasks Page Error</strong>
                    <p>There was an error loading your tasks. Please refresh the page or contact support if the problem persists.</p>
                </div>
                <p><a href="{{ url_for('user_tasks') }}">Refresh Tasks</a> | <a href="{{ url_for('dashboard') }}">Back to Dashboard</a></p>
            </body>
            </html>
            ''')



    @app.route('/training/<int:video_id>')
    @login_required
    def view_training_video(video_id):
        """View and take harassment training video with quizzes"""
        video = TrainingVideo.query.get(video_id)

        if not video:
            flash('Training video not found.', 'error')
            return redirect(url_for('dashboard'))

        if not video.is_active:
            flash('This training video is not active.', 'error')
            return redirect(url_for('dashboard'))

        user_store_id = main.get_current_user_store_id()
        if not training_video_visible_to_store(video, user_store_id):
            flash('This training video is not available for your store.', 'error')
            return redirect(url_for('list_training_videos'))

        # Get or create user progress
        progress = UserTrainingProgress.query.filter_by(
            username=current_user.username,
            video_id=video_id
        ).order_by(UserTrainingProgress.attempt_number.desc()).first()

        if not progress or progress.is_completed:
            # Create new attempt
            attempt_number = 1
            if progress:
                attempt_number = progress.attempt_number + 1

            progress = UserTrainingProgress(
                username=current_user.username,
                video_id=video_id,
                attempt_number=attempt_number
            )
            db.session.add(progress)
            db.session.commit()

        # Get questions ordered properly
        mid_questions = [q for q in video.questions if q.question_type == 'mid']
        mid_questions.sort(key=lambda x: x.video_timestamp or 0)
        end_questions = [q for q in video.questions if q.question_type == 'end']
        end_questions.sort(key=lambda x: x.order)

        return render_template('user/training_video.html', video=video, progress=progress, mid_questions=[q.to_dict() for q in mid_questions], 
             end_questions=[q.to_dict() for q in end_questions])

    @app.route('/tasks/<int:task_id>/complete', methods=['POST'])
    @login_required
    def complete_task(task_id):
        """Mark a task as completed"""
        task = UserTask.query.get_or_404(task_id)
        if task.username != current_user.username:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        task.status = 'completed'
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        db.session.commit()
        try:
            maybe_send_all_tasks_completed_email(current_user.username)
        except Exception as e:
            app.logger.warning(f"All-tasks-completed email check failed: {e}")
        return jsonify({'success': True})

    @app.route('/tasks/<int:task_id>/in-progress', methods=['POST'])
    @login_required
    def start_task(task_id):
        """Mark a task as in progress"""
        task = UserTask.query.get_or_404(task_id)
        if task.username != current_user.username:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        task.status = 'in_progress'
        task.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/user')
    @login_required
    def api_user():
        """Get current user info"""
        return jsonify({
            'username': current_user.username,
            'domain': current_user.domain,
            'role': current_user.role,
            'is_admin': current_user.is_admin(),
        })

