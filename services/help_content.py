"""Help Center: article visibility, search, seeding, and body rendering."""
from __future__ import annotations

import re
from html import escape

from flask_login import current_user
from markupsafe import Markup
from sqlalchemy import or_

from models import HelpArticle, db
from services.stores_scope import MANAGER_PERMISSION_KEYS, manager_has_permission


HELP_AUDIENCES = (
    ('all', 'Everyone'),
    ('user', 'Users'),
    ('manager', 'Managers'),
    ('admin', 'Admins'),
)

_PERMISSION_LABELS = dict(MANAGER_PERMISSION_KEYS)


def slugify(value: str) -> str:
    s = (value or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s[:200] or 'article'


def unique_slug(title: str, exclude_id: int | None = None) -> str:
    base = slugify(title)
    slug = base
    n = 2
    while True:
        q = HelpArticle.query.filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(HelpArticle.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f'{base}-{n}'
        n += 1


def permission_label(key: str | None) -> str:
    if not key:
        return ''
    return _PERMISSION_LABELS.get(key, key)


def current_help_role() -> str:
    try:
        if current_user.is_authenticated:
            if current_user.is_admin():
                return 'admin'
            if current_user.is_manager():
                return 'manager'
    except Exception:
        pass
    return 'user'


def article_visible_to_current_user(article: HelpArticle) -> bool:
    if not article or not article.is_published:
        return False
    role = current_help_role()
    audience = (article.audience or 'all').lower()
    if role == 'admin':
        return True
    if audience not in ('all', role):
        return False
    if role == 'manager' and article.permission_key:
        return manager_has_permission(article.permission_key)
    return True


def visible_articles_query():
    """Base query of published articles the current user may see."""
    role = current_help_role()
    q = HelpArticle.query.filter_by(is_published=True)
    if role == 'admin':
        return q.order_by(HelpArticle.sort_order.asc(), HelpArticle.title.asc())
    if role == 'manager':
        allowed_keys = [
            key for key, _ in MANAGER_PERMISSION_KEYS if manager_has_permission(key)
        ]
        audience_ok = or_(
            HelpArticle.audience == 'all',
            HelpArticle.audience == 'manager',
        )
        if allowed_keys:
            perm_ok = or_(
                HelpArticle.permission_key.is_(None),
                HelpArticle.permission_key == '',
                HelpArticle.permission_key.in_(allowed_keys),
            )
        else:
            perm_ok = or_(
                HelpArticle.permission_key.is_(None),
                HelpArticle.permission_key == '',
            )
        q = q.filter(audience_ok).filter(perm_ok)
    else:
        q = q.filter(or_(HelpArticle.audience == 'all', HelpArticle.audience == 'user'))
    return q.order_by(HelpArticle.sort_order.asc(), HelpArticle.title.asc())


def search_articles(query: str, limit: int = 20):
    q = (query or '').strip()
    base = visible_articles_query()
    if len(q) < 2:
        return base.limit(limit).all()
    like = f'%{q}%'
    ranked = (
        base.filter(
            or_(
                HelpArticle.title.like(like),
                HelpArticle.body.like(like),
                HelpArticle.tags.like(like),
            )
        )
        .all()
    )
    title_hits = [a for a in ranked if q.lower() in (a.title or '').lower()]
    other = [a for a in ranked if a not in title_hits]
    return (title_hits + other)[:limit]


def render_article_body(body: str) -> Markup:
    """Escape plain text and turn paragraphs / blank lines into HTML."""
    text = (body or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return Markup('')
    parts = []
    for block in re.split(r'\n\s*\n', text):
        block = block.strip()
        if not block:
            continue
        lines = '<br>\n'.join(escape(line) for line in block.split('\n'))
        parts.append(f'<p>{lines}</p>')
    return Markup('\n'.join(parts))


# Comprehensive starter library. ensure_seed_help_articles() inserts missing
# titles and refreshes system-authored bodies so local DBs pick up new content.
_SEED_ARTICLES = [
    # ----- Getting started / account -----
    {
        'title': 'How to use Help',
        'audience': 'all',
        'tags': 'help,search,ask,question,howto',
        'related_path': '/help',
        'sort_order': 1,
        'body': (
            'Click the ? icon in the top left of any page to open Help.\n\n'
            'Search for what you want to do, or browse the articles listed for your role. '
            'Open an article to read the steps.\n\n'
            'If nothing matches, use the Feedback button in the header to contact the team.'
        ),
    },
    {
        'title': 'Logging in',
        'audience': 'all',
        'tags': 'login,sign in,password,email,access',
        'related_path': '/login',
        'sort_order': 3,
        'body': (
            'Open the login page and sign in with the email and password from your onboarding invite '
            'or password reset email.\n\n'
            'After a successful login you usually see the Welcome screen, then your Home dashboard.\n\n'
            'If login fails, check the email spelling and password. If your access was revoked, you '
            'cannot sign in until a manager or admin restores it.'
        ),
    },
    {
        'title': 'Changing your password',
        'audience': 'all',
        'tags': 'password,change password,reset,security,forgot',
        'related_path': '/change-password',
        'sort_order': 4,
        'body': (
            'Go to Change Password when the app asks you to after a reset, or when you want a new password.\n\n'
            'Enter your current password, then choose a new one (at least 6 characters, and different from '
            'a temporary password). Confirm the new password and save.\n\n'
            'If you were forced to change your password, other pages stay blocked until you finish.\n\n'
            'If you cannot log in, use Forgot password? on the login page. We email a one-time reset link '
            'to your account email. The link expires in 1 hour and can only be used once.'
        ),
    },
    {
        'title': 'Forgot password / reset by email',
        'audience': 'all',
        'tags': 'password,forgot,reset,email,locked out',
        'related_path': '/forgot-password',
        'sort_order': 45,
        'body': (
            'On the login page, click Forgot password? and enter the email you use to sign in.\n\n'
            'If an account exists for that email, we send a one-time reset link. Open the link, choose a new '
            'password, then log in.\n\n'
            'The link expires in 1 hour and works only once. If you do not get an email, check spam, wait a '
            'minute and try again, or ask your manager/admin for help. For security, the app does not say '
            'whether the email was found.'
        ),
    },
    {
        'title': 'Why can\'t I log in?',
        'audience': 'all',
        'tags': 'login,access,revoked,locked,password,error',
        'related_path': '/login',
        'sort_order': 5,
        'body': (
            'Common reasons you cannot log in:\n\n'
            '• Wrong email or password — try again carefully, or ask for a password reset.\n'
            '• Temporary password not changed yet — check email for reset instructions, then use Change Password.\n'
            '• Access revoked — a manager or admin set an end date or cancelled access. Contact them to restore it.\n\n'
            'Managers and admins restore access from the hire details or Manage Users screens.'
        ),
    },
    {
        'title': 'Logging out',
        'audience': 'all',
        'tags': 'logout,sign out,security',
        'related_path': '/logout',
        'sort_order': 6,
        'body': (
            'Open the user menu (your initial icon) and choose Logout.\n\n'
            'You return to the login page. On a shared computer, always log out when you are finished.'
        ),
    },
    {
        'title': 'Sending app feedback',
        'audience': 'all',
        'tags': 'feedback,bug,suggestion,asana',
        'related_path': '/feedback',
        'sort_order': 7,
        'body': (
            'Use the Feedback button in the header to report a bug, leave a comment, or suggest an improvement.\n\n'
            'Describe what happened and optionally attach a screenshot. The page you came from can be included '
            'automatically. Feedback may create a task for the team to review.'
        ),
    },
    {
        'title': 'Switching between User, Manager, and Admin',
        'audience': 'all',
        'tags': 'manager console,admin console,dashboard,role,menu',
        'related_path': '/dashboard',
        'sort_order': 8,
        'body': (
            'Your Home dashboard is for completing your own onboarding work.\n\n'
            'If you are a manager or admin, open the user menu and choose Manager Console or Admin Console '
            'to manage other people, forms, and training.\n\n'
            'Use User Dashboard (or Home) anytime to return to your personal tasks.'
        ),
    },

    # ----- User home & navigation -----
    {
        'title': 'Using your Home dashboard',
        'audience': 'user',
        'tags': 'dashboard,home,progress,navigation',
        'related_path': '/dashboard',
        'sort_order': 10,
        'body': (
            'Home shows your onboarding progress, items still to do, and External Links.\n\n'
            'Use the top tabs (or mobile bottom nav): Home, Tasks, Files, Videos, and Profile.\n\n'
            'Open any incomplete item to fill a form, watch training, or view a task. Locked “Up next” '
            'items unlock after you finish earlier required steps.'
        ),
    },
    {
        'title': 'Welcome screen after login',
        'audience': 'user',
        'tags': 'welcome,login,message,onboarding',
        'related_path': '/welcome',
        'sort_order': 11,
        'body': (
            'After you log in, you may see a Welcome message with helpful orientation text.\n\n'
            'Read it, then continue to your Home dashboard. Admins can customize this message under '
            'Onboarding Messages.'
        ),
    },
    {
        'title': 'Understanding task progress and locked steps',
        'audience': 'user',
        'tags': 'tasks,locked,progress,depends,order,up next',
        'related_path': '/dashboard',
        'sort_order': 12,
        'body': (
            'Some tasks must be done in order. If a card says it is locked or “Up next,” finish the earlier '
            'task first.\n\n'
            'The progress bar on Home shows how much of your assigned work is complete. Completing the '
            'current items unlocks the next ones.'
        ),
    },
    {
        'title': 'Finding and completing your tasks',
        'audience': 'user',
        'tags': 'tasks,todo,checklist,documents,training',
        'related_path': '/tasks',
        'sort_order': 13,
        'body': (
            'Open Tasks from Home (or the Tasks tab) to see everything assigned to you.\n\n'
            'Tasks may be documents to fill and sign, training videos to watch, or other checklist items. '
            'Work through them in order when one depends on another.\n\n'
            'Use Fill & Sign, Watch Training, or View Task on each item to open the right screen.'
        ),
    },
    {
        'title': 'Notifications bell',
        'audience': 'user',
        'tags': 'notifications,bell,reminders,unread',
        'related_path': '/dashboard',
        'sort_order': 14,
        'body': (
            'The bell on Home lists unread reminders for training and tasks.\n\n'
            'Click an item to open it and mark it read, or use Mark all read. The badge count drops as you clear items.'
        ),
    },
    {
        'title': 'External Links on Home',
        'audience': 'user',
        'tags': 'external links,sidebar,quick links,hr,resources',
        'related_path': '/dashboard',
        'sort_order': 15,
        'body': (
            'The External Links area on Home lists useful company websites and tools.\n\n'
            'Click a link to open it in a new tab. Admins manage which links appear under External Links '
            'in the Admin Console.'
        ),
    },
    {
        'title': 'I finished everything — what happens next?',
        'audience': 'user',
        'tags': 'complete,done,finale,finished,onboarding complete',
        'related_path': '/dashboard',
        'sort_order': 16,
        'body': (
            'When all assigned tasks are complete, Home may show a completion (finale) message and sometimes '
            'a document link. You may also receive a completion email.\n\n'
            'Keep using External Links and Profile as needed. If your manager assigns new work later, it will '
            'appear on Home and Tasks again.'
        ),
    },
    {
        'title': 'A task or document is missing',
        'audience': 'user',
        'tags': 'missing,not showing,assign,help,task missing',
        'related_path': '/tasks',
        'sort_order': 17,
        'body': (
            'Refresh Home, Tasks, and Files. If the item still does not appear, it was probably not assigned '
            'to you yet, or it is not visible for your store.\n\n'
            'Ask your manager to assign the document or training (Start onboarding, Assign document, or Assign task). '
            'You can also use Feedback in the header if you still need help.'
        ),
    },

    # ----- Documents / wizard / training / profile -----
    {
        'title': 'Using Files (your documents)',
        'audience': 'user',
        'tags': 'files,documents,forms,pdf',
        'related_path': '/documents',
        'sort_order': 20,
        'body': (
            'Open Files to see forms assigned to you.\n\n'
            'Incomplete forms need Fill & Sign. Completed forms can be viewed, printed, or downloaded.\n\n'
            'Only forms that were assigned to you (and set up for filling) can be completed in the app.'
        ),
    },
    {
        'title': 'Filling out a document with the wizard',
        'audience': 'user',
        'tags': 'documents,forms,wizard,signature,fill,sign',
        'related_path': '/documents',
        'sort_order': 21,
        'body': (
            'Open a form from Tasks or Files. When a guided wizard is available, you move through one field '
            'at a time.\n\n'
            'Use Next and Back. Required fields must be filled before you can finish. For signature steps, '
            'draw or type your signature, or apply your saved signature from Profile.\n\n'
            'Your progress is saved so you can leave and come back later.'
        ),
    },
    {
        'title': 'Signing a form on the classic PDF page',
        'audience': 'user',
        'tags': 'documents,classic,pdf,sign,overlay',
        'related_path': '/documents',
        'sort_order': 22,
        'body': (
            'Some forms open on the classic PDF signing page instead of the step wizard.\n\n'
            'Fill typed fields, place your signature where required, then submit or complete the form. '
            'If you need to reopen a completed form and editing is still allowed, use Edit from Files.'
        ),
    },
    {
        'title': 'Viewing, printing, or downloading a completed form',
        'audience': 'user',
        'tags': 'print,download,completed,pdf,view',
        'related_path': '/documents',
        'sort_order': 23,
        'body': (
            'After you finish a form, open it from Files to view the completed PDF.\n\n'
            'Use print or download options when you need a paper or file copy for your records.'
        ),
    },
    {
        'title': 'Watching training videos',
        'audience': 'user',
        'tags': 'training,video,videos,watch',
        'related_path': '/training',
        'sort_order': 30,
        'body': (
            'Open Videos (Training) from Home to see training available for your store.\n\n'
            'Open a video and watch it through. Required training also appears on Home and Tasks until it is complete. '
            'Watch progress is saved so you can resume later.'
        ),
    },
    {
        'title': 'Taking a training quiz',
        'audience': 'user',
        'tags': 'training,quiz,test,pass,score',
        'related_path': '/training',
        'sort_order': 31,
        'body': (
            'Some training videos include quiz questions during or after the video.\n\n'
            'Answer each question and submit. Passing marks the training complete for that assignment. '
            'If you do not pass, you can try again according to how the quiz is set up.\n\n'
            'Incomplete required training stays on Tasks and in notifications until finished.'
        ),
    },
    {
        'title': 'Viewing your profile',
        'audience': 'user',
        'tags': 'profile,name,email,position',
        'related_path': '/profile',
        'sort_order': 40,
        'body': (
            'Open Profile from the Profile tab or user menu.\n\n'
            'You can review your name, email, position, and start date from your hire record. '
            'Use Manage Signature from Profile to save a reusable signature. Use Change Password to update your password.'
        ),
    },
    {
        'title': 'Saving a default signature',
        'audience': 'user',
        'tags': 'signature,profile,draw,typed,sign',
        'related_path': '/profile/signature',
        'sort_order': 41,
        'body': (
            'From Profile, open Manage Signature. Draw or type a signature and save it.\n\n'
            'When a form asks you to sign, you can apply your saved signature to that field. '
            'It is not applied automatically to every field — you choose when to use it.\n\n'
            'Clear removes the saved signature if you need to create a new one.'
        ),
    },

    # ----- Manager -----
    {
        'title': 'Using the Manager Console',
        'audience': 'manager',
        'tags': 'manager,console,store,dashboard',
        'related_path': '/manager',
        'sort_order': 100,
        'body': (
            'The Manager Console is limited to your store. Cards and menu items appear only for permissions '
            'your admin granted you.\n\n'
            'Typical tools: Start onboarding, New hires, Forms / documents, Training library, and Onboarding checklists.\n\n'
            'Use User Dashboard anytime to return to your personal Home.'
        ),
    },
    {
        'title': 'What if I don\'t see a Manager card?',
        'audience': 'manager',
        'tags': 'permissions,missing,card,access,manager',
        'related_path': '/manager',
        'sort_order': 101,
        'body': (
            'Manager cards are permission-gated. If you do not see Start onboarding, Forms, Training, or Checklists, '
            'your admin has not granted that permission.\n\n'
            'Ask an admin to update your manager permissions under Manage Users.'
        ),
    },
    {
        'title': 'Store scope: why I only see my location',
        'audience': 'manager',
        'tags': 'store,scope,location,other stores',
        'related_path': '/manager',
        'sort_order': 102,
        'body': (
            'Manager tools only show people, forms, and training for your assigned store.\n\n'
            'Admins can see all stores from the Admin Console. If you need access to another location, '
            'an admin must update your store assignment or handle that store themselves.'
        ),
    },
    {
        'title': 'Starting onboarding for a new hire',
        'audience': 'manager',
        'permission_key': 'start_onboarding',
        'tags': 'onboarding,new hire,hire,add,start',
        'related_path': '/admin/new-hire/add',
        'sort_order': 110,
        'body': (
            'From the Manager Console, open Start onboarding.\n\n'
            'Enter the new hire’s details, confirm the store, choose position/role when prompted, and assign '
            'the documents and training they need. Set an access end date if required.\n\n'
            'They receive login credentials and will see their tasks on Home after they sign in.'
        ),
    },
    {
        'title': 'Viewing new hires at your store',
        'audience': 'manager',
        'tags': 'new hires,list,progress,track',
        'related_path': '/manager/new-hires',
        'sort_order': 111,
        'body': (
            'Open New hires from the Manager Console to see people onboarding at your store.\n\n'
            'Progress indicators show how far each person has gotten. Open a person for full details, tasks, '
            'and access status.'
        ),
    },
    {
        'title': 'Tracking a new hire\'s progress',
        'audience': 'manager',
        'tags': 'progress,details,nudge,status,incomplete',
        'related_path': '/manager/new-hires',
        'sort_order': 112,
        'body': (
            'Open a hire from New hires to see training, documents/tasks, checklist status, and whether login '
            'is active or revoked.\n\n'
            'Use this screen to find what is blocking completion. You may be able to nudge incomplete tasks, '
            'assign extra work, or cancel/restore access depending on your permissions.'
        ),
    },
    {
        'title': 'How managers see whether someone is done',
        'audience': 'manager',
        'tags': 'complete,done,progress,checklist,status',
        'related_path': '/manager/new-hires',
        'sort_order': 113,
        'body': (
            'Use the New hires list for a quick progress view, then open hire details for training, tasks, and checklist.\n\n'
            'Onboarding checklists (if you have permission) show manager-side checklist sign-off. '
            'Nudge reminders help when someone is stuck on incomplete tasks.'
        ),
    },
    {
        'title': 'Assigning an extra task to a hire',
        'audience': 'manager',
        'tags': 'assign task,extra,document,training',
        'related_path': '/manager/assign-task',
        'sort_order': 114,
        'body': (
            'If someone needs an extra document, training video, or custom task after onboarding started, '
            'use Assign task (from hire details or the assign-task page).\n\n'
            'Pick the person and what to assign. They will see it on Home and Tasks.'
        ),
    },
    {
        'title': 'Managing forms for your location',
        'audience': 'manager',
        'permission_key': 'manage_documents',
        'tags': 'documents,forms,library,store',
        'related_path': '/admin/documents',
        'sort_order': 120,
        'body': (
            'Open Forms / documents from the Manager Console to see forms for your store.\n\n'
            'Review what is available, and use Assign when a specific person needs a form. '
            'Some library changes (upload, field setup) may be limited to admins.'
        ),
    },
    {
        'title': 'Assigning a document to someone',
        'audience': 'manager',
        'permission_key': 'manage_documents',
        'tags': 'assign,document,form,user',
        'related_path': '/admin/documents',
        'sort_order': 121,
        'body': (
            'From Forms / documents, open Assign for the form you need.\n\n'
            'Select the user(s). They get a document task and can complete it under Files. '
            'Remove an assignment if it was sent by mistake.'
        ),
    },
    {
        'title': 'Managing training for your team',
        'audience': 'manager',
        'permission_key': 'manage_training',
        'tags': 'training,videos,library',
        'related_path': '/admin/training',
        'sort_order': 130,
        'body': (
            'Open Training library from the Manager Console to review videos available for your store.\n\n'
            'Assign required training when starting onboarding, and check progress from New hires or checklist views. '
            'Uploading videos and editing quizzes is usually an admin task.'
        ),
    },
    {
        'title': 'Viewing onboarding checklists',
        'audience': 'manager',
        'permission_key': 'manage_user_checklists',
        'tags': 'checklist,onboarding,progress,finale',
        'related_path': '/admin/user-checklists',
        'sort_order': 140,
        'body': (
            'Open Onboarding checklists to see per-hire checklist progress for your store.\n\n'
            'Update completion as items are done. When everything is finished, you may be able to send the '
            'completion (finale) message depending on how your process is set up.\n\n'
            'The checklist template itself is managed by admins under Onboarding Tasks / checklist.'
        ),
    },

    # ----- Admin -----
    {
        'title': 'Using the Admin Dashboard',
        'audience': 'admin',
        'tags': 'admin,dashboard,console,stores',
        'related_path': '/admin',
        'sort_order': 200,
        'body': (
            'The Admin Dashboard summarizes stores and active new hires. Search for a hire, or open a store '
            'to see its people.\n\n'
            'Use the left Admin menu for full tools: users, forms, training, checklists, reports, messages, and Help.'
        ),
    },
    {
        'title': 'Viewing all new hires',
        'audience': 'admin',
        'tags': 'new hires,all stores,filter,search',
        'related_path': '/admin/new-hires',
        'sort_order': 210,
        'body': (
            'Open New hires (all stores) from the admin menu to browse everyone in onboarding.\n\n'
            'Filter by store when needed, then open a person for details, progress, tasks, and access actions.'
        ),
    },
    {
        'title': 'New hire detail actions (nudge, access, finale)',
        'audience': 'admin',
        'tags': 'nudge,revoke,restore,access,finale,details',
        'related_path': '/admin/new-hires',
        'sort_order': 211,
        'body': (
            'From a hire’s details you can review training and tasks, nudge incomplete items, update hire info, '
            'cancel or restore login access, assign extra tasks, and manage completion messaging.\n\n'
            'Cancelled or expired access prevents the person from logging in until restored.'
        ),
    },
    {
        'title': 'Managing users and manager permissions',
        'audience': 'admin',
        'tags': 'users,permissions,manager,role,store',
        'related_path': '/admin/users',
        'sort_order': 220,
        'body': (
            'Open Manage Users to create or update accounts. Set role (user, manager, or admin), assign a store, '
            'and for managers check the permission boxes (start onboarding, documents, training, checklists, reports).\n\n'
            'You can also reset passwords and revoke or restore access from this screen.'
        ),
    },
    {
        'title': 'Resetting a user\'s password',
        'audience': 'admin',
        'tags': 'password,reset,email,must change',
        'related_path': '/admin/users',
        'sort_order': 221,
        'body': (
            'On Manage Users, use Reset password or Send password reset email for the account.\n\n'
            'After an email reset, the user is usually required to Change Password on next login. '
            'Tell them to check email, sign in, and set a new password.'
        ),
    },
    {
        'title': 'Managing admin accounts',
        'audience': 'admin',
        'tags': 'admins,manage admins,accounts',
        'related_path': '/admin/manage-admins',
        'sort_order': 222,
        'body': (
            'Open Manage Admins to add or update admin accounts and passwords.\n\n'
            'Admins see the full console. Avoid removing the last remaining admin account without a backup plan.'
        ),
    },
    {
        'title': 'Assigning a task (admin)',
        'audience': 'admin',
        'tags': 'assign task,document,training,custom',
        'related_path': '/admin/assign-task',
        'sort_order': 223,
        'body': (
            'Use Assign task to give a user a document, training video, or custom task after onboarding has started.\n\n'
            'Prefer this when something was missed at hire time or extra paperwork is needed mid-onboarding.'
        ),
    },
    {
        'title': 'Managing the forms library',
        'audience': 'admin',
        'tags': 'documents,forms,upload,visibility,pdf',
        'related_path': '/admin/documents',
        'sort_order': 230,
        'body': (
            'Open Manage Forms to upload PDFs, set which stores can see them, rename, toggle visibility, delete, '
            'and open Assign or field-configuration tools.\n\n'
            'Forms need signature/typed fields configured before employees can complete them in the wizard.'
        ),
    },
    {
        'title': 'Uploading a new form',
        'audience': 'admin',
        'tags': 'upload,document,pdf,new form',
        'related_path': '/admin/upload-document',
        'sort_order': 231,
        'body': (
            'From Manage Forms, upload a PDF, set a display name and store visibility, then save.\n\n'
            'Next, configure signature and typed fields, then assign the form to the people who must complete it. '
            'Until fields exist, users cannot finish the form in the wizard.'
        ),
    },
    {
        'title': 'Configuring signature and form fields',
        'audience': 'admin',
        'tags': 'signature fields,acroform,wizard,pdf fields',
        'related_path': '/admin/documents',
        'sort_order': 232,
        'body': (
            'Open a form’s signature/field editor from Manage Forms.\n\n'
            'Place signature and typed fields on the PDF (or import AcroForm fields when available). '
            'Field setup controls what employees see in the fill wizard. Test with a sample user after saving.'
        ),
    },
    {
        'title': 'Managing training videos and quizzes',
        'audience': 'admin',
        'tags': 'training,upload,quiz,video,stores',
        'related_path': '/admin/training',
        'sort_order': 240,
        'body': (
            'Open Training Library to upload videos, set store visibility, toggle active/inactive, delete, '
            'and manage quiz questions.\n\n'
            'Inactive videos or videos not shared with a store do not appear for those users. '
            'Assign required training when creating a new hire or via Assign task.'
        ),
    },
    {
        'title': 'Managing the onboarding checklist template',
        'audience': 'admin',
        'tags': 'checklist,template,onboarding tasks',
        'related_path': '/admin/checklist',
        'sort_order': 250,
        'body': (
            'Open Onboarding Tasks / checklist to define the checklist items managers track for each hire.\n\n'
            'Add, reorder, edit, or delete items. Per-hire progress is tracked under User Checklists.'
        ),
    },
    {
        'title': 'Managing per-user checklists and sending finale',
        'audience': 'admin',
        'tags': 'user checklists,finale,completion,message',
        'related_path': '/admin/user-checklists',
        'sort_order': 251,
        'body': (
            'Open User Checklists to update checklist completion for each hire.\n\n'
            'When onboarding work is done, send the completion (finale) message/document so the employee sees '
            'it on Home. Default finale text is configured under Onboarding Messages.'
        ),
    },
    {
        'title': 'Managing stores',
        'audience': 'admin',
        'tags': 'stores,locations,code',
        'related_path': '/admin/stores',
        'sort_order': 260,
        'body': (
            'Open Manage Stores to add, edit, or remove locations and store codes.\n\n'
            'Store assignment scopes managers, new hires, documents, and training visibility. '
            'Dashboard store rows link into filtered new-hire lists.'
        ),
    },
    {
        'title': 'Managing departments',
        'audience': 'admin',
        'tags': 'departments,hire,org',
        'related_path': '/admin/departments',
        'sort_order': 261,
        'body': (
            'Open Manage Departments to maintain the department list used when creating new hires.\n\n'
            'Keep names accurate so hire records and reporting stay consistent.'
        ),
    },
    {
        'title': 'Managing positions and default documents',
        'audience': 'admin',
        'tags': 'roles,positions,titles,default documents',
        'related_path': '/admin/roles',
        'sort_order': 262,
        'body': (
            'Open Manage Position/Title (roles) to define job titles used in onboarding.\n\n'
            'Set default documents per role so Start Onboarding can pre-select the right forms for that position.'
        ),
    },
    {
        'title': 'Viewing reports',
        'audience': 'admin',
        'tags': 'reports,progress,training,completion,status',
        'related_path': '/admin/reports',
        'sort_order': 270,
        'body': (
            'Open Reports for summaries of hires, users, documents, training completion, checklists, and per-hire progress.\n\n'
            'Use reports for leadership status views. Day-to-day follow-up still happens from New hires and hire details.'
        ),
    },
    {
        'title': 'Background jobs',
        'audience': 'admin',
        'tags': 'jobs,queue,email,stuck,requeue',
        'related_path': '/admin/jobs',
        'sort_order': 271,
        'body': (
            'Open Background Jobs to inspect queued, running, or failed jobs (for example emails or async work).\n\n'
            'If something seems stuck, review the job details and requeue when appropriate.'
        ),
    },
    {
        'title': 'Managing External Links',
        'audience': 'admin',
        'tags': 'external links,sidebar,quick links',
        'related_path': '/admin/external-links',
        'sort_order': 280,
        'body': (
            'Open External Links to add, edit, reorder, activate/deactivate, or delete links shown on the employee Home sidebar.\n\n'
            'Only active links appear for users. You can attach icons/images where supported.'
        ),
    },
    {
        'title': 'Configuring onboarding messages',
        'audience': 'admin',
        'tags': 'welcome,finale,email,messages,onboarding',
        'related_path': '/admin/onboarding-messages',
        'sort_order': 281,
        'body': (
            'Open Onboarding Messages to set the Welcome headline and body, the default finale (completion) message '
            'and optional document, and the all-tasks-completed email subject and body.\n\n'
            'These drive what new hires see after login, on Home when finished, and in completion emails.'
        ),
    },
    {
        'title': 'Managing Help articles',
        'audience': 'admin',
        'tags': 'help,articles,howto,publish',
        'related_path': '/admin/help',
        'sort_order': 290,
        'body': (
            'Open Help Articles to create or edit how-to content.\n\n'
            'Set audience (everyone, users, managers, or admins). For manager topics, optionally set a permission key '
            'so only managers with that permission see the article. Add tags and a related page path when useful.\n\n'
            'Unpublished articles stay hidden from non-admins.'
        ),
    },
    {
        'title': 'Asana Feedback inbox',
        'audience': 'admin',
        'tags': 'asana,feedback,inbox',
        'related_path': '/admin/asana/feedback',
        'sort_order': 292,
        'body': (
            'Feedback submitted from the app may create Asana tasks for the team.\n\n'
            'Use the Asana Feedback admin area to review connection status and related feedback. '
            'If tasks fail to create, reconnect Asana or check the saved feedback message.'
        ),
    },
]


_RETIRED_SEED_TITLES = (
    'Asking a help question',
    'Answering Help requests',
)


def ensure_seed_help_articles() -> int:
    """Insert missing seed articles; refresh body/metadata for system-authored ones.

    Returns number of rows created or updated.
    """
    changed = 0
    try:
        HelpArticle.query.limit(1).all()
    except Exception:
        db.session.rollback()
        return 0

    for title in _RETIRED_SEED_TITLES:
        retired = HelpArticle.query.filter(
            or_(HelpArticle.title == title, HelpArticle.slug == slugify(title))
        ).filter_by(created_by='system').all()
        for article in retired:
            if article.is_published:
                article.is_published = False
                changed += 1

    for item in _SEED_ARTICLES:
        title = item['title']
        slug = slugify(title)
        existing = HelpArticle.query.filter(
            or_(HelpArticle.slug == slug, HelpArticle.title == title)
        ).first()
        payload = dict(
            title=title,
            slug=slug,
            body=item['body'],
            audience=item.get('audience') or 'all',
            permission_key=item.get('permission_key'),
            related_path=item.get('related_path'),
            tags=item.get('tags'),
            is_published=True,
            sort_order=int(item.get('sort_order') or 0),
        )
        if existing is None:
            article = HelpArticle(created_by='system', **payload)
            # Avoid slug clash if another article already took this slug
            article.slug = unique_slug(title)
            db.session.add(article)
            changed += 1
        elif (existing.created_by or '') == 'system':
            for key, value in payload.items():
                if key == 'slug':
                    continue
                setattr(existing, key, value)
            changed += 1
    if not changed:
        return 0
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return 0
    return changed


def seed_help_articles_if_empty() -> int:
    """Backward-compatible alias used by migrations."""
    return ensure_seed_help_articles()
