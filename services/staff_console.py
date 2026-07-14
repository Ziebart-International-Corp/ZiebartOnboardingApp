"""Staff console navigation, scope, and URL helpers."""
from __future__ import annotations

from flask import redirect, session, url_for, request
from flask_login import current_user

from models import NewHire, User as UserModel

STAFF_CONSOLE_HOME_KEY = "staff_console_home"
STAFF_CONSOLE_QUERY_KEY = "staff_console"


def get_current_user_store_id():
    from services.stores_scope import get_current_user_store_id as _fn
    return _fn()

def touch_staff_console_home(which):
    """Persist last staff landing: 'admin' or 'manager' (for hybrid-role users)."""
    try:
        if not current_user.is_authenticated:
            return
    except Exception:
        return
    if which == 'admin' and current_user.is_admin():
        session[STAFF_CONSOLE_HOME_KEY] = 'admin'
    elif which == 'manager' and current_user.is_manager():
        session[STAFF_CONSOLE_HOME_KEY] = 'manager'


def staff_console_home_url():
    """Target for 'Back to Dashboard' on pages shared by admin and manager consoles."""
    try:
        authed = current_user.is_authenticated
    except Exception:
        authed = False
    if not authed:
        return url_for('dashboard')
    is_ad = current_user.is_admin()
    is_mg = current_user.is_manager()
    pref = session.get(STAFF_CONSOLE_HOME_KEY)
    if pref == 'manager' and is_mg:
        return url_for('manager_dashboard')
    if pref == 'admin' and is_ad:
        return url_for('admin_dashboard')
    if is_mg and not is_ad:
        return url_for('manager_dashboard')
    if is_ad and is_mg:
        # Hybrid with no session: prefer admin home (managers set session via ?staff_console=manager on links)
        return url_for('admin_dashboard')
    if is_ad:
        return url_for('admin_dashboard')
    if is_mg:
        return url_for('manager_dashboard')
    return url_for('dashboard')

def uses_manager_new_hires_home():
    """True when user should land on /manager/new-hires (not admin home) after onboarding or similar."""
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    pref = (session.get(STAFF_CONSOLE_HOME_KEY) or '').strip().lower()
    db_role = (getattr(current_user, 'role', None) or '').strip().lower()
    if db_role == 'manager':
        return True
    if pref == 'manager' and current_user.is_manager():
        return True
    return False

def uses_manager_console_scope(force_manager=False):
    """True when shared /admin/* tools should behave like Manager Console (store-scoped, view-only).

    Pure managers always qualify. Admin+manager hybrids qualify when ?staff_console=manager or session
    staff_console_home is manager (same rule as _view_all_new_hires_impl).
    """
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    if current_user.is_manager() and not current_user.is_admin():
        return True
    if current_user.is_admin() and current_user.is_manager():
        if force_manager:
            return True
        sc = (
            request.args.get(STAFF_CONSOLE_QUERY_KEY)
            or session.get(STAFF_CONSOLE_HOME_KEY)
            or ''
        ).strip().lower()
        return sc == 'manager'
    return False

def document_manage_requires_store_scope():
    """True when document list/download should be limited to the user's store (not full admin)."""
    return uses_manager_console_scope()

def staff_store_scope_id():
    """Store ID when staff tools should list store-scoped data; None for org-wide admin console."""
    return get_current_user_store_id() if uses_manager_console_scope() else None

def is_pure_manager():
    """True for role=manager without admin role (store-scoped staff by default)."""
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    return current_user.is_manager() and not current_user.is_admin()


def can_assign_extra_tasks():
    """Admins and store managers may assign one-off tasks."""
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    return current_user.is_admin() or is_pure_manager()

def assign_task_link_context():
    """Pick assign-task route from active staff console, not role alone."""
    if uses_manager_console_scope() or is_pure_manager():
        return 'manager_assign_task', 'manager'
    return 'admin_assign_task', 'admin'

def assign_task_url(**kwargs):
    """URL for assign-task links (manager console → /manager/assign-task)."""
    endpoint, sc = assign_task_link_context()
    kwargs.setdefault('staff_console', sc)
    return url_for(endpoint, **kwargs)

def new_hire_details_link_context(force_manager=False):
    """Pick new-hire details route from active staff console, not role alone."""
    if force_manager or uses_manager_console_scope():
        return 'manager_view_new_hire_details', 'manager'
    return 'view_new_hire_details', 'admin'

