"""User task ordering, training task helpers, onboarding completion."""
from __future__ import annotations

from datetime import datetime

from flask import current_app

from models import NewHire, UserTask, UserTrainingProgress, db


def document_fully_completed_for_user(doc_id, username):
    from services.document_fields import document_fully_completed_for_user as _fn
    return _fn(doc_id, username)


def get_admin_setting(key, default=""):
    from services.onboarding_messages import get_admin_setting as _fn
    return _fn(key, default)


def send_email(to_email, subject, body_html, body_text=None):
    from services.mail import send_email as _fn
    return _fn(to_email, subject, body_html, body_text)


def render_onboarding_message_html(text, for_email=False):
    from services.onboarding_messages import render_onboarding_message_html as _fn
    return _fn(text, for_email=for_email)


def render_onboarding_message_plain(text):
    from services.onboarding_messages import render_onboarding_message_plain as _fn
    return _fn(text)


def apply_message_template(template, **replacements):
    from services.onboarding_messages import apply_message_template as _fn
    return _fn(template, **replacements)


def maybe_apply_default_finale_message(username):
    from services.onboarding_messages import maybe_apply_default_finale_message as _fn
    return _fn(username)


def get_email_for_username(username):
    import app as main
    return main.get_email_for_username(username)


def _ensure_new_hires_finale_columns():
    from db.migrations_runtime import _ensure_new_hires_finale_columns as _fn
    return _fn()


def _app_const(name):
    import app as main
    return getattr(main, name)

def get_visible_ordered_user_tasks(task_list):
    """From a list of UserTask, return only tasks that are visible (dependency satisfied) and sorted by display_order then priority/due_date/created_at.
    A task is visible if depends_on_task_id is None or the depended-on task is completed. Tasks are ordered so the next task appears only after the previous is done."""
    from datetime import date as date_type
    completed_ids = {t.id for t in task_list if t.status == 'completed'}
    def visible(t):
        dep = getattr(t, 'depends_on_task_id', None)
        return dep is None or dep in completed_ids
    visible_list = [t for t in task_list if visible(t)]
    def sort_key(t):
        # display_order is nullable; mixed None/int breaks tuple sort (TypeError on dashboard)
        order = getattr(t, 'display_order', None)
        if order is None:
            order = 999999
        prio = {'urgent': 3, 'high': 2, 'normal': 1, 'low': 0}.get((t.priority or 'normal').lower(), 1)
        due = t.due_date or date_type.max
        created = t.created_at or datetime.min
        return (order, -prio, due, created)
    visible_list.sort(key=sort_key)
    return visible_list

def training_video_id_from_task(task):
    """Parse video_id from a training UserTask notes field (video_id:123)."""
    if getattr(task, 'task_type', None) != 'training':
        return None
    notes = getattr(task, 'notes', None) or ''
    if not notes.startswith('video_id:'):
        return None
    try:
        return int(notes.split(':')[1])
    except (ValueError, IndexError):
        return None

def training_video_ids_from_user_tasks(task_list):
    """Video IDs already represented by training UserTask rows."""
    ids = set()
    for task in task_list:
        vid = training_video_id_from_task(task)
        if vid is not None:
            ids.add(vid)
    return ids

def attach_training_video_ids_to_tasks(task_list):
    """Set task.video_id for templates (Watch Training links)."""
    for task in task_list:
        task.video_id = training_video_id_from_task(task)

def dashboard_onboarding_work(required_videos, all_user_tasks, completed_required_video_ids):
    """Dedupe required training vs UserTask items for dashboard cards and progress bar."""
    completed_set = set(completed_required_video_ids or [])
    covered_video_ids = training_video_ids_from_user_tasks(all_user_tasks)
    standalone_required = [v for v in (required_videos or []) if v.id not in covered_video_ids]
    incomplete_standalone_training = [v for v in standalone_required if v.id not in completed_set]
    total_tasks = len(all_user_tasks) + len(standalone_required)
    completed_tasks = len([t for t in all_user_tasks if t.status == 'completed']) + len(
        [v for v in standalone_required if v.id in completed_set]
    )
    progress_percentage = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
    return {
        'incomplete_standalone_training': incomplete_standalone_training,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'progress_percentage': progress_percentage,
    }

def user_onboarding_is_fully_complete(username):
    """True when required training and all visible user tasks are done (same rules as dashboard)."""
    user_new_hire = NewHire.query.filter_by(username=username).first()
    required_videos = []
    if user_new_hire:
        try:
            required_videos = list(user_new_hire.required_training_videos)
        except Exception:
            required_videos = []
    all_user_tasks = UserTask.query.filter_by(username=username).all()
    covered_video_ids = training_video_ids_from_user_tasks(all_user_tasks)
    for video in required_videos:
        if video.id in covered_video_ids:
            continue
        progress = UserTrainingProgress.query.filter_by(
            username=username,
            video_id=video.id,
            is_completed=True,
            is_passed=True,
        ).first()
        if not progress:
            return False
    if not required_videos and not all_user_tasks:
        return False
    visible_ordered = get_visible_ordered_user_tasks(all_user_tasks)
    incomplete = [t for t in visible_ordered if t.status != 'completed']
    return len(incomplete) == 0

def maybe_send_all_tasks_completed_email(username):
    """Send one congratulatory email when the user finishes all onboarding tasks (once per new hire)."""
    maybe_apply_default_finale_message(username)
    if not _app_const('MAIL_AVAILABLE'):
        return False
    _ensure_new_hires_finale_columns()
    new_hire = NewHire.query.filter_by(username=username).first()
    if new_hire and getattr(new_hire, 'all_tasks_completed_email_sent_at', None):
        return False
    if not user_onboarding_is_fully_complete(username):
        return False
    to_email = get_email_for_username(username)
    if not to_email:
        return False
    from services.document_urls import onboarding_tasks_url
    dashboard_link = onboarding_tasks_url().replace('/tasks', '/dashboard')
    subject = get_admin_setting('all_tasks_completed_email_subject', _app_const('DEFAULT_ALL_TASKS_EMAIL_SUBJECT')).strip()
    body_template = get_admin_setting('all_tasks_completed_email_body', _app_const('DEFAULT_ALL_TASKS_EMAIL_BODY'))
    body_text = render_onboarding_message_plain(body_template).strip()
    if '{dashboard_link}' in body_text:
        body_text = apply_message_template(body_text, dashboard_link=dashboard_link).strip()
    body_html = f'<div style="font-family: Arial, sans-serif; line-height: 1.6;">{render_onboarding_message_html(body_template, for_email=True)}</div>'
    if not subject:
        subject = _app_const('DEFAULT_ALL_TASKS_EMAIL_SUBJECT')
    if not send_email(to_email, subject, body_html, body_text=body_text):
        return False
    if new_hire:
        new_hire.all_tasks_completed_email_sent_at = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return True

def reset_onboarding_completion_state(username):
    """Clear completion email + finale dismissal when new onboarding work is assigned."""
    _ensure_new_hires_finale_columns()
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        return
    changed = False
    if getattr(new_hire, 'all_tasks_completed_email_sent_at', None):
        new_hire.all_tasks_completed_email_sent_at = None
        changed = True
    if getattr(new_hire, 'finale_message_dismissed_at', None):
        new_hire.finale_message_dismissed_at = None
        changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

def clear_all_tasks_completed_email_sent(username):
    """Allow a new completion email after more onboarding work is assigned."""
    reset_onboarding_completion_state(username)