def view_new_hire_details_url(username, **kwargs):
    """URL for new-hire detail links (manager console → /manager/new-hire/.../details)."""
    endpoint, sc = new_hire_details_link_context()
    kwargs['username'] = username
    if endpoint == 'manager_view_new_hire_details':
        return url_for(endpoint, **kwargs)
    kwargs.setdefault('staff_console', sc)
    return url_for(endpoint, **kwargs)

def new_hire_details_back_url():
    """Back link from new-hire details: manager list vs staff dashboard."""
    if uses_manager_console_scope() or uses_manager_new_hires_home():
        return manager_new_hires_list_url()
    return staff_console_home_url()

def redirect_new_hire_details(username):
    """Redirect back to details in the correct console context."""
    endpoint, sc = new_hire_details_link_context()
    if endpoint == 'manager_view_new_hire_details':
        return redirect(url_for(endpoint, username=username))
    return redirect(url_for(endpoint, username=username, staff_console=sc))

def build_user_display_and_store_maps(users=None):
    """Build display names and store IDs for user pickers."""
    if users is None:
        users = UserModel.query.order_by(UserModel.username).all()
    new_hires_by_username = {nh.username: nh for nh in NewHire.query.all()}
    user_display_names = {}
    user_store_ids = {}
    for u in users:
        new_hire = new_hires_by_username.get(u.username)
        if new_hire:
            user_display_names[u.username] = f"{new_hire.first_name} {new_hire.last_name}".strip() or u.username
        elif getattr(u, 'full_name', None) and u.full_name.strip():
            user_display_names[u.username] = u.full_name.strip()
        else:
            user_display_names[u.username] = u.username
        sid = getattr(u, 'store_id', None)
        if sid is None and new_hire:
            sid = getattr(new_hire, 'store_id', None)
        user_store_ids[u.username] = sid
    return users, user_display_names, user_store_ids

def manager_new_hires_list_url():
    """URL for the manager-scoped new hires list (/manager/new-hires)."""
    sid = get_current_user_store_id()
    if sid is not None:
        return url_for('manager_new_hires', store_id=sid)
    return url_for('manager_new_hires')

def staff_header_display_name(username):
    """Label for staff headers: User.full_name, else NewHire first+last, else username."""
    if not username:
        return 'User'
    try:
        row = UserModel.query.filter_by(username=username).first()
        if row and (getattr(row, 'full_name', None) or '').strip():
            return (row.full_name or '').strip()
        nh = NewHire.query.filter_by(username=username).first()
        if nh:
            fn = (nh.first_name or '').strip()
            ln = (nh.last_name or '').strip()
            composed = f'{fn} {ln}'.strip()
            if composed:
                return composed
    except Exception:
        db.session.rollback()
    return username

def _access_revoke_calendar_date(val):
    """Normalize access_revoked_at from the DB to a calendar date (drivers may return datetime)."""
    if val is None:
        return None
    from datetime import date as _date_cls, datetime as _datetime_cls
    if isinstance(val, _datetime_cls):
        return val.date()
    if isinstance(val, _date_cls):
        return val
    return None

def _staff_can_view_user_documents(target_username):
    """Org-wide admin or store-scoped staff may view another user's signed documents."""
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    if current_user.username == target_username:
        return True
    if current_user.is_admin() and not uses_manager_console_scope():
        return True
    if current_user.is_admin() or current_user.is_manager():
        store_id = get_current_user_store_id()
        if store_id is None:
            return False
        nh = NewHire.query.filter(
            NewHire.username == target_username,
            NewHire.store_id == store_id,
            NewHire.status != 'removed',
        ).first()
        return nh is not None
    return False

def _staff_new_hire_details_url(username):
    if uses_manager_console_scope():
        return url_for('manager_view_new_hire_details', username=username)
    return url_for('view_new_hire_details', username=username)

def _assign_task_redirect(staff_console):
    endpoint = 'manager_assign_task' if staff_console == 'manager' else 'admin_assign_task'
    return redirect(url_for(endpoint, staff_console=staff_console))

def _manager_can_act_on_new_hire(username):
    """True if org-wide admin, or manager acting on a new hire at their store."""
    if current_user.is_admin() and not uses_manager_console_scope():
        return True
    if not current_user.is_manager():
        return False
    store_id = get_current_user_store_id()
    if store_id is None:
        return False
    allowed = NewHire.query.filter(
        NewHire.status != 'removed',
        NewHire.store_id == store_id,
        NewHire.username == username
    ).first()
    return allowed is not None

