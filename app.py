"""
Onboarding App - Main Flask Application
Email + password login with Admin and User roles
"""
from flask import Flask, render_template_string, redirect, url_for, request, flash, jsonify, send_file, send_from_directory, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import exists, or_, text
from auth import login_required, admin_required, User, check_user_can_login_as_admin, authenticate_by_email_password
from models import (db, NewHire, User as UserModel, Document, ChecklistItem, NewHireChecklist,
                    TrainingVideo, QuizQuestion, QuizAnswer, UserTrainingProgress, UserQuizResponse, UserTask,
                    DocumentSignatureField, DocumentSignature, DocumentTypedField, DocumentTypedFieldValue, DocumentAssignment, UserNotification, ExternalLink, Role, AdminSetting)
from membership import get_token_groups, get_local_groups
from config import SECRET_KEY, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_ENGINE_OPTIONS, BASE_DIR, \
    MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USE_SSL, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash
from io import BytesIO
import base64
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except (ImportError, Exception):
    PDF2IMAGE_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from pyhanko.sign import signers, fields
    from pyhanko.sign.timestamps import HTTPTimeStamper
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    import hashlib
    PYHANKO_AVAILABLE = True
except ImportError:
    PYHANKO_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = SQLALCHEMY_ENGINE_OPTIONS
app.config['UPLOAD_FOLDER'] = BASE_DIR / 'uploads'
app.config['VIDEO_UPLOAD_FOLDER'] = BASE_DIR / 'uploads' / 'videos'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size (for videos)
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'svg'}
app.config['ALLOWED_VIDEO_EXTENSIONS'] = {'mp4', 'webm', 'ogg', 'mov', 'avi'}

# HTTPS/Security Configuration
# Enable secure cookies when HTTPS is available (detected via request headers)
# IIS passes X-Forwarded-Proto header when HTTPS is enabled
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configure secure cookies based on request scheme
# This will be set dynamically in a before_request handler
@app.before_request
def configure_secure_cookies():
    """Configure secure cookies based on request scheme"""
    # Check if request is HTTPS (via IIS X-Forwarded-Proto header or direct HTTPS)
    is_https = (
        request.headers.get('X-Forwarded-Proto', '').lower() == 'https' or
        request.scheme == 'https' or
        request.is_secure
    )
    app.config['SESSION_COOKIE_SECURE'] = is_https
    app.config['PREFERRED_URL_SCHEME'] = 'https' if is_https else 'http'

# Mail (optional - only if MAIL_USERNAME/MAIL_PASSWORD set)
try:
    from flask_mail import Mail, Message
    app.config['MAIL_SERVER'] = MAIL_SERVER
    app.config['MAIL_PORT'] = MAIL_PORT
    app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
    app.config['MAIL_USE_SSL'] = MAIL_USE_SSL
    app.config['MAIL_USERNAME'] = MAIL_USERNAME
    app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
    app.config['MAIL_DEFAULT_SENDER'] = MAIL_DEFAULT_SENDER
    mail = Mail(app)
    MAIL_AVAILABLE = bool(MAIL_USERNAME and MAIL_PASSWORD)
except Exception:
    mail = None
    MAIL_AVAILABLE = False

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


def get_email_for_username(username):
    """Get best available email for a username (NewHire first, then User)."""
    new_hire = NewHire.query.filter_by(username=username).first()
    if new_hire and getattr(new_hire, 'email', None) and new_hire.email.strip():
        return new_hire.email.strip()
    user = UserModel.query.filter_by(username=username).first()
    if user and getattr(user, 'full_name', None):
        pass  # keep checking email
    if user and getattr(user, 'email', None) and user.email and str(user.email).strip():
        return str(user.email).strip()
    return None


def send_email(to_email, subject, body_html, body_text=None):
    """Send an email. No-op if mail not configured or send fails."""
    if not MAIL_AVAILABLE or not to_email or not to_email.strip():
        return False
    try:
        msg = Message(
            subject=subject,
            recipients=[to_email.strip()],
            body=body_text or body_html.replace('<br>', '\n').replace('</p>', '\n'),
            html=body_html
        )
        mail.send(msg)
        return True
    except Exception as e:
        app.logger.warning(f"Email send failed to {to_email}: {e}")
        return False


_users_access_revoked_at_migrated = False


def _ensure_users_access_revoked_at_column():
    """Ensure users.access_revoked_at exists (one-time migration). Prevents 500 on load_user and index."""
    global _users_access_revoked_at_migrated
    if _users_access_revoked_at_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 access_revoked_at FROM users"))
        _users_access_revoked_at_migrated = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE users ADD access_revoked_at DATE NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        _users_access_revoked_at_migrated = True


_new_hires_finale_migrated = False


def _ensure_new_hires_finale_columns():
    """Ensure new_hires has finale_message, finale_message_sent_at, finale_document_id, finale_message_dismissed_at."""
    global _new_hires_finale_migrated
    if _new_hires_finale_migrated:
        return
    for col, sql_type in [
        ('finale_message', 'NVARCHAR(MAX) NULL'),
        ('finale_message_sent_at', 'DATETIME NULL'),
        ('finale_document_id', 'INT NULL'),
        ('finale_message_dismissed_at', 'DATETIME NULL'),
    ]:
        try:
            db.session.execute(text(f"SELECT TOP 1 {col} FROM new_hires"))
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text(f"ALTER TABLE new_hires ADD {col} {sql_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    _new_hires_finale_migrated = True


_admin_settings_table_migrated = False


def _ensure_admin_settings_table():
    """Create admin_settings table if it does not exist."""
    global _admin_settings_table_migrated
    if _admin_settings_table_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 key FROM admin_settings"))
        _admin_settings_table_migrated = True
        return
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text(
            "CREATE TABLE admin_settings (key NVARCHAR(100) PRIMARY KEY, value NVARCHAR(MAX) NULL)"
        ))
        db.session.commit()
        _admin_settings_table_migrated = True
    except Exception as e:
        db.session.rollback()
        app.logger.warning("admin_settings table create failed: %s", e)
        # Do not set migrated=True so we retry on next request


@app.before_request
def _run_users_migration_if_needed():
    """Run one-time migration for users.access_revoked_at, new_hires finale columns, admin_settings before any request."""
    if request.path.startswith('/static'):
        return
    try:
        _ensure_users_access_revoked_at_column()
        _ensure_new_hires_finale_columns()
        _ensure_admin_settings_table()
    except Exception:
        pass


@login_manager.user_loader
def load_user(user_id):
    """Load user from session (user_id is username)."""
    try:
        user_record = UserModel.query.filter_by(username=user_id).first()
    except Exception:
        db.session.rollback()
        _ensure_users_access_revoked_at_column()
        try:
            user_record = UserModel.query.filter_by(username=user_id).first()
        except Exception:
            return None
    if not user_record:
        return None
    return User(user_record.username, user_record.domain, user_record.role)


@app.before_request
def check_authentication():
    """Redirect unauthenticated users to login (no Windows auto-login)."""
    if request.path.startswith('/static'):
        return
    if request.path in ('/login', '/logout', '/'):
        return
    if not current_user.is_authenticated:
        return redirect(url_for('login', next=request.url))


def update_last_login(username):
    """Update last_login for user after successful login."""
    try:
        user_record = UserModel.query.filter_by(username=username).first()
        if user_record:
            user_record.last_login = datetime.utcnow()
            db.session.commit()
    except Exception:
        db.session.rollback()


# Database tables are created using init_db.py script
# Run: python init_db.py to create tables

# Helper functions
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def allowed_video_file(filename):
    """Check if video file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_VIDEO_EXTENSIONS']


# Routes
@app.route('/')
def index():
    """Home: redirect to dashboard if logged in, else to login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login with email and password."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    next_url = request.args.get('next') or url_for('dashboard')
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        user = authenticate_by_email_password(email, password)
        if user:
            login_user(user, remember=True)
            update_last_login(user.username)
            next_after = request.form.get('next') or request.args.get('next') or url_for('dashboard')
            return redirect(next_after)
        flash('Invalid email or password. Please try again.', 'error')
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Log in - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #1a1a1a;
            }
            .login-box {
                background: #fff;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                width: 100%;
                max-width: 400px;
            }
            h1 {
                color: #000;
                font-weight: 800;
                margin-bottom: 8px;
                font-size: 1.5rem;
            }
            .subtitle { color: #666; font-size: 0.9rem; margin-bottom: 24px; }
            .form-group { margin-bottom: 20px; }
            .form-group label {
                display: block;
                font-weight: 600;
                color: #333;
                margin-bottom: 6px;
                font-size: 0.9rem;
            }
            .form-group input {
                width: 100%;
                padding: 12px 14px;
                border: 1px solid #ccc;
                border-radius: 6px;
                font-size: 1rem;
            }
            .form-group input:focus {
                outline: none;
                border-color: #FE0100;
                box-shadow: 0 0 0 2px rgba(254,1,0,0.2);
            }
            .btn-login {
                width: 100%;
                padding: 14px;
                background: #FE0100;
                color: #fff;
                border: none;
                border-radius: 6px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                font-family: inherit;
            }
            .btn-login:hover { background: #d90000; }
            .alert {
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-size: 0.9rem;
            }
            .alert-error { background: #fee; color: #c33; border: 1px solid #fcc; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>Ziebart Onboarding</h1>
            <p class="subtitle">Sign in with your email</p>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, msg in messages %}
                    <div class="alert alert-{{ category }}">{{ msg }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST" action="{{ url_for('login') }}">
                <input type="hidden" name="next" value="{{ next_url }}">
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required autocomplete="email" placeholder="you@company.com">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password" placeholder="••••••••">
                </div>
                <button type="submit" class="btn-login">Log in</button>
            </form>
        </div>
    </body>
    </html>
    ''')


@app.route('/logout')
@login_required
def logout():
    """Logout and redirect to login."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


def is_signature_field_signed(document_id, field, username):
    """
    Check if a signature field is signed by a user.
    Handles cases where the field was deleted and recreated by checking:
    1. Signatures with matching signature_field_id
    2. Signatures with null signature_field_id that match field location (within tolerance)
    """
    # First check for signature with matching field ID
    if field.id:
        sig = DocumentSignature.query.filter_by(
            document_id=document_id,
            signature_field_id=field.id,
            username=username
        ).first()
        if sig:
            return True
    
    # If no match by ID, check for signatures with null field_id that match location
    # Use a tolerance of 10 pixels for position matching (in case field was slightly moved)
    # Check if new columns exist (handle case where database hasn't been migrated yet)
    try:
        # Try to query for orphaned signatures - this might fail if columns don't exist
        tolerance = 10.0
        try:
            orphaned_sigs = DocumentSignature.query.filter_by(
                document_id=document_id,
                username=username
            ).filter(DocumentSignature.signature_field_id.is_(None)).all()
        except Exception:
            # If query fails (columns don't exist), return False
            return False
        
        for sig in orphaned_sigs:
            # Safely access new fields (may not exist if database not migrated)
            try:
                field_page = getattr(sig, 'field_page_number', None)
                field_x = getattr(sig, 'field_x_position', None)
                field_y = getattr(sig, 'field_y_position', None)
                
                if (field_page == field.page_number and
                    field_x is not None and field_y is not None and
                    abs(field_x - field.x_position) <= tolerance and
                    abs(field_y - field.y_position) <= tolerance):
                    return True
            except (AttributeError, Exception):
                # If accessing fields fails, skip this signature
                continue
    except Exception:
        # If anything fails, just return False (no orphaned signature match)
        pass
    
    return False


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
        
        incomplete_training = [v for v in required_videos if v.id not in completed_required_videos]
        
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
                        # Check if all required signature fields are signed
                        try:
                            required_fields = DocumentSignatureField.query.filter_by(
                                document_id=task.document_id,
                                is_required=True
                            ).all()
                            
                            if required_fields:
                                # Check if all required fields are signed (using helper to handle deleted fields)
                                try:
                                    all_signed = all(is_signature_field_signed(task.document_id, f, current_user.username) for f in required_fields)
                                    
                                    if all_signed and task.status != 'completed':
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
                                        assignment.is_completed = all_signed
                                        if all_signed and not assignment.completed_at:
                                            assignment.completed_at = datetime.utcnow()
                                        db.session.commit()
                                except Exception as e:
                                    # If checking signatures fails, skip this task
                                    continue
                        except Exception as e:
                            # If getting required fields fails, skip this task
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
        # Filter out completed tasks for dashboard display
        user_tasks = [t for t in all_user_tasks if t.status != 'completed']
        completed_user_tasks = [t for t in all_user_tasks if t.status == 'completed']
        
        # Check if all tasks are completed
        all_tasks_completed = (len(incomplete_training) == 0 and len(user_tasks) == 0) if (required_videos or all_user_tasks) else False
        
        # Calculate progress percentage (training videos + user tasks)
        total_training_tasks = len(required_videos)
        completed_training_tasks = len(completed_required_videos)
        total_user_tasks = len(all_user_tasks)
        completed_user_tasks_count = len(completed_user_tasks)
        
        # Total tasks = training videos + user tasks
        total_tasks = total_training_tasks + total_user_tasks
        completed_tasks = completed_training_tasks + completed_user_tasks_count
        progress_percentage = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
        
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
                    task_url = url_for('sign_document', doc_id=task.document_id) if (task.task_type == 'document' and task.document_id) else url_for('user_tasks')
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
        
        # Get all training videos (for the training videos section)
        try:
            all_videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.created_at.desc()).limit(6).all()
        except Exception as e:
            all_videos = []
        
        # Get visible documents
        # Only show assigned documents to users (not just visible ones)
        assigned_doc_ids = set()
        try:
            if not is_admin:
                assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
                assigned_doc_ids = set(a.document_id for a in assigned_documents)
                if assigned_doc_ids:
                    visible_documents = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.created_at.desc()).limit(3).all()
                else:
                    visible_documents = []
            else:
                visible_documents = Document.query.filter_by(is_visible=True).order_by(Document.created_at.desc()).limit(3).all()
        except Exception as e:
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

        # Finale message from admin (show in center of page when set and not dismissed)
        show_finale = False
        finale_message = ''
        finale_document = None
        if user_new_hire:
            msg = getattr(user_new_hire, 'finale_message', None)
            sent_at = getattr(user_new_hire, 'finale_message_sent_at', None)
            dismissed_at = getattr(user_new_hire, 'finale_message_dismissed_at', None)
            if msg and sent_at and not dismissed_at:
                show_finale = True
                finale_message = msg
                doc_id = getattr(user_new_hire, 'finale_document_id', None)
                if doc_id:
                    try:
                        finale_document = Document.query.get(int(doc_id))
                    except Exception:
                        finale_document = None

        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            html, body {
                width: 100%;
                min-width: 100%;
                margin: 0;
                padding: 0;
                overflow-x: hidden;
            }
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                font-family: 'URW Form', Arial, sans-serif;
                transition: color 0.2s;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .notification-icon {
                font-size: 1.3em;
                cursor: pointer;
                position: relative;
                color: #ffffff;
            }
            .notification-dropdown {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 350px;
                max-width: 400px;
                max-height: 500px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .notification-dropdown.show {
                display: block;
            }
            .notification-header {
                padding: 15px 20px;
                border-bottom: 1px solid #eee;
                background: #f8f9fa;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .notification-header h3 {
                font-size: 1em;
                font-weight: 600;
                color: #000000;
                margin: 0;
            }
            .notification-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .notification-item {
                padding: 15px 20px;
                border-bottom: 1px solid #f0f0f0;
                cursor: pointer;
                transition: background 0.2s;
            }
            .notification-item:hover {
                background: #f8f9fa;
            }
            .notification-item:last-child {
                border-bottom: none;
            }
            .notification-item.unread {
                background: #e7f3ff;
            }
            .notification-item.unread:hover {
                background: #d0e7ff;
            }
            .notification-title {
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 5px;
                font-size: 0.95em;
            }
            .notification-message {
                font-family: 'URW Form', Arial, sans-serif;
                color: #808080;
                font-size: 0.85em;
                line-height: 1.4;
            }
            .notification-empty {
                padding: 40px 20px;
                text-align: center;
                color: #999;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .dropdown-divider {
                height: 1px;
                background: #eee;
            }
            /* Wrapper so hero can "break out" to full viewport width */
            .dashboard-view {
                max-width: 1200px;
                margin: 0 auto;
                width: 100%;
            }
            .dashboard-container {
                max-width: 1200px;
                margin: 0 auto;
                width: 100%;
            }
            /* Full-bleed welcome bar: 100vw + negative margin so it spans edge-to-edge */
            .dashboard-hero-full {
                width: 100vw;
                max-width: none;
                margin: 0;
                padding: 0;
                margin-left: calc(50% - 50vw);
                background: #e5e5e5;
                box-sizing: border-box;
            }
            .dashboard-hero-banner {
                width: 100%;
                max-width: 2000px;
                margin: 0 auto;
                padding: 40px 20px 48px;
                color: #333;
                position: relative;
                overflow: hidden;
                background: transparent;
            }
            .dashboard-hero-banner .hero-confetti-bg {
                position: absolute;
                inset: 0;
                z-index: 0;
            }
            .dashboard-hero-banner .hero-confetti-bg img,
            .dashboard-hero-banner .hero-confetti-bg video {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .dashboard-hero-banner .hero-overlay {
                position: absolute;
                inset: 0;
                background: rgba(0,0,0,0.35);
                z-index: 1;
            }
            .dashboard-hero-banner .hero-inner {
                position: relative;
                z-index: 2;
                text-align: left;
            }
            .dashboard-hero-banner .hero-title {
                font-size: 2.2em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #fff;
                margin: 0 0 8px;
                line-height: 1.2;
            }
            .dashboard-hero-banner .hero-subtitle {
                font-size: 1.1em;
                color: rgba(255,255,255,0.9);
                margin: 0;
                font-weight: 400;
            }
            .dashboard-page-wrap {
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 20px 24px;
            }
            .main-content {
                display: grid;
                grid-template-columns: 1fr 320px;
                gap: 24px;
                align-items: start;
                margin-top: -24px;
                position: relative;
                z-index: 2;
            }
            .main-content.main-content-two-col {
                grid-template-columns: 1fr;
            }
            .dashboard-tasks-col {
                min-width: 0;
            }
            .dashboard-tasks-card,
            .dashboard-card {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                min-height: 280px;
                max-height: min(520px, 70vh);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .dashboard-card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 12px;
                margin-bottom: 12px;
            }
            .dashboard-tasks-card .section-title,
            .dashboard-card .section-title {
                margin-bottom: 0;
                flex-shrink: 0;
            }
            .dashboard-tasks-card .progress-bar-container {
                flex-shrink: 0;
                margin-bottom: 12px;
            }
            .dashboard-tasks-card .task-cards {
                overflow-y: auto;
                flex: 1;
                min-height: 0;
            }
            .section-title-dash {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 12px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
            }
            .dashboard-cta-link {
                padding: 8px 16px;
                background: rgba(254,1,0,0.12);
                color: #FE0100;
                text-decoration: none;
                border-radius: 0.5rem;
                font-size: 0.9em;
                font-weight: 600;
                white-space: nowrap;
            }
            .dashboard-cta-link:hover {
                background: #FE0100;
                color: #fff;
            }
            .sidebar-right {
                min-width: 0;
            }
            .sidebar-right .section {
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                padding: 1.5rem;
                min-height: 280px;
                max-height: min(520px, 70vh);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .sidebar-right .section-title-dash {
                margin-bottom: 16px;
            }
            .sidebar-right .quick-links {
                overflow-y: auto;
                flex: 1;
                min-height: 0;
            }
            @keyframes heroFadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes heroGradientShift {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.96; }
            }
            @keyframes heroBarShine {
                0%, 100% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
            }
            @keyframes heroBadgePulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.9; transform: scale(1.02); }
            }
            .welcome-section {
                text-align: center;
                margin-bottom: 40px;
            }
            .welcome-section h1 {
                font-size: 3em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 10px;
            }
            .welcome-section p {
                font-size: 1.2em;
                font-family: 'URW Form', Arial, sans-serif;
                color: #808080;
                font-weight: 400;
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .progress-bar-container {
                background: #e9ecef;
                height: 30px;
                border-radius: 15px;
                overflow: hidden;
                margin-bottom: 25px;
            }
            .progress-bar-fill {
                background: linear-gradient(90deg, #FE0100 0%, #cc0000 100%);
                height: 100%;
                transition: width 0.3s;
            }
            .task-cards {
                display: grid;
                gap: 15px;
            }
            .task-card {
                background: #ffffff;
                border-radius: 0.5rem;
                padding: 20px;
                display: flex;
                align-items: center;
                gap: 15px;
                border-left: 4px solid #dc3545;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .task-icon {
                font-size: 2em;
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: white;
                border-radius: 0.5rem;
            }
            .task-content {
                flex: 1;
            }
            .task-content h3 {
                font-size: 1.1em;
                margin-bottom: 5px;
                color: #000000;
            }
            .task-content p {
                color: #808080;
                font-size: 0.9em;
            }
            .task-btn {
                padding: 12px 24px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                font-size: 1em;
                font-weight: 600;
                font-family: 'URW Form', Arial, sans-serif;
                transition: background 0.2s;
            }
            .task-btn:hover {
                background: #FE0100;
            }
            .videos-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 20px;
            }
            .video-card {
                background: #f8f9fa;
                border-radius: 0.5rem;
                overflow: hidden;
            }
            .video-thumbnail {
                width: 100%;
                height: 160px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 3em;
            }
            .video-info {
                padding: 15px;
            }
            .video-info h3 {
                font-size: 1em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 10px;
                color: #000000;
            }
            .video-btn {
                display: block;
                width: 100%;
                padding: 12px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                text-align: center;
                font-size: 1em;
                font-weight: 600;
                transition: background 0.2s;
            }
            .video-btn:hover {
                background: #FE0100;
            }
            .quick-links {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            .quick-link {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 15px;
                text-decoration: none;
                color: #000000;
                padding: 15px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                transition: all 0.2s;
            }
            .quick-link:hover {
                transform: translateX(5px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
            }
            .quick-link-icon {
                width: 80px;
                height: 80px;
                background: #ffffff;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.5em;
                overflow: hidden;
                flex-shrink: 0;
                border: 1px solid #e0e0e0;
                padding: 8px;
            }
            .quick-link-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                background: #ffffff;
            }
            .quick-link-content {
                flex: 1;
            }
            .quick-link-text {
                font-size: 1.1em;
                font-weight: 600;
                text-align: left;
                color: #000000;
                margin-bottom: 4px;
            }
            .quick-link-description {
                font-size: 0.9em;
                color: #808080;
                text-align: left;
            }
            /* Mobile Menu Toggle */
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
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
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 10px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .notification-icon {
                    font-size: 1.2em;
                }
                .notification-dropdown {
                    min-width: 280px;
                    max-width: 90vw;
                    right: -10px;
                }
                .dashboard-page-wrap {
                    padding: 0 15px 20px;
                }
                .dashboard-hero-banner {
                    padding: 28px 20px 36px;
                }
                .dashboard-hero-banner .hero-title {
                    font-size: 1.75em;
                }
                .dashboard-hero-banner .hero-subtitle {
                    font-size: 1em;
                }
                .main-content {
                    grid-template-columns: 1fr;
                    margin-top: -20px;
                    gap: 20px;
                }
                .dashboard-tasks-card {
                    max-height: none;
                }
                .sidebar-right {
                    order: -1;
                }
                .welcome-section h1 {
                    font-size: 2em;
                }
                .welcome-section p {
                    font-size: 1em;
                }
                .section {
                    padding: 1.5rem;
                    margin-bottom: 20px;
                }
                .section-title {
                    font-size: 1.3em;
                }
                .videos-grid {
                    grid-template-columns: 1fr;
                    gap: 15px;
                }
                .task-card {
                    flex-direction: column;
                    align-items: stretch;
                    gap: 15px;
                }
                .task-btn {
                    width: 100%;
                    text-align: center;
                }
                .quick-link {
                    padding: 12px;
                }
                .quick-link-icon {
                    width: 60px;
                    height: 60px;
                    font-size: 2em;
                }
                .quick-link-text {
                    font-size: 1em;
                }
                .quick-link-description {
                    font-size: 0.85em;
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
                .welcome-section h1 {
                    font-size: 1.5em;
                }
                .section {
                    padding: 1rem;
                }
                .section-title {
                    font-size: 1.2em;
                }
                .task-card {
                    padding: 15px;
                }
                .btn, .task-btn, .video-btn {
                    padding: 12px 16px;
                    font-size: 0.95em;
                    min-height: 44px;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="mobile-nav" id="mobileNav">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="notification-icon" style="position: relative;" onclick="toggleNotificationDropdown(event)">
                    🔔
                    {% if pending_count > 0 %}
                    <span class="notification-badge" id="notificationBadge" style="position: absolute; top: -5px; right: -5px; background: #FE0100; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 0.7em; font-weight: bold;">{{ pending_count }}</span>
                    {% endif %}
                    <div class="notification-dropdown" id="notificationDropdown">
                        <div class="notification-header">
                            <h3>Notifications</h3>
                            <button onclick="markAllAsRead()" style="background: none; border: none; color: #FE0100; cursor: pointer; font-size: 0.85em; padding: 0;">Mark all read</button>
                        </div>
                        <div class="notification-list">
                            {% if notifications %}
                                {% for notification in notifications %}
                                <div class="notification-item {% if not notification.is_read %}unread{% endif %}" onclick="handleNotificationClick({{ notification.id }}, '{{ notification.type }}', '{{ notification.url }}', event)">
                                    <div class="notification-title">{{ notification.title }}</div>
                                    <div class="notification-message">{{ notification.message }}</div>
                                </div>
                                {% endfor %}
                            {% else %}
                                <div class="notification-empty">
                                    <p>No new notifications</p>
                                </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_first_name[0].upper() if user_first_name else 'U' }}</div>
                    <span>{{ user_full_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="dashboard-view">
        <div class="dashboard-hero-full">
            <div class="dashboard-hero-banner">
                {% if hero_media_url %}
                <div class="hero-confetti-bg">
                    {% if hero_media_type == 'video' %}
                    <video src="{{ hero_media_url }}" autoplay loop muted playsinline></video>
                    {% else %}
                    <img src="{{ hero_media_url }}" alt="" />
                    {% endif %}
                </div>
                <div class="hero-overlay"></div>
                {% endif %}
                <div class="hero-inner">
                    <h1 class="hero-title">Congrats on getting hired, {{ user_first_name }}!</h1>
                    <p class="hero-subtitle">Complete your tasks below to continue onboarding.</p>
                </div>
            </div>
        </div>

        <div class="dashboard-container">
        <div class="dashboard-page-wrap">
            <div class="main-content{% if not external_links %} main-content-two-col{% endif %}">
                {% if show_finale %}
                <div class="dashboard-tasks-col">
                    <div class="section dashboard-tasks-card" style="text-align: center; padding: 48px 40px; min-height: 400px; display: flex; flex-direction: column; justify-content: center; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 2px solid #28a745;">
                        <h2 class="section-title-dash" style="font-size: 1.75em; margin-bottom: 20px;">🎉 Message for you</h2>
                        <div style="white-space: pre-wrap; text-align: center; font-size: 1.2em; line-height: 1.75; color: #333; margin-bottom: 24px;">{{ finale_message }}</div>
                        {% if finale_document %}
                        <p style="margin-bottom: 0;">
                            <a href="{{ url_for('view_document_embed', doc_id=finale_document.id) }}" target="_blank" style="display: inline-block; padding: 12px 24px; background: #FE0100; color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">📄 {{ finale_document.name_for_users or finale_document.original_filename }}</a>
                        </p>
                        {% endif %}
                    </div>
                </div>
                {% else %}
                <div class="dashboard-tasks-col">
                    {% if required_videos or user_tasks %}
                    <div class="section dashboard-tasks-card">
                        <div class="dashboard-card-header">
                            <h2 class="section-title-dash">Tasks</h2>
                            <a href="{{ url_for('user_tasks') }}" class="dashboard-cta-link">Complete items &gt;</a>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <div class="progress-bar-container" style="flex: 1; min-width: 0;">
                                <div class="progress-bar-fill" style="width: {{ progress_percentage }}%;"></div>
                            </div>
                            <span style="font-size: 0.9em; font-weight: 600; color: #333; flex-shrink: 0;">{{ progress_percentage }}%</span>
                        </div>
                        <div style="text-align: center; margin-top: 8px; color: #808080; font-size: 0.85em; flex-shrink: 0;">
                        {{ completed_tasks }} of {{ total_tasks }} tasks completed
                    </div>
                    
                    {% if incomplete_training or user_tasks %}
                    <div class="task-cards">
                        {% for video in incomplete_training %}
                        <div class="task-card">
                            <div class="task-icon">▶️</div>
                            <div class="task-content">
                                <h3>{{ video.title }}</h3>
                                <p>Complete required training video</p>
                            </div>
                            <a href="{{ url_for('view_training_video', video_id=video.id) }}" class="task-btn">Start ></a>
                        </div>
                        {% endfor %}
                        {% for task in user_tasks %}
                        <div class="task-card">
                            <div class="task-icon">
                                {% if task.task_type == 'document' %}
                                ✍️
                                {% else %}
                                📋
                                {% endif %}
                            </div>
                            <div class="task-content">
                                <h3>{{ task.task_title }}</h3>
                                <p>{{ task.task_description or 'Complete this task' }}</p>
                            </div>
                            {% if task.task_type == 'document' and task.document_id %}
                            <a href="{{ url_for('sign_document', doc_id=task.document_id) }}" class="task-btn">Sign Document ></a>
                            {% else %}
                            <a href="{{ url_for('user_tasks') }}" class="task-btn">View Task ></a>
                            {% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 40px 20px; color: #28a745;">
                        <div style="font-size: 3em; margin-bottom: 15px;">✓</div>
                        <h3 style="font-size: 1.5em; margin-bottom: 10px; color: #000000; font-weight: 800; font-family: 'URW Form', Arial, sans-serif;">All Tasks Completed!</h3>
                        <p style="color: #808080; font-size: 1.1em;">Great job! You've completed all your onboarding tasks.</p>
                    </div>
                    {% endif %}
                </div>
                {% else %}
                <div class="section dashboard-card">
                    <h2 class="section-title-dash">Tasks</h2>
                    <p style="color: #808080; font-size: 0.95em;">No tasks assigned yet. Check back soon or contact HR.</p>
                </div>
                {% endif %}
                </div>
                {% endif %}
            
                {% if external_links %}
                <div class="sidebar-right">
                    <div class="section">
                        <h2 class="section-title-dash">External Links</h2>
                    <div class="quick-links">
                        {% for link in external_links %}
                        <a href="{{ link.url }}" target="_blank" rel="noopener noreferrer" class="quick-link">
                            <div class="quick-link-icon">
                                {% if link.image_filename %}
                                <img src="{{ url_for('serve_quick_link_image', filename=link.image_filename) }}" alt="{{ link.title }}">
                                {% elif link.icon and link.icon != '??' %}
                                {{ link.icon }}
                                {% elif link.title and ('mobile' in link.title|lower or 'app' in link.title|lower) %}
                                📱
                                {% else %}
                                🔗
                                {% endif %}
                            </div>
                            <div class="quick-link-content">
                                <div class="quick-link-text">{{ link.title }}</div>
                                {% if link.description %}
                                <div class="quick-link-description">{{ link.description }}</div>
                                {% endif %}
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </div>
                {% endif %}
            </div>
        </div>
        </div>
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            function toggleNotificationDropdown(event) {
                event.stopPropagation();
                var dropdown = document.getElementById('notificationDropdown');
                dropdown.classList.toggle('show');
            }
            
            function handleNotificationClick(notificationId, notificationType, url, event) {
                if (event) {
                    event.stopPropagation();
                }
                // Mark notification as read
                fetch('/api/notifications/mark-read', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        notification_type: notificationType,
                        notification_id: String(notificationId)
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Update badge count immediately
                        updateNotificationBadge();
                        // Also remove the notification item from the dropdown
                        var clickedElement = event ? event.currentTarget : null;
                        if (clickedElement) {
                            clickedElement.classList.remove('unread');
                            // Remove after a short delay to show visual feedback
                            setTimeout(function() {
                                clickedElement.remove();
                                // Check if there are any notifications left
                                var notificationList = document.querySelector('.notification-list');
                                if (notificationList && notificationList.querySelectorAll('.notification-item').length === 0) {
                                    notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                                }
                            }, 100);
                        }
                    }
                    // Navigate to the notification URL (only if it's not the same page)
                    if (url && url !== window.location.pathname) {
                        window.location.href = url;
                    } else {
                        // If same page, just reload to refresh the notification count
                        setTimeout(function() {
                            window.location.reload();
                        }, 200);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    // Still navigate even if marking as read fails
                    if (url && url !== window.location.pathname) {
                        window.location.href = url;
                    } else {
                        window.location.reload();
                    }
                });
            }
            
            function markAllAsRead() {
                fetch('/api/notifications/mark-all-read', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Update badge count immediately
                        updateNotificationBadge();
                        // Update the notification list
                        var notificationList = document.querySelector('.notification-list');
                        if (notificationList) {
                            notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                        }
                        // Remove unread styling from any remaining items
                        var unreadItems = document.querySelectorAll('.notification-item.unread');
                        unreadItems.forEach(function(item) {
                            item.classList.remove('unread');
                        });
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
            
            function updateNotificationBadge() {
                fetch('/api/notifications/count')
                .then(response => response.json())
                .then(data => {
                    var badge = document.getElementById('notificationBadge');
                    if (data.count > 0) {
                        if (badge) {
                            badge.textContent = data.count;
                            badge.style.display = 'flex';
                        } else {
                            // Create badge if it doesn't exist
                            var icon = document.querySelector('.notification-icon');
                            if (icon) {
                                var newBadge = document.createElement('span');
                                newBadge.id = 'notificationBadge';
                                newBadge.className = 'notification-badge';
                                newBadge.textContent = data.count;
                                newBadge.style.cssText = 'position: absolute; top: -5px; right: -5px; background: #FE0100; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 0.7em; font-weight: bold;';
                                icon.appendChild(newBadge);
                            }
                        }
                    } else {
                        if (badge) {
                            badge.style.display = 'none';
                            badge.textContent = '0';
                        }
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
            
            function toggleMobileMenu() {
                var mobileNav = document.getElementById('mobileNav');
                if (mobileNav) {
                    mobileNav.classList.toggle('show');
                }
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.notification-icon')) {
                    var notifDropdown = document.getElementById('notificationDropdown');
                    if (notifDropdown && notifDropdown.classList.contains('show')) {
                        notifDropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.mobile-menu-toggle') && !event.target.closest('.mobile-nav')) {
                    var mobileNav = document.getElementById('mobileNav');
                    if (mobileNav && mobileNav.classList.contains('show')) {
                        mobileNav.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name,
         required_videos=required_videos, completed_required_videos=completed_required_videos,
         incomplete_training=incomplete_training, all_tasks_completed=all_tasks_completed,
         progress_percentage=progress_percentage, all_videos=all_videos, visible_documents=visible_documents,
         user_tasks=user_tasks, total_tasks=total_tasks, completed_tasks=completed_tasks,
         pending_count=pending_count, notifications=notifications, external_links=external_links,
         hero_media_url=hero_media_url, hero_media_type=hero_media_type,
         show_finale=show_finale, finale_message=finale_message, finale_document=finale_document)
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
        flash(f'Error loading dashboard: {str(e)}. Some data may be missing.', 'error')
        
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dashboard - Onboarding App</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: 'URW Form', Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                .error-box { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                .error-box strong { color: #856404; }
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
    """User tasks page - shows tasks assigned to the current user"""
    try:
        is_admin = current_user.is_admin()
        
        # Get tasks assigned to current user
        try:
            user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
                UserTask.priority.desc(),
                UserTask.due_date.asc(),
                UserTask.created_at.desc()
            ).all()
        except Exception as e:
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
                UserTask.priority.desc(),
                UserTask.due_date.asc(),
                UserTask.created_at.desc()
            ).all()
        except Exception as e:
            user_tasks = []
        
        # Check document tasks and update completion status
        for task in user_tasks:
            try:
                if task.task_type == 'document' and task.document_id:
                    try:
                        document = Document.query.get(task.document_id)
                        if document:
                            # Check if all required signature fields are signed
                            try:
                                required_fields = DocumentSignatureField.query.filter_by(
                                    document_id=task.document_id,
                                    is_required=True
                                ).all()
                                
                                if required_fields:
                                    # Check if all required fields are signed (using helper to handle deleted fields)
                                    try:
                                        all_signed = all(is_signature_field_signed(task.document_id, f, current_user.username) for f in required_fields)
                                        
                                        if all_signed and task.status != 'completed':
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
                                            assignment.is_completed = all_signed
                                            if all_signed and not assignment.completed_at:
                                                assignment.completed_at = datetime.utcnow()
                                            db.session.commit()
                                    except Exception as e:
                                        # If checking signatures fails, skip this task
                                        continue
                            except Exception as e:
                                # If getting required fields fails, skip this task
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
                UserTask.priority.desc(),
                UserTask.due_date.asc(),
                UserTask.created_at.desc()
            ).all()
        except Exception as e:
            user_tasks = []

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
        
        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>My Tasks - Onboarding App</title>
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                font-family: 'URW Form', Arial, sans-serif;
                transition: color 0.2s;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .nav-links a.active {
                color: #FE0100;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .dropdown-divider {
                height: 1px;
                background: #eee;
            }
            body { background: #f5f5f5; }
            .main-content {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px 20px;
            }
            .page-title {
                font-size: 2em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 8px;
            }
            .page-subtitle {
                color: #808080;
                font-size: 1em;
                margin-bottom: 24px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 24px;
            }
            .stat-card {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
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
            .task-section {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                margin-bottom: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .section-title-dash {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
            }
            .section-title {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
                display: block;
            }
            .task-list {
                display: grid;
                gap: 15px;
            }
            .task-item {
                background: #ffffff;
                border-radius: 0.5rem;
                padding: 20px;
                border-left: 4px solid #FE0100;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .task-item:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            .task-item.completed {
                border-left-color: #28a745;
                opacity: 0.7;
            }
            .task-item.high-priority {
                border-left-color: #FE0100;
            }
            .task-item.urgent-priority {
                border-left-color: #FE0100;
                background: #fff5f5;
            }
            .task-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 10px;
            }
            .task-title {
                font-size: 1.1em;
                font-weight: 600;
                color: #000000;
                flex: 1;
            }
            .task-badges {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
            }
            .badge {
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.75em;
                font-weight: 500;
            }
            .badge-pending {
                background: #808080;
                color: white;
            }
            .badge-pending {
                background: #808080;
                color: white;
            }
            .badge-in-progress {
                background: #808080;
                color: white;
            }
            .badge-completed {
                background: #28a745;
                color: white;
            }
            .badge-priority {
                background: #FE0100;
                color: white;
            }
            .badge-type {
                background: #e7f3ff;
                color: #055160;
            }
            .task-description {
                color: #808080;
                margin-bottom: 15px;
                line-height: 1.5;
            }
            .task-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 0.85em;
                color: #999;
            }
            .task-actions {
                display: flex;
                gap: 10px;
            }
            .btn {
                padding: 8px 16px;
                border-radius: 0.5rem;
                text-decoration: none;
                font-size: 0.9em;
                font-weight: 500;
                cursor: pointer;
                border: none;
                transition: background 0.2s;
            }
            .btn-primary {
                background: #FE0100;
                color: white;
            }
            .btn-primary:hover {
                background: #FE0100;
            }
            .btn-success {
                background: #FE0100;
                color: white;
            }
            .btn-success:hover {
                background: #FE0100;
            }
            .btn-secondary {
                background: transparent;
                color: #FE0100;
                border: 2px solid #FE0100;
                border-radius: 0.5rem;
            }
            .btn-secondary:hover {
                background: #FE0100;
                color: white;
            }
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #999;
            }
            .empty-state-icon {
                font-size: 4em;
                margin-bottom: 20px;
            }
            /* Mobile Menu */
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
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
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 10px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .main-content {
                    padding: 20px 15px;
                }
                .page-title {
                    font-size: 2em;
                }
                .page-subtitle {
                    font-size: 1em;
                }
                .stats-grid {
                    grid-template-columns: repeat(2, 1fr);
                    gap: 15px;
                }
                .task-header {
                    flex-direction: column;
                    gap: 10px;
                }
                .task-badges {
                    width: 100%;
                }
                .task-actions {
                    flex-direction: column;
                    width: 100%;
                }
                .task-actions .btn {
                    width: 100%;
                    text-align: center;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
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
                .page-title {
                    font-size: 1.5em;
                }
                .stats-grid {
                    grid-template-columns: 1fr;
                }
                .task-item {
                    padding: 15px;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}" class="active">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="mobile-nav" id="mobileNav">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_first_name[0].upper() if user_first_name else 'U' }}</div>
                    <span>{{ user_full_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('dashboard') }}" class="dropdown-item">Dashboard</a>
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <h1 class="page-title">My Tasks</h1>
            <p class="page-subtitle">Tasks assigned to you</p>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{{ user_tasks|length }}</div>
                    <div class="stat-label">Total Tasks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{ pending_tasks|length }}</div>
                    <div class="stat-label">Pending</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{ in_progress_tasks|length }}</div>
                    <div class="stat-label">In Progress</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{ completed_tasks|length }}</div>
                    <div class="stat-label">Completed</div>
                </div>
            </div>
            
            {% if user_tasks %}
            <div class="task-section">
                <h2 class="section-title">All Tasks</h2>
                <div class="task-list">
                    {% for task in user_tasks %}
                    <div class="task-item {{ 'completed' if task.status == 'completed' else '' }} {{ 'high-priority' if task.priority == 'high' else '' }} {{ 'urgent-priority' if task.priority == 'urgent' else '' }}">
                        <div class="task-header">
                            <div class="task-title">
                                {% if task.status != 'completed' and task.task_type == 'document' %}
                                {% if task.document_id %}
                                <a href="{{ url_for('sign_document', doc_id=task.document_id) }}" style="color: inherit; text-decoration: none;">{{ task.task_title }}</a>
                                {% else %}
                                <a href="{{ url_for('view_documents') }}" style="color: inherit; text-decoration: none;">{{ task.task_title }}</a>
                                {% endif %}
                                {% else %}
                                {{ task.task_title }}
                                {% endif %}
                            </div>
                            <div class="task-badges">
                                <span class="badge badge-{{ task.status.replace('_', '-') }}">{{ task.status.replace('_', ' ').title() }}</span>
                                {% if task.priority in ['high', 'urgent'] %}
                                <span class="badge badge-priority">{{ task.priority.title() }}</span>
                                {% endif %}
                                {% if task.task_type %}
                                <span class="badge badge-type">{{ task.task_type.title() }}</span>
                                {% endif %}
                            </div>
                        </div>
                        {% if task.task_description %}
                        <div class="task-description">{{ task.task_description }}</div>
                        {% endif %}
                        <div class="task-meta">
                            <div>
                                {% if task.due_date %}
                                <span>Due: {{ task.due_date.strftime('%B %d, %Y') }}</span>
                                {% endif %}
                                {% if task.assigned_by %}
                                <span> • Assigned by: {{ task.assigned_by }}</span>
                                {% endif %}
                                {% if task.assigned_at %}
                                <span> • {{ task.assigned_at.strftime('%b %d, %Y') }}</span>
                                {% endif %}
                            </div>
                            <div class="task-actions">
                                {% if task.status != 'completed' %}
                                    {% if task.task_type == 'document' %}
                                        {% if task.document_id %}
                                        <a href="{{ url_for('sign_document', doc_id=task.document_id) }}" class="btn btn-success" style="flex-shrink: 0;">✍️ Sign Document</a>
                                        {% else %}
                                        <a href="{{ url_for('view_documents') }}" class="btn btn-success" style="flex-shrink: 0;">✍️ Sign Document</a>
                                        {% endif %}
                                    {% elif task.task_type == 'training' and task.video_id %}
                                        <a href="{{ url_for('view_training_video', video_id=task.video_id) }}" class="btn btn-success">▶️ Watch Training</a>
                                    {% else %}
                                        <button class="btn btn-success" onclick="markComplete({{ task.id }})">Mark Complete</button>
                                        {% if task.status == 'pending' %}
                                        <button class="btn btn-primary" onclick="markInProgress({{ task.id }})">Start</button>
                                        {% endif %}
                                    {% endif %}
                                {% else %}
                                <span style="color: #28a745; font-weight: 600;">✓ Completed</span>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% else %}
            <div class="task-section">
                <div class="empty-state">
                    <div class="empty-state-icon">✓</div>
                    <h3>No tasks assigned</h3>
                    <p>You don't have any tasks assigned to you yet.</p>
                </div>
            </div>
            {% endif %}
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            function toggleMobileMenu() {
                var mobileNav = document.getElementById('mobileNav');
                if (mobileNav) {
                    mobileNav.classList.toggle('show');
                }
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.mobile-menu-toggle') && !event.target.closest('.mobile-nav')) {
                    var mobileNav = document.getElementById('mobileNav');
                    if (mobileNav && mobileNav.classList.contains('show')) {
                        mobileNav.classList.remove('show');
                    }
                }
            }
            
            function markComplete(taskId) {
                if (confirm('Mark this task as completed?')) {
                    fetch('/tasks/' + taskId + '/complete', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({})
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert('Error: ' + (data.error || 'Failed to update task'));
                        }
                    })
                    .catch(error => {
                        alert('Error: ' + error);
                    });
                }
            }
            
            function markInProgress(taskId) {
                fetch('/tasks/' + taskId + '/in-progress', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Error: ' + (data.error || 'Failed to update task'));
                    }
                })
                .catch(error => {
                    alert('Error: ' + error);
                });
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name,
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
        flash(f'Error loading tasks: {str(e)}. Some data may be missing.', 'error')
        
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>My Tasks - Onboarding App</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: 'URW Form', Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                .error-box { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                .error-box strong { color: #856404; }
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




def get_user_domain_groups_via_netapi(username, domain=None):
    """
    Get domain groups for a specific user using NetUserGetGroups
    This queries the domain controller directly for the user's groups
    """
    groups = []
    try:
        import win32net
        import win32netcon
        
        if not domain:
            import config
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else None
        
        # Get domain controller name
        try:
            dc_name = win32net.NetGetAnyDCName(None, domain)
        except:
            dc_name = None
        
        # Query user's groups from domain
        try:
            # NetUserGetGroups gets groups the user is a direct member of
            user_groups = win32net.NetUserGetGroups(dc_name, username)
            
            for group_info in user_groups:
                group_name = group_info.get('name', '')
                if group_name:
                    # Format: DOMAIN\\GroupName
                    if domain:
                        groups.append(f"{domain}\\{group_name}")
                    else:
                        groups.append(group_name)
        except Exception as e:
            print(f"Error getting user groups via NetUserGetGroups: {str(e)}")
            
            # Fallback: try NetUserGetLocalGroups on domain controller
            try:
                local_groups = win32net.NetUserGetLocalGroups(dc_name, username, 0)
                for group_name in local_groups:
                    if domain:
                        groups.append(f"{domain}\\{group_name}")
                    else:
                        groups.append(group_name)
            except:
                pass
        
    except Exception as e:
        print(f"Error in get_user_domain_groups_via_netapi: {str(e)}")
        return []
    
    return groups


def get_user_domain_groups_via_ldap(username, domain=None):
    """
    Get all domain groups for a user via LDAP (includes nested groups)
    This queries Active Directory for the user's memberOf attribute
    """
    groups = []
    try:
        from ldap3 import Server, Connection, ALL, SIMPLE
        import config
        
        if not domain:
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else 'YOURDOMAIN'
        
        # Get domain controller
        dc = config.DOMAIN_CONTROLLER if hasattr(config, 'DOMAIN_CONTROLLER') and config.DOMAIN_CONTROLLER else None
        if not dc:
            try:
                import win32net
                dc = win32net.NetGetAnyDCName(None, domain)
                if dc:
                    dc = dc.replace('\\\\', '')  # Remove leading backslashes
            except:
                try:
                    import socket
                    fqdn = socket.getfqdn()
                    dc = fqdn.split('.', 1)[1] if '.' in fqdn else domain.lower()
                except:
                    dc = domain.lower()
        
        # Build base DN
        base_dn = config.LDAP_BASE_DN if hasattr(config, 'LDAP_BASE_DN') and config.LDAP_BASE_DN else None
        if not base_dn:
            # Construct base DN from domain name
            base_dn = ','.join([f'DC={part}' for part in domain.lower().split('.')])
        
        # Connect to LDAP server
        server = Server(dc, get_info=ALL)
        
        # Use SIMPLE authentication (Windows integrated auth)
        try:
            conn = Connection(server, user='', password='', authentication=SIMPLE, auto_bind=True)
        except:
            # If that fails, try with domain\username
            try:
                conn = Connection(server, user=f'{domain}\\{username}', password='', authentication=SIMPLE, auto_bind=True)
            except:
                return []
        
        # Search for user's groups via memberOf attribute
        search_filter = f'(&(objectClass=user)(sAMAccountName={username}))'
        conn.search(base_dn, search_filter, attributes=['memberOf'])
        
        if conn.entries:
            entry = conn.entries[0]
            if hasattr(entry, 'memberOf') and entry.memberOf:
                for group_dn in entry.memberOf.values:
                    if group_dn:
                        # Extract group name from DN (CN=GroupName,OU=...,DC=...)
                        # Format: CN=GroupName,OU=Groups,DC=domain,DC=com
                        parts = group_dn.split(',')
                        for part in parts:
                            if part.startswith('CN='):
                                group_name = part.replace('CN=', '')
                                if domain:
                                    groups.append(f"{domain}\\{group_name}")
                                else:
                                    groups.append(group_name)
                                break
        
        conn.unbind()
        
    except Exception as e:
        print(f"Error getting user groups via LDAP: {str(e)}")
        return []
    
    return groups


def get_user_domain_groups(username, domain=None):
    """
    Get domain groups for a user using Windows API methods
    Primary method: get_token_groups() - reads from security token (includes nested groups)
    Secondary: get_local_groups() - gets local machine groups
    Returns a list of group names with domain prefix (e.g., ZIEBART\\GroupName)
    """
    user_groups = set()
    
    try:
        if not domain:
            import config
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else None
        
        # Method 1: Get token groups (PRIMARY METHOD - includes nested groups)
        # Returns: ['ZIEBART\\IT_Staff', 'ZIEBART\\Developers', 'BUILTIN\\Administrators', ...]
        token_groups = get_token_groups() or []
        if domain:
            domain_upper = domain.upper()
            for group in token_groups:
                # Only include groups from the user's domain (e.g., ZIEBART\...)
                if group.startswith(f"{domain_upper}\\"):
                    user_groups.add(group)
        else:
            # If no domain, include all token groups
            for group in token_groups:
                user_groups.add(group)
        
        # Method 2: Get local machine groups (these won't have domain prefix)
        local_groups = get_local_groups(username) or []
        for group in local_groups:
            # Only add if it's not already in domain groups
            if group not in [g.split('\\')[-1] for g in user_groups]:
                user_groups.add(group)
        
    except Exception as e:
        print(f"Error getting Windows groups: {str(e)}")
        return []
    
    # Return sorted list of unique group names
    # Domain groups will have format: ZIEBART\\GroupName
    # Local groups will just be: GroupName
    return sorted(list(user_groups))


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
            user_position = user_new_hire.position
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

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Profile - Onboarding App</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #f5f5f5;
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                font-family: 'URW Form', Arial, sans-serif;
                transition: color 0.2s;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .dropdown-divider {
                height: 1px;
                background: #eee;
            }
            .main-content {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px 20px;
            }
            .profile-header {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 40px;
                margin-bottom: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                text-align: center;
            }
            .profile-avatar {
                width: 120px;
                height: 120px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 3em;
                font-weight: bold;
                margin: 0 auto 20px;
            }
            .profile-name {
                font-size: 2.5em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 10px;
            }
            .profile-position {
                color: #808080;
                font-size: 1.1em;
            }
            .info-section {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                margin-bottom: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .section-title-dash {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
            }
            .section-title {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
                display: block;
            }
            .info-item {
                padding: 15px 0;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .info-item:last-child {
                border-bottom: none;
            }
            .info-label {
                font-weight: 600;
                color: #808080;
                font-size: 0.95em;
            }
            .info-value {
                color: #000000;
                font-size: 0.95em;
            }
            /* Mobile Menu */
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
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
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 10px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .main-content {
                    padding: 20px 15px;
                }
                .profile-header {
                    padding: 30px 20px;
                }
                .profile-name {
                    font-size: 1.5em;
                }
                .info-section {
                    padding: 20px;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
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
                .profile-header {
                    padding: 20px 15px;
                }
                .profile-name {
                    font-size: 1.3em;
                }
                .info-section {
                    padding: 15px;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="mobile-nav" id="mobileNav">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_name[0].upper() if user_name else 'U' }}</div>
                    <span>{{ user_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                <div class="flash flash-{{ category }}" style="padding: 12px 20px; margin-bottom: 20px; border-radius: 0.5rem; background: {% if category == 'error' %}#f8d7da; color: #721c24{% else %}#d4edda; color: #155724{% endif %};">{{ msg }}</div>
                {% endfor %}
            {% endif %}
            {% endwith %}
            <div class="profile-header">
                <div class="profile-avatar">{{ user_name[0].upper() if user_name else 'U' }}</div>
                <div class="profile-name">{{ user_name }}</div>
                {% if user_position %}
                <div class="profile-position">{{ user_position }}</div>
                {% endif %}
            </div>
            
            <div class="info-section">
                <h2 class="section-title-dash">Profile</h2>
                <div class="info-item">
                    <span class="info-label">Name</span>
                    <span class="info-value">{{ user_name }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Position</span>
                    <span class="info-value">{{ user_position or 'Not set' }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Email</span>
                    <span class="info-value">{{ user_email }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Start Date</span>
                    <span class="info-value">{{ user_start_date.strftime('%B %d, %Y') if user_start_date else 'Not set' }}</span>
                </div>
            </div>
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_name=user_name, user_email=user_email,
         user_position=user_position, user_start_date=user_start_date)


@app.route('/admin/new-hires')
@admin_required
def view_all_new_hires():
    """View all new hires with progress information"""
    import traceback
    try:
        return _view_all_new_hires_impl()
    except Exception as e:
        app.logger.exception("view_all_new_hires failed")
        db.session.rollback()
        return f'<html><body><h1>New Hires Page Error</h1><pre>{traceback.format_exc()}</pre></body></html>', 500


def _view_all_new_hires_impl():
    """Implementation for admin new-hires list."""
    # Get all new hires with their progress (exclude removed / flaked-out users)
    all_new_hires = NewHire.query.filter(NewHire.status != 'removed').order_by(NewHire.created_at.desc()).all()
    new_hires_with_progress = []
    
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
        
        new_hires_with_progress.append({
            'new_hire': new_hire,
            'progress': progress_percentage,
            'completed': completed_items,
            'total': total_items,
            'training': {'completed': completed_videos, 'total': total_videos},
            'tasks': {'completed': completed_user_tasks, 'total': total_user_tasks},
            'checklist': {'completed': checklist_completed, 'total': checklist_total}
        })
    
    admin_name = current_user.username
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>New Hires List - Admin Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #FFFFFF;
                color: #000000;
            }
            .top-header {
                background: #000000;
                padding: 12px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                min-height: 60px;
            }
            .logo-section {
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 1.4em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #ffffff;
            }
            .logo-section img {
                height: 80px;
                width: auto;
                align-self: flex-end;
                margin-bottom: -40px;
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
            .container {
                max-width: 1600px;
                margin: 30px auto;
                padding: 0 20px;
            }
            .section {
                background: white;
                border-radius: 12px;
                padding: 25px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }
            .section-title {
                font-size: 1.6em;
                font-weight: 800;
                color: #000000;
                margin-bottom: 20px;
            }
            .new-hires-list {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .new-hire-item {
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 0.5rem;
                transition: all 0.2s;
            }
            .new-hire-item:hover {
                background: #e9ecef;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .progress-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                flex-shrink: 0;
            }
            .new-hire-info {
                flex: 1;
            }
            .new-hire-name {
                font-weight: 600;
                margin-bottom: 5px;
            }
            .new-hire-name a {
                color: #000000;
                text-decoration: none;
            }
            .new-hire-name a:hover {
                color: #FE0100;
            }
            .new-hire-meta {
                font-size: 0.85em;
                color: #808080;
            }
            .progress-percentage {
                font-weight: 600;
                color: #1976d2;
                min-width: 60px;
                text-align: right;
            }
            .progress-bar-container {
                width: 150px;
                height: 8px;
                background: #e0e0e0;
                border-radius: 0.5rem;
                overflow: hidden;
            }
            .progress-bar-fill {
                height: 100%;
                border-radius: 0.5rem;
                transition: width 0.3s;
            }
            .progress-bar-fill.completed { background: #4caf50; }
            .progress-bar-fill.in-progress { background: #ff9800; }
            .progress-bar-fill.not-started { background: #2196f3; }
            
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
                .container {
                    padding: 15px;
                }
                .section {
                    padding: 20px;
                }
                .new-hire-item {
                    flex-wrap: wrap;
                    gap: 10px;
                }
                .progress-bar-container {
                    width: 100%;
                    margin-top: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="section">
                <h2 class="section-title">New Hires List</h2>
                {% if new_hires_with_progress %}
                <div class="new-hires-list">
                    {% for item in new_hires_with_progress %}
                    <div class="new-hire-item">
                        <div class="progress-avatar">{{ item.new_hire.first_name[0].upper() if item.new_hire.first_name else 'N' }}</div>
                        <div class="new-hire-info">
                            <div class="new-hire-name">
                                <a href="{{ url_for('view_new_hire_details', username=item.new_hire.username) }}">
                                    {{ item.new_hire.first_name }} {{ item.new_hire.last_name }}
                                </a>
                            </div>
                            <div class="new-hire-meta">
                                {{ item.new_hire.username }}
                                {% if item.new_hire.department %} • {{ item.new_hire.department }}{% endif %}
                                {% if item.new_hire.position %} • {{ item.new_hire.position }}{% endif %}
                                {% if item.total > 0 %} • {{ item.completed }}/{{ item.total }} videos{% endif %}
                            </div>
                        </div>
                        <div class="progress-bar-container">
                            {% if item.progress == 100 %}
                            <div class="progress-bar-fill completed" style="width: 100%;"></div>
                            {% elif item.progress > 0 %}
                            <div class="progress-bar-fill in-progress" style="width: {{ item.progress }}%;"></div>
                            {% else %}
                            <div class="progress-bar-fill not-started" style="width: 100%;"></div>
                            {% endif %}
                        </div>
                        <div class="progress-percentage">{{ item.progress }}%</div>
                        <a href="{{ url_for('remove_new_hire_user', username=item.new_hire.username) }}" class="remove-user-link" title="Remove user from active list">Remove user</a>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p style="color: #666; text-align: center; padding: 40px;">No new hires found.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', new_hires_with_progress=new_hires_with_progress, admin_name=admin_name)


@app.route('/admin/new-hire/add')
@admin_required
def add_new_hire():
    """Add a new hire with step-by-step onboarding wizard"""
    videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.title).all()
    # Get documents that are visible and have signature fields
    documents = Document.query.filter(
        Document.is_visible == True,
        exists().where(DocumentSignatureField.document_id == Document.id)
    ).order_by(Document.original_filename).all()
    checklist_items = ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order).all()
    # Roles for default-document pre-selection
    try:
        roles = Role.query.order_by(Role.name).all()
        role_default_documents = {str(r.id): [d.id for d in r.default_documents.all()] for r in roles}
    except Exception:
        roles = []
        role_default_documents = {}
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>New Hire Onboarding Wizard - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
                max-width: 1000px;
                margin: 30px auto;
                padding: 0 20px;
            }
            .wizard-container {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .wizard-steps {
                display: flex;
                background: #f8f9fa;
                border-bottom: 2px solid #e0e0e0;
                overflow-x: auto;
            }
            .wizard-step {
                flex: 1;
                padding: 15px 20px;
                text-align: center;
                position: relative;
                min-width: 150px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .wizard-step.active {
                background: #FE0100;
                color: white;
            }
            .wizard-step.completed {
                background: #28a745;
                color: white;
            }
            .wizard-step-number {
                display: inline-block;
                width: 30px;
                height: 30px;
                border-radius: 50%;
                background: rgba(255,255,255,0.3);
                line-height: 30px;
                margin-right: 8px;
                font-weight: bold;
            }
            .wizard-step.active .wizard-step-number,
            .wizard-step.completed .wizard-step-number {
                background: rgba(255,255,255,0.9);
                color: #FE0100;
            }
            .wizard-step.completed .wizard-step-number {
                background: rgba(255,255,255,0.9);
                color: #28a745;
            }
            .wizard-step-title {
                font-weight: 600;
                font-size: 0.9em;
            }
            .wizard-content {
                padding: 30px;
            }
            .wizard-step-panel {
                display: none;
            }
            .wizard-step-panel.active {
                display: block;
            }
            .step-header {
                margin-bottom: 25px;
            }
            .step-header h2 {
                font-family: 'URW Form', Arial, sans-serif;
                font-weight: 800;
                color: #000000;
                font-size: 1.8em;
                margin-bottom: 10px;
            }
            .step-header p {
                color: #808080;
                font-size: 1em;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
            }
            .form-group input,
            .form-group textarea,
            .form-group select {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 16px;
                min-height: 44px;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group textarea {
                min-height: 100px;
                resize: vertical;
            }
            .form-group small {
                color: #666;
                font-size: 0.85em;
                display: block;
                margin-top: 5px;
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
            .checkbox-group, .document-group {
                max-height: 400px;
                overflow-y: auto;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 0.5rem;
                background: #f8f9fa;
                margin-top: 10px;
            }
            .checkbox-item, .document-item {
                padding: 12px;
                margin: 8px 0;
                background: white;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                gap: 12px;
                border: 2px solid transparent;
                transition: all 0.2s;
            }
            .checkbox-item:hover, .document-item:hover {
                border-color: #FE0100;
                box-shadow: 0 2px 8px rgba(254,1,0,0.1);
            }
            .checkbox-item input[type="checkbox"],
            .document-item input[type="checkbox"] {
                width: 20px;
                height: 20px;
                cursor: pointer;
            }
            .checkbox-item label,
            .document-item label {
                flex: 1;
                cursor: pointer;
                margin: 0;
                font-weight: 500;
            }
            .review-summary {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 0.5rem;
                margin-bottom: 20px;
            }
            .review-section {
                margin-bottom: 20px;
                padding-bottom: 20px;
                border-bottom: 1px solid #e0e0e0;
            }
            .review-section:last-child {
                border-bottom: none;
            }
            .review-section h3 {
                font-weight: 800;
                color: #000000;
                margin-bottom: 10px;
            }
            .review-item {
                padding: 8px 0;
                color: #333;
            }
            .wizard-actions {
                display: flex;
                justify-content: space-between;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e0e0e0;
            }
            .btn {
                display: inline-block;
                padding: 12px 24px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                border: none;
                cursor: pointer;
                font-size: 1em;
                font-weight: 600;
                font-family: 'URW Form', Arial, sans-serif;
                transition: all 0.2s;
                min-height: 44px;
            }
            .btn:hover {
                background: #d60000;
            }
            .btn-secondary {
                background: #6c757d;
            }
            .btn-secondary:hover {
                background: #5a6268;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-success:hover {
                background: #218838;
            }
            .btn:disabled {
                background: #ccc;
                cursor: not-allowed;
            }
            .step-indicator {
                text-align: center;
                color: #808080;
                margin-bottom: 20px;
                font-size: 0.9em;
            }
            
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
                .wizard-content {
                    padding: 20px;
                }
                .wizard-step {
                    min-width: 120px;
                    padding: 12px 10px;
                }
                .wizard-step-title {
                    font-size: 0.8em;
                }
                .step-header h2 {
                    font-size: 1.5em;
                }
                .form-row {
                    grid-template-columns: 1fr;
                }
                .checkbox-group, .document-group {
                    max-height: 300px;
                }
                .wizard-actions {
                    flex-direction: column;
                    gap: 10px;
                }
                .btn {
                    width: 100%;
                }
            }
            
            @media (max-width: 480px) {
                .header-content h1 {
                    font-size: 1em;
                }
                .wizard-step {
                    min-width: 100px;
                    padding: 10px 8px;
                }
                .wizard-step-title {
                    display: none;
                }
                .wizard-content {
                    padding: 15px;
                }
                .step-header h2 {
                    font-size: 1.3em;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>🚀 New Hire Onboarding Wizard</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="wizard-container">
                <div class="wizard-steps">
                    <div class="wizard-step active" data-step="1">
                        <span class="wizard-step-number">1</span>
                        <span class="wizard-step-title">Basic Info</span>
                    </div>
                    <div class="wizard-step" data-step="2">
                        <span class="wizard-step-number">2</span>
                        <span class="wizard-step-title">Training</span>
                    </div>
                    <div class="wizard-step" data-step="3">
                        <span class="wizard-step-number">3</span>
                        <span class="wizard-step-title">Documents</span>
                    </div>
                    <div class="wizard-step" data-step="4">
                        <span class="wizard-step-number">4</span>
                        <span class="wizard-step-title">Review</span>
                    </div>
                </div>
                
                <form method="POST" action="{{ url_for('create_new_hire') }}" id="onboardingForm">
                    <div class="wizard-content">
                        <!-- Step 1: Basic Information -->
                        <div class="wizard-step-panel active" id="step1">
                            <div class="step-header">
                                <h2>Step 1: Basic Information</h2>
                                <p>Enter the new hire's basic information. All fields marked with * are required.</p>
                            </div>
                            
                            <div class="form-group">
                                <label for="username">Username (Domain Username) *</label>
                                <input type="text" name="username" id="username" required placeholder="e.g., jdoe (without domain)">
                                <small>Internal ID; new hire logs in with their email and this password</small>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="password">Password (for login) *</label>
                                    <input type="password" name="password" id="password" required minlength="6" placeholder="Min 6 characters">
                                </div>
                                <div class="form-group">
                                    <label for="password_confirm">Confirm Password *</label>
                                    <input type="password" name="password_confirm" id="password_confirm" required minlength="6" placeholder="Same as above">
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="first_name">First Name *</label>
                                    <input type="text" name="first_name" id="first_name" required>
                                </div>
                                <div class="form-group">
                                    <label for="last_name">Last Name *</label>
                                    <input type="text" name="last_name" id="last_name" required>
                                </div>
                            </div>
                            
                            <div class="form-group">
                                <label for="email">Email Address</label>
                                <input type="email" name="email" id="email" placeholder="Will auto-generate if left blank">
                                <small>If left blank, will be generated as username@ziebart.com</small>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="start_date">Start Date</label>
                                    <input type="date" name="start_date" id="start_date">
                                </div>
                                <div class="form-group">
                                    <label for="access_revoked_at">Revoke access on</label>
                                    <input type="date" name="access_revoked_at" id="access_revoked_at">
                                    <small>Optional. After this date the user will no longer be able to log in.</small>
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="department">Department</label>
                                    <input type="text" name="department" id="department" placeholder="e.g., Sales, IT, HR">
                                </div>
                                <div class="form-group">
                                    <label for="position">Position/Title</label>
                                    <input type="text" name="position" id="position" placeholder="e.g., Sales Associate, Developer">
                                </div>
                            </div>
                            
                            <div class="form-group">
                                <label for="role_id">Role</label>
                                <select name="role_id" id="role_id" onchange="applyRoleDefaultsWhenEnteringStep3()">
                                    <option value="">— No role —</option>
                                    {% for role in roles %}
                                    <option value="{{ role.id }}">{{ role.name }}</option>
                                    {% endfor %}
                                </select>
                                <small>Optional. Choosing a role pre-selects default documents in Step 3.</small>
                            </div>
                            
                            <div class="wizard-actions">
                                <div></div>
                                <button type="button" class="btn" onclick="nextStep()">Next: Training Videos →</button>
                            </div>
                        </div>
                        
                        <!-- Step 2: Training Videos -->
                        <div class="wizard-step-panel" id="step2">
                            <div class="step-header">
                                <h2>Step 2: Required Training Videos</h2>
                                <p>Select which training videos this new hire must complete. At least one video is required.</p>
                            </div>
                            
                            <div class="form-group">
                                <label>Training Videos *</label>
                                <div class="checkbox-group">
                                    {% if videos %}
                                        {% for video in videos %}
                                        <div class="checkbox-item">
                                            <input type="checkbox" name="required_videos" value="{{ video.id }}" id="video_{{ video.id }}">
                                            <label for="video_{{ video.id }}">{{ video.title }}</label>
                                        </div>
                                        {% endfor %}
                                    {% else %}
                                        <p style="padding: 20px; text-align: center; color: #666;">
                                            No training videos available. 
                                            <a href="{{ url_for('manage_training') }}" style="color: #FE0100;">Upload videos first</a>.
                                        </p>
                                    {% endif %}
                                </div>
                                <small>Check all training videos that are required for this new hire</small>
                            </div>
                            
                            <div class="wizard-actions">
                                <button type="button" class="btn btn-secondary" onclick="prevStep()">← Previous</button>
                                <button type="button" class="btn" onclick="nextStep()">Next: Documents →</button>
                            </div>
                        </div>
                        
                        <!-- Step 3: Documents -->
                        <div class="wizard-step-panel" id="step3">
                            <div class="step-header">
                                <h2>Step 3: Documents to Sign</h2>
                                <p>Select which documents this new hire needs to sign. This step is optional - you can assign documents later.</p>
                            </div>
                            
                            <div class="form-group">
                                <label>Documents with Signature Fields</label>
                                {% if documents %}
                                <div class="document-group">
                                    {% for doc in documents %}
                                    <div class="document-item">
                                        <input type="checkbox" name="required_documents" value="{{ doc.id }}" id="doc_{{ doc.id }}">
                                        <label for="doc_{{ doc.id }}">
                                            <strong>{{ doc.name_for_users }}</strong>
                                            {% if doc.description %}
                                            <br><span style="color: #666; font-size: 0.9em;">{{ doc.description }}</span>
                                            {% endif %}
                                        </label>
                                    </div>
                                    {% endfor %}
                                </div>
                                {% else %}
                                <p style="padding: 20px; text-align: center; color: #666;">
                                    No documents with signature fields available. 
                                    <a href="{{ url_for('manage_documents') }}" style="color: #FE0100;">Upload documents first</a>.
                                </p>
                                {% endif %}
                                <small>Optional: Select documents that need to be signed during onboarding</small>
                            </div>
                            
                            <div class="wizard-actions">
                                <button type="button" class="btn btn-secondary" onclick="prevStep()">← Previous</button>
                                <button type="button" class="btn" onclick="nextStep()">Next: Review →</button>
                            </div>
                        </div>
                        
                        <!-- Step 4: Review -->
                        <div class="wizard-step-panel" id="step4">
                            <div class="step-header">
                                <h2>Step 4: Review & Complete</h2>
                                <p>Review all the information below. Click "Complete Onboarding" to finish setting up this new hire.</p>
                            </div>
                            
                            <div class="review-summary">
                                <div class="review-section">
                                    <h3>👤 Basic Information</h3>
                                    <div class="review-item"><strong>Username:</strong> <span id="review-username">-</span></div>
                                    <div class="review-item"><strong>Password:</strong> <input type="text" id="review-password" readonly style="width: 100%; max-width: 280px; padding: 6px 10px; margin-left: 4px; border: 1px solid #ddd; border-radius: 4px; background: #f9f9f9; font-family: inherit;" value=""> <small style="color: #666;">(copy to give to new hire)</small></div>
                                    <div class="review-item"><strong>Name:</strong> <span id="review-name">-</span></div>
                                    <div class="review-item"><strong>Email:</strong> <span id="review-email">-</span></div>
                                    <div class="review-item"><strong>Department:</strong> <span id="review-department">-</span></div>
                                    <div class="review-item"><strong>Position:</strong> <span id="review-position">-</span></div>
                                    <div class="review-item"><strong>Start Date:</strong> <span id="review-start-date">-</span></div>
                                    <div class="review-item"><strong>Revoke access on:</strong> <span id="review-revoke-date">-</span></div>
                                    <div class="review-item"><strong>Role:</strong> <span id="review-role">-</span></div>
                                </div>
                                
                                <div class="review-section">
                                    <h3>🎥 Training Videos</h3>
                                    <div id="review-videos">None selected</div>
                                </div>
                                
                                <div class="review-section">
                                    <h3>📄 Documents to Sign</h3>
                                    <div id="review-documents">None selected</div>
                                </div>
                            </div>
                            
                            <div class="wizard-actions">
                                <button type="button" class="btn btn-secondary" onclick="prevStep()">← Previous</button>
                                <button type="submit" class="btn btn-success">✓ Complete Onboarding</button>
                            </div>
                        </div>
                    </div>
                </form>
            </div>
        </div>
        
        <script>
            let currentStep = 1;
            const totalSteps = 4;
            var roleDefaultDocuments = {{ role_default_documents|tojson }};
            
            function applyRoleDefaultsWhenEnteringStep3() {
                var roleId = document.getElementById('role_id').value;
                if (!roleId || !roleDefaultDocuments[roleId]) return;
                var docIds = roleDefaultDocuments[roleId];
                docIds.forEach(function(docId) {
                    var cb = document.getElementById('doc_' + docId);
                    if (cb) cb.checked = true;
                });
            }
            
            function updateStepIndicator() {
                document.querySelectorAll('.wizard-step').forEach((step, index) => {
                    step.classList.remove('active', 'completed');
                    if (index + 1 < currentStep) {
                        step.classList.add('completed');
                    } else if (index + 1 === currentStep) {
                        step.classList.add('active');
                    }
                });
            }
            
            function showStep(step) {
                document.querySelectorAll('.wizard-step-panel').forEach(panel => {
                    panel.classList.remove('active');
                });
                document.getElementById('step' + step).classList.add('active');
                currentStep = step;
                updateStepIndicator();
                
                if (step === 3) {
                    applyRoleDefaultsWhenEnteringStep3();
                }
                if (step === 4) {
                    updateReview();
                }
            }
            
            function nextStep() {
                if (validateCurrentStep()) {
                    if (currentStep < totalSteps) {
                        showStep(currentStep + 1);
                    }
                }
            }
            
            function prevStep() {
                if (currentStep > 1) {
                    showStep(currentStep - 1);
                }
            }
            
            function validateCurrentStep() {
                if (currentStep === 1) {
                    const username = document.getElementById('username').value.trim();
                    const firstName = document.getElementById('first_name').value.trim();
                    const lastName = document.getElementById('last_name').value.trim();
                    const password = document.getElementById('password').value;
                    const passwordConfirm = document.getElementById('password_confirm').value;
                    
                    if (!username || !firstName || !lastName) {
                        alert('Please fill in all required fields: Username, First Name, and Last Name');
                        return false;
                    }
                    if (!password || password.length < 6) {
                        alert('Password is required and must be at least 6 characters.');
                        return false;
                    }
                    if (password !== passwordConfirm) {
                        alert('Password and Confirm Password do not match.');
                        return false;
                    }
                } else if (currentStep === 2) {
                    const videos = document.querySelectorAll('input[name="required_videos"]:checked');
                    if (videos.length === 0) {
                        alert('Please select at least one training video');
                        return false;
                    }
                }
                return true;
            }
            
            function updateReview() {
                // Basic Info
                document.getElementById('review-username').textContent = document.getElementById('username').value || '-';
                var pwd = document.getElementById('password').value || '';
                document.getElementById('review-password').value = pwd || '';
                const firstName = document.getElementById('first_name').value || '';
                const lastName = document.getElementById('last_name').value || '';
                document.getElementById('review-name').textContent = (firstName + ' ' + lastName).trim() || '-';
                document.getElementById('review-email').textContent = document.getElementById('email').value || 'Will be auto-generated';
                document.getElementById('review-department').textContent = document.getElementById('department').value || '-';
                document.getElementById('review-position').textContent = document.getElementById('position').value || '-';
                const startDate = document.getElementById('start_date').value;
                document.getElementById('review-start-date').textContent = startDate || '-';
                const revokeDate = document.getElementById('access_revoked_at').value;
                document.getElementById('review-revoke-date').textContent = revokeDate || 'Not set';
                const roleSelect = document.getElementById('role_id');
                const roleText = roleSelect && roleSelect.options[roleSelect.selectedIndex] ? roleSelect.options[roleSelect.selectedIndex].text : '';
                document.getElementById('review-role').textContent = roleSelect && roleSelect.value ? roleText : '-';
                
                // Training Videos
                const selectedVideos = Array.from(document.querySelectorAll('input[name="required_videos"]:checked'))
                    .map(cb => {
                        const label = document.querySelector('label[for="' + cb.id + '"]');
                        return label ? label.textContent.trim() : '';
                    })
                    .filter(v => v);
                document.getElementById('review-videos').innerHTML = selectedVideos.length > 0 
                    ? '<ul style="margin-left: 20px; margin-top: 5px;">' + selectedVideos.map(v => '<li>' + v + '</li>').join('') + '</ul>'
                    : 'None selected';
                
                // Documents
                const selectedDocs = Array.from(document.querySelectorAll('input[name="required_documents"]:checked'))
                    .map(cb => {
                        const label = document.querySelector('label[for="' + cb.id + '"]');
                        return label ? label.querySelector('strong').textContent : '';
                    })
                    .filter(d => d);
                document.getElementById('review-documents').innerHTML = selectedDocs.length > 0
                    ? '<ul style="margin-left: 20px; margin-top: 5px;">' + selectedDocs.map(d => '<li>' + d + '</li>').join('') + '</ul>'
                    : 'None selected';
            }
            
            // Allow clicking on step indicators to navigate (only to completed steps)
            document.querySelectorAll('.wizard-step').forEach((step, index) => {
                step.addEventListener('click', function() {
                    const stepNum = index + 1;
                    if (stepNum < currentStep) {
                        showStep(stepNum);
                    }
                });
            });
        </script>
    </body>
    </html>
    ''', videos=videos, documents=documents, checklist_items=checklist_items, roles=roles, role_default_documents=role_default_documents)


@app.route('/admin/new-hire/create', methods=['POST'])
@admin_required
def create_new_hire():
    """Create a new hire with required training videos and documents"""
    username = request.form.get('username', '').strip()
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    department = request.form.get('department', '').strip()
    position = request.form.get('position', '').strip()
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
            email = f"{username}@{email_domain}"
        
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
        
        # Create new hire
        new_hire = NewHire(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            department=department if department else None,
            position=position if position else None,
            start_date=start_date,
            access_revoked_at=access_revoked_at,
            created_by=current_user.username
        )
        if role_id is not None and hasattr(NewHire, 'role_id'):
            new_hire.role_id = role_id
        db.session.add(new_hire)
        db.session.flush()  # Get the ID
        
        # Ensure User exists with email and password so new hire can log in (email + password)
        user = UserModel.query.filter_by(username=username).first()
        if not user:
            user = UserModel(
                username=username,
                email=email,
                role='user',
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
        else:
            user.email = email
            user.password_hash = generate_password_hash(password)
        
        # Add required training videos
        for video_id in required_videos:
            video = TrainingVideo.query.get(int(video_id))
            if video:
                new_hire.required_training_videos.append(video)
                
                # Create a UserTask for this training video
                # Check if task already exists
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
                        notes=f'video_id:{video_id}'
                    )
                    db.session.add(task)
        
        # Assign documents if selected
        for doc_id in required_documents:
            document = Document.query.get(int(doc_id))
            if document:
                # Check if assignment already exists
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
                    
                    # Create a UserTask for this document assignment
                    task = UserTask(
                        username=username,
                        task_title=f"Sign Document: {document.name_for_users}",
                        task_description=f"Please review and sign the document: {document.description or document.name_for_users}",
                        task_type='document',
                        document_id=doc_id,
                        priority='normal',
                        status='pending',
                        assigned_by=current_user.username
                    )
                    db.session.add(task)
        
        db.session.commit()
        
        # Build success message
        msg_parts = [f'Onboarding started for "{first_name} {last_name}" ({username})']
        msg_parts.append(f'with {len(required_videos)} training video(s)')
        if required_documents:
            msg_parts.append(f'and {len(required_documents)} document(s) to sign')
        msg_parts.append('.')
        
        flash(' '.join(msg_parts), 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error starting onboarding: {str(e)}', 'error')
        return redirect(url_for('add_new_hire'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    import traceback
    try:
        return _admin_dashboard_impl()
    except Exception as e:
        app.logger.exception("admin_dashboard failed")
        db.session.rollback()
        return f'<html><body><h1>Admin Dashboard Error</h1><pre>{traceback.format_exc()}</pre></body></html>', 500


def _admin_dashboard_impl():
    """Admin dashboard implementation (called from admin_dashboard)."""
    total_users = 0
    total_new_hires = 0
    admin_users = 0
    forms_completed = 0
    total_checklist_items = 0
    all_new_hires = []
    new_hires_with_progress = []
    form_status_data = []
    recent_activity = []
    admin_name = current_user.username if current_user else "Admin"
    pending_count = 0
    notifications = []

    try:
        total_users = UserModel.query.count()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: total_users failed: {e}")
    try:
        total_new_hires = NewHire.query.filter(NewHire.status != 'removed').count()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: total_new_hires failed: {e}")
    try:
        admin_users = UserModel.query.filter_by(role='admin').count()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: admin_users failed: {e}")
    try:
        forms_completed = Document.query.filter_by(is_visible=True).count()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: forms_completed failed: {e}")
    try:
        total_checklist_items = ChecklistItem.query.filter_by(is_active=True).count()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: total_checklist_items failed: {e}")
    try:
        all_new_hires = NewHire.query.filter(NewHire.status != 'removed').order_by(NewHire.created_at.desc()).all()
        # Exclude new hires whose user was revoked or deleted (so they don't show in Progress/Recent Activity)
        from datetime import date as _date
        today = _date.today()
        kept = []
        for nh in all_new_hires:
            user = UserModel.query.filter_by(username=nh.username).first()
            if not user:
                continue  # User deleted (revoked = remove)
            revoked_at = getattr(user, 'access_revoked_at', None)
            if revoked_at is not None and today >= revoked_at:
                continue  # Access revoked (old revoke flow)
            kept.append(nh)
        all_new_hires = kept
        total_new_hires = len(all_new_hires)  # Keep count in sync with filtered list
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"admin_dashboard: all_new_hires failed: {e}")
        all_new_hires = []

    try:
        for new_hire in all_new_hires:
            try:
                # Training videos progress
                required_videos = list(new_hire.required_training_videos)
                total_videos = len(required_videos)
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
                        # Skip this video if there's an error
                        continue
                
                # User tasks progress
                try:
                    all_user_tasks = UserTask.query.filter_by(username=new_hire.username).all()
                    total_user_tasks = len(all_user_tasks)
                    completed_user_tasks = len([t for t in all_user_tasks if t.status == 'completed'])
                except Exception as e:
                    # If there's an error getting tasks, use defaults
                    all_user_tasks = []
                    total_user_tasks = 0
                    completed_user_tasks = 0
                
                # Checklist progress
                try:
                    checklist_completed = NewHireChecklist.query.filter_by(
                        new_hire_id=new_hire.id,
                        is_completed=True
                    ).count()
                    checklist_total = ChecklistItem.query.filter_by(is_active=True).count()
                except Exception as e:
                    # If there's an error getting checklist, use defaults
                    checklist_completed = 0
                    checklist_total = 0
                
                # Calculate overall progress (training videos + user tasks + checklist items)
                total_items = total_videos + total_user_tasks + checklist_total
                completed_items = completed_videos + completed_user_tasks + checklist_completed
                progress_percentage = int((completed_items / total_items * 100)) if total_items > 0 else 0
                
                new_hires_with_progress.append({
                    'new_hire': new_hire,
                    'progress': progress_percentage,
                    'completed': completed_items,
                    'total': total_items,
                    'training': {'completed': completed_videos, 'total': total_videos},
                    'tasks': {'completed': completed_user_tasks, 'total': total_user_tasks},
                    'checklist': {'completed': checklist_completed, 'total': checklist_total}
                })
            except Exception as e:
                # If there's an error processing this new hire, skip it or use defaults
                import traceback
                app.logger.error(f'Error processing new hire {new_hire.username}: {str(e)}')
                app.logger.error(traceback.format_exc())
                # Add with default values so the dashboard still shows
                new_hires_with_progress.append({
                    'new_hire': new_hire,
                    'progress': 0,
                    'completed': 0,
                    'total': 0,
                    'training': {'completed': 0, 'total': 0},
                    'tasks': {'completed': 0, 'total': 0},
                    'checklist': {'completed': 0, 'total': 0}
                })
        
        # Get recent activity (new hires ordered by creation date)
        recent_activity = all_new_hires[:10]
        
        # Get form status stats - documents with signature fields
        # Use only users who are assigned each document (not all users in the system)
        form_status_data = []
        try:
            documents_with_signatures = Document.query.join(DocumentSignatureField).distinct().all()
            
            for doc in documents_with_signatures:
                # Get all required signature fields for this document
                required_fields = DocumentSignatureField.query.filter_by(
                    document_id=doc.id,
                    is_required=True
                ).all()
                
                total_required = len(required_fields)
                if total_required == 0:
                    continue  # Skip documents with no required fields
                
                # Only count users who have this document assigned (same logic as view_form_signatures)
                assignments = DocumentAssignment.query.filter_by(document_id=doc.id).all()
                assigned_usernames = [a.username for a in assignments]
                total_assigned = len(assigned_usernames)
                
                if total_assigned == 0:
                    # No one assigned - show 0/0 or skip; include so admin can see the form exists
                    form_status_data.append({
                        'doc_id': doc.id,
                        'name': doc.name_for_users or 'Untitled Document',
                        'signed': 0,
                        'total': 0,
                        'percentage': 0
                    })
                    continue
                
                # Count how many assigned users have signed all required fields
                signed_count = 0
                for username in assigned_usernames:
                    try:
                        all_signed = all(is_signature_field_signed(doc.id, f, username) for f in required_fields)
                        if all_signed:
                            signed_count += 1
                    except Exception as e:
                        print(f"Error checking signatures for user {username}: {e}")
                        continue
                
                percentage = int((signed_count / total_assigned * 100)) if total_assigned > 0 else 0
                
                form_status_data.append({
                    'doc_id': doc.id,
                    'name': doc.name_for_users or 'Untitled Document',
                    'signed': signed_count,
                    'total': total_assigned,
                    'percentage': percentage
                })
        except Exception as e:
            # If form status calculation fails, just use empty list
            print(f"Error calculating form status: {e}")
            import traceback
            traceback.print_exc()
            form_status_data = []
        
        # Sort by percentage descending and limit to 4 items
        form_status_data.sort(key=lambda x: x['percentage'], reverse=True)
        form_status_data = form_status_data[:4]
        
        # Get admin user info
        admin_user = current_user
        admin_name = f"{admin_user.username}"
        
        # Build notifications for admin (can be empty for now, or add admin-specific notifications)
        notifications = []
        
        # Add test notification for "aka" user
        if admin_user.username.lower() == 'aka':
            # Check if test notification has been read
            test_notification = UserNotification.query.filter_by(
                username=admin_user.username,
                notification_type='test',
                notification_id='999'
            ).first()
            
            is_read = test_notification.is_read if test_notification else False
            
            if not is_read:
                notifications.append({
                    'type': 'test',
                    'id': 999,
                    'title': 'Test Notification',
                    'message': 'This is a test notification to verify the notification system is working correctly.',
                    'url': url_for('admin_dashboard'),
                    'is_read': False
                })
        
        pending_count = len([n for n in notifications if not n['is_read']])
    except Exception as e:
        # Log error but keep counts already computed (so summary cards still show data)
        import traceback
        traceback.print_exc()
        app.logger.error(f"Error in admin_dashboard (progress/form status): {e}")
        db.session.rollback()
        new_hires_with_progress = new_hires_with_progress if new_hires_with_progress else []
        recent_activity = all_new_hires[:10] if all_new_hires else []
        # form_status_data, notifications, pending_count already have defaults from above
        if not notifications:
            pending_count = 0
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard - Onboarding App</title>
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                transition: color 0.2s;
                padding: 5px 10px;
                border-radius: 0.5rem;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .nav-links a.active {
                color: #FE0100;
                background: rgba(254, 1, 0, 0.1);
                font-weight: 600;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .notification-icon {
                font-size: 1.3em;
                cursor: pointer;
                position: relative;
                color: #ffffff;
            }
            .notification-dropdown {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 350px;
                max-width: 400px;
                max-height: 500px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .notification-dropdown.show {
                display: block;
            }
            .notification-header {
                padding: 15px 20px;
                border-bottom: 1px solid #eee;
                background: #f8f9fa;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .notification-header h3 {
                font-size: 1em;
                font-weight: 600;
                color: #000000;
                margin: 0;
            }
            .notification-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .notification-item {
                padding: 15px 20px;
                border-bottom: 1px solid #f0f0f0;
                cursor: pointer;
                transition: background 0.2s;
            }
            .notification-item:hover {
                background: #f8f9fa;
            }
            .notification-item:last-child {
                border-bottom: none;
            }
            .notification-item.unread {
                background: #e7f3ff;
            }
            .notification-item.unread:hover {
                background: #d0e7ff;
            }
            .notification-title {
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 5px;
                font-size: 0.95em;
            }
            .notification-message {
                font-family: 'URW Form', Arial, sans-serif;
                color: #808080;
                font-size: 0.85em;
                line-height: 1.4;
            }
            .notification-empty {
                padding: 40px 20px;
                text-align: center;
                color: #999;
            }
            .notification-badge {
                position: absolute;
                top: -5px;
                right: -8px;
                background: #FE0100;
                color: white;
                border-radius: 50%;
                width: 18px;
                height: 18px;
                font-size: 0.7em;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .main-container {
                max-width: 1600px;
                margin: 0 auto;
                padding: 20px;
                display: grid;
                grid-template-columns: 1fr 350px;
                gap: 20px;
            }
            .main-content {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            .welcome-banner {
                background: white;
                border-radius: 12px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .welcome-banner h1 {
                font-size: 2.5em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
            }
            .filter-dropdown {
                padding: 8px 15px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                background: white;
                font-size: 0.9em;
            }
            .summary-cards {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
            }
            .summary-card {
                background: white;
                border-radius: 12px;
                padding: 25px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                align-items: center;
                gap: 15px;
            }
            .summary-icon {
                width: 60px;
                height: 60px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2em;
            }
            .summary-icon.blue { background: #e3f2fd; }
            .summary-icon.green { background: #e8f5e9; }
            .summary-content h3 {
                font-size: 0.9em;
                color: #808080;
                margin-bottom: 5px;
            }
            .summary-content .number {
                font-size: 2em;
                font-weight: bold;
                color: #000000;
            }
            .section {
                background: white;
                border-radius: 12px;
                padding: 25px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .section-title {
                font-size: 1.6em;
                font-weight: 800;
                color: #000000;
            }
            .progress-item {
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 15px 0;
                border-bottom: 1px solid #f0f0f0;
            }
            .progress-item:last-child {
                border-bottom: none;
            }
            .progress-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .progress-info {
                flex: 1;
            }
            .progress-name {
                font-weight: 600;
                margin-bottom: 5px;
            }
            .progress-bar {
                height: 8px;
                background: #e0e0e0;
                border-radius: 0.5rem;
                overflow: hidden;
                position: relative;
            }
            .progress-fill {
                height: 100%;
                border-radius: 0.5rem;
                transition: width 0.3s;
            }
            .progress-fill.completed { background: #4caf50; }
            .progress-fill.in-progress { background: #ff9800; }
            .progress-fill.not-started { background: #2196f3; }
            .progress-percentage {
                font-weight: 600;
                color: #000000;
                min-width: 50px;
                text-align: right;
            }
            .legend {
                display: flex;
                gap: 20px;
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #f0f0f0;
            }
            .legend-item {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.85em;
                color: #808080;
            }
            .legend-color {
                width: 12px;
                height: 12px;
                border-radius: 2px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #f0f0f0;
            }
            th {
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                font-size: 0.9em;
            }
            td {
                font-family: 'URW Form', Arial, sans-serif;
            }
            .table-progress {
                width: 100px;
                height: 6px;
                background: #e0e0e0;
                border-radius: 3px;
                overflow: hidden;
                display: inline-block;
                vertical-align: middle;
            }
            .table-progress-fill {
                height: 100%;
                background: #4caf50;
                border-radius: 3px;
                min-width: 0;
            }
            .table-progress-fill[style*="width: 0%"] {
                display: none;
            }
            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            .sidebar-section {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .sidebar-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .sidebar-title {
                font-size: 1.2em;
                font-weight: 800;
                color: #000000;
            }
            .form-status-item {
                padding: 12px 0;
                border-bottom: 1px solid #f0f0f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: background 0.2s;
                gap: 10px;
            }
            .form-status-item:hover {
                background: #f8f9fa;
            }
            .form-status-item:last-child {
                border-bottom: none;
            }
            .form-status-name {
                font-size: 0.9em;
                color: #000000;
                flex: 1;
                min-width: 0;
                word-break: break-word;
                overflow-wrap: break-word;
            }
            .form-status-progress {
                width: 120px;
                height: 6px;
                background: #e0e0e0;
                border-radius: 3px;
                overflow: hidden;
                flex-shrink: 0;
            }
            .form-status-fill {
                height: 100%;
                background: #4caf50;
                border-radius: 3px;
                min-width: 0;
            }
            .form-status-fill[style*="width: 0%"] {
                display: none;
            }
            .form-status-count {
                font-size: 0.85em;
                color: #808080;
                min-width: 50px;
                text-align: right;
                flex-shrink: 0;
            }
            .quick-link-item {
                padding: 12px 0;
                border-bottom: 1px solid #f0f0f0;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .quick-link-item:last-child {
                border-bottom: none;
            }
            .quick-link-icon {
                font-size: 1.2em;
            }
            .quick-link-text {
                flex: 1;
                font-size: 0.9em;
                color: #000000;
            }
            .quick-link-count {
                font-size: 0.85em;
                color: #808080;
            }
            .new-hires-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .new-hire-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 0;
                border-bottom: 1px solid #f0f0f0;
            }
            .new-hire-item:last-child {
                border-bottom: none;
            }
            /* Mobile Menu */
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
            @media (max-width: 1200px) {
                .main-container {
                    grid-template-columns: 1fr;
                }
                .summary-cards {
                    grid-template-columns: 1fr;
                }
            }
            
            @media (max-width: 768px) {
                .top-header {
                    padding: 12px 15px;
                    flex-wrap: wrap;
                    min-height: 50px;
                }
                .logo-section {
                    font-size: 1.1em;
                    flex: 1;
                    min-width: 0;
                }
                .logo-section .logo-text {
                    display: none;
                }
                .logo-section img {
                    height: 50px;
                    margin-bottom: -25px;
                }
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 8px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .notification-icon {
                    font-size: 1.1em;
                }
                .notification-dropdown {
                    min-width: 280px;
                    max-width: 90vw;
                    right: -10px;
                }
                .main-container {
                    padding: 15px;
                    gap: 15px;
                }
                .welcome-banner {
                    padding: 15px;
                }
                .summary-cards {
                    gap: 12px;
                }
                .summary-card {
                    padding: 15px;
                }
                .summary-icon {
                    width: 50px;
                    height: 50px;
                    font-size: 1.5em;
                }
                .summary-content .number {
                    font-size: 1.5em;
                }
                .welcome-banner {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 15px;
                    padding: 20px;
                }
                .welcome-banner h1 {
                    font-size: 1.8em;
                }
                .filter-dropdown {
                    width: 100%;
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px; /* Touch-friendly */
                }
                .summary-cards {
                    grid-template-columns: 1fr;
                    gap: 15px;
                }
                .section {
                    padding: 20px;
                }
                .section-title {
                    font-size: 1.3em;
                }
                .progress-item {
                    flex-wrap: wrap;
                    gap: 10px;
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
                .sidebar {
                    margin-top: 20px;
                }
                .form-status-item {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }
                .form-status-name {
                    width: 100%;
                    max-width: none;
                }
                .form-status-progress {
                    width: 100%;
                }
                .form-status-count {
                    min-width: auto;
                    width: 100%;
                    text-align: left;
                    font-size: 0.8em;
                }
            }
            
            @media (max-width: 480px) {
                .top-header {
                    padding: 10px 12px;
                    min-height: 45px;
                }
                .logo-section {
                    font-size: 0.9em;
                }
                .logo-section .logo-text {
                    display: none;
                }
                .logo-section img {
                    height: 40px;
                    margin-bottom: -20px;
                }
                .back-btn {
                    font-size: 0.75em;
                    padding: 6px 10px;
                }
                .welcome-banner {
                    padding: 12px;
                }
                .welcome-banner h1 {
                    font-size: 1.3em;
                }
                .summary-card {
                    padding: 12px;
                }
                .summary-icon {
                    width: 40px;
                    height: 40px;
                    font-size: 1.2em;
                }
                .summary-content .number {
                    font-size: 1.3em;
                }
                .section {
                    padding: 12px;
                }
                .section-title {
                    font-size: 1.1em;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 16px;
                    font-size: 0.95em;
                }
                .section-header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 10px;
                }
                .section-header .filter-dropdown {
                    width: 100%;
                    font-size: 16px;
                    min-height: 44px;
                }
                .progress-item {
                    padding: 10px 0;
                }
                .progress-avatar {
                    width: 35px;
                    height: 35px;
                    font-size: 0.9em;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">User Dashboard</a>
            </div>
            <div class="mobile-nav" id="mobileNav">
                <a href="{{ url_for('dashboard') }}">User Dashboard</a>
            </div>
            <div class="user-section">
                <div class="notification-icon" style="position: relative;" onclick="toggleNotificationDropdown(event)">
                    🔔
                    {% if pending_count > 0 %}
                    <span class="notification-badge" id="notificationBadge" style="position: absolute; top: -5px; right: -5px; background: #FE0100; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 0.7em; font-weight: bold;">{{ pending_count }}</span>
                    {% endif %}
                    <div class="notification-dropdown" id="notificationDropdown">
                        <div class="notification-header">
                            <h3>Notifications</h3>
                            <button onclick="markAllAsRead()" style="background: none; border: none; color: #FE0100; cursor: pointer; font-size: 0.85em; padding: 0;">Mark all read</button>
                        </div>
                        <div class="notification-list">
                            {% if notifications %}
                                {% for notification in notifications %}
                                <div class="notification-item {% if not notification.is_read %}unread{% endif %}" onclick="handleNotificationClick({{ notification.id }}, '{{ notification.type }}', '{{ notification.url }}', event)">
                                    <div class="notification-title">{{ notification.title }}</div>
                                    <div class="notification-message">{{ notification.message }}</div>
                                </div>
                                {% endfor %}
                            {% else %}
                                <div class="notification-empty">
                                    <p>No new notifications</p>
                                </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ admin_name[0].upper() if admin_name else 'A' }}</div>
                    <span>{{ admin_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('dashboard') }}" class="dropdown-item">User Dashboard</a>
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-container">
            <div class="main-content">
                <div class="welcome-banner">
                    <h1>Welcome to the Admin Dashboard</h1>
                    <select class="filter-dropdown">
                        <option>Last 30 Days</option>
                        <option>Last 7 Days</option>
                        <option>Last 90 Days</option>
                        <option>All Time</option>
                    </select>
                </div>
                
                <div class="summary-cards">
                    <div class="summary-card" style="cursor: pointer;" onclick="window.location.href='{{ url_for('view_all_new_hires') }}'">
                        <div class="summary-icon blue">👥</div>
                        <div class="summary-content">
                            <h3>New Hires</h3>
                            <div class="number">{{ total_new_hires }}</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-icon green">📋</div>
                        <div class="summary-content">
                            <h3>Forms Completed</h3>
                            <div class="number">{{ forms_completed }}</div>
                        </div>
                    </div>
                    <div class="summary-card" style="cursor: pointer;" onclick="window.location.href='{{ url_for('view_user_checklists') }}'">
                        <div class="summary-icon blue">✅</div>
                        <div class="summary-content">
                            <h3>Onboarding Checklists</h3>
                            <div class="number">{{ total_checklist_items }}</div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-header">
                        <h2 class="section-title">Progress Overview</h2>
                        <select class="filter-dropdown" style="font-size: 0.85em;">
                            <option>Last 30 Days</option>
                            <option>Last 7 Days</option>
                            <option>Last 90 Days</option>
                        </select>
                    </div>
                    <div class="progress-list">
                        {% for item in new_hires_with_progress[:7] %}
                        <div class="progress-item">
                            <div class="progress-avatar">{{ item.new_hire.first_name[0].upper() if item.new_hire.first_name else 'N' }}</div>
                            <div class="progress-info">
                                <div class="progress-name"><a href="{{ url_for('view_new_hire_details', username=item.new_hire.username) }}" style="color: #000000; text-decoration: none; cursor: pointer;">{{ item.new_hire.first_name }} {{ item.new_hire.last_name }}</a></div>
                                <div class="progress-bar">
                                    {% if item.progress == 100 %}
                                    <div class="progress-fill completed" style="width: 100%;"></div>
                                    {% elif item.progress > 0 %}
                                    <div class="progress-fill in-progress" style="width: {{ item.progress }}%;"></div>
                                    {% else %}
                                    <div class="progress-fill not-started" style="width: 0%;"></div>
                                    {% endif %}
                                </div>
                            </div>
                            <div class="progress-percentage">{{ item.progress }}%</div>
                        </div>
                        {% endfor %}
                    </div>
                    <div class="legend">
                        <div class="legend-item">
                            <div class="legend-color" style="background: #2196f3;"></div>
                            <span>Not Started</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #ff9800;"></div>
                            <span>In Progress</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #4caf50;"></div>
                            <span>Completed</span>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2 class="section-title">Recent Activity</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Position</th>
                                <th>Department</th>
                                <th>Progress</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for item in new_hires_with_progress[:6] %}
                            <tr>
                                <td data-label="Name"><a href="{{ url_for('view_new_hire_details', username=item.new_hire.username) }}" style="color: #333; text-decoration: none; font-weight: 600;">{{ item.new_hire.first_name }} {{ item.new_hire.last_name }}</a></td>
                                <td data-label="Position">{{ item.new_hire.position or '-' }}</td>
                                <td data-label="Department">{{ item.new_hire.department or '-' }}</td>
                                <td data-label="Progress">
                                    <div class="table-progress">
                                        {% if item.progress > 0 %}
                                        <div class="table-progress-fill" style="width: {{ item.progress }}%;"></div>
                                        {% else %}
                                        <div class="table-progress-fill" style="width: 0%;"></div>
                                        {% endif %}
                                    </div>
                                    <span style="font-size: 0.85em; color: #808080; margin-left: 8px;">{{ item.progress }}%</span>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
            </div>
            
            <div class="sidebar">
                <div class="sidebar-section">
                    <div class="sidebar-header">
                        <h3 class="sidebar-title">Form Status</h3>
                    </div>
                    <div class="form-status-list">
                        {% if form_status_data %}
                            {% for form in form_status_data %}
                            <a href="{{ url_for('view_form_signatures', doc_id=form.doc_id) }}" style="text-decoration: none; color: inherit; display: block;">
                                <div class="form-status-item" style="cursor: pointer; transition: background 0.2s;">
                                    <span class="form-status-name">{{ form.name }}</span>
                                    <div class="form-status-progress">
                                        {% if form.percentage > 0 %}
                                        <div class="form-status-fill" style="width: {{ form.percentage }}%;"></div>
                                        {% else %}
                                        <span style="color: #666; font-size: 0.75em;">0%</span>
                                        {% endif %}
                                    </div>
                                    <span class="form-status-count">{{ form.signed }}/{{ form.total }}</span>
                                </div>
                            </a>
                            {% endfor %}
                        {% else %}
                            <div class="form-status-item">
                                <span class="form-status-name" style="color: #999; font-style: italic;">No forms with signatures yet</span>
                            </div>
                        {% endif %}
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="sidebar-header">
                        <h3 class="sidebar-title">Quick Links</h3>
                    </div>
                    <div class="quick-links-list">
                        <a href="{{ url_for('manage_checklist') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">📋</span>
                            <span class="quick-link-text">Onboarding Tasks</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_training') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">▶️</span>
                            <span class="quick-link-text">Training Library</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_documents') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">📄</span>
                            <span class="quick-link-text">Manage Forms</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('add_new_hire') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">➕</span>
                            <span class="quick-link-text">Start Onboarding</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_users') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">👥</span>
                            <span class="quick-link-text">Manage Users</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_admins') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">🛡️</span>
                            <span class="quick-link-text">Manage Admins</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_roles') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">🎭</span>
                            <span class="quick-link-text">Manage Roles</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('admin_reports') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">📊</span>
                            <span class="quick-link-text">Reports</span>
                            <span class="quick-link-count">→</span>
                        </a>
                        <a href="{{ url_for('manage_external_links') }}" class="quick-link-item" style="text-decoration: none;">
                            <span class="quick-link-icon">🔗</span>
                            <span class="quick-link-text">External Links</span>
                            <span class="quick-link-count">→</span>
                        </a>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            function toggleMobileMenu() {
                var mobileNav = document.getElementById('mobileNav');
                if (mobileNav) {
                    mobileNav.classList.toggle('show');
                }
            }
            
            function toggleNotificationDropdown(event) {
                event.stopPropagation();
                var dropdown = document.getElementById('notificationDropdown');
                dropdown.classList.toggle('show');
            }
            
            function handleNotificationClick(notificationId, notificationType, url, event) {
                if (event) {
                    event.stopPropagation();
                }
                // Mark notification as read
                fetch('/api/notifications/mark-read', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        notification_type: notificationType,
                        notification_id: String(notificationId)
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Update badge count immediately
                        updateNotificationBadge();
                        // Also remove the notification item from the dropdown
                        var clickedElement = event ? event.currentTarget : null;
                        if (clickedElement) {
                            clickedElement.classList.remove('unread');
                            // Remove after a short delay to show visual feedback
                            setTimeout(function() {
                                clickedElement.remove();
                                // Check if there are any notifications left
                                var notificationList = document.querySelector('.notification-list');
                                if (notificationList && notificationList.querySelectorAll('.notification-item').length === 0) {
                                    notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                                }
                            }, 100);
                        }
                    }
                    // Navigate to the notification URL (only if it's not the same page)
                    if (url && url !== window.location.pathname) {
                        window.location.href = url;
                    } else {
                        // If same page, just reload to refresh the notification count
                        setTimeout(function() {
                            window.location.reload();
                        }, 200);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    // Still navigate even if marking as read fails
                    if (url && url !== window.location.pathname) {
                        window.location.href = url;
                    } else {
                        window.location.reload();
                    }
                });
            }
            
            function markAllAsRead() {
                fetch('/api/notifications/mark-all-read', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Update badge count immediately
                        updateNotificationBadge();
                        // Update the notification list
                        var notificationList = document.querySelector('.notification-list');
                        if (notificationList) {
                            notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                        }
                        // Remove unread styling from any remaining items
                        var unreadItems = document.querySelectorAll('.notification-item.unread');
                        unreadItems.forEach(function(item) {
                            item.classList.remove('unread');
                        });
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
            
            function updateNotificationBadge() {
                fetch('/api/notifications/count')
                .then(response => response.json())
                .then(data => {
                    var badge = document.getElementById('notificationBadge');
                    if (data.count > 0) {
                        if (badge) {
                            badge.textContent = data.count;
                            badge.style.display = 'flex';
                        } else {
                            // Create badge if it doesn't exist
                            var icon = document.querySelector('.notification-icon');
                            if (icon) {
                                var newBadge = document.createElement('span');
                                newBadge.id = 'notificationBadge';
                                newBadge.className = 'notification-badge';
                                newBadge.textContent = data.count;
                                newBadge.style.cssText = 'position: absolute; top: -5px; right: -5px; background: #FE0100; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 0.7em; font-weight: bold;';
                                icon.appendChild(newBadge);
                            }
                        }
                    } else {
                        if (badge) {
                            badge.style.display = 'none';
                            badge.textContent = '0';
                        }
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.notification-icon')) {
                    var notifDropdown = document.getElementById('notificationDropdown');
                    if (notifDropdown && notifDropdown.classList.contains('show')) {
                        notifDropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.mobile-menu-toggle') && !event.target.closest('.mobile-nav')) {
                    var mobileNav = document.getElementById('mobileNav');
                    if (mobileNav && mobileNav.classList.contains('show')) {
                        mobileNav.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', total_users=total_users, total_new_hires=total_new_hires, admin_users=admin_users,
         forms_completed=forms_completed, total_checklist_items=total_checklist_items,
         new_hires_with_progress=new_hires_with_progress, recent_activity=recent_activity,
         form_status_data=form_status_data, admin_name=admin_name, pending_count=pending_count, notifications=notifications)


@app.route('/admin/users')
@admin_required
def manage_users():
    """Manage users: add, edit, reset password, revoke/restore access. Admin roles are managed on Manage Admins."""
    try:
        users = []
        try:
            users = UserModel.query.filter_by(role='user').order_by(UserModel.username).all()
        except Exception as e:
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE users ADD access_revoked_at DATE NULL"))
                db.session.commit()
            except Exception:
                db.session.rollback()
            try:
                users = UserModel.query.filter_by(role='user').order_by(UserModel.username).all()
            except Exception:
                db.session.rollback()
                users = []
        today = datetime.utcnow().date()
        for u in users:
            revoked_at = getattr(u, 'access_revoked_at', None)
            try:
                u.is_revoked = bool(revoked_at is not None and today >= revoked_at)
            except (TypeError, ValueError):
                u.is_revoked = False
        # Only show active users (revoked users are removed from list; revoke = delete)
        users = [u for u in users if not getattr(u, 'is_revoked', False)]
        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Users - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body { background: #f5f5f5; }
            .header { background: #000; color: white; padding: 12px 30px; display: flex; justify-content: space-between; align-items: center; min-height: 60px; }
            .header h1 { font-weight: 800; margin: 0; font-size: 1.4em; }
            .back-btn { background: rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; border-radius: 0.5rem; text-decoration: none; border: 1px solid rgba(255,255,255,0.3); }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #fff; }
            .container { max-width: 1200px; margin: 24px auto; padding: 0 20px; }
            .card { background: white; border-radius: 0.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 24px; }
            .card h2 { font-size: 1.2em; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid #E0E0E0; }
            .form-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 12px; }
            .form-group { flex: 1; min-width: 140px; }
            .form-group label { display: block; font-size: 0.85em; color: #666; margin-bottom: 4px; }
            .form-group input { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 0.5rem; font-size: 16px; min-height: 44px; }
            .btn { padding: 10px 20px; border: none; border-radius: 0.5rem; cursor: pointer; font-size: 1em; font-weight: 600; text-decoration: none; display: inline-block; min-height: 44px; }
            .btn-primary { background: #FE0100; color: white; }
            .btn-primary:hover { background: #cc0000; color: white; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; color: white; }
            .btn-success { background: #28a745; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-warning { background: #ffc107; color: #000; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; }
            th { background: #f8f9fa; font-weight: 600; font-size: 0.9em; }
            .actions-cell { display: flex; flex-wrap: wrap; gap: 8px; }
            .badge { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; }
            .badge-admin { background: #FE0100; color: white; }
            .badge-user { background: #6c757d; color: white; }
            .badge-active { background: #d4edda; color: #155724; }
            .badge-revoked { background: #f8d7da; color: #721c24; }
            .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; }
            .modal.show { display: flex; }
            .modal-content { background: white; border-radius: 0.5rem; padding: 24px; max-width: 420px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
            .modal-content h3 { margin-bottom: 16px; }
            .modal-content .form-group { margin-bottom: 16px; }
            .modal-actions { margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end; }
            .flash { padding: 12px 20px; margin-bottom: 20px; border-radius: 0.5rem; }
            .flash.success { background: #d4edda; color: #155724; }
            .flash.error { background: #f8d7da; color: #721c24; }
            @media (max-width: 768px) { .form-row { flex-direction: column; } .form-group { min-width: 100%; } th, td { padding: 10px; font-size: 0.9em; } .actions-cell { flex-direction: column; } }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>👥 Manage Users</h1>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        <div class="container">
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                <div class="flash {{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
            {% endwith %}

            <div class="card">
                <h2>Users</h2>
                {% if users %}
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Email</th>
                            <th>Full Name</th>
                            <th>Access</th>
                            <th>Last Login</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for user in users %}
                        <tr>
                            <td>{{ user.username }}</td>
                            <td>{{ user.email or '-' }}</td>
                            <td>{{ user.full_name or '-' }}</td>
                            <td>
                                {% if user.is_revoked %}
                                <span class="badge badge-revoked">Revoked</span>
                                {% else %}
                                <span class="badge badge-active">Active</span>
                                {% endif %}
                            </td>
                            <td>{{ user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never' }}</td>
                            <td class="actions-cell">
                                <button type="button" class="btn btn-secondary btn-edit-user" data-id="{{ user.id }}" data-username="{{ user.username|e }}" data-email="{{ (user.email or '')|e }}" data-full-name="{{ (user.full_name or '')|e }}">Edit</button>
                                <button type="button" class="btn btn-secondary btn-password-user" data-id="{{ user.id }}" data-username="{{ user.username|e }}">Reset Password</button>
                                {% if user.username != current_user.username and not user.is_revoked %}
                                    <form method="POST" action="{{ url_for('users_revoke', user_id=user.id) }}" style="display: inline;" onsubmit="return confirm('Remove {{ user.username }}? This will delete their account and they will no longer be able to log in.');">
                                        <button type="submit" class="btn btn-danger">Revoke Access</button>
                                    </form>
                                {% elif user.username == current_user.username %}
                                <span style="color: #999; font-size: 0.9em;">(you)</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color: #666;">No users yet. Users are created when you add a new hire and they start onboarding.</p>
                {% endif %}
            </div>
        </div>

        <div id="editModal" class="modal">
            <div class="modal-content">
                <h3>Edit User</h3>
                <form method="POST" id="editUserForm">
                    <input type="hidden" name="user_id" id="editUserId">
                    <div class="form-group">
                        <label>Username</label>
                        <input type="text" id="editUsername" readonly style="background: #f0f0f0;">
                    </div>
                    <div class="form-group">
                        <label>Email</label>
                        <input type="email" name="email" id="editUserEmail" placeholder="user@example.com">
                    </div>
                    <div class="form-group">
                        <label>Full name</label>
                        <input type="text" name="full_name" id="editUserFullName" placeholder="Full Name">
                    </div>
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('editModal').classList.remove('show')">Cancel</button>
                        <button type="submit" class="btn btn-primary">Save</button>
                    </div>
                </form>
            </div>
        </div>

        <div id="passwordModal" class="modal">
            <div class="modal-content">
                <h3>Reset Password</h3>
                <p id="passwordModalUsername" style="margin-bottom: 12px; color: #666;"></p>
                <form method="POST" id="passwordUserForm">
                    <input type="hidden" name="user_id" id="passwordUserId">
                    <div class="form-group">
                        <label>New password</label>
                        <input type="password" name="new_password" id="userNewPassword" placeholder="••••••••" required minlength="6">
                    </div>
                    <div class="form-group">
                        <label>Confirm password</label>
                        <input type="password" name="confirm_password" id="userConfirmPassword" placeholder="••••••••" required minlength="6">
                    </div>
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('passwordModal').classList.remove('show')">Cancel</button>
                        <button type="submit" class="btn btn-primary">Update Password</button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            document.querySelectorAll('.btn-edit-user').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var id = this.getAttribute('data-id');
                    document.getElementById('editUserId').value = id;
                    document.getElementById('editUsername').value = this.getAttribute('data-username') || '';
                    document.getElementById('editUserEmail').value = this.getAttribute('data-email') || '';
                    document.getElementById('editUserFullName').value = this.getAttribute('data-full-name') || '';
                    document.getElementById('editUserForm').action = '/admin/users/' + id + '/update';
                    document.getElementById('editModal').classList.add('show');
                });
            });
            document.querySelectorAll('.btn-password-user').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var id = this.getAttribute('data-id');
                    var username = this.getAttribute('data-username') || '';
                    document.getElementById('passwordUserId').value = id;
                    document.getElementById('passwordModalUsername').textContent = 'Set new password for: ' + username;
                    document.getElementById('passwordUserForm').action = '/admin/users/' + id + '/reset-password';
                    document.getElementById('userNewPassword').value = '';
                    document.getElementById('userConfirmPassword').value = '';
                    document.getElementById('passwordModal').classList.add('show');
                });
            });
            document.getElementById('passwordUserForm').onsubmit = function() {
                if (document.getElementById('userNewPassword').value !== document.getElementById('userConfirmPassword').value) {
                    alert('Passwords do not match.');
                    return false;
                }
                if (document.getElementById('userNewPassword').value.length < 6) {
                    alert('Password must be at least 6 characters.');
                    return false;
                }
                return true;
            };
            window.onclick = function(e) { if (e.target.classList.contains('modal')) e.target.classList.remove('show'); };
        </script>
    </body>
    </html>
    ''', users=users)
    except Exception as e:
        import traceback
        app.logger.error(f'Error in manage_users: {str(e)}')
        app.logger.error(traceback.format_exc())
        db.session.rollback()
        flash('Unable to load users list. Please try again.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/users/add', methods=['POST'])
@admin_required
def users_add():
    """User creation is disabled; users are only created when starting onboarding (add new hire)."""
    flash('Users cannot be added here. Add a new hire from the New Hires / onboarding flow to create a user.', 'error')
    return redirect(url_for('manage_users'))


@app.route('/admin/users/<int:user_id>/update', methods=['POST'])
@admin_required
def users_update(user_id):
    """Update user email and full name."""
    user = UserModel.query.get(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('manage_users'))
    email = (request.form.get('email') or '').strip()
    full_name = (request.form.get('full_name') or '').strip()
    user.email = email or None
    user.full_name = full_name or None
    try:
        db.session.commit()
        flash(f'User "{user.username}" updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating: {str(e)}', 'error')
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
    try:
        db.session.commit()
        flash(f'Password updated for "{user.username}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating password: {str(e)}', 'error')
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
        flash(f'Error removing user: {str(e)}', 'error')
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
                flash(f'Error: {str(e)}', 'error')
        else:
            flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('manage_users'))


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
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Roles - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body { background: #f5f5f5; }
            .header { background: #000; color: white; padding: 12px 30px; display: flex; justify-content: space-between; align-items: center; min-height: 60px; }
            .header h1 { font-weight: 800; margin: 0; }
            .back-btn { background: rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; border-radius: 0.5rem; text-decoration: none; border: 1px solid rgba(255,255,255,0.3); }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #fff; }
            .container { max-width: 900px; margin: 30px auto; padding: 0 20px; }
            .panel { background: white; padding: 25px; border-radius: 0.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
            .panel h2 { margin-bottom: 20px; color: #000; font-size: 1.3em; }
            .btn { display: inline-block; padding: 10px 20px; background: #FE0100; color: white; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; font-size: 1em; }
            .btn:hover { background: #c00; color: white; }
            .btn-success { background: #28a745; }
            .btn-success:hover { background: #218838; color: white; }
            .btn-secondary { background: #6c757d; color: white; text-decoration: none; }
            .btn-secondary:hover { color: white; background: #5a6268; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid #eee; }
            th { background: #f8f9fa; font-weight: 600; }
            tr:hover { background: #f8f9fa; }
            .form-group { margin-bottom: 15px; }
            .form-group label { display: block; margin-bottom: 6px; font-weight: 600; }
            .form-group input[type="text"] { width: 100%; max-width: 300px; padding: 10px 12px; border: 1px solid #ddd; border-radius: 0.5rem; }
            .role-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎭 Manage Roles</h1>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        <div class="container">
            <div class="panel">
                <h2>Add role</h2>
                <form method="POST" action="{{ url_for('add_role') }}" style="display: flex; gap: 15px; align-items: flex-end; flex-wrap: wrap;">
                    <div class="form-group" style="margin-bottom: 0;">
                        <label for="role_name">Role name</label>
                        <input type="text" name="name" id="role_name" placeholder="e.g., Sales Associate" required>
                    </div>
                    <button type="submit" class="btn btn-success">Add role</button>
                </form>
            </div>
            <div class="panel">
                <h2>Job roles ({{ roles|length }})</h2>
                <p style="color: #666; margin-bottom: 15px;">Set default documents per role. When a role is selected during onboarding, those documents are pre-selected for the new hire.</p>
                {% if roles %}
                <table>
                    <thead>
                        <tr><th>Role</th><th>Default documents</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                        {% for role in roles %}
                        <tr>
                            <td><strong>{{ role.name }}</strong></td>
                            <td>{{ role.default_documents.count() }} document(s)</td>
                            <td>
                                <div class="role-actions">
                                    <a href="{{ url_for('role_default_documents', role_id=role.id) }}" class="btn btn-secondary">Default documents</a>
                                    <form method="POST" action="{{ url_for('delete_role', role_id=role.id) }}" style="display: inline;" onsubmit="return confirm('Delete role {{ role.name }}?');">
                                        <button type="submit" class="btn" style="background: #dc3545;">Delete</button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color: #666;">No roles yet. Add one above.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', roles=roles)


@app.route('/admin/roles/add', methods=['POST'])
@admin_required
def add_role():
    """Create a new role"""
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Role name is required.', 'error')
        return redirect(url_for('manage_roles'))
    existing = Role.query.filter(db.func.lower(Role.name) == name.lower()).first()
    if existing:
        flash(f'Role "{name}" already exists.', 'error')
        return redirect(url_for('manage_roles'))
    try:
        role = Role(name=name)
        db.session.add(role)
        db.session.commit()
        flash(f'Role "{name}" added.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding role: {str(e)}', 'error')
    return redirect(url_for('manage_roles'))


@app.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
@admin_required
def delete_role(role_id):
    """Delete a role"""
    role = Role.query.get(role_id)
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('manage_roles'))
    try:
        # Clear default_documents and new hires' role_id
        NewHire.query.filter_by(role_id=role_id).update({NewHire.role_id: None})
        db.session.delete(role)
        db.session.commit()
        flash(f'Role "{role.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting role: {str(e)}', 'error')
    return redirect(url_for('manage_roles'))


@app.route('/admin/roles/<int:role_id>/documents', methods=['GET', 'POST'])
@admin_required
def role_default_documents(role_id):
    """Manage default documents for a role"""
    role = Role.query.get(role_id)
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('manage_roles'))
    # Documents that have signature fields (same as onboarding)
    documents = Document.query.filter(
        Document.is_visible == True,
        exists().where(DocumentSignatureField.document_id == Document.id)
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
            flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('manage_roles'))
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Default documents - {{ role.name }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body { background: #f5f5f5; }
            .header { background: #000; color: white; padding: 12px 30px; display: flex; justify-content: space-between; align-items: center; min-height: 60px; }
            .header h1 { font-weight: 800; margin: 0; }
            .back-btn { background: rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; border-radius: 0.5rem; text-decoration: none; border: 1px solid rgba(255,255,255,0.3); }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #fff; }
            .container { max-width: 700px; margin: 30px auto; padding: 0 20px; }
            .panel { background: white; padding: 25px; border-radius: 0.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
            .panel h2 { margin-bottom: 15px; color: #000; }
            .btn { display: inline-block; padding: 10px 20px; background: #FE0100; color: white; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; font-size: 1em; }
            .btn:hover { background: #c00; color: white; }
            .btn-secondary { background: #6c757d; color: white; text-decoration: none; margin-left: 10px; }
            .btn-secondary:hover { color: white; }
            .doc-item { padding: 12px 0; border-bottom: 1px solid #eee; display: flex; align-items: center; gap: 12px; }
            .doc-item:last-child { border-bottom: none; }
            .doc-item input[type="checkbox"] { width: 18px; height: 18px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Default documents: {{ role.name }}</h1>
            <a href="{{ url_for('manage_roles') }}" class="back-btn">← Back to Roles</a>
        </div>
        <div class="container">
            <div class="panel">
                <h2>Documents to assign by default</h2>
                <p style="color: #666; margin-bottom: 20px;">When this role is selected during onboarding, these documents will be pre-selected. You can still change the selection in the wizard.</p>
                <form method="POST">
                    {% if documents %}
                    {% for doc in documents %}
                    <div class="doc-item">
                        <input type="checkbox" name="document_id" value="{{ doc.id }}" id="doc_{{ doc.id }}" {{ 'checked' if doc.id in default_doc_ids else '' }}>
                        <label for="doc_{{ doc.id }}">{{ doc.name_for_users }}</label>
                    </div>
                    {% endfor %}
                    {% else %}
                    <p style="color: #666;">No documents with signature fields available. <a href="{{ url_for('manage_documents') }}">Manage Forms</a> first.</p>
                    {% endif %}
                    {% if documents %}
                    <div style="margin-top: 20px;">
                        <button type="submit" class="btn">Save default documents</button>
                        <a href="{{ url_for('manage_roles') }}" class="btn btn-secondary">Cancel</a>
                    </div>
                    {% endif %}
                </form>
            </div>
        </div>
    </body>
    </html>
    ''', role=role, documents=documents, default_doc_ids=default_doc_ids)


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


@app.route('/admin/manage-admins')
@admin_required
def manage_admins():
    """Manage admin users: add, update, delete, change password"""
    admins = UserModel.query.filter_by(role='admin').order_by(UserModel.username).all()
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Admins - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body { background: #f5f5f5; }
            .header {
                background: #000000;
                color: white;
                padding: 12px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                min-height: 60px;
            }
            .header h1 { font-size: 1.4em; font-weight: 800; }
            .back-btn {
                background: rgba(255,255,255,0.2);
                color: #FFFFFF;
                padding: 8px 16px;
                border-radius: 0.5rem;
                text-decoration: none;
                font-size: 0.95em;
                border: 1px solid rgba(255,255,255,0.3);
            }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #FFFFFF; }
            .container { max-width: 1000px; margin: 24px auto; padding: 0 20px; }
            .card {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                padding: 24px;
                margin-bottom: 24px;
            }
            .card h2 { font-size: 1.2em; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid #E0E0E0; }
            .form-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 12px; }
            .form-group { flex: 1; min-width: 140px; }
            .form-group label { display: block; font-size: 0.85em; color: #666; margin-bottom: 4px; }
            .form-group input {
                width: 100%;
                padding: 8px 12px;
                border: 1px solid #ddd;
                border-radius: 0.35rem;
                font-size: 15px;
            }
            .btn {
                padding: 6px 12px;
                border: none;
                border-radius: 0.35rem;
                cursor: pointer;
                font-size: 0.85em;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                white-space: nowrap;
            }
            .btn-sm { padding: 4px 10px; font-size: 0.8em; }
            .btn-primary { background: #FE0100; color: white; }
            .btn-primary:hover { background: #cc0000; color: white; }
            .btn-success { background: #28a745; color: white; }
            .btn-success:hover { background: #218838; color: white; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-danger:hover { background: #c82333; color: white; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.95em; }
            th { background: #f8f9fa; font-weight: 600; font-size: 0.85em; }
            .actions-cell {
                display: flex;
                flex-wrap: nowrap;
                gap: 6px;
                align-items: center;
            }
            .actions-cell .btn { margin: 0; }
            .actions-cell form { display: inline; margin: 0; }
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0; top: 0;
                width: 100%; height: 100%;
                background: rgba(0,0,0,0.5);
                align-items: center;
                justify-content: center;
            }
            .modal.show { display: flex; }
            .modal-content {
                background: white;
                border-radius: 0.5rem;
                padding: 24px;
                max-width: 420px;
                width: 90%;
                box-shadow: 0 4px 20px rgba(0,0,0,0.2);
            }
            .modal-content h3 { margin-bottom: 16px; }
            .modal-content .form-group { margin-bottom: 16px; }
            .modal-actions { margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end; }
            .flash { padding: 12px 20px; margin-bottom: 20px; border-radius: 0.5rem; }
            .flash.success { background: #d4edda; color: #155724; }
            .flash.error { background: #f8d7da; color: #721c24; }
            @media (max-width: 768px) {
                .form-row { flex-direction: column; }
                .form-group { min-width: 100%; }
                th, td { padding: 10px; font-size: 0.9em; }
                .actions-cell { flex-direction: column; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🛡️ Manage Admins</h1>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        <div class="container">
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                <div class="flash {{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
            {% endwith %}

            <div class="card">
                <h2>Add Admin</h2>
                <form method="POST" action="{{ url_for('manage_admins_add') }}">
                    <div class="form-row">
                        <div class="form-group">
                            <label>Username</label>
                            <input type="text" name="username" placeholder="Username" required>
                        </div>
                        <div class="form-group">
                            <label>Email (for login)</label>
                            <input type="email" name="email" placeholder="admin@example.com">
                        </div>
                        <div class="form-group">
                            <label>Password</label>
                            <input type="password" name="password" placeholder="••••••••" required>
                        </div>
                        <div class="form-group">
                            <label>Full name (optional)</label>
                            <input type="text" name="full_name" placeholder="Full Name">
                        </div>
                        <div class="form-group" style="flex: 0; align-self: flex-end;">
                            <label>&nbsp;</label>
                            <button type="submit" class="btn btn-primary btn-sm">Add Admin</button>
                        </div>
                    </div>
                </form>
            </div>

            <div class="card">
                <h2>Admin Users</h2>
                {% if admins %}
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Email</th>
                            <th>Full Name</th>
                            <th>Last Login</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for admin in admins %}
                        <tr>
                            <td>{{ admin.username }}</td>
                            <td>{{ admin.email or '-' }}</td>
                            <td>{{ admin.full_name or '-' }}</td>
                            <td>{{ admin.last_login.strftime('%Y-%m-%d %H:%M') if admin.last_login else 'Never' }}</td>
                            <td class="actions-cell">
                                <button type="button" class="btn btn-secondary btn-sm btn-edit-admin" data-id="{{ admin.id }}" data-username="{{ admin.username|e }}" data-email="{{ (admin.email or '')|e }}" data-full-name="{{ (admin.full_name or '')|e }}">Edit</button>
                                <button type="button" class="btn btn-secondary btn-sm btn-password-admin" data-id="{{ admin.id }}" data-username="{{ admin.username|e }}">Password</button>
                                {% if admin.username != current_user.username %}
                                <form method="POST" action="{{ url_for('manage_admins_remove', user_id=admin.id) }}" style="display: inline;" onsubmit="return confirm('Remove admin role from {{ admin.username }}? They will become a regular user.');">
                                    <button type="submit" class="btn btn-danger btn-sm">Remove</button>
                                </form>
                                {% else %}
                                <span style="color: #999; font-size: 0.8em;">(you)</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color: #666;">No admin users yet. Add one above.</p>
                {% endif %}
            </div>
        </div>

        <div id="editModal" class="modal">
            <div class="modal-content">
                <h3>Edit Admin</h3>
                <form method="POST" id="editForm">
                    <input type="hidden" name="user_id" id="editUserId">
                    <div class="form-group">
                        <label>Username</label>
                        <input type="text" id="editUsername" readonly style="background: #f0f0f0;">
                    </div>
                    <div class="form-group">
                        <label>Email</label>
                        <input type="email" name="email" id="editEmail" placeholder="admin@example.com">
                    </div>
                    <div class="form-group">
                        <label>Full name</label>
                        <input type="text" name="full_name" id="editFullName" placeholder="Full Name">
                    </div>
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeEditModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Save</button>
                    </div>
                </form>
            </div>
        </div>

        <div id="passwordModal" class="modal">
            <div class="modal-content">
                <h3>Change Password</h3>
                <p id="passwordModalUsername" style="margin-bottom: 12px; color: #666;"></p>
                <form method="POST" id="passwordForm">
                    <input type="hidden" name="user_id" id="passwordUserId">
                    <div class="form-group">
                        <label>New password</label>
                        <input type="password" name="new_password" id="newPassword" placeholder="••••••••" required minlength="6">
                    </div>
                    <div class="form-group">
                        <label>Confirm password</label>
                        <input type="password" name="confirm_password" id="confirmPassword" placeholder="••••••••" required minlength="6">
                    </div>
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="closePasswordModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Update Password</button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            document.querySelectorAll('.btn-edit-admin').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var id = this.getAttribute('data-id');
                    var username = this.getAttribute('data-username') || '';
                    var email = this.getAttribute('data-email') || '';
                    var fullName = this.getAttribute('data-full-name') || '';
                    document.getElementById('editUserId').value = id;
                    document.getElementById('editUsername').value = username;
                    document.getElementById('editEmail').value = email;
                    document.getElementById('editFullName').value = fullName;
                    document.getElementById('editForm').action = '/admin/manage-admins/' + id + '/update';
                    document.getElementById('editModal').classList.add('show');
                });
            });
            document.querySelectorAll('.btn-password-admin').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var id = this.getAttribute('data-id');
                    var username = this.getAttribute('data-username') || '';
                    document.getElementById('passwordUserId').value = id;
                    document.getElementById('passwordModalUsername').textContent = 'Set new password for: ' + username;
                    document.getElementById('passwordForm').action = '/admin/manage-admins/' + id + '/change-password';
                    document.getElementById('newPassword').value = '';
                    document.getElementById('confirmPassword').value = '';
                    document.getElementById('passwordModal').classList.add('show');
                });
            });
            function closeEditModal() {
                document.getElementById('editModal').classList.remove('show');
            }
            function closePasswordModal() {
                document.getElementById('passwordModal').classList.remove('show');
            }
            function closePasswordModal() {
                document.getElementById('passwordModal').classList.remove('show');
            }
            document.getElementById('passwordForm').onsubmit = function() {
                var p1 = document.getElementById('newPassword').value;
                var p2 = document.getElementById('confirmPassword').value;
                if (p1 !== p2) {
                    alert('Passwords do not match.');
                    return false;
                }
                if (p1.length < 6) {
                    alert('Password must be at least 6 characters.');
                    return false;
                }
                return true;
            };
            window.onclick = function(e) {
                if (e.target.classList.contains('modal')) {
                    e.target.classList.remove('show');
                }
            };
        </script>
    </body>
    </html>
    ''', admins=admins)


@app.route('/admin/manage-admins/add', methods=['POST'])
@admin_required
def manage_admins_add():
    """Add a new admin user"""
    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip()
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
        flash(f'Error adding admin: {str(e)}', 'error')
    return redirect(url_for('manage_admins'))


@app.route('/admin/manage-admins/<int:user_id>/update', methods=['POST'])
@admin_required
def manage_admins_update(user_id):
    """Update admin email and full name"""
    user = UserModel.query.get(user_id)
    if not user or user.role != 'admin':
        flash('Admin not found.', 'error')
        return redirect(url_for('manage_admins'))

    email = (request.form.get('email') or '').strip()
    full_name = (request.form.get('full_name') or '').strip()
    user.email = email or None
    user.full_name = full_name or None
    try:
        db.session.commit()
        flash(f'Admin "{user.username}" updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating: {str(e)}', 'error')
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
        flash(f'Error updating password: {str(e)}', 'error')
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
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('manage_admins'))


@app.route('/admin/documents')
@admin_required
def manage_documents():
    """Manage documents - upload and manage new hire paperwork"""
    try:
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
                return redirect(url_for('admin_dashboard'))
            documents = Document.query.order_by(Document.created_at.desc()).all()
        else:
            raise
    try:
        # Get signature status for each document
        for doc in documents:
            signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
            doc.signature_fields_count = len(signature_fields)
            # Count how many users have signed
            try:
                signatures = DocumentSignature.query.filter_by(document_id=doc.id).all()
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
        documents = Document.query.order_by(Document.created_at.desc()).all()
        for doc in documents:
            doc.signature_fields_count = 0
            doc.signatures_count = 0
            doc.signed_users_count = 0
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Documents - Onboarding App</title>
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
            .btn-danger {
                background: #FE0100;
            }
            .btn-primary {
                background: #007bff;
            }
            .btn-view {
                background: white;
                color: #000000;
                border: 2px solid #000000;
                border-radius: 0.5rem;
            }
            .btn-view:hover {
                background: #f5f5f5;
            }
            .upload-form {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 0.5rem;
                margin-bottom: 20px;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group input[type="file"],
            .form-group input[type="text"],
            .form-group textarea {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 14px;
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .form-group input[type="checkbox"] {
                width: auto;
                margin-right: 10px;
            }
            .checkbox-group {
                display: flex;
                align-items: center;
            }
            table {
                width: 100%;
                background: white;
                border-radius: 0.5rem;
                overflow: visible;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-top: 20px;
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            td {
                position: relative;
            }
            th {
                background: #f8f9fa;
                font-weight: bold;
            }
            .badge {
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 0.85em;
                font-weight: bold;
            }
            .badge-visible {
                background: #28a745;
                color: white;
            }
            .badge-hidden {
                background: #808080;
                color: white;
            }
            .action-btn {
                padding: 6px 12px;
                border: none;
                border-radius: 0.5rem;
                cursor: pointer;
                font-size: 0.85em;
                text-decoration: none;
                display: inline-block;
                margin: 2px 3px;
                white-space: nowrap;
            }
            .actions-group {
                display: flex;
                flex-wrap: nowrap;
                gap: 5px;
                align-items: center;
                justify-content: space-between;
                width: 100%;
            }
            .actions-primary {
                display: flex;
                gap: 5px;
                flex-wrap: nowrap;
                flex-shrink: 0;
            }
            .actions-secondary {
                position: relative;
                display: inline-block;
                flex-shrink: 0;
                margin-left: auto;
            }
            .actions-menu-btn {
                padding: 6px 12px;
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 0.5rem;
                cursor: pointer;
                font-size: 0.85em;
            }
            .actions-menu-btn:hover {
                background: #5a6268;
            }
            .actions-dropdown {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 180px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                border-radius: 0.5rem;
                margin-top: 5px;
                z-index: 1000;
                border: 1px solid #ddd;
            }
            .actions-dropdown.show {
                display: block;
            }
            .actions-dropdown.show-up {
                top: auto;
                bottom: 100%;
                margin-top: 0;
                margin-bottom: 5px;
            }
            .actions-dropdown-item {
                padding: 10px 15px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
                border-bottom: 1px solid #f0f0f0;
                font-size: 0.9em;
            }
            .actions-dropdown-item:last-child {
                border-bottom: none;
            }
            .actions-dropdown-item:hover {
                background: #f5f5f5;
            }
            .actions-dropdown-item.danger {
                color: #FE0100;
            }
            .actions-dropdown-item.danger:hover {
                background: #f8d7da;
            }
            .signature-status {
                font-size: 0.85em;
            }
            .signature-status-badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                background: #e7f3ff;
                color: #0066cc;
                margin-top: 3px;
            }
            .file-size {
                color: #808080;
                font-size: 0.9em;
            }
            .modal {
                display: none;
                position: fixed;
                z-index: 10000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.7);
                overflow: auto;
            }
            .modal.show {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .modal-content {
                background-color: white;
                margin: auto;
                padding: 0;
                border: none;
                border-radius: 0.5rem;
                width: 90%;
                max-width: 1600px;
                max-height: 90vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }
            .modal-header {
                padding: 20px;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: #f8f9fa;
                border-radius: 8px 8px 0 0;
            }
            .modal-header h2 {
                margin: 0;
                color: #000000;
            }
            .close-modal {
                color: #aaa;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                background: none;
                border: none;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .close-modal:hover {
                color: #000;
            }
            .modal-body {
                padding: 0;
                overflow: auto;
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #525252;
            }
            .modal-body iframe {
                width: 100%;
                height: 70vh;
                border: none;
            }
            .modal-body img {
                max-width: 100%;
                max-height: 70vh;
                object-fit: contain;
            }
            .modal-body .document-viewer {
                width: 100%;
                height: 70vh;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
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
                .admin-panel h2 {
                    font-size: 1.3em;
                }
                .upload-form {
                    padding: 15px;
                }
                .form-group input[type="text"],
                .form-group textarea,
                .form-group input[type="file"] {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
                }
                table {
                    display: block;
                    overflow-x: auto;
                    -webkit-overflow-scrolling: touch;
                    font-size: 0.85em;
                }
                th, td {
                    padding: 10px 8px;
                    white-space: nowrap;
                }
                .actions-group {
                    flex-direction: column;
                    align-items: stretch;
                }
                .actions-primary {
                    flex-direction: column;
                    width: 100%;
                }
                .actions-primary .action-btn {
                    width: 100%;
                    margin: 5px 0;
                    min-height: 44px;
                }
                .actions-secondary {
                    width: 100%;
                    margin-left: 0;
                    margin-top: 10px;
                }
                .actions-menu-btn {
                    width: 100%;
                    min-height: 44px;
                }
                .modal-content {
                    width: 95%;
                    max-height: 95vh;
                }
                .modal-body iframe {
                    height: 60vh !important;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
                    font-size: 1em;
                }
            }
            
            @media (max-width: 480px) {
                .header-content h1 {
                    font-size: 1em;
                }
                .admin-panel {
                    padding: 12px;
                }
                .admin-panel h2 {
                    font-size: 1.2em;
                }
                th, td {
                    padding: 8px 6px;
                    font-size: 0.8em;
                }
                .modal-content {
                    width: 100%;
                    max-height: 100vh;
                    border-radius: 0;
                }
                .modal-body iframe {
                    height: 50vh !important;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>📄 Manage Documents</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Upload New Document</h2>
                <form method="POST" action="{{ url_for('upload_document') }}" enctype="multipart/form-data" class="upload-form">
                    <div class="form-group">
                        <label for="file">Select File:</label>
                        <input type="file" name="file" id="file" required>
                        <small style="color: #666;">Allowed: PDF, DOC, DOCX, XLS, XLSX, TXT, JPG, PNG, GIF (Max 50MB)</small>
                    </div>
                    <div class="form-group">
                        <label for="display_name">Name (visible to users):</label>
                        <input type="text" name="display_name" id="display_name" placeholder="Leave blank to use file name" maxlength="255" style="width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 0.5rem;">
                        <small style="color: #666;">Optional. This is the title users see (e.g. "Employee Handbook"). If blank, the file name is used.</small>
                    </div>
                    <div class="form-group">
                        <label for="description">Description (optional):</label>
                        <textarea name="description" id="description" placeholder="Enter document description..."></textarea>
                    </div>
                    <div class="form-group">
                        <div class="checkbox-group">
                            <input type="checkbox" name="is_visible" id="is_visible" value="1">
                            <label for="is_visible">Make visible to regular users</label>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success">Upload Document</button>
                </form>
            </div>
            
            <div class="admin-panel">
                <h2>Uploaded Documents</h2>
                {% if documents %}
                <table>
                    <thead>
                        <tr>
                            <th>Filename</th>
                            <th>Description</th>
                            <th>Size</th>
                            <th>Visibility</th>
                            <th>Signature Status</th>
                            <th>Uploaded By</th>
                            <th>Uploaded</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for doc in documents %}
                        <tr>
                            <td><strong>{{ doc.display_name or doc.original_filename }}</strong></td>
                            <td>{{ doc.description or '-' }}</td>
                            <td class="file-size">
                                {% if doc.file_size %}
                                    {% if doc.file_size < 1024 %}
                                        {{ doc.file_size }} B
                                    {% elif doc.file_size < 1048576 %}
                                        {{ "%.1f"|format(doc.file_size / 1024) }} KB
                                    {% else %}
                                        {{ "%.1f"|format(doc.file_size / 1048576) }} MB
                                    {% endif %}
                                {% else %}
                                    -
                                {% endif %}
                            </td>
                            <td>
                                <span class="badge badge-{{ 'visible' if doc.is_visible else 'hidden' }}">
                                    {{ 'Visible' if doc.is_visible else 'Hidden' }}
                                </span>
                            </td>
                            <td class="signature-status">
                                {% if doc.signature_fields_count > 0 %}
                                    <div class="signature-status-badge">
                                        ✍️ {{ doc.signature_fields_count }} field(s)
                                    </div>
                                    <div style="font-size: 0.75em; color: #666; margin-top: 2px;">
                                        {{ doc.signed_users_count }} user(s) signed
                                    </div>
                                {% else %}
                                    <span style="color: #999;">-</span>
                                {% endif %}
                            </td>
                            <td>{{ doc.uploaded_by }}</td>
                            <td>{{ doc.created_at.strftime('%Y-%m-%d %H:%M') if doc.created_at else '-' }}</td>
                            <td>
                                <div class="actions-group">
                                    <div class="actions-primary">
                                        <button onclick="openDocumentModal({{ doc.id }}, '{{ doc.original_filename }}', '{{ doc.file_type or '' }}')" class="action-btn btn-view" title="View Document">👁️ View</button>
                                        <a href="{{ url_for('download_document', doc_id=doc.id) }}" class="action-btn btn-primary" title="Download Document">⬇️ Download</a>
                                        <a href="{{ url_for('set_signature_fields', doc_id=doc.id) }}" class="action-btn btn-success" title="Set Signature Fields">✍️ Signatures</a>
                                    </div>
                                    <div class="actions-secondary">
                                        <button class="actions-menu-btn" onclick="toggleActionsMenu({{ doc.id }})" title="More Options">⋮</button>
                                        <div class="actions-dropdown" id="menu-{{ doc.id }}">
                                            {% if doc.signature_fields_count > 0 and doc.signed_users_count > 0 %}
                                            <a href="{{ url_for('view_signed_documents', doc_id=doc.id) }}" class="actions-dropdown-item">
                                                📥 Download Signed Copies
                                            </a>
                                        {% endif %}
                                        <a href="{{ url_for('assign_document', doc_id=doc.id) }}" class="actions-dropdown-item">
                                                👤 Assign to Users
                                            </a>
                                            <a href="{{ url_for('rename_document', doc_id=doc.id) }}" class="actions-dropdown-item">
                                                ✏️ Rename
                                            </a>
                                            <a href="{{ url_for('view_document_embed', doc_id=doc.id) }}" class="actions-dropdown-item" target="_blank" title="Open in new tab to print">
                                                🖨️ Print
                                            </a>
                                            <form method="POST" action="{{ url_for('toggle_document_visibility') }}" style="display: block;">
                                                <input type="hidden" name="doc_id" value="{{ doc.id }}">
                                                <button type="submit" class="actions-dropdown-item" style="width: 100%; text-align: left; border: none; background: none; cursor: pointer;">
                                                    {{ '👁️ Make Visible' if not doc.is_visible else '🙈 Make Hidden' }}
                                                </button>
                                            </form>
                                            <form method="POST" action="{{ url_for('delete_document') }}" style="display: block;">
                                                <input type="hidden" name="doc_id" value="{{ doc.id }}">
                                                <button type="submit" class="actions-dropdown-item danger" style="width: 100%; text-align: left; border: none; background: none; cursor: pointer;" 
                                                        onclick="return confirm('Delete {{ doc.original_filename }}?')">
                                                    🗑️ Delete
                                                </button>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p>No documents uploaded yet.</p>
                {% endif %}
            </div>
        </div>
        
        <!-- Document Viewer Modal -->
        <div id="documentModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 id="modalTitle">Document Viewer</h2>
                    <button class="close-modal" onclick="closeDocumentModal()">&times;</button>
                </div>
                <div class="modal-body" id="modalBody">
                    <div class="document-viewer">Loading document...</div>
                </div>
            </div>
        </div>
        
        <script>
            function openDocumentModal(docId, filename, fileType) {
                var modal = document.getElementById('documentModal');
                var modalTitle = document.getElementById('modalTitle');
                var modalBody = document.getElementById('modalBody');
                
                modalTitle.textContent = filename;
                modalBody.innerHTML = '<div class="document-viewer">Loading document...</div>';
                modal.classList.add('show');
                
                // Determine file type
                var ext = filename.split('.').pop().toLowerCase();
                var viewUrl = "{{ url_for('view_document_embed', doc_id=0) }}".replace('0', docId);
                
                // Check if it's an image
                if (['jpg', 'jpeg', 'png', 'gif'].includes(ext) || (fileType && fileType.startsWith('image/'))) {
                    modalBody.innerHTML = '<img src="' + viewUrl + '" alt="' + filename + '">';
                }
                // Check if it's a PDF
                else if (ext === 'pdf' || fileType === 'application/pdf') {
                    modalBody.innerHTML = '<iframe src="' + viewUrl + '"></iframe>';
                }
                // Check if it's a text file
                else if (ext === 'txt' || fileType === 'text/plain') {
                    fetch(viewUrl)
                        .then(response => response.text())
                        .then(text => {
                            modalBody.innerHTML = '<pre style="padding: 20px; white-space: pre-wrap; word-wrap: break-word; color: white;">' + escapeHtml(text) + '</pre>';
                        })
                        .catch(error => {
                            modalBody.innerHTML = '<div class="document-viewer">Error loading document. Please download it instead.</div>';
                        });
                }
                // For other file types, show message
                else {
                    modalBody.innerHTML = '<div class="document-viewer">This file type cannot be viewed in browser. Please download it.</div>';
                }
            }
            
            function closeDocumentModal() {
                var modal = document.getElementById('documentModal');
                modal.classList.remove('show');
                var modalBody = document.getElementById('modalBody');
                modalBody.innerHTML = '';
            }
            
            function escapeHtml(text) {
                var map = {
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#039;'
                };
                return text.replace(/[&<>"']/g, function(m) { return map[m]; });
            }
            
            // Close modal when clicking outside
            window.onclick = function(event) {
                var modal = document.getElementById('documentModal');
                if (event.target == modal) {
                    closeDocumentModal();
                }
                
                // Close dropdown menus when clicking outside
                if (!event.target.matches('.actions-menu-btn') && !event.target.closest('.actions-dropdown')) {
                    var dropdowns = document.querySelectorAll('.actions-dropdown');
                    dropdowns.forEach(function(dropdown) {
                        if (dropdown.classList.contains('show')) {
                            dropdown.classList.remove('show');
                        }
                    });
                }
            }
            
            // Close modal with Escape key
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape') {
                    closeDocumentModal();
                }
            });
            
            // Toggle actions dropdown menu
            function toggleActionsMenu(docId) {
                var menu = document.getElementById('menu-' + docId);
                var allMenus = document.querySelectorAll('.actions-dropdown');
                
                // Close all other menus
                allMenus.forEach(function(m) {
                    if (m !== menu) {
                        m.classList.remove('show');
                        m.classList.remove('show-up');
                    }
                });
                
                // Toggle current menu
                var isShowing = menu.classList.contains('show');
                menu.classList.toggle('show');
                
                if (!isShowing) {
                    // Check if there's enough space below, if not, show above
                    setTimeout(function() {
                        var rect = menu.getBoundingClientRect();
                        var viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                        var spaceBelow = viewportHeight - rect.bottom;
                        var spaceAbove = rect.top;
                        var menuHeight = rect.height;
                        
                        // If not enough space below (less than 50px buffer) and more space above, show upward
                        if (spaceBelow < 50 && spaceAbove > menuHeight) {
                            menu.classList.add('show-up');
                        } else {
                            menu.classList.remove('show-up');
                        }
                    }, 10);
                }
            }
        </script>
    </body>
    </html>
    ''', documents=documents)


@app.route('/admin/upload-document', methods=['POST'])
@admin_required
def upload_document():
    """Upload a new document"""
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('manage_documents'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('manage_documents'))
    
    if not allowed_file(file.filename):
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
        
        db.session.add(document)
        db.session.commit()
        
        flash(f'Document "{original_filename}" uploaded successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error uploading file: {str(e)}', 'error')
    
    return redirect(url_for('manage_documents'))


@app.route('/admin/toggle-document-visibility', methods=['POST'])
@admin_required
def toggle_document_visibility():
    """Toggle document visibility"""
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
    
    status = 'visible' if document.is_visible else 'hidden'
    flash(f'Document visibility set to {status}.', 'success')
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
        # Unlink user tasks that referenced this document (column is nullable)
        for task in UserTask.query.filter_by(document_id=doc_id).all():
            task.document_id = None
        
        # Delete file from filesystem
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass  # continue even if file already gone
        
        # Delete document
        db.session.delete(document)
        db.session.commit()
        
        flash(f'Document "{original_filename}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting document: {str(e)}', 'error')
    
    return redirect(url_for('manage_documents'))


@app.route('/admin/documents/<int:doc_id>/rename', methods=['GET', 'POST'])
@admin_required
def rename_document(doc_id):
    """Rename a document (set the name visible to users)"""
    document = Document.query.get(doc_id)
    if not document:
        flash('Document not found.', 'error')
        return redirect(url_for('manage_documents'))
    
    current_name = document.display_name or document.original_filename or ''
    
    if request.method == 'POST':
        new_name = (request.form.get('display_name') or '').strip()
        try:
            if not new_name or new_name == document.original_filename:
                document.display_name = None  # use file name
                db.session.commit()
                flash('Document now uses the file name.', 'success')
            else:
                document.display_name = new_name
                db.session.commit()
                flash(f'Document renamed to "{new_name}".', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error renaming: {str(e)}', 'error')
        return redirect(url_for('manage_documents'))
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rename Document - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'URW Form', Arial, sans-serif; background: #f5f5f5; }
            .header {
                background: #000000;
                color: white;
                padding: 12px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                min-height: 60px;
            }
            .header-content h1 { font-weight: 800; margin: 0; }
            .back-btn {
                background: rgba(255,255,255,0.2);
                color: #fff;
                padding: 8px 16px;
                border-radius: 0.5rem;
                text-decoration: none;
                border: 1px solid rgba(255,255,255,0.3);
            }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #fff; }
            .container { max-width: 600px; margin: 30px auto; padding: 0 20px; }
            .panel {
                background: white;
                padding: 25px;
                border-radius: 0.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .panel h2 { margin-bottom: 20px; color: #000; }
            .form-group { margin-bottom: 20px; }
            .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
            .form-group input[type="text"] {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 1em;
            }
            .form-group small { color: #666; font-size: 0.9em; display: block; margin-top: 6px; }
            .btn {
                display: inline-block;
                padding: 10px 24px;
                background: #FE0100;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 1em;
                font-weight: 600;
                cursor: pointer;
            }
            .btn:hover { background: #c00; color: white; }
            .btn-secondary { background: #6c757d; }
            .btn-secondary:hover { background: #5a6268; color: white; }
            .file-name { color: #666; font-size: 0.9em; margin-top: 8px; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content"><h1>✏️ Rename Document</h1></div>
            <a href="{{ url_for('manage_documents') }}" class="back-btn">← Back to Documents</a>
        </div>
        <div class="container">
            <div class="panel">
                <h2>Name visible to users</h2>
                <p class="file-name">File: {{ document.original_filename }}</p>
                <form method="POST" action="{{ url_for('rename_document', doc_id=document.id) }}">
                    <div class="form-group">
                        <label for="display_name">Display name</label>
                        <input type="text" name="display_name" id="display_name" value="{{ current_name }}" maxlength="255" placeholder="e.g. Employee Handbook">
                        <small>This is the title users see. Leave blank (or match the file name) to use the file name.</small>
                    </div>
                    <button type="submit" class="btn">Save</button>
                    <a href="{{ url_for('manage_documents') }}" class="btn btn-secondary" style="margin-left: 10px; text-decoration: none;">Cancel</a>
                </form>
            </div>
        </div>
    </body>
    </html>
    ''', document=document, current_name=current_name)


@app.route('/admin/documents/<int:doc_id>/signature-fields')
@admin_required
def set_signature_fields(doc_id):
    """Admin interface to set signature field locations on a document"""
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
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Set Signature Fields - {{ document.name_for_users }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
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
                margin: 20px auto;
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
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-primary {
                background: #007bff;
            }
            .btn-danger {
                background: #FE0100;
            }
            .main-content {
                display: grid;
                grid-template-columns: 1fr 350px;
                gap: 20px;
            }
            .document-viewer-container {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
                position: relative;
            }
            .document-viewer {
                position: relative;
                background: #525252;
                min-height: 800px;
                overflow: auto;
                padding: 20px;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }
            #pdfCanvas {
                max-width: 100%;
                height: auto;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                background: white;
                display: block;
                cursor: crosshair;
            }
            .signature-field-indicator {
                position: absolute;
                border: 2px dashed #28a745;
                background: rgba(40, 167, 69, 0.1);
                pointer-events: all;
                z-index: 100;
                cursor: move;
                user-select: none;
                -webkit-user-select: none;
                -moz-user-select: none;
                -ms-user-select: none;
            }
            .signature-field-indicator.resizing {
                border: 2px solid #28a745;
                background: rgba(40, 167, 69, 0.2);
            }
            .resize-handle {
                position: absolute;
                width: 12px;
                height: 12px;
                background: #28a745;
                border: 2px solid white;
                border-radius: 50%;
                cursor: nwse-resize;
                z-index: 101;
                pointer-events: all;
                user-select: none;
                -webkit-user-select: none;
            }
            .resize-handle.bottom-right {
                bottom: -6px;
                right: -6px;
                cursor: nwse-resize;
            }
            .resize-handle.bottom-left {
                bottom: -6px;
                left: -6px;
                cursor: nesw-resize;
            }
            .resize-handle.top-right {
                top: -6px;
                right: -6px;
                cursor: nesw-resize;
            }
            .resize-handle.top-left {
                top: -6px;
                left: -6px;
                cursor: nwse-resize;
            }
            .existing-field-marker {
                position: absolute;
                border: 2px solid #007bff;
                background: rgba(0, 123, 255, 0.1);
                pointer-events: none;
                z-index: 5;
            }
            .existing-field-marker::before {
                content: attr(data-label);
                position: absolute;
                top: -20px;
                left: 0;
                background: #007bff;
                color: white;
                padding: 2px 6px;
                font-size: 11px;
                border-radius: 3px;
                white-space: nowrap;
            }
            .existing-typed-field-marker {
                position: absolute;
                border: 2px solid #ffc107;
                background: rgba(255, 193, 7, 0.1);
                pointer-events: none;
                z-index: 5;
            }
            .existing-typed-field-marker::before {
                content: attr(data-label);
                position: absolute;
                top: -20px;
                left: 0;
                background: #ffc107;
                color: #000;
                padding: 2px 6px;
                font-size: 11px;
                border-radius: 3px;
                white-space: nowrap;
                font-weight: bold;
            }
            .sidebar-panel {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
                font-size: 0.9em;
            }
            .form-group input,
            .form-group select {
                width: 100%;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 16px; /* Prevents zoom on iOS */
                min-height: 44px; /* Touch-friendly */
            }
            .signature-field-item {
                background: #f8f9fa;
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 0.5rem;
                border-left: 3px solid #007bff;
            }
            .signature-field-item h4 {
                margin-bottom: 5px;
                font-size: 0.9em;
            }
            .signature-field-item p {
                font-size: 0.8em;
                color: #808080;
                margin: 3px 0;
            }
            .instructions {
                background: #e7f3ff;
                padding: 15px;
                border-radius: 0.5rem;
                margin-bottom: 20px;
                border-left: 4px solid #007bff;
            }
            .instructions h3 {
                margin-bottom: 10px;
                font-size: 1em;
            }
            .instructions ol {
                margin-left: 20px;
            }
            .instructions li {
                margin-bottom: 5px;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>✍️ Set Signature Fields - {{ document.name_for_users }}</h1>
            </div>
            <a href="{{ url_for('manage_documents') }}" class="back-btn">← Back to Documents</a>
        </div>
        
        <div class="container">
            
            <div class="main-content">
                <div class="document-viewer-container">
                    <h3 style="margin-bottom: 15px;">Document Preview</h3>
                    <div class="document-viewer" id="documentViewer">
                        {% if is_pdf %}
                        <canvas id="pdfCanvas"></canvas>
                        {% else %}
                        <p style="padding: 20px; color: white;">Signature fields can only be set on PDF documents. Please convert this document to PDF first.</p>
                        {% endif %}
                    </div>
                </div>
                
                <div class="sidebar-panel">
                    <h3 style="margin-bottom: 15px;">Add Field</h3>
                    <form id="fieldForm" method="POST" onsubmit="return submitFieldForm(event)">
                        <div class="form-group">
                            <label for="field_type_selector">Field Type:</label>
                            <select name="field_type_selector" id="field_type_selector" required onchange="toggleFieldTypeOptions()">
                                <option value="signature">Signature Field</option>
                                <option value="typed">Typed Field</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="field_label">Field Label:</label>
                            <input type="text" name="field_label" id="field_label" placeholder="e.g., Employee Signature, Name, Date" required>
                        </div>
                        <div class="form-group">
                            <label for="page_number">Page Number:</label>
                            <input type="number" name="page_number" id="page_number" value="1" min="1" required>
                            <p style="font-size: 0.85em; color: #666; margin-top: 5px;">Change this to navigate to different pages</p>
                        </div>
                        
                        <!-- Signature Field Options -->
                        <div id="signatureFieldOptions" class="field-type-options">
                            <div class="form-group">
                                <label for="signature_type">Signature Type:</label>
                                <select name="signature_type" id="signature_type">
                                    <option value="image">Image Signature (Simple)</option>
                                    <option value="cryptographic">Cryptographic Signature (Legally Compliant)</option>
                                </select>
                                <p style="font-size: 0.85em; color: #666; margin-top: 5px;">
                                    <strong>Image:</strong> Visual signature overlay<br>
                                    <strong>Cryptographic:</strong> Legally binding, tamper-evident signature
                                </p>
                            </div>
                        </div>
                        
                        <!-- Typed Field Options -->
                        <div id="typedFieldOptions" class="field-type-options" style="display: none;">
                            <div class="form-group">
                                <label for="typed_field_type">Input Type:</label>
                                <select name="typed_field_type" id="typed_field_type">
                                    <option value="text">Text</option>
                                    <option value="name">Name</option>
                                    <option value="typed_name">Typed Name (auto-fills user's name, click to sign)</option>
                                    <option value="typed_initials">Typed Initials (auto-fills initials, click to sign)</option>
                                    <option value="date">Date</option>
                                    <option value="number">Number</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="typed_placeholder">Placeholder (optional):</label>
                                <input type="text" name="placeholder" id="typed_placeholder" placeholder="e.g., Enter your name">
                            </div>
                            <div class="form-group">
                                <div class="checkbox-group">
                                    <input type="checkbox" name="is_required" id="typed_is_required" checked>
                                    <label for="typed_is_required">Required field</label>
                                </div>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Position (drag on document to create field):</label>
                            <input type="hidden" name="x_position" id="x_position" required>
                            <input type="hidden" name="y_position" id="y_position" required>
                            <input type="hidden" name="width" id="width" value="200">
                            <input type="hidden" name="height" id="height" value="80">
                            <div id="positionDisplay" style="font-size: 0.85em; color: #666; margin-top: 5px; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                                <strong>How to add a field:</strong><br>
                                1. Select field type above (Signature or Typed Field)<br>
                                2. Switch to the corresponding mode using the button above the document<br>
                                3. Click and hold at the top-left corner where you want the field<br>
                                4. Drag to the bottom-right corner to set the size<br>
                                5. Release to create the field<br>
                                6. You can then drag the field to move it, or drag the corner handles to resize it
                            </div>
                        </div>
                        <button type="submit" class="btn btn-success" style="width: 100%;" id="submitButton">Add Field</button>
                    </form>
                    
                    <h3 style="margin-top: 30px; margin-bottom: 15px;">Existing Signature Fields</h3>
                    <div id="existingFields">
                        {% if existing_fields %}
                            {% for field in existing_fields %}
                            <div class="signature-field-item">
                                <h4>{{ field.field_label or 'Signature Field' }}</h4>
                                <p>Page: {{ field.page_number }}</p>
                                <p>Position: ({{ "%.0f"|format(field.x_position) }}, {{ "%.0f"|format(field.y_position) }})</p>
                                <form method="POST" action="{{ url_for('delete_signature_field', field_id=field.id) }}" style="display: inline;">
                                    <button type="submit" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8em;" onclick="return confirm('Delete this signature field?')">Delete</button>
                                </form>
                            </div>
                            {% endfor %}
                        {% else %}
                            <p style="color: #666; font-size: 0.9em;">No signature fields yet.</p>
                        {% endif %}
                    </div>
                    
                    <h3 style="margin-top: 30px; margin-bottom: 15px;">Existing Typed Fields</h3>
                    <div id="existingTypedFields">
                        {% if existing_typed_fields %}
                            {% for field in existing_typed_fields %}
                            <div class="signature-field-item" style="border-left-color: #ffc107;">
                                <h4>{{ field.field_label or 'Typed Field' }}</h4>
                                <p>Type: {{ field.field_type|title }} • Page: {{ field.page_number }}</p>
                                <p>Position: ({{ "%.0f"|format(field.x_position) }}, {{ "%.0f"|format(field.y_position) }})</p>
                                <form method="POST" action="{{ url_for('delete_typed_field', field_id=field.id) }}" style="display: inline;">
                                    <button type="submit" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8em;" onclick="return confirm('Delete this typed field?')">Delete</button>
                                </form>
                            </div>
                            {% endfor %}
                        {% else %}
                            <p style="color: #666; font-size: 0.9em;">No typed fields yet.</p>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            var pdfDoc = null;
            var currentPage = 1;
            var pdfScale = 1.0;
            var canvasOffsetX = 0;
            var canvasOffsetY = 0;
            var currentIndicator = null;
            var isResizing = false;
            var resizeStartX = 0;
            var resizeStartY = 0;
            var resizeStartWidth = 0;
            var resizeStartHeight = 0;
            var resizeHandle = null;
            
            // Load PDF using PDF.js
            function loadPDF() {
                var canvas = document.getElementById('pdfCanvas');
                if (!canvas) return;
                
                // Set up PDF.js worker
                pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                
                // Get PDF URL
                var pdfUrl = '{{ url_for("view_document_embed", doc_id=document.id) }}';
                
                    // Load the PDF
                    pdfjsLib.getDocument(pdfUrl).promise.then(function(pdf) {
                        pdfDoc = pdf;
                        renderPage(1);
                        // Wait a bit for canvas to be fully rendered before displaying fields
                        setTimeout(function() {
                            displayExistingFields();
                        }, 100);
                    }).catch(function(error) {
                        console.error('Error loading PDF:', error);
                        document.getElementById('documentViewer').innerHTML = '<p style="padding: 20px; color: white;">Error loading PDF. Please try again.</p>';
                    });
            }
            
            // Render a PDF page
            function renderPage(pageNum) {
                if (!pdfDoc) return;
                
                var canvas = document.getElementById('pdfCanvas');
                var ctx = canvas.getContext('2d');
                
                pdfDoc.getPage(pageNum).then(function(page) {
                    // Calculate scale to fit 800px height (matching user view and embedding)
                    var viewerHeight = 800;
                    var viewport = page.getViewport({ scale: 1.0 });
                    var scale = viewerHeight / viewport.height;
                    pdfScale = scale;
                    
                    // Set canvas size
                    var scaledViewport = page.getViewport({ scale: scale });
                    canvas.width = scaledViewport.width;
                    canvas.height = scaledViewport.height;
                    
                    // Render PDF page
                    var renderContext = {
                        canvasContext: ctx,
                        viewport: scaledViewport
                    };
                    
                    page.render(renderContext).promise.then(function() {
                        // Calculate canvas offset within viewer
                        var viewer = document.getElementById('documentViewer');
                        var viewerRect = viewer.getBoundingClientRect();
                        var canvasRect = canvas.getBoundingClientRect();
                        canvasOffsetX = canvasRect.left - viewerRect.left;
                        canvasOffsetY = canvasRect.top - viewerRect.top;
                        
                        currentPage = pageNum;
                        // Wait a bit for canvas to be fully rendered before displaying fields
                        setTimeout(function() {
                            displayExistingFields();
                        }, 50);
                    });
                });
            }
            
            // Display existing signature fields on the canvas
            function displayExistingFields() {
                // Remove ONLY the saved field markers, NOT the temporary indicators being created/edited
                var existing = document.querySelectorAll('.existing-field-marker, .existing-typed-field-marker');
                existing.forEach(function(el) { el.remove(); });
                
                var viewer = document.getElementById('documentViewer');
                var canvas = document.getElementById('pdfCanvas');
                if (!viewer || !canvas) return;
                
                // Get signature fields for current page
                var fields = [
                    {% for field in existing_fields %}
                    {
                        id: {{ field.id }},
                        label: '{{ field.field_label or "Signature" }}',
                        x: {{ field.x_position }},
                        y: {{ field.y_position }},
                        width: {{ field.width or 200 }},
                        height: {{ field.height or 80 }},
                        page: {{ field.page_number }}
                    }{% if not loop.last %},{% endif %}
                    {% endfor %}
                ];
                
                fields.forEach(function(field) {
                    if (field.page !== currentPage) return;
                    
                    var marker = document.createElement('div');
                    marker.className = 'existing-field-marker';
                    marker.setAttribute('data-label', field.label);
                    // Position markers relative to canvas (convert PDF coordinates to screen coordinates)
                    var canvas = document.getElementById('pdfCanvas');
                    if (canvas && canvas.width > 0 && canvas.height > 0) {
                        var canvasRect = canvas.getBoundingClientRect();
                        var viewerRect = viewer.getBoundingClientRect();
                        // Convert PDF coordinates to screen coordinates using scale
                        var scaleX = canvas.width / canvasRect.width;
                        var scaleY = canvas.height / canvasRect.height;
                        if (scaleX > 0 && scaleY > 0) {
                            marker.style.left = (canvasRect.left - viewerRect.left + (field.x / scaleX)) + 'px';
                            marker.style.top = (canvasRect.top - viewerRect.top + (field.y / scaleY)) + 'px';
                            marker.style.width = (field.width / scaleX) + 'px';
                            marker.style.height = (field.height / scaleY) + 'px';
                        } else {
                            // Fallback if scale calculation fails
                            marker.style.left = (canvasOffsetX + (field.x / pdfScale)) + 'px';
                            marker.style.top = (canvasOffsetY + (field.y / pdfScale)) + 'px';
                            marker.style.width = (field.width / pdfScale) + 'px';
                            marker.style.height = (field.height / pdfScale) + 'px';
                        }
                    } else {
                        // Fallback if canvas not ready
                        marker.style.left = (canvasOffsetX + (field.x / pdfScale)) + 'px';
                        marker.style.top = (canvasOffsetY + (field.y / pdfScale)) + 'px';
                        marker.style.width = (field.width / pdfScale) + 'px';
                        marker.style.height = (field.height / pdfScale) + 'px';
                    }
                    viewer.appendChild(marker);
                });
                
                // Get typed fields for current page
                var typedFields = [
                    {% if existing_typed_fields %}
                    {% for field in existing_typed_fields %}
                    {
                        id: {{ field.id }},
                        label: '{{ field.field_label or "Typed Field" }}',
                        type: '{{ field.field_type }}',
                        x: {{ field.x_position }},
                        y: {{ field.y_position }},
                        width: {{ field.width or 200 }},
                        height: {{ field.height or 30 }},
                        page: {{ field.page_number }}
                    }{% if not loop.last %},{% endif %}
                    {% endfor %}
                    {% endif %}
                ];
                
                typedFields.forEach(function(field) {
                    if (field.page !== currentPage) return;
                    
                    var marker = document.createElement('div');
                    marker.className = 'existing-typed-field-marker';
                    marker.setAttribute('data-label', field.label + ' (' + field.type + ')');
                    // Position markers relative to canvas (convert PDF coordinates to screen coordinates)
                    var canvas = document.getElementById('pdfCanvas');
                    if (canvas && canvas.width > 0 && canvas.height > 0) {
                        var canvasRect = canvas.getBoundingClientRect();
                        var viewerRect = viewer.getBoundingClientRect();
                        // Convert PDF coordinates to screen coordinates using scale
                        var scaleX = canvas.width / canvasRect.width;
                        var scaleY = canvas.height / canvasRect.height;
                        if (scaleX > 0 && scaleY > 0) {
                            marker.style.left = (canvasRect.left - viewerRect.left + (field.x / scaleX)) + 'px';
                            marker.style.top = (canvasRect.top - viewerRect.top + (field.y / scaleY)) + 'px';
                            marker.style.width = (field.width / scaleX) + 'px';
                            marker.style.height = (field.height / scaleY) + 'px';
                        } else {
                            // Fallback if scale calculation fails
                            marker.style.left = (canvasOffsetX + (field.x / pdfScale)) + 'px';
                            marker.style.top = (canvasOffsetY + (field.y / pdfScale)) + 'px';
                            marker.style.width = (field.width / pdfScale) + 'px';
                            marker.style.height = (field.height / pdfScale) + 'px';
                        }
                    } else {
                        // Fallback if canvas not ready
                        marker.style.left = (canvasOffsetX + (field.x / pdfScale)) + 'px';
                        marker.style.top = (canvasOffsetY + (field.y / pdfScale)) + 'px';
                        marker.style.width = (field.width / pdfScale) + 'px';
                        marker.style.height = (field.height / pdfScale) + 'px';
                    }
                    viewer.appendChild(marker);
                });
            }
            
            // Handle canvas drag-to-create signature field
            var canvas = document.getElementById('pdfCanvas');
            var isDraggingIndicator = false;
            var isCreatingField = false;
            var createStartX = 0;
            var createStartY = 0;
            var previewIndicator = null;
            var fieldMode = 'signature'; // 'signature' or 'typed'
            
            if (canvas) {
                canvas.addEventListener('mousedown', function(e) {
                    // Don't start creating if clicking on existing indicator or resize handle
                    if (e.target.closest('.signature-field-indicator') || e.target.closest('.typed-field-indicator') || e.target.classList.contains('resize-handle')) {
                        return;
                    }
                    // Don't start creating if already dragging/resizing an existing indicator
                    if (isDraggingIndicator || isResizing) {
                        return;
                    }
                    // Don't start creating if there's already a current indicator being interacted with
                    if (currentIndicator && (e.target.closest('.signature-field-indicator') || e.target.closest('.typed-field-indicator'))) {
                        return;
                    }
                    
                    // Start creating a new field (signature or typed based on mode)
                    isCreatingField = true;
                    var canvasRect = canvas.getBoundingClientRect();
                    
                    // Get click position in canvas coordinates
                    var clickX = e.clientX - canvasRect.left;
                    var clickY = e.clientY - canvasRect.top;
                    
                    // Convert to canvas pixel coordinates (accounting for scale)
                    var scaleX = canvas.width / canvasRect.width;
                    var scaleY = canvas.height / canvasRect.height;
                    createStartX = clickX * scaleX;
                    createStartY = clickY * scaleY;
                    
                    // Create preview indicator (style based on mode)
                    if (previewIndicator) {
                        previewIndicator.remove();
                    }
                    previewIndicator = document.createElement('div');
                    if (fieldMode === 'typed') {
                        previewIndicator.className = 'typed-field-indicator';
                        previewIndicator.style.cssText = 'position: absolute; border: 2px dashed #ffc107; background: rgba(255, 193, 7, 0.1); pointer-events: none; z-index: 100; opacity: 0.7;';
                    } else {
                        previewIndicator.className = 'signature-field-indicator';
                        previewIndicator.style.pointerEvents = 'none';
                        previewIndicator.style.opacity = '0.7';
                    }
                    var viewerRect = document.getElementById('documentViewer').getBoundingClientRect();
                    previewIndicator.style.left = (canvasRect.left - viewerRect.left + clickX) + 'px';
                    previewIndicator.style.top = (canvasRect.top - viewerRect.top + clickY) + 'px';
                    previewIndicator.style.width = '0px';
                    previewIndicator.style.height = '0px';
                    document.getElementById('documentViewer').appendChild(previewIndicator);
                    
                    e.preventDefault();
                    e.stopPropagation();
                });
                
                // Track mouse movement while creating field
                document.addEventListener('mousemove', function(e) {
                    if (!isCreatingField || !previewIndicator) return;
                    
                    var canvasRect = canvas.getBoundingClientRect();
                    var viewerRect = document.getElementById('documentViewer').getBoundingClientRect();
                    
                    // Get current mouse position in canvas coordinates
                    var currentX = e.clientX - canvasRect.left;
                    var currentY = e.clientY - canvasRect.top;
                    
                    // Convert to canvas pixel coordinates
                    var scaleX = canvas.width / canvasRect.width;
                    var scaleY = canvas.height / canvasRect.height;
                    var currentXCanvas = currentX * scaleX;
                    var currentYCanvas = currentY * scaleY;
                    
                    // Calculate field dimensions (from start to current position)
                    var fieldWidth = Math.abs(currentXCanvas - createStartX);
                    var fieldHeight = Math.abs(currentYCanvas - createStartY);
                    
                    // Ensure minimum size (different for typed vs signature)
                    if (fieldMode === 'typed') {
                        if (fieldWidth < 50) fieldWidth = 50;
                        if (fieldHeight < 20) fieldHeight = 20;
                    } else {
                        if (fieldWidth < 50) fieldWidth = 50;
                        if (fieldHeight < 30) fieldHeight = 30;
                    }
                    
                    // Calculate top-left corner (always use the smaller coordinates)
                    var xPos = Math.min(createStartX, currentXCanvas);
                    var yPos = Math.min(createStartY, currentYCanvas);
                    
                    // Keep within canvas bounds
                    xPos = Math.max(0, Math.min(xPos, canvas.width - fieldWidth));
                    yPos = Math.max(0, Math.min(yPos, canvas.height - fieldHeight));
                    fieldWidth = Math.min(fieldWidth, canvas.width - xPos);
                    fieldHeight = Math.min(fieldHeight, canvas.height - yPos);
                    
                    // Update preview indicator position and size
                    previewIndicator.style.left = (canvasRect.left - viewerRect.left + (xPos / scaleX)) + 'px';
                    previewIndicator.style.top = (canvasRect.top - viewerRect.top + (yPos / scaleY)) + 'px';
                    previewIndicator.style.width = (fieldWidth / scaleX) + 'px';
                    previewIndicator.style.height = (fieldHeight / scaleY) + 'px';
                    
                    // Update position display
                    updatePositionDisplay(xPos, yPos, fieldWidth, fieldHeight);
                });
                
                // Finalize field creation on mouseup
                document.addEventListener('mouseup', function(e) {
                    if (!isCreatingField) return;
                    
                    var canvasRect = canvas.getBoundingClientRect();
                    
                    // Get final mouse position
                    var currentX = e.clientX - canvasRect.left;
                    var currentY = e.clientY - canvasRect.top;
                    
                    // Convert to canvas pixel coordinates
                    var scaleX = canvas.width / canvasRect.width;
                    var scaleY = canvas.height / canvasRect.height;
                    var currentXCanvas = currentX * scaleX;
                    var currentYCanvas = currentY * scaleY;
                    
                    // Calculate final field dimensions
                    var fieldWidth = Math.abs(currentXCanvas - createStartX);
                    var fieldHeight = Math.abs(currentYCanvas - createStartY);
                    
                    // Ensure minimum size (different for typed vs signature)
                    var minWidth = 50;
                    var minHeight = fieldMode === 'typed' ? 20 : 30;
                    if (fieldWidth < minWidth) fieldWidth = minWidth;
                    if (fieldHeight < minHeight) fieldHeight = minHeight;
                    
                    // Calculate top-left corner
                    var xPos = Math.min(createStartX, currentXCanvas);
                    var yPos = Math.min(createStartY, currentYCanvas);
                    
                    // Keep within canvas bounds
                    xPos = Math.max(0, Math.min(xPos, canvas.width - fieldWidth));
                    yPos = Math.max(0, Math.min(yPos, canvas.height - fieldHeight));
                    fieldWidth = Math.min(fieldWidth, canvas.width - xPos);
                    fieldHeight = Math.min(fieldHeight, canvas.height - yPos);
                    
                    // Set the position inputs
                    document.getElementById('x_position').value = xPos;
                    document.getElementById('y_position').value = yPos;
                    document.getElementById('width').value = fieldWidth;
                    document.getElementById('height').value = fieldHeight;
                    
                    // Update page number to match current page
                    document.getElementById('page_number').value = currentPage;
                    
                    // Update position display
                    updatePositionDisplay(xPos, yPos, fieldWidth, fieldHeight);
                    
                    // Remove preview indicator
                    if (previewIndicator) {
                        previewIndicator.remove();
                        previewIndicator = null;
                    }
                    
                    // Remove previous final indicator if exists
                    if (currentIndicator) {
                        currentIndicator.remove();
                    }
                    
                    // Create final indicator (style based on mode) - always create if we have valid dimensions
                    if (fieldWidth >= minWidth && fieldHeight >= minHeight) {
                        var indicator = document.createElement('div');
                        if (fieldMode === 'typed') {
                            indicator.className = 'typed-field-indicator';
                            indicator.style.cssText = 'position: absolute; border: 2px solid #ffc107; background: rgba(255, 193, 7, 0.1); pointer-events: all; z-index: 100; cursor: move;';
                        } else {
                            indicator.className = 'signature-field-indicator';
                        }
                        var viewerRect = document.getElementById('documentViewer').getBoundingClientRect();
                        indicator.style.left = (canvasRect.left - viewerRect.left + (xPos / scaleX)) + 'px';
                        indicator.style.top = (canvasRect.top - viewerRect.top + (yPos / scaleY)) + 'px';
                        indicator.style.width = (fieldWidth / scaleX) + 'px';
                        indicator.style.height = (fieldHeight / scaleY) + 'px';
                        indicator.dataset.x = xPos;
                        indicator.dataset.y = yPos;
                        indicator.dataset.width = fieldWidth;
                        indicator.dataset.height = fieldHeight;
                        
                        // Add resize handles
                        var handles = ['bottom-right', 'bottom-left', 'top-right', 'top-left'];
                        handles.forEach(function(handleClass) {
                            var handle = document.createElement('div');
                            handle.className = 'resize-handle ' + handleClass;
                            indicator.appendChild(handle);
                        });
                        
                        // Make indicator draggable
                        makeIndicatorDraggable(indicator);
                        
                        // Make handles resizable
                        makeIndicatorResizable(indicator);
                        
                        document.getElementById('documentViewer').appendChild(indicator);
                        currentIndicator = indicator;
                        
                        // Focus on label input
                        document.getElementById('field_label').focus();
                    }
                    
                    isCreatingField = false;
                });
            }
            
            // Make the indicator draggable
            function makeIndicatorDraggable(indicator) {
                var isDragging = false;
                var startX = 0;
                var startY = 0;
                var startLeft = 0;
                var startTop = 0;
                
                indicator.addEventListener('mousedown', function(e) {
                    // Don't drag if clicking on a resize handle
                    if (e.target.classList.contains('resize-handle') || e.target.closest('.resize-handle')) {
                        return;
                    }
                    isDragging = true;
                    isDraggingIndicator = true;
                    startX = e.clientX;
                    startY = e.clientY;
                    startLeft = parseFloat(indicator.dataset.x) || 0;
                    startTop = parseFloat(indicator.dataset.y) || 0;
                    indicator.style.cursor = 'grabbing';
                    e.preventDefault();
                    e.stopPropagation();
                    e.cancelBubble = true;
                    return false;
                });
                
                var mouseMoveHandler = function(e) {
                    if (!isDragging) return;
                    
                    // Get fresh references to canvas and viewer
                    var canvas = document.getElementById('pdfCanvas');
                    var viewer = document.getElementById('documentViewer');
                    if (!canvas || !viewer) return;
                    
                    var canvasRectCurrent = canvas.getBoundingClientRect();
                    var viewerRectCurrent = viewer.getBoundingClientRect();
                    
                    // Convert mouse delta to canvas coordinates
                    var scaleX = canvas.width / canvasRectCurrent.width;
                    var scaleY = canvas.height / canvasRectCurrent.height;
                    
                    var deltaX = (e.clientX - startX) * scaleX;
                    var deltaY = (e.clientY - startY) * scaleY;
                    
                    var newLeft = startLeft + deltaX;
                    var newTop = startTop + deltaY;
                    
                    // Keep within canvas bounds
                    var currentWidth = parseFloat(indicator.dataset.width) || 200;
                    var currentHeight = parseFloat(indicator.dataset.height) || 80;
                    newLeft = Math.max(0, Math.min(newLeft, canvas.width - currentWidth));
                    newTop = Math.max(0, Math.min(newTop, canvas.height - currentHeight));
                    
                    // Update indicator position
                    indicator.style.left = (canvasRectCurrent.left - viewerRectCurrent.left + newLeft) + 'px';
                    indicator.style.top = (canvasRectCurrent.top - viewerRectCurrent.top + newTop) + 'px';
                    indicator.dataset.x = newLeft;
                    indicator.dataset.y = newTop;
                    
                    // Update hidden inputs
                    var xInput = document.getElementById('x_position');
                    var yInput = document.getElementById('y_position');
                    if (xInput) xInput.value = newLeft;
                    if (yInput) yInput.value = newTop;
                    
                    updatePositionDisplay(newLeft, newTop, currentWidth, currentHeight);
                    
                    e.preventDefault();
                    e.stopPropagation();
                };
                
                var mouseUpHandler = function(e) {
                    if (isDragging) {
                        isDragging = false;
                        isDraggingIndicator = false;
                        indicator.style.cursor = 'move';
                        // Small delay to prevent click event from firing
                        setTimeout(function() {
                            isDraggingIndicator = false;
                        }, 100);
                    }
                };
                
                document.addEventListener('mousemove', mouseMoveHandler);
                document.addEventListener('mouseup', mouseUpHandler);
                
                // Store handlers for cleanup if needed
                indicator._dragHandlers = { move: mouseMoveHandler, up: mouseUpHandler };
            }
            
            // Make the indicator resizable via corner handles
            function makeIndicatorResizable(indicator) {
                var handles = indicator.querySelectorAll('.resize-handle');
                
                handles.forEach(function(handle) {
                    handle.addEventListener('mousedown', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        isResizing = true;
                        resizeHandle = handle.className.split(' ')[1]; // Get handle position
                        resizeStartX = e.clientX;
                        resizeStartY = e.clientY;
                        
                        resizeStartWidth = parseFloat(indicator.dataset.width) || 200;
                        resizeStartHeight = parseFloat(indicator.dataset.height) || 80;
                        
                        indicator.classList.add('resizing');
                        return false;
                    });
                });
                
                var resizeMoveHandler = function(e) {
                    if (!isResizing || !resizeHandle) return;
                    
                    // Get fresh references
                    var canvas = document.getElementById('pdfCanvas');
                    var viewer = document.getElementById('documentViewer');
                    if (!canvas || !viewer) return;
                    
                    var canvasRectCurrent = canvas.getBoundingClientRect();
                    var viewerRectCurrent = viewer.getBoundingClientRect();
                    var scaleX = canvas.width / canvasRectCurrent.width;
                    var scaleY = canvas.height / canvasRectCurrent.height;
                    
                    var deltaXCanvas = (e.clientX - resizeStartX) * scaleX;
                    var deltaYCanvas = (e.clientY - resizeStartY) * scaleY;
                    
                    var newWidth = resizeStartWidth;
                    var newHeight = resizeStartHeight;
                    var newLeft = parseFloat(indicator.dataset.x) || 0;
                    var newTop = parseFloat(indicator.dataset.y) || 0;
                    
                    // Adjust based on which handle is being dragged
                    if (resizeHandle === 'bottom-right') {
                        newWidth = Math.max(50, resizeStartWidth + deltaXCanvas);
                        newHeight = Math.max(30, resizeStartHeight + deltaYCanvas);
                    } else if (resizeHandle === 'bottom-left') {
                        newWidth = Math.max(50, resizeStartWidth - deltaXCanvas);
                        newHeight = Math.max(30, resizeStartHeight + deltaYCanvas);
                        newLeft = parseFloat(indicator.dataset.x) + (resizeStartWidth - newWidth);
                    } else if (resizeHandle === 'top-right') {
                        newWidth = Math.max(50, resizeStartWidth + deltaXCanvas);
                        newHeight = Math.max(30, resizeStartHeight - deltaYCanvas);
                        newTop = parseFloat(indicator.dataset.y) + (resizeStartHeight - newHeight);
                    } else if (resizeHandle === 'top-left') {
                        newWidth = Math.max(50, resizeStartWidth - deltaXCanvas);
                        newHeight = Math.max(30, resizeStartHeight - deltaYCanvas);
                        newLeft = parseFloat(indicator.dataset.x) + (resizeStartWidth - newWidth);
                        newTop = parseFloat(indicator.dataset.y) + (resizeStartHeight - newHeight);
                    }
                    
                    // Keep within canvas bounds
                    var canvasWidth = canvas.width;
                    var canvasHeight = canvas.height;
                    newLeft = Math.max(0, Math.min(newLeft, canvasWidth - newWidth));
                    newTop = Math.max(0, Math.min(newTop, canvasHeight - newHeight));
                    newWidth = Math.min(newWidth, canvasWidth - newLeft);
                    newHeight = Math.min(newHeight, canvasHeight - newTop);
                    
                    // Update indicator
                    indicator.style.width = newWidth + 'px';
                    indicator.style.height = newHeight + 'px';
                    indicator.style.left = (canvasRectCurrent.left - viewerRectCurrent.left + newLeft) + 'px';
                    indicator.style.top = (canvasRectCurrent.top - viewerRectCurrent.top + newTop) + 'px';
                    indicator.dataset.x = newLeft;
                    indicator.dataset.y = newTop;
                    indicator.dataset.width = newWidth;
                    indicator.dataset.height = newHeight;
                    
                    // Update hidden inputs
                    var xInput = document.getElementById('x_position');
                    var yInput = document.getElementById('y_position');
                    if (xInput) xInput.value = newLeft;
                    if (yInput) yInput.value = newTop;
                    document.getElementById('width').value = newWidth;
                    document.getElementById('height').value = newHeight;
                    
                    updatePositionDisplay(newLeft, newTop, newWidth, newHeight);
                    
                    e.preventDefault();
                };
                
                var resizeUpHandler = function(e) {
                    if (isResizing) {
                        isResizing = false;
                        resizeHandle = null;
                        if (indicator) {
                            indicator.classList.remove('resizing');
                        }
                    }
                };
                
                document.addEventListener('mousemove', resizeMoveHandler);
                document.addEventListener('mouseup', resizeUpHandler);
                
                // Store handlers for cleanup if needed
                indicator._resizeHandlers = { move: resizeMoveHandler, up: resizeUpHandler };
            }
            
            // Helper function to update position display
            function updatePositionDisplay(x, y, width, height) {
                var posDisplay = document.getElementById('positionDisplay');
                if (posDisplay) {
                    var text = 'Position: (' + Math.round(x) + ', ' + Math.round(y) + ') px<br>Page: ' + currentPage;
                    if (width && height) {
                        text += '<br>Size: ' + Math.round(width) + ' x ' + Math.round(height) + ' px';
                    }
                    posDisplay.innerHTML = text;
                    // Color based on current mode
                    var fieldType = document.getElementById('field_type_selector');
                    if (fieldType && fieldType.value === 'typed') {
                        posDisplay.style.color = '#ffc107';
                    } else {
                        posDisplay.style.color = '#28a745';
                    }
                    posDisplay.style.fontWeight = 'bold';
                }
            }
            
            // Handle page number change
            var pageInput = document.getElementById('page_number');
            if (pageInput) {
                pageInput.addEventListener('change', function() {
                    var pageNum = parseInt(this.value) || 1;
                    if (pdfDoc && pageNum >= 1 && pageNum <= pdfDoc.numPages) {
                        renderPage(pageNum);
                    }
                });
            }
            
            // Toggle field type options based on selection
            function toggleFieldTypeOptions() {
                var fieldType = document.getElementById('field_type_selector').value;
                var signatureOptions = document.getElementById('signatureFieldOptions');
                var typedOptions = document.getElementById('typedFieldOptions');
                var submitButton = document.getElementById('submitButton');
                
                if (fieldType === 'signature') {
                    signatureOptions.style.display = 'block';
                    typedOptions.style.display = 'none';
                    submitButton.textContent = 'Add Signature Field';
                    submitButton.className = 'btn btn-success';
                    // Set default size for signature fields
                    document.getElementById('width').value = 200;
                    document.getElementById('height').value = 80;
                    // Update mode to signature
                    if (typeof fieldMode !== 'undefined') {
                        fieldMode = 'signature';
                        var sigBtn = document.getElementById('modeSignature');
                        var typedBtn = document.getElementById('modeTyped');
                        if (sigBtn && typedBtn) {
                            sigBtn.style.background = '#28a745';
                            sigBtn.style.color = 'white';
                            typedBtn.style.background = '#e0e0e0';
                            typedBtn.style.color = '#000';
                        }
                    }
                } else {
                    signatureOptions.style.display = 'none';
                    typedOptions.style.display = 'block';
                    submitButton.textContent = 'Add Typed Field';
                    submitButton.className = 'btn btn-primary';
                    // Set default size for typed fields
                    document.getElementById('width').value = 200;
                    document.getElementById('height').value = 30;
                    // Update mode to typed
                    if (typeof fieldMode !== 'undefined') {
                        fieldMode = 'typed';
                        var sigBtn = document.getElementById('modeSignature');
                        var typedBtn = document.getElementById('modeTyped');
                        if (sigBtn && typedBtn) {
                            typedBtn.style.background = '#ffc107';
                            typedBtn.style.color = '#000';
                            sigBtn.style.background = '#e0e0e0';
                            sigBtn.style.color = '#000';
                        }
                    }
                }
            }
            
            // Handle form submission - use AJAX for typed fields to avoid page reload
            function submitFieldForm(e) {
                e.preventDefault();
                var fieldType = document.getElementById('field_type_selector').value;
                var xPos = document.getElementById('x_position').value;
                var yPos = document.getElementById('y_position').value;
                var width = document.getElementById('width').value;
                var height = document.getElementById('height').value;
                
                if (!xPos || !yPos || xPos == '0' || yPos == '0') {
                    alert('Please place the field on the document first by clicking and dragging.');
                    return false;
                }
                
                if (!width || !height || width == '0' || height == '0') {
                    alert('Please place the field on the document first by clicking and dragging.');
                    return false;
                }
                
                var form = document.getElementById('fieldForm');
                var formData = new FormData(form);
                
                // Validate required fields
                var fieldLabel = formData.get('field_label');
                if (!fieldLabel || fieldLabel.trim() === '') {
                    alert('Please enter a field label.');
                    document.getElementById('field_label').focus();
                    return false;
                }
                
                if (fieldType === 'signature') {
                    // Submit as signature field (traditional form submit)
                    var signatureData = {
                        field_label: fieldLabel,
                        page_number: formData.get('page_number'),
                        signature_type: formData.get('signature_type'),
                        x_position: xPos,
                        y_position: yPos,
                        width: width,
                        height: height
                    };
                    
                    // Create a temporary form and submit it
                    var tempForm = document.createElement('form');
                    tempForm.method = 'POST';
                    tempForm.action = '{{ url_for("add_signature_field", doc_id=document.id) }}';
                    for (var key in signatureData) {
                        var input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = key;
                        input.value = signatureData[key];
                        tempForm.appendChild(input);
                    }
                    document.body.appendChild(tempForm);
                    tempForm.submit();
                } else {
                    // Submit as typed field using AJAX (no page reload)
                    var submitButton = document.getElementById('submitButton');
                    var originalText = submitButton.textContent;
                    submitButton.disabled = true;
                    submitButton.textContent = 'Saving...';
                    
                    var typedData = {
                        field_label: fieldLabel,
                        page_number: formData.get('page_number'),
                        field_type: formData.get('typed_field_type') || 'text',
                        placeholder: formData.get('placeholder') || '',
                        is_required: formData.get('is_required') ? 'on' : '',
                        x_position: xPos,
                        y_position: yPos,
                        width: width,
                        height: height
                    };
                    
                    // Create FormData for AJAX
                    var ajaxFormData = new FormData();
                    for (var key in typedData) {
                        if (typedData[key] !== null && typedData[key] !== undefined) {
                            ajaxFormData.append(key, typedData[key]);
                        }
                    }
                    
                    // Submit via AJAX
                    fetch('{{ url_for("add_typed_field", doc_id=document.id) }}', {
                        method: 'POST',
                        body: ajaxFormData,
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(function(response) {
                        // Check if response is OK
                        if (!response.ok) {
                            // Try to get error message from response
                            return response.json().catch(function() {
                                return response.text().then(function(text) {
                                    throw new Error(text || 'Server error: ' + response.status);
                                });
                            }).then(function(data) {
                                throw new Error(data.message || 'Server error: ' + response.status);
                            });
                        }
                        
                        // Try to parse as JSON
                        var contentType = response.headers.get('content-type');
                        if (contentType && contentType.includes('application/json')) {
                            return response.json();
                        } else {
                            // If not JSON, assume success if status is OK
                            return {success: true, message: 'Field saved successfully'};
                        }
                    })
                    .then(function(data) {
                        if (data && data.success) {
                            // Success - show message and reload to display the new field
                            alert('Typed field saved successfully!');
                            window.location.reload();
                        } else {
                            var errorMsg = (data && data.message) ? data.message : 'Unknown error occurred';
                            alert('Error: ' + errorMsg);
                            submitButton.disabled = false;
                            submitButton.textContent = originalText;
                        }
                    })
                    .catch(function(error) {
                        console.error('Error:', error);
                        var errorMsg = error.message || 'Unknown error occurred';
                        alert('Error saving typed field: ' + errorMsg);
                        submitButton.disabled = false;
                        submitButton.textContent = originalText;
                    });
                }
                
                return false;
            }
            
            
            // Initialize field type options on page load
            if (document.getElementById('field_type_selector')) {
                toggleFieldTypeOptions();
            }
            
            // Add mode toggle buttons for signature vs typed field (only once, after page loads)
            // Also sync with the field type selector
            setTimeout(function() {
                var viewerContainer = document.querySelector('.document-viewer-container');
                if (viewerContainer && !document.getElementById('modeContainer')) {
                    var modeContainer = document.createElement('div');
                    modeContainer.id = 'modeContainer';
                    modeContainer.style.cssText = 'position: absolute; top: 10px; right: 10px; z-index: 200; background: white; padding: 10px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);';
                    modeContainer.innerHTML = '<label style="font-size: 0.9em; font-weight: bold; margin-right: 10px;">Mode:</label>' +
                        '<button type="button" id="modeSignature" style="padding: 5px 15px; margin-right: 5px; background: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer;">Signature</button>' +
                        '<button type="button" id="modeTyped" style="padding: 5px 15px; background: #e0e0e0; color: #000; border: none; border-radius: 3px; cursor: pointer;">Typed Field</button>';
                    viewerContainer.appendChild(modeContainer);
                    
                    document.getElementById('modeSignature').addEventListener('click', function() {
                        fieldMode = 'signature';
                        this.style.background = '#28a745';
                        this.style.color = 'white';
                        document.getElementById('modeTyped').style.background = '#e0e0e0';
                        document.getElementById('modeTyped').style.color = '#000';
                        // Sync with form selector
                        var selector = document.getElementById('field_type_selector');
                        if (selector) selector.value = 'signature';
                        toggleFieldTypeOptions();
                    });
                    
                    document.getElementById('modeTyped').addEventListener('click', function() {
                        fieldMode = 'typed';
                        this.style.background = '#ffc107';
                        this.style.color = '#000';
                        document.getElementById('modeSignature').style.background = '#e0e0e0';
                        document.getElementById('modeSignature').style.color = '#000';
                        // Sync with form selector
                        var selector = document.getElementById('field_type_selector');
                        if (selector) selector.value = 'typed';
                        toggleFieldTypeOptions();
                    });
                    
                    // Sync mode buttons when form selector changes
                    var selector = document.getElementById('field_type_selector');
                    if (selector) {
                        selector.addEventListener('change', function() {
                            if (this.value === 'signature') {
                                document.getElementById('modeSignature').click();
                            } else {
                                document.getElementById('modeTyped').click();
                            }
                        });
                    }
                }
            }, 500);
            
            
            // Initialize when page loads
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', loadPDF);
            } else {
                loadPDF();
            }
        </script>
    </body>
    </html>
    ''', document=document, existing_fields=existing_fields, existing_typed_fields=existing_typed_fields, is_pdf=is_pdf)


@app.route('/admin/documents/<int:doc_id>/signature-fields/add', methods=['POST'])
@admin_required
def add_signature_field(doc_id):
    """Add a signature field to a document"""
    document = Document.query.get(doc_id)
    if not document:
        flash('Document not found.', 'error')
        return redirect(url_for('manage_documents'))
    
    try:
        signature_type = request.form.get('signature_type', 'image')  # 'image' or 'cryptographic'
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
        
        flash('Signature field added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding signature field: {str(e)}', 'error')
    
    return redirect(url_for('set_signature_fields', doc_id=doc_id))


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
        # Check if table exists by trying to query it
        try:
            DocumentTypedField.query.first()
        except Exception as e:
            error_msg = 'Typed fields feature requires database tables to be created. Please run init_db.py first.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('set_signature_fields', doc_id=doc_id))
        
        field_type = request.form.get('field_type', 'text')  # 'text', 'date', 'name', etc.
        
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
            placeholder=request.form.get('placeholder', '').strip() or None,
            is_required=request.form.get('is_required') == 'on',
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
        
        flash('Typed field added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        error_msg = f'Error adding typed field: {str(e)}'
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_msg}), 500
        
        flash(error_msg, 'error')
    
    return redirect(url_for('set_signature_fields', doc_id=doc_id))


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
            flash('Typed field deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting typed field: {str(e)}', 'error')
        
        return redirect(url_for('set_signature_fields', doc_id=doc_id))
    except Exception as e:
        flash(f'Error: {str(e)}. Typed fields feature may not be available.', 'error')
        return redirect(url_for('manage_documents'))


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
        
        flash('Signature field deleted successfully. Existing signatures have been preserved.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting signature field: {str(e)}', 'error')
    
    return redirect(url_for('set_signature_fields', doc_id=doc_id))


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
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Assign Document - {{ document.name_for_users }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
                max-width: 1000px;
                margin: 20px auto;
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
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn-success {
                background: #28a745;
            }
            .admin-panel {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 25px;
                margin-bottom: 20px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: bold;
            }
            .form-group input[type="text"],
            .form-group input[type="date"],
            .form-group textarea {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 16px; /* Prevents zoom on iOS */
                min-height: 44px; /* Touch-friendly */
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .users-list {
                max-height: 400px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                padding: 10px;
                background: #f8f9fa;
            }
            .user-item {
                padding: 10px;
                margin-bottom: 5px;
                background: white;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            .user-item input[type="checkbox"] {
                margin-right: 10px;
                min-width: 20px;
                min-height: 20px; /* Touch-friendly */
            }
            .user-item label {
                flex: 1;
                cursor: pointer;
                font-weight: normal;
            }
            .assigned-badge {
                background: #28a745;
                color: white;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                margin-left: 10px;
            }
            .current-assignments {
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
            }
            .assignment-item {
                padding: 10px;
                margin-bottom: 10px;
                background: #f8f9fa;
                border-radius: 0.5rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
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
                .admin-panel h2 {
                    font-size: 1.3em;
                }
                .form-group input[type="text"],
                .form-group input[type="date"],
                .form-group textarea {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
                }
                .users-list {
                    max-height: 300px;
                }
                .user-item {
                    flex-wrap: wrap;
                    gap: 10px;
                }
                .assignment-item {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 10px;
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
                .admin-panel h2 {
                    font-size: 1.2em;
                }
                .users-list {
                    max-height: 250px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>👤 Assign Document - {{ document.original_filename }}</h1>
            </div>
            <a href="{{ url_for('manage_documents') }}" class="back-btn">← Back to Documents</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Assign to Users</h2>
                <form method="POST" action="{{ url_for('assign_document_submit', doc_id=document.id) }}">
                    <div class="form-group">
                        <label>Select Users:</label>
                        <div class="users-list">
                            {% if all_users %}
                                {% for user in all_users %}
                                <div class="user-item">
                                    <input type="checkbox" name="usernames" value="{{ user.username }}" id="user-{{ user.username }}" 
                                           {% if user.username in assigned_usernames %}checked{% endif %}>
                                    <label for="user-{{ user.username }}">{{ user_display_names.get(user.username, user.username) }}</label>
                                    {% if user.username in assigned_usernames %}
                                    <span class="assigned-badge">Assigned</span>
                                    {% endif %}
                                </div>
                                {% endfor %}
                            {% else %}
                                <p style="color: #666; padding: 20px;">No users found. Users will appear here after they log in.</p>
                            {% endif %}
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="due_date">Due Date (optional):</label>
                        <input type="date" name="due_date" id="due_date">
                    </div>
                    
                    <div class="form-group">
                        <label for="notes">Notes (optional):</label>
                        <textarea name="notes" id="notes" placeholder="Add any notes about this assignment..."></textarea>
                    </div>
                    
                    <button type="submit" class="btn btn-success">Assign Document</button>
                </form>
                
                {% if current_assignments %}
                <div class="current-assignments">
                    <h3>Current Assignments</h3>
                    {% for assignment in current_assignments %}
                    <div class="assignment-item">
                        <div>
                            <strong>{{ user_display_names.get(assignment.username, assignment.username) }}</strong>
                            {% if assignment.due_date %}
                            <span style="color: #666; margin-left: 10px;">Due: {{ assignment.due_date.strftime('%Y-%m-%d') }}</span>
                            {% endif %}
                            {% if assignment.is_completed %}
                            <span class="assigned-badge" style="margin-left: 10px;">✓ Completed</span>
                            {% endif %}
                        </div>
                        <form method="POST" action="{{ url_for('remove_document_assignment', assignment_id=assignment.id) }}" style="display: inline;">
                            <button type="submit" class="btn" style="padding: 5px 15px; font-size: 0.85em;" 
                                    onclick="return confirm('Remove assignment for {{ user_display_names.get(assignment.username, assignment.username) }}?')">
                                Remove
                            </button>
                        </form>
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', document=document, all_users=all_users, assigned_usernames=assigned_usernames, current_assignments=current_assignments, user_display_names=user_display_names)


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
                
                # Create a UserTask for this document assignment
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
                    notes=notes
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
        
        # Send email to newly assigned users (if mail configured)
        sign_url = url_for('sign_document', doc_id=doc_id, _external=True)
        doc_name = document.name_for_users or 'Document'
        due_str = f" Due: {due_date_str}" if due_date_str else ""
        for username in newly_assigned_usernames:
            to_email = get_email_for_username(username)
            if to_email:
                send_email(
                    to_email,
                    subject=f"Document to sign: {doc_name}",
                    body_html=f"""
                    <p>Hello,</p>
                    <p>You have been assigned to sign the following document: <strong>{doc_name}</strong>.</p>
                    <p><a href="{sign_url}">Sign the document here</a></p>
                    {f'<p>Due date: {due_date_str}</p>' if due_date_str else ''}
                    <p>— Ziebart Onboarding</p>
                    """.strip()
                )
        
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


@app.route('/documents')
@login_required
def view_documents():
    """View assigned documents (regular users) or all documents (admins). Supports ?sign=<doc_id> to open sign page."""
    sign_id = request.args.get('sign')
    if sign_id:
        try:
            doc_id = int(sign_id)
            # Serve sign page at this URL so it works even when /documents/<id>/sign is not routed (e.g. proxy)
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

    try:
        if current_user.is_admin():
            documents = Document.query.order_by(Document.created_at.desc()).all()
        else:
            assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
            assigned_doc_ids = [a.document_id for a in assigned_documents]
            if assigned_doc_ids:
                documents = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.created_at.desc()).all()
            else:
                documents = []
    except Exception as e:
        db.session.rollback()
        # Try adding display_name if missing (MSSQL/pyodbc error text can vary)
        err_str = (str(e) or '').lower()
        try:
            db.session.execute(text("ALTER TABLE documents ADD display_name NVARCHAR(255) NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # Retry the query (succeeds if the only issue was missing display_name)
        try:
            if current_user.is_admin():
                documents = Document.query.order_by(Document.created_at.desc()).all()
            else:
                assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
                assigned_doc_ids = [a.document_id for a in assigned_documents]
                documents = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.created_at.desc()).all() if assigned_doc_ids else []
        except Exception:
            db.session.rollback()
            raise

        # Get assigned documents for current user
        assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
        assigned_doc_ids = set(a.document_id for a in assigned_documents)

        # Check signature status for each document
        for doc in documents:
            signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
            doc.has_signature_fields = len(signature_fields) > 0
            # Check if current user has signed all required fields (using helper to handle deleted fields)
            required_fields = [f for f in signature_fields if f.is_required]
            try:
                doc.all_signed = len(required_fields) > 0 and all(is_signature_field_signed(doc.id, f, current_user.username) for f in required_fields)
            except Exception as e:
                # If checking signatures fails, assume not signed
                doc.all_signed = False
            # Only require signature if document is assigned
            doc.is_assigned = doc.id in assigned_doc_ids
            doc.needs_signature = doc.is_assigned and len(required_fields) > 0 and not doc.all_signed
            if doc.is_assigned:
                doc.assignment = next((a for a in assigned_documents if a.document_id == doc.id), None)

        # Get user info for header (guard against None first/last name from NewHire)
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
        app.logger.error(f'Error in view_documents for {current_user.username if current_user else "unknown"}: {str(e)}')
        app.logger.error(traceback.format_exc())
        db.session.rollback()
        flash('Unable to load document list. Showing empty list.', 'error')
        documents = []
        is_admin = current_user.is_admin() if current_user else False
        user_first_name = (current_user.username if current_user else 'User') or 'User'
        user_full_name = (current_user.username if current_user else 'User') or 'User'
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Documents - Onboarding App</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #f5f5f5;
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                font-family: 'URW Form', Arial, sans-serif;
                transition: color 0.2s;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .nav-links a.active {
                color: #FE0100;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .dropdown-divider {
                height: 1px;
                background: #eee;
            }
            body { background: #f5f5f5; }
            .main-content {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px 20px;
            }
            .page-title {
                font-size: 2em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 8px;
            }
            .page-subtitle {
                color: #808080;
                font-size: 1em;
                margin-bottom: 24px;
            }
            .section-title-dash {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
            }
            .documents-list {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 24px;
            }
            .document-list {
                display: grid;
                gap: 15px;
            }
            .document-item {
                background: #ffffff;
                border-radius: 0.5rem;
                padding: 20px;
                border-left: 4px solid #FE0100;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 12px;
            }
            .document-item:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            .document-item.signed {
                border-left-color: #28a745;
            }
            .document-item.needs-signature {
                border-left-color: #FE0100;
            }
            .document-info {
                flex: 1;
                min-width: 0;
            }
            .document-info h3 {
                font-size: 1.1em;
                font-weight: 600;
                color: #000000;
                margin-bottom: 6px;
            }
            .document-info p {
                color: #808080;
                font-size: 0.9em;
                margin: 4px 0;
                line-height: 1.5;
            }
            .document-meta {
                font-size: 0.85em;
                color: #999;
                margin-top: 8px;
            }
            .document-actions {
                display: flex;
                gap: 12px;
                align-items: stretch;
                flex-shrink: 0;
            }
            .document-actions .btn,
            .document-actions .badge {
                min-height: 44px;
                padding: 12px 20px;
                border-radius: 0.5rem;
                font-size: 0.9em;
                font-weight: 600;
                font-family: 'URW Form', Arial, sans-serif;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                transition: background 0.2s, box-shadow 0.2s;
                box-sizing: border-box;
            }
            .document-actions .badge {
                background: #28a745;
                color: white;
                text-decoration: none;
                cursor: default;
                border: none;
            }
            .document-actions .btn {
                text-decoration: none;
                border: none;
                cursor: pointer;
                background: #FE0100;
                color: white;
            }
            .document-actions .btn:hover {
                background: #cc0000;
                color: white;
                box-shadow: 0 2px 8px rgba(254,1,0,0.3);
            }
            .document-actions .btn-sign {
                background: #28a745;
                color: white;
            }
            .document-actions .btn-sign:hover {
                background: #218838;
                color: white;
                box-shadow: 0 2px 8px rgba(40,167,69,0.3);
            }
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #999;
            }
            .empty-state-icon {
                font-size: 4em;
                margin-bottom: 20px;
            }
            /* Mobile Menu */
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
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
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 10px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .main-content {
                    padding: 20px 15px;
                }
                .documents-list {
                    padding: 1rem;
                }
                .document-item {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 15px;
                    padding: 15px;
                }
                .document-info {
                    width: 100%;
                }
                .document-info h3 {
                    font-size: 1em;
                    word-break: break-word;
                }
                .document-actions {
                    width: 100%;
                    flex-direction: column;
                    gap: 10px;
                }
                .document-actions .btn,
                .document-actions .badge {
                    width: 100%;
                    text-align: center;
                }
                .btn, .badge {
                    min-height: 44px;
                    padding: 12px 20px;
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
                .documents-list {
                    padding: 12px;
                }
                .document-item {
                    padding: 12px;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="mobile-nav" id="mobileNav">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_first_name[0].upper() if user_first_name else 'U' }}</div>
                    <span>{{ user_full_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('dashboard') }}" class="dropdown-item">Dashboard</a>
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <h1 class="page-title">Files</h1>
            <p class="page-subtitle">Your assigned documents and downloads</p>
            
            <div class="documents-list">
                <h2 class="section-title-dash">Available Documents</h2>
                {% if documents %}
                <div class="document-list">
                    {% for doc in documents %}
                    <div class="document-item {{ 'signed' if (doc.has_signature_fields and doc.all_signed) else 'needs-signature' if doc.needs_signature else '' }}">
                        <div class="document-info">
                            <h3>
                                {% if doc.needs_signature %}
                                <a href="{{ url_for('view_documents', sign=doc.id) }}" style="color: inherit; text-decoration: none;">{{ doc.name_for_users }}</a>
                                {% else %}
                                {{ doc.name_for_users }}
                                {% endif %}
                            </h3>
                            {% if doc.description %}
                            <p>{{ doc.description }}</p>
                            {% endif %}
                            {% if doc.is_assigned and doc.assignment and doc.needs_signature %}
                            <p style="color: #FE0100; font-weight: 600;">
                                Required Signature
                                {% if doc.assignment.due_date %}
                                • Due: {{ doc.assignment.due_date.strftime('%B %d, %Y') }}
                                {% endif %}
                            </p>
                            {% endif %}
                            <p class="document-meta">
                                {% if doc.file_size %}
                                    {% if doc.file_size < 1024 %}{{ doc.file_size }} B
                                    {% elif doc.file_size < 1048576 %}{{ "%.1f"|format(doc.file_size / 1024) }} KB
                                    {% else %}{{ "%.1f"|format(doc.file_size / 1048576) }} MB{% endif %}
                                {% endif %}
                                {% if doc.file_size and doc.uploaded_by %} • {% endif %}
                                Uploaded by {{ doc.uploaded_by or '-' }} on {{ doc.created_at.strftime('%Y-%m-%d') if doc.created_at else '-' }}
                            </p>
                        </div>
                        <div class="document-actions">
                            {% if doc.has_signature_fields %}
                                {% if doc.all_signed %}
                                    <span class="badge">✓ Signed</span>
                                {% else %}
                                    <a href="{{ url_for('view_documents', sign=doc.id) }}" class="btn btn-sign" title="Open document to sign">✍️ Sign Document</a>
                                {% endif %}
                            {% endif %}
                            <a href="{{ url_for('download_document', doc_id=doc.id) }}" class="btn">⬇️ Download</a>
                            <a href="{{ url_for('view_document_embed', doc_id=doc.id, username=current_user.username) }}" class="btn" target="_blank" title="Open in new tab to print">🖨️ Print</a>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <div class="empty-state">
                    <div class="empty-state-icon">📄</div>
                    <h3>No documents available</h3>
                    <p>You don't have any documents assigned yet.</p>
                </div>
                {% endif %}
            </div>
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            function toggleMobileMenu() {
                var mobileNav = document.getElementById('mobileNav');
                if (mobileNav) {
                    mobileNav.classList.toggle('show');
                }
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.mobile-menu-toggle') && !event.target.closest('.mobile-nav')) {
                    var mobileNav = document.getElementById('mobileNav');
                    if (mobileNav && mobileNav.classList.contains('show')) {
                        mobileNav.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name, documents=documents)


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
    
    # Check if file exists
    if not os.path.exists(document.file_path):
        flash('File not found on server.', 'error')
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
            document.file_path,
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
    
    # Check permissions - only allow if document is assigned to user (unless admin)
    if not current_user.is_admin():
        assignment = DocumentAssignment.query.filter_by(document_id=doc_id, username=current_user.username).first()
        if not assignment:
            return "This document has not been assigned to you.", 403
    
    # If username is provided and current user is admin OR it's their own username, show signed version
    # Otherwise, show original blank document
    show_signed = False
    if username:
        if current_user.is_admin() or username == current_user.username:
            show_signed = True
    
    # If showing signed version, create a temporary PDF with signatures embedded
    if show_signed:
        try:
            # Get user's signatures for this document
            try:
                user_signatures = DocumentSignature.query.filter_by(
                    document_id=doc_id,
                    username=username
                ).all()
            except Exception as e:
                # If query fails (columns don't exist), use empty list
                user_signatures = []
            
            # Get typed field values for this user (handle case where table might not exist yet)
            try:
                user_typed_values = DocumentTypedFieldValue.query.filter_by(
                    document_id=doc_id,
                    username=username
                ).all()
                typed_value_map = {val.typed_field_id: val.field_value for val in user_typed_values}
            except Exception:
                typed_value_map = {}
            
            if (user_signatures or typed_value_map) and FITZ_AVAILABLE:
                
                # Create a temporary signed copy
                import tempfile
                import shutil
                
                # Create temp file
                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)
                
                # Copy original PDF
                shutil.copy2(document.file_path, temp_path)
                
                # Embed signatures and typed field values into temp copy
                pdf_doc = fitz.open(temp_path)
                
                # Embed signatures
                for sig in user_signatures:
                    if not sig.signature_image:
                        continue
                    
                    # Get signature field (may be None if field was deleted)
                    field = None
                    if sig.signature_field_id:
                        field = DocumentSignatureField.query.get(sig.signature_field_id)
                    
                    # Use stored field metadata if field doesn't exist (field was deleted)
                    # This preserves signatures even when admin deletes and recreates fields
                    # Safely access new fields (may not exist if database not migrated)
                    try:
                        sig_field_page = getattr(sig, 'field_page_number', None)
                        sig_field_x = getattr(sig, 'field_x_position', None)
                        sig_field_y = getattr(sig, 'field_y_position', None)
                        sig_field_width = getattr(sig, 'field_width', None)
                        sig_field_height = getattr(sig, 'field_height', None)
                    except Exception:
                        sig_field_page = None
                        sig_field_x = None
                        sig_field_y = None
                        sig_field_width = None
                        sig_field_height = None
                    
                    if not field:
                        if not sig_field_page or not sig_field_x or not sig_field_y:
                            # Missing metadata, skip this signature
                            continue
                        # Use stored metadata
                        page_number = sig_field_page
                        x_position = sig_field_x
                        y_position = sig_field_y
                        width = sig_field_width or 200
                        height = sig_field_height or 80
                    else:
                        # Use current field data (prefer stored metadata if available for consistency)
                        page_number = sig_field_page if sig_field_page else field.page_number
                        x_position = sig_field_x if sig_field_x else field.x_position
                        y_position = sig_field_y if sig_field_y else field.y_position
                        width = sig_field_width if sig_field_width else (field.width or 200)
                        height = sig_field_height if sig_field_height else (field.height or 80)
                    
                    # Embed this signature
                    try:
                        from PIL import Image
                        import base64
                        from io import BytesIO
                        
                        page_num = page_number - 1
                        if page_num < 0 or page_num >= len(pdf_doc):
                            continue
                        
                        page = pdf_doc[page_num]
                        page_rect = page.rect
                        page_width = page_rect.width
                        page_height = page_rect.height
                        
                        # Convert coordinates (same logic as embed_signature_in_pdf)
                        viewer_height_px = 800.0
                        scale_y = page_height / viewer_height_px
                        viewer_width_px = viewer_height_px * (page_width / page_height)
                        scale_x = page_width / viewer_width_px
                        
                        x_pdf = x_position * scale_x
                        y_pdf = y_position * scale_y
                        width_pdf = width * scale_x
                        height_pdf = height * scale_y
                        
                        # Clamp to page bounds
                        x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                        y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                        
                        # Decode and embed signature
                        sig_image_data = base64.b64decode(sig.signature_image)
                        sig_img = Image.open(BytesIO(sig_image_data))
                        
                        img_bytes = BytesIO()
                        sig_img.save(img_bytes, format='PNG')
                        img_bytes.seek(0)
                        
                        img_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                        page.insert_image(img_rect, stream=img_bytes.getvalue())
                    except Exception as e:
                        print(f"Error embedding signature {sig.id}: {e}")
                        continue
                
                # Embed typed field values as text (handle case where table might not exist yet)
                try:
                    for typed_field_id, field_value in typed_value_map.items():
                        try:
                            typed_field = DocumentTypedField.query.get(typed_field_id)
                            if not typed_field:
                                continue
                            
                            page_num = typed_field.page_number - 1
                            if page_num < 0 or page_num >= len(pdf_doc):
                                continue
                            
                            page = pdf_doc[page_num]
                            page_rect = page.rect
                            page_width = page_rect.width
                            page_height = page_rect.height
                            
                            # Convert coordinates
                            viewer_height_px = 800.0
                            scale_y = page_height / viewer_height_px
                            viewer_width_px = viewer_height_px * (page_width / page_height)
                            scale_x = page_width / viewer_width_px
                            
                            x_pdf = typed_field.x_position * scale_x
                            y_pdf = typed_field.y_position * scale_y
                            width_pdf = (typed_field.width or 200) * scale_x
                            height_pdf = (typed_field.height or 30) * scale_y
                            
                            # Clamp to page bounds
                            x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                            y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                            
                            # Create text rectangle
                            text_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                            
                            # Insert text
                            # Calculate font size based on height (roughly 70% of height)
                            font_size = int(height_pdf * 0.7)
                            if font_size < 8:
                                font_size = 8
                            elif font_size > 72:
                                font_size = 72
                            
                            # Debug output
                            print(f"\n=== Typed Field Embedding ===")
                            print(f"Field ID: {typed_field_id}, Value: {field_value}")
                            print(f"Browser coords: x={typed_field.x_position:.1f}, y={typed_field.y_position:.1f}")
                            print(f"PDF coords: x={x_pdf:.2f}, y={y_pdf:.2f}")
                            print(f"Size: {width_pdf:.2f} x {height_pdf:.2f}, Font: {font_size}")
                            print(f"Text rect: {text_rect}")
                            print(f"========================\n")
                            
                            # Insert text using insert_textbox (handles wrapping and clipping)
                            try:
                                # Ensure text rect is valid
                                if text_rect.width <= 0 or text_rect.height <= 0:
                                    print(f"Invalid text rect: {text_rect}, using insert_text instead")
                                    raise ValueError("Invalid text rectangle")
                                
                                rc = page.insert_textbox(
                                    text_rect,
                                    field_value,
                                    fontsize=font_size,
                                    align=0,  # Left align
                                    color=(0, 0, 0),  # Black text
                                    render_mode=0  # Fill text
                                )
                                # insert_textbox returns the number of characters that didn't fit
                                # Negative return means error, 0 means all text fit
                                if rc < 0:
                                    print(f"Textbox insertion failed (rc={rc}), trying insert_text")
                                    # Use insert_text as fallback (single line, no wrapping)
                                    # Position text at top of box with some padding
                                    # Use insert_text with proper baseline positioning
                                    # y_pdf is top of box, need to add font_size for baseline
                                    # Also add small padding from left edge
                                    text_y = y_pdf + font_size + 2  # Baseline position with padding
                                    page.insert_text(
                                        (x_pdf + 2, text_y),  # Position at baseline with small padding
                                        field_value[:100],  # Limit to 100 chars to avoid overflow
                                        fontsize=font_size,
                                        color=(0, 0, 0)  # Black text
                                    )
                                    print(f"Used insert_text fallback at ({x_pdf + 2:.2f}, {text_y:.2f})")
                                elif rc > 0:
                                    print(f"Warning: {rc} characters did not fit in textbox")
                                else:
                                    print(f"Textbox inserted successfully")
                            except Exception as textbox_error:
                                print(f"Textbox insertion error: {textbox_error}, trying insert_text")
                                # Fallback to insert_text
                                try:
                                    # Use insert_text with proper baseline positioning
                                    # y_pdf is top of box, need to add font_size for baseline
                                    text_y = y_pdf + font_size + 2  # Baseline position with padding
                                    page.insert_text(
                                        (x_pdf + 2, text_y),  # Position at baseline with small padding
                                        field_value[:100],  # Limit to 100 chars
                                        fontsize=font_size,
                                        color=(0, 0, 0)  # Black text
                                    )
                                    print(f"Used insert_text fallback in exception handler at ({x_pdf + 2:.2f}, {text_y:.2f})")
                                except Exception as text_error:
                                    print(f"Text insertion also failed: {text_error}")
                                    import traceback
                                    traceback.print_exc()
                                    raise
                        except Exception as e:
                            print(f"Error embedding typed field {typed_field_id}: {e}")
                            continue
                except Exception as e:
                    print(f"Error processing typed fields: {e}")
                    # Continue without typed fields
                
                # Save the PDF with all modifications
                pdf_doc.save(temp_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                pdf_doc.close()
                
                # Verify the file was saved
                if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                    raise Exception("Failed to save PDF with typed fields")
                
                # Serve the temp file
                file_type = document.file_type or 'application/pdf'
                response = send_file(
                    temp_path,
                    as_attachment=False,
                    mimetype=file_type
                )
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
                # Prevent caching to ensure fresh PDF with typed fields
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                
                return response
        except Exception as e:
            print(f"Error creating signed copy: {e}")
            import traceback
            traceback.print_exc()
            # Fall through to serve original
    
    # Serve original blank document
    if not os.path.exists(document.file_path):
        return "File not found on server.", 404
    
    file_type = document.file_type or 'application/octet-stream'
    
    response = send_file(
        document.file_path,
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
            flash('This document does not have any fields configured.', 'error')
            return redirect(url_for('view_documents'))
        
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
        
        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sign Document - {{ document.name_for_users }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
                margin: 20px auto;
                padding: 0 20px;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 5px;
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-danger {
                background: #FE0100;
            }
            .main-content {
                display: grid;
                grid-template-columns: 1fr 400px;
                gap: 20px;
            }
            .document-viewer-container {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
                position: relative;
            }
            .document-viewer {
                position: relative;
                background: #525252;
                min-height: 800px;
                overflow: auto;
                padding: 20px;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }
            #pdfCanvas {
                max-width: 100%;
                height: auto;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                background: white;
                display: block;
            }
            .signature-overlay {
                position: absolute;
                pointer-events: none;
                z-index: 1000;
                top: 20px;
                left: 20px;
                right: 20px;
                bottom: 20px;
                overflow: visible;
            }
            .signature-overlay-item {
                position: absolute;
                border: 2px solid #28a745;
                background: rgba(255, 255, 255, 0.95);
                pointer-events: none;
                box-sizing: border-box;
                padding: 2px;
                z-index: 1001;
                transform: translateZ(0);
            }
            .signature-overlay-item img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                background: white;
                display: block;
            }
            .signature-panel {
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
            }
            .signature-pad-container {
                border: 2px solid #ddd;
                border-radius: 0.5rem;
                margin-bottom: 15px;
                background: white;
            }
            #signaturePad {
                width: 100%;
                height: 200px;
                cursor: crosshair;
                border: none;
            }
            .signature-controls {
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
            }
            .signature-controls button {
                flex: 1;
                padding: 8px;
                border: 1px solid #ddd;
                background: #f8f9fa;
                border-radius: 0.5rem;
                cursor: pointer;
            }
            .signature-controls button:hover {
                background: #e9ecef;
            }
            .signature-fields-list {
                margin-top: 20px;
            }
            .signature-field-item {
                background: #f8f9fa;
                padding: 15px;
                margin-bottom: 10px;
                border-radius: 0.5rem;
                border-left: 3px solid #007bff;
            }
            .signature-field-item.signed {
                border-left-color: #28a745;
                background: #d4edda;
            }
            .signature-field-item h4 {
                margin-bottom: 5px;
                font-size: 0.9em;
            }
            .signature-field-item p {
                font-size: 0.8em;
                color: #808080;
                margin: 3px 0;
            }
            .signature-preview {
                margin-top: 10px;
                padding: 10px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                max-height: 100px;
                overflow: hidden;
            }
            .signature-preview img {
                max-width: 100%;
                max-height: 80px;
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
                .main-content {
                    grid-template-columns: 1fr;
                    gap: 20px;
                }
                .document-viewer-container {
                    padding: 15px;
                }
                .document-viewer {
                    min-height: 500px;
                    padding: 10px;
                }
                .document-viewer iframe {
                    height: 500px !important;
                }
                .signature-panel {
                    padding: 15px;
                }
                .signature-pad-container {
                    margin-bottom: 10px;
                }
                #signaturePad {
                    height: 150px;
                }
                canvas[id^="signaturePad-"] {
                    width: 100% !important;
                    height: 150px !important;
                }
                .signature-controls {
                    flex-direction: column;
                }
                .signature-controls button {
                    width: 100%;
                    min-height: 44px;
                    padding: 12px;
                }
                .signature-field-item {
                    padding: 12px;
                }
                .btn, .btn-success {
                    min-height: 44px;
                    padding: 12px 20px;
                    font-size: 1em;
                }
                input[type="text"], input[type="date"], input[type="number"] {
                    min-height: 44px;
                    font-size: 16px; /* Prevents zoom on iOS */
                }
            }
            
            @media (max-width: 480px) {
                .header-content h1 {
                    font-size: 1em;
                }
                .document-viewer {
                    min-height: 400px;
                }
                .document-viewer iframe {
                    height: 400px !important;
                }
                #signaturePad {
                    height: 120px;
                }
                canvas[id^="signaturePad-"] {
                    height: 120px !important;
                }
                .signature-field-item {
                    padding: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>✍️ Sign Document - {{ document.name_for_users }}</h1>
            </div>
            <a href="{{ url_for('view_documents') }}" class="back-btn">← Back to Documents</a>
        </div>
        
        <div class="container">
            
            <div class="main-content">
                <div class="document-viewer-container">
                    <h3 style="margin-bottom: 15px;">Document Preview</h3>
                    <div class="document-viewer" id="documentViewer">
                        {% if is_pdf %}
                        <iframe src="{{ url_for('view_document_embed', doc_id=document.id, username=current_user.username) }}" style="width: 100%; height: 800px; border: none;"></iframe>
                        {% else %}
                        <p style="padding: 20px; color: white;">Please download the document to view it.</p>
                        {% endif %}
                    </div>
                </div>
                
                <div class="signature-panel">
                    <h3 style="margin-bottom: 15px;">Signature Fields</h3>
                    
                    {% for field in signature_fields %}
                    <div class="signature-field-item {% if field.is_signed %}signed{% endif %} sign-field-item" id="field-{{ field.id }}" data-field-id="{{ field.id }}" data-field-type="signature">
                        <h4>{{ field.field_label or 'Signature Field' }}</h4>
                        <p>Page: {{ field.page_number }}</p>
                        {% if field.signature_type == 'cryptographic' %}
                            <p style="font-size: 0.85em; color: #0066cc; margin-bottom: 10px;">
                                <strong>🔒 Cryptographic Signature</strong><br>
                                This is a legally binding, tamper-evident signature.
                            </p>
                        {% endif %}
                        <div id="signature-field-container-{{ field.id }}">
                        {% if field.is_signed and field.matching_signature %}
                            <p style="color: #28a745; font-weight: bold;">✓ Signed</p>
                            {% set sig = field.matching_signature %}
                            {% if sig.signature_type and sig.signature_type == 'cryptographic' %}
                                <div class="signature-preview" style="padding: 15px; background: #e8f4f8; border: 2px solid #0066cc; border-radius: 4px;">
                                    <p style="margin: 0; color: #0066cc; font-weight: bold;">🔒 Cryptographically Signed</p>
                                    <p style="margin: 5px 0 0 0; font-size: 0.85em; color: #666;">
                                        Signed: {{ sig.signed_at.strftime('%Y-%m-%d %H:%M:%S') if sig.signed_at else 'N/A' }}<br>
                                        {% if sig.signature_hash %}
                                        Hash: {{ sig.signature_hash[:16] }}...
                                        {% endif %}
                                    </p>
                                </div>
                            {% else %}
                                {% if sig.signature_image %}
                                <div class="signature-preview">
                                    <img src="data:image/png;base64,{{ sig.signature_image }}" alt="Signature">
                                </div>
                                {% endif %}
                            {% endif %}
                            <button type="button" onclick="redoSignature({{ field.id }})" class="btn" style="width: 100%; margin-top: 10px; padding: 8px; background: #ffc107; color: #000;">Redo Signature</button>
                        {% else %}
                            {% if field.signature_type == 'cryptographic' %}
                                <div class="cryptographic-signature-form">
                                    <div style="padding: 15px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; margin-bottom: 15px;">
                                        <p style="margin: 0 0 10px 0; font-weight: bold;">Electronic Signature Consent</p>
                                        <p style="margin: 0; font-size: 0.9em; color: #856404;">
                                            By clicking "Sign Electronically", you agree that:<br>
                                            • This electronic signature has the same legal effect as a handwritten signature<br>
                                            • You consent to conduct business electronically<br>
                                            • The signed document will be legally binding
                                        </p>
                                    </div>
                                    <label style="display: flex; align-items: center; margin-bottom: 15px; cursor: pointer;">
                                        <input type="checkbox" id="consent-{{ field.id }}" style="margin-right: 8px; width: 18px; height: 18px;">
                                        <span>I agree to sign this document electronically</span>
                                    </label>
                                    <button type="button" onclick="saveCryptographicSignature({{ field.id }})" class="btn-success" style="width: 100%; padding: 12px; font-size: 1em; font-weight: bold;">
                                        🔒 Sign Electronically
                                    </button>
                                </div>
                            {% else %}
                                <div class="signature-pad-container">
                                    <canvas id="signaturePad-{{ field.id }}" width="350" height="200"></canvas>
                                </div>
                                <div class="signature-controls">
                                    <button type="button" onclick="clearSignature({{ field.id }})">Clear</button>
                                    <button type="button" onclick="saveSignature({{ field.id }})" class="btn-success">Save Signature</button>
                                </div>
                            {% endif %}
                        {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                    
                    {% if typed_fields %}
                    <hr style="margin: 30px 0; border: 1px solid #ddd;">
                    <h3 style="margin-bottom: 15px;">Typed Fields</h3>
                    
                    {% for field in typed_fields %}
                    <div class="signature-field-item sign-field-item typed-field-item" style="border-left-color: #ffc107;" id="typed-field-item-{{ field.id }}" data-field-id="{{ field.id }}" data-field-type="typed" data-typed-type="{{ field.field_type }}">
                        <h4>{{ field.field_label or 'Typed Field' }}</h4>
                        <p>Type: {{ field.field_type|replace('_', ' ')|title }} • Page: {{ field.page_number }}</p>
                        <div id="typed-field-container-{{ field.id }}">
                        {% if field.id in filled_typed_field_ids %}
                            <p style="color: #28a745; font-weight: bold;">✓ Filled</p>
                            <div style="padding: 10px; background: #f8f9fa; border-radius: 4px; margin-top: 10px;">
                                <strong>Value:</strong> {{ filled_typed_field_ids[field.id] }}
                            </div>
                            <button type="button" onclick="redoTypedField({{ field.id }})" class="btn" style="width: 100%; margin-top: 10px; padding: 8px; background: #ffc107; color: #000;">Redo Field</button>
                        {% else %}
                            <div class="form-group" style="margin-top: 10px;">
                                {% if field.field_type == 'typed_name' %}
                                    <input type="text" id="typed-field-{{ field.id }}" class="typed-field-input" readonly
                                           value="{{ user_display_name }}"
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: #f8f9fa;">
                                    <p style="font-size: 0.85em; color: #666; margin-top: 5px;">Your name will be used. Click below to sign.</p>
                                    <button type="button" onclick="saveTypedField({{ field.id }})" class="btn-success" style="width: 100%; margin-top: 10px; padding: 10px;">Click to Sign</button>
                                {% elif field.field_type == 'typed_initials' %}
                                    <input type="text" id="typed-field-{{ field.id }}" class="typed-field-input" readonly
                                           value="{{ user_initials }}"
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: #f8f9fa;">
                                    <p style="font-size: 0.85em; color: #666; margin-top: 5px;">Your initials will be used. Click below to sign.</p>
                                    <button type="button" onclick="saveTypedField({{ field.id }})" class="btn-success" style="width: 100%; margin-top: 10px; padding: 10px;">Click to Sign</button>
                                {% elif field.field_type == 'date' %}
                                    <input type="date" id="typed-field-{{ field.id }}" class="typed-field-input" readonly
                                           value="{{ today_date }}"
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: #f8f9fa;">
                                    <p style="font-size: 0.85em; color: #666; margin-top: 5px;">Today's date. Click below to sign.</p>
                                    <button type="button" onclick="saveTypedField({{ field.id }})" class="btn-success" style="width: 100%; margin-top: 10px; padding: 10px;">Click to Sign</button>
                                {% elif field.field_type == 'number' %}
                                    <input type="number" id="typed-field-{{ field.id }}" class="typed-field-input" 
                                           placeholder="{{ field.placeholder or 'Enter number' }}" 
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;"
                                           {% if field.is_required %}required{% endif %}>
                                {% else %}
                                    <input type="text" id="typed-field-{{ field.id }}" class="typed-field-input" 
                                           placeholder="{{ field.placeholder or 'Enter ' + field.field_label|lower }}" 
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;"
                                           {% if field.is_required %}required{% endif %}>
                                {% endif %}
                                {% if field.field_type not in ['typed_name', 'typed_initials', 'date'] %}
                                <button type="button" onclick="saveTypedField({{ field.id }})" class="btn-success" style="width: 100%; margin-top: 10px; padding: 10px;">Save {{ field.field_label }}</button>
                                {% endif %}
                            </div>
                        {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                    {% endif %}
                    
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd;">
                        <p style="font-size: 0.9em; color: #666; margin-bottom: 10px;">
                            By signing this document, you acknowledge that you have read and agree to its contents.
                        </p>
                        <a href="{{ url_for('view_documents') }}" class="btn" style="width: 100%;">Done</a>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            var signaturePads = {};
            var isDrawing = false;
            var pdfDoc = null;
            var pdfScale = 1.0;
            var canvasOffsetX = 0;
            var canvasOffsetY = 0;
            
            // Scroll sidebar to the first incomplete (unsigned/unfilled) field
            function scrollToFirstIncompleteField() {
                var panel = document.querySelector('.signature-panel');
                if (!panel) return;
                var items = panel.querySelectorAll('.sign-field-item');
                for (var i = 0; i < items.length; i++) {
                    if (!items[i].classList.contains('signed')) {
                        items[i].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                        break;
                    }
                }
            }
            
            // Load PDF using PDF.js
            function loadPDF() {
                var canvas = document.getElementById('pdfCanvas');
                if (!canvas) return;
                
                // Set up PDF.js worker
                pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                
                // Get PDF URL
                var pdfUrl = '{{ url_for("view_document_embed", doc_id=document.id) }}';
                
                // Load the PDF
                pdfjsLib.getDocument(pdfUrl).promise.then(function(pdf) {
                    pdfDoc = pdf;
                    
                    // Render first page (or page with signature fields)
                    var pageNum = 1;
                    {% if signature_fields %}
                    pageNum = {{ signature_fields[0].page_number }};
                    {% endif %}
                    
                    renderPage(pageNum);
                }).catch(function(error) {
                    console.error('Error loading PDF:', error);
                    document.getElementById('documentViewer').innerHTML = '<p style="padding: 20px; color: white;">Error loading PDF. Please try downloading the document.</p>';
                });
            }
            
            // Render a PDF page
            function renderPage(pageNum) {
                if (!pdfDoc) return;
                
                var canvas = document.getElementById('pdfCanvas');
                var ctx = canvas.getContext('2d');
                
                pdfDoc.getPage(pageNum).then(function(page) {
                    // Calculate scale to fit 800px height (matching viewer where admin clicked)
                    var viewerHeight = 800;
                    var viewport = page.getViewport({ scale: 1.0 });
                    var scale = viewerHeight / viewport.height;
                    pdfScale = scale;
                    
                    // Set canvas size
                    var scaledViewport = page.getViewport({ scale: scale });
                    canvas.width = scaledViewport.width;
                    canvas.height = scaledViewport.height;
                    
                    // Render PDF page
                    var renderContext = {
                        canvasContext: ctx,
                        viewport: scaledViewport
                    };
                    
                    page.render(renderContext).promise.then(function() {
                        // Calculate canvas offset within viewer (accounting for padding/centering)
                        var viewer = document.getElementById('documentViewer');
                        var viewerRect = viewer.getBoundingClientRect();
                        var canvasRect = canvas.getBoundingClientRect();
                        canvasOffsetX = canvasRect.left - viewerRect.left;
                        canvasOffsetY = canvasRect.top - viewerRect.top;
                        
                        // After PDF is rendered, display signatures
                        displaySignaturesOnPDF();
                    });
                });
            }
            
            // Display existing signatures on PDF
            function displaySignaturesOnPDF() {
                var overlay = document.getElementById('signatureOverlay');
                var canvas = document.getElementById('pdfCanvas');
                var viewer = document.getElementById('documentViewer');
                if (!overlay || !canvas || !viewer) {
                    console.log('Missing elements:', {overlay: !!overlay, canvas: !!canvas, viewer: !!viewer});
                    return;
                }
                
                // Clear existing overlays
                overlay.innerHTML = '';
                
                // Get actual dimensions of viewer container
                var viewerRect = viewer.getBoundingClientRect();
                
                // Signature data from server - build a map of field_id to field data
                var fieldMap = {
                    {% for field in signature_fields %}
                    {{ field.id }}: {
                        x_position: {{ field.x_position }},
                        y_position: {{ field.y_position }},
                        width: {{ field.width or 200 }},
                        height: {{ field.height or 80 }},
                        page_number: {{ field.page_number }}
                    }{% if not loop.last %},{% endif %}
                    {% endfor %}
                };
                
                var signatures = [
                    {% for sig in user_signatures %}
                    {
                        field_id: {{ sig.signature_field_id }},
                        signature_image: 'data:image/png;base64,{{ sig.signature_image }}',
                        field: fieldMap[{{ sig.signature_field_id }}]
                    }{% if not loop.last %},{% endif %}
                    {% endfor %}
                ];
                
                console.log('Viewer container dimensions:', viewerRect.width, 'x', viewerRect.height);
                console.log('Signatures to display:', signatures.length);
                console.log('Field map:', fieldMap);
                
                // Display each signature
                // Coordinates are stored relative to viewer container (where admin clicked)
                // Adjust for canvas offset within viewer
                signatures.forEach(function(sigData) {
                    if (!sigData.field || sigData.field.x_position === undefined) {
                        return;
                    }
                    
                    var overlayItem = document.createElement('div');
                    overlayItem.className = 'signature-overlay-item';
                    
                    // Use coordinates directly - they're stored relative to viewer
                    // and overlay is also positioned relative to viewer
                    overlayItem.style.position = 'absolute';
                    overlayItem.style.left = sigData.field.x_position + 'px';
                    overlayItem.style.top = sigData.field.y_position + 'px';
                    overlayItem.style.width = (sigData.field.width || 200) + 'px';
                    overlayItem.style.height = (sigData.field.height || 80) + 'px';
                    
                    var img = document.createElement('img');
                    img.src = sigData.signature_image;
                    img.alt = 'Signature';
                    img.style.display = 'block';
                    img.style.width = '100%';
                    img.style.height = '100%';
                    img.style.objectFit = 'contain';
                    overlayItem.appendChild(img);
                    
                    overlay.appendChild(overlayItem);
                    
                    console.log('Positioned signature at:', sigData.field.x_position, sigData.field.y_position);
                });
            }
            
            // Initialize when page loads
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', loadPDF);
            } else {
                loadPDF();
            }
            
            // Initialize signature pads for unsigned fields
            {% for field in signature_fields %}
                {% if field.id not in signed_field_ids %}
                (function() {
                    var canvas = document.getElementById('signaturePad-{{ field.id }}');
                    var ctx = canvas.getContext('2d');
                    ctx.strokeStyle = '#000';
                    ctx.lineWidth = 2;
                    ctx.lineCap = 'round';
                    ctx.lineJoin = 'round';
                    
                    var lastX = 0;
                    var lastY = 0;
                    
                    function startDrawing(e) {
                        isDrawing = true;
                        var rect = canvas.getBoundingClientRect();
                        lastX = e.clientX - rect.left;
                        lastY = e.clientY - rect.top;
                    }
                    
                    function draw(e) {
                        if (!isDrawing) return;
                        var rect = canvas.getBoundingClientRect();
                        var currentX = e.clientX - rect.left;
                        var currentY = e.clientY - rect.top;
                        
                        ctx.beginPath();
                        ctx.moveTo(lastX, lastY);
                        ctx.lineTo(currentX, currentY);
                        ctx.stroke();
                        
                        lastX = currentX;
                        lastY = currentY;
                    }
                    
                    function stopDrawing() {
                        isDrawing = false;
                    }
                    
                    canvas.addEventListener('mousedown', startDrawing);
                    canvas.addEventListener('mousemove', draw);
                    canvas.addEventListener('mouseup', stopDrawing);
                    canvas.addEventListener('mouseout', stopDrawing);
                    
                    // Touch events for mobile
                    canvas.addEventListener('touchstart', function(e) {
                        e.preventDefault();
                        var touch = e.touches[0];
                        var mouseEvent = new MouseEvent('mousedown', {
                            clientX: touch.clientX,
                            clientY: touch.clientY
                        });
                        canvas.dispatchEvent(mouseEvent);
                    });
                    
                    canvas.addEventListener('touchmove', function(e) {
                        e.preventDefault();
                        var touch = e.touches[0];
                        var mouseEvent = new MouseEvent('mousemove', {
                            clientX: touch.clientX,
                            clientY: touch.clientY
                        });
                        canvas.dispatchEvent(mouseEvent);
                    });
                    
                    canvas.addEventListener('touchend', function(e) {
                        e.preventDefault();
                        var mouseEvent = new MouseEvent('mouseup', {});
                        canvas.dispatchEvent(mouseEvent);
                    });
                    
                    signaturePads[{{ field.id }}] = canvas;
                })();
                {% endif %}
            {% endfor %}
            
            function clearSignature(fieldId) {
                var canvas = document.getElementById('signaturePad-' + fieldId);
                if (canvas) {
                    var ctx = canvas.getContext('2d');
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                }
            }
            
            function saveSignature(fieldId) {
                var canvas = document.getElementById('signaturePad-' + fieldId);
                if (!canvas) return;
                
                // Check if canvas has any drawing
                var ctx = canvas.getContext('2d');
                var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                var hasDrawing = false;
                for (var i = 0; i < imageData.data.length; i += 4) {
                    if (imageData.data[i + 3] > 0) {
                        hasDrawing = true;
                        break;
                    }
                }
                
                if (!hasDrawing) {
                    alert('Please sign before saving.');
                    return;
                }
                
                // Convert canvas to base64
                var signatureData = canvas.toDataURL('image/png');
                var base64Data = signatureData.split(',')[1];
                
                // Send to server
                fetch('{{ url_for("submit_signature", doc_id=document.id) }}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        signature_field_id: fieldId,
                        signature_image: base64Data,
                        consent_given: false
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Signature saved successfully!');
                        // Reload to show signature on PDF
                        location.reload();
                    } else {
                        alert('Error saving signature: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error saving signature. Please try again.');
                });
            }
            
            function saveCryptographicSignature(fieldId) {
                var consentCheckbox = document.getElementById('consent-' + fieldId);
                if (!consentCheckbox || !consentCheckbox.checked) {
                    alert('You must agree to sign electronically before proceeding.');
                    return;
                }
                
                if (!confirm('This will create a legally binding, cryptographically signed document. Continue?')) {
                    return;
                }
                
                // Send to server
                fetch('{{ url_for("submit_signature", doc_id=document.id) }}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        signature_field_id: fieldId,
                        signature_image: null,
                        consent_given: true
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Document signed cryptographically! The signature is legally binding and tamper-evident.');
                        // Reload to show signature status
                        location.reload();
                    } else {
                        alert('Error signing document: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error signing document. Please try again.');
                });
            }
            
            function saveTypedField(fieldId) {
                var input = document.getElementById('typed-field-' + fieldId);
                if (!input) return;
                
                var value = input.value.trim();
                if (!value) {
                    alert('Please enter a value for this field.');
                    return;
                }
                
                // Send to server
                fetch('{{ url_for("submit_typed_field", doc_id=document.id) }}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        typed_field_id: fieldId,
                        field_value: value
                    })
                })
                .then(response => {
                    // Check if response is OK
                    if (!response.ok) {
                        // Try to get error message from JSON response
                        return response.json().catch(() => {
                            // If not JSON, return error with status text
                            throw new Error('Server error: ' + response.status + ' ' + response.statusText);
                        }).then(data => {
                            throw new Error(data.error || 'Server error: ' + response.status);
                        });
                    }
                    // Parse JSON response
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        // Update UI to show field is filled without reloading
                        var fieldContainer = document.getElementById('typed-field-container-' + fieldId);
                        if (fieldContainer) {
                            var itemEl = fieldContainer.closest('.signature-field-item');
                            if (itemEl) itemEl.classList.add('signed');
                            fieldContainer.innerHTML = '<p style="color: #28a745; font-weight: bold;">✓ Filled</p>' +
                                '<div style="padding: 10px; background: #f8f9fa; border-radius: 4px; margin-top: 10px;"><strong>Value:</strong> ' + value + '</div>' +
                                '<button type="button" onclick="redoTypedField(' + fieldId + ')" class="btn" style="width: 100%; margin-top: 10px; padding: 8px; background: #ffc107; color: #000;">Redo Field</button>';
                            scrollToFirstIncompleteField();
                            
                            // Reload the PDF iframe to show the typed field value
                            setTimeout(function() {
                                var iframe = document.querySelector('iframe[src*="view_document_embed"]') || 
                                             document.querySelector('iframe[src*="embed"]') ||
                                             document.getElementById('documentViewer')?.querySelector('iframe');
                                if (iframe) {
                                    var currentSrc = iframe.src;
                                    // Remove existing cache-busting parameter if present
                                    currentSrc = currentSrc.split('&_t=')[0].split('?_t=')[0];
                                    // Add cache-busting parameter
                                    var separator = currentSrc.includes('?') ? '&' : '?';
                                    iframe.src = currentSrc + separator + '_t=' + Date.now();
                                } else {
                                    // Fallback: reload the entire page
                                    console.log('Iframe not found, reloading page');
                                    location.reload();
                                }
                            }, 500); // Small delay to ensure PDF is generated
                        } else {
                            // Fallback: reload if container not found
                            location.reload();
                        }
                    } else {
                        alert('Error saving field: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    var errorMsg = error.message || 'Unknown error occurred';
                    alert('Error saving field: ' + errorMsg);
                });
            }
            
            // Redo signature field - delete existing signature and show input form again
            function redoSignature(fieldId) {
                if (!confirm('Are you sure you want to redo this signature? The current signature will be deleted.')) {
                    return;
                }
                
                fetch('{{ url_for("delete_signature", doc_id=document.id) }}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        signature_field_id: fieldId
                    })
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Server error: ' + response.status);
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        // Reload page to show signature input form again
                        location.reload();
                    } else {
                        alert('Error: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error redoing signature: ' + error.message);
                });
            }
            
            // On load: scroll to first incomplete field; ensure date fields are pre-filled with today
            document.addEventListener('DOMContentLoaded', function() {
                var today = new Date();
                var yyyy = today.getFullYear();
                var mm = String(today.getMonth() + 1).padStart(2, '0');
                var dd = String(today.getDate()).padStart(2, '0');
                var todayStr = yyyy + '-' + mm + '-' + dd;
                document.querySelectorAll('input.typed-field-input[type="date"]').forEach(function(inp) {
                    if (!inp.value || inp.value.trim() === '') inp.value = todayStr;
                });
                setTimeout(scrollToFirstIncompleteField, 400);
            });
            
            // Redo typed field - delete existing value and show input form again
            function redoTypedField(fieldId) {
                if (!confirm('Are you sure you want to redo this field? The current value will be deleted.')) {
                    return;
                }
                
                fetch('{{ url_for("delete_typed_field_value", doc_id=document.id) }}', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        typed_field_id: fieldId
                    })
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Server error: ' + response.status);
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        // Reload page to show input form again
                        location.reload();
                    } else {
                        alert('Error: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error redoing field: ' + error.message);
                });
            }
        </script>
    </body>
    </html>
    ''', document=document, signature_fields=signature_fields, signed_field_ids=signed_field_ids, 
         user_signatures=user_signatures, typed_fields=typed_fields, filled_typed_field_ids=filled_typed_field_ids, is_pdf=is_pdf,
         user_display_name=user_display_name, user_initials=user_initials, today_date=today_date)
    except Exception as e:
        import traceback
        traceback.print_exc()
        app.logger.error(f'Error in sign_document (doc_id={doc_id}): {e}')
        flash('Unable to load the sign document page. Please try again or contact support.', 'error')
        return redirect(url_for('view_documents'))


@app.route('/documents/<int:doc_id>/sign')
@login_required
def sign_document(doc_id):
    """Sign a document - only allowed if document is assigned to user."""
    return _serve_sign_document_page(doc_id)


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
    
    if not signature_field_id:
        return jsonify({'success': False, 'error': 'Missing signature field ID'}), 400
    
    # Verify signature field exists and belongs to this document
    signature_field = DocumentSignatureField.query.get(signature_field_id)
    if not signature_field or signature_field.document_id != doc_id:
        return jsonify({'success': False, 'error': 'Invalid signature field'}), 400
    
    # Check signature type (default to 'image' if None)
    signature_type = signature_field.signature_type or 'image'
    is_cryptographic = signature_type == 'cryptographic'
    
    if is_cryptographic:
        # Cryptographic signatures require consent
        if not consent_given:
            return jsonify({'success': False, 'error': 'Electronic signature consent is required'}), 400
    else:
        # Image signatures require the image
        if not signature_image:
            return jsonify({'success': False, 'error': 'Missing signature image'}), 400
    
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
            if not is_cryptographic:
                existing_signature.signature_image = signature_image
            existing_signature.signed_at = datetime.utcnow()
            existing_signature.ip_address = request.remote_addr
            existing_signature.user_agent = request.headers.get('User-Agent', '')
            existing_signature.consent_given = consent_given
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
                signature_image=signature_image if not is_cryptographic else None,
                signature_type=signature_field.signature_type,
                signed_at=datetime.utcnow(),
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', ''),
                consent_given=consent_given
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
        
        # Embed signature based on type
        if is_cryptographic:
            # Cryptographic signature
            success, message = sign_pdf_cryptographically(document, signature_field, current_user.username)
            if success:
                # Calculate hash of signed PDF for audit trail
                pdf_hash = calculate_pdf_hash(document.file_path)
                sig_to_embed.signature_hash = pdf_hash
        else:
            # Image signature - don't embed into original, just save to database
            # The signature will be displayed as an overlay when viewing
            success, message = True, "Signature saved to database"
        
        if not success:
            db.session.rollback()
            return jsonify({'success': False, 'error': message}), 500
        
        db.session.commit()
        
        # Check if all required fields are signed (using helper to handle deleted fields)
        all_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()
        required_fields = [f for f in all_fields if f.is_required]
        all_signed = all(is_signature_field_signed(doc_id, f, current_user.username) for f in required_fields) if required_fields else False
        
        # Update task completion if all fields signed
        if all_signed:
            # Mark document assignment as completed
            assignment = DocumentAssignment.query.filter_by(
                document_id=doc_id,
                username=current_user.username
            ).first()
            if assignment:
                assignment.is_completed = True
                assignment.completed_at = datetime.utcnow()
            
            # Mark user task as completed (UserTask uses status, not is_completed; task_type is 'document')
            task = UserTask.query.filter_by(
                document_id=doc_id,
                username=current_user.username,
                task_type='document'
            ).first()
            if task:
                task.status = 'completed'
                task.completed_at = datetime.utcnow()
            
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Signature saved and embedded in PDF'})
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


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
        
        if not field_value:
            return jsonify({'success': False, 'error': 'Field value is required'}), 400
        
        # Verify typed field exists and belongs to this document
        try:
            typed_field = DocumentTypedField.query.get(typed_field_id)
        except Exception:
            return jsonify({'success': False, 'error': 'Typed fields feature is not available. Please contact administrator.'}), 500
        
        if not typed_field or typed_field.document_id != doc_id:
            return jsonify({'success': False, 'error': 'Invalid typed field'}), 400
        
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
        
        if not field_value:
            return jsonify({'success': False, 'error': 'Field value is required'}), 400
    
        try:
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
            
            if existing_value:
                # Update existing value
                existing_value.field_value = field_value
                existing_value.filled_at = datetime.utcnow()
                existing_value.ip_address = request.remote_addr
                existing_value.user_agent = request.headers.get('User-Agent', '')
            else:
                # Create new value record
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
            return jsonify({'success': True, 'message': 'Typed field value saved successfully'})
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Error saving typed field: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/documents/<int:doc_id>/download')
@login_required
def download_document(doc_id):
    """Download a document - for users, download their signed version; for admins, download original"""
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
    
    # Check if file exists
    if not os.path.exists(document.file_path):
        flash('File not found on server.', 'error')
        return redirect(url_for('dashboard'))
    
    # For regular users, generate and download their signed version
    # For admins, download the original document
    if not current_user.is_admin():
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
            
            if (user_signatures or typed_value_map) and FITZ_AVAILABLE:
                # Create a temporary signed copy
                import tempfile
                import shutil
                
                # Create temp file
                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)
                
                # Copy original PDF
                shutil.copy2(document.file_path, temp_path)
                
                # Embed signatures and typed field values into temp copy
                pdf_doc = fitz.open(temp_path)
                
                # Embed signatures
                for sig in user_signatures:
                    if not sig.signature_image:
                        continue
                    
                    # Get signature field
                    field = DocumentSignatureField.query.get(sig.signature_field_id)
                    if not field:
                        continue
                    
                    # Embed this signature
                    try:
                        from PIL import Image
                        import base64
                        from io import BytesIO
                        
                        page_num = field.page_number - 1
                        if page_num < 0 or page_num >= len(pdf_doc):
                            continue
                        
                        page = pdf_doc[page_num]
                        page_rect = page.rect
                        page_width = page_rect.width
                        page_height = page_rect.height
                        
                        # Convert coordinates (same logic as embed_signature_in_pdf)
                        viewer_height_px = 800.0
                        scale_y = page_height / viewer_height_px
                        viewer_width_px = viewer_height_px * (page_width / page_height)
                        scale_x = page_width / viewer_width_px
                        
                        x_pdf = field.x_position * scale_x
                        y_pdf = field.y_position * scale_y
                        width_pdf = (field.width or 200) * scale_x
                        height_pdf = (field.height or 80) * scale_y
                        
                        # Clamp to page bounds
                        x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                        y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                        
                        # Decode and embed signature
                        sig_image_data = base64.b64decode(sig.signature_image)
                        sig_img = Image.open(BytesIO(sig_image_data))
                        
                        img_bytes = BytesIO()
                        sig_img.save(img_bytes, format='PNG')
                        img_bytes.seek(0)
                        
                        img_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                        page.insert_image(img_rect, stream=img_bytes.getvalue())
                    except Exception as e:
                        print(f"Error embedding signature {sig.id}: {e}")
                        continue
                
                # Embed typed field values as text
                try:
                    for typed_field_id, field_value in typed_value_map.items():
                        try:
                            typed_field = DocumentTypedField.query.get(typed_field_id)
                            if not typed_field:
                                continue
                            
                            page_num = typed_field.page_number - 1
                            if page_num < 0 or page_num >= len(pdf_doc):
                                continue
                            
                            page = pdf_doc[page_num]
                            page_rect = page.rect
                            page_width = page_rect.width
                            page_height = page_rect.height
                            
                            # Convert coordinates
                            viewer_height_px = 800.0
                            scale_y = page_height / viewer_height_px
                            viewer_width_px = viewer_height_px * (page_width / page_height)
                            scale_x = page_width / viewer_width_px
                            
                            x_pdf = typed_field.x_position * scale_x
                            y_pdf = typed_field.y_position * scale_y
                            width_pdf = (typed_field.width or 200) * scale_x
                            height_pdf = (typed_field.height or 30) * scale_y
                            
                            # Clamp to page bounds
                            x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                            y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                            
                            # Create text rectangle
                            text_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                            
                            # Calculate font size
                            font_size = int(height_pdf * 0.7)
                            if font_size < 8:
                                font_size = 8
                            elif font_size > 72:
                                font_size = 72
                            
                            # Insert text using insert_textbox
                            try:
                                if text_rect.width > 0 and text_rect.height > 0:
                                    rc = page.insert_textbox(
                                        text_rect,
                                        field_value,
                                        fontsize=font_size,
                                        align=0,
                                        color=(0, 0, 0),
                                        render_mode=0
                                    )
                                    if rc < 0:
                                        # Fallback to insert_text
                                        text_y = y_pdf + font_size + 2
                                        page.insert_text(
                                            (x_pdf + 2, text_y),
                                            field_value[:100],
                                            fontsize=font_size,
                                            color=(0, 0, 0)
                                        )
                            except Exception as text_error:
                                # Fallback to insert_text
                                try:
                                    text_y = y_pdf + font_size + 2
                                    page.insert_text(
                                        (x_pdf + 2, text_y),
                                        field_value[:100],
                                        fontsize=font_size,
                                        color=(0, 0, 0)
                                    )
                                except Exception:
                                    pass
                        except Exception as e:
                            print(f"Error embedding typed field {typed_field_id}: {e}")
                            continue
                except Exception as e:
                    print(f"Error processing typed fields: {e}")
                
                # Save the PDF
                pdf_doc.save(temp_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                pdf_doc.close()
                
                # Generate download filename with user's name
                base_name = os.path.splitext(document.original_filename)[0]
                ext = os.path.splitext(document.original_filename)[1]
                download_filename = f"{base_name}_signed_{current_user.username}{ext}"
                
                # Send the signed PDF
                # Note: Temp file will be cleaned up by OS, but we could implement
                # a background cleanup task if needed for production
                return send_file(
                    temp_path,
                    as_attachment=True,
                    download_name=download_filename,
                    mimetype=document.file_type or 'application/pdf'
                )
            else:
                # No signatures or typed fields, just download original
                return send_file(
                    document.file_path,
                    as_attachment=True,
                    download_name=document.original_filename,
                    mimetype=document.file_type or 'application/octet-stream'
                )
        except Exception as e:
            print(f"Error generating signed PDF: {e}")
            import traceback
            traceback.print_exc()
            # Fall through to download original
            return send_file(
                document.file_path,
                as_attachment=True,
                download_name=document.original_filename,
                mimetype=document.file_type or 'application/octet-stream'
            )
    else:
        # Admin downloads original document
        return send_file(
            document.file_path,
            as_attachment=True,
            download_name=document.original_filename,
            mimetype=document.file_type or 'application/octet-stream'
        )


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
    
    # Get signature fields to check if all required fields are signed
    signature_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()
    required_fields = [f for f in signature_fields if f.is_required]
    
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
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>📥 Signed Copies - {{ document.name_for_users }}</h1>
            </div>
            <a href="{{ url_for('manage_documents') }}" class="back-btn">← Back to Documents</a>
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
        
        # Get all required signature fields for this document
        required_fields = DocumentSignatureField.query.filter_by(
            document_id=doc_id,
            is_required=True
        ).all()
        
        if not required_fields:
            flash('This document has no required signature fields.', 'error')
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
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


@app.route('/admin/documents/<int:doc_id>/signed-copy/<username>')
@admin_required
def download_signed_document(doc_id, username):
    """Download a signed copy of a document for a specific user"""
    document = Document.query.get(doc_id)
    if not document:
        flash('Document not found.', 'error')
        return redirect(url_for('manage_documents'))
    
    # On error, return to form signatures if they were trying to print (inline); else signed-copies page
    def _error_redirect():
        return redirect(url_for('view_form_signatures', doc_id=doc_id)) if request.args.get('inline') else redirect(url_for('view_signed_documents', doc_id=doc_id))
    
    # Check if file exists
    if not os.path.exists(document.file_path):
        flash('File not found on server.', 'error')
        return _error_redirect()
    
    # Check if document is a PDF
    is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
    
    if not is_pdf:
        flash('Signed copies can only be generated for PDF documents.', 'error')
        return _error_redirect()
    
    # Get all signatures by this user for this document
    try:
        user_signatures = DocumentSignature.query.filter_by(
            document_id=doc_id,
            username=username
        ).all()
    except Exception as e:
        # If query fails (columns don't exist), use empty list
        user_signatures = []
    
    # Get typed field values for this user (handle case where table might not exist yet)
    try:
        user_typed_values = DocumentTypedFieldValue.query.filter_by(
            document_id=doc_id,
            username=username
        ).all()
        typed_value_map = {val.typed_field_id: val.field_value for val in user_typed_values}
    except Exception:
        typed_value_map = {}
    
    if not user_signatures and not typed_value_map:
        flash('No signatures or typed fields found for this user.', 'error')
        return _error_redirect()
    
    try:
        if (user_signatures or typed_value_map) and FITZ_AVAILABLE:
            # Create a temporary signed copy
            import tempfile
            import shutil
            
            # Create temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)
            
            # Copy original PDF
            shutil.copy2(document.file_path, temp_path)
            
            # Embed signatures and typed field values into temp copy
            pdf_doc = fitz.open(temp_path)
            
            # Embed signatures
            for sig in user_signatures:
                if not sig.signature_image:
                    continue
                
                # Get signature field
                field = DocumentSignatureField.query.get(sig.signature_field_id)
                if not field:
                    continue
                
                # Embed this signature
                try:
                    from PIL import Image
                    import base64
                    from io import BytesIO
                    
                    page_num = field.page_number - 1
                    if page_num < 0 or page_num >= len(pdf_doc):
                        continue
                    
                    page = pdf_doc[page_num]
                    page_rect = page.rect
                    page_width = page_rect.width
                    page_height = page_rect.height
                    
                    # Convert coordinates (same logic as embed_signature_in_pdf)
                    viewer_height_px = 800.0
                    scale_y = page_height / viewer_height_px
                    viewer_width_px = viewer_height_px * (page_width / page_height)
                    scale_x = page_width / viewer_width_px
                    
                    x_pdf = field.x_position * scale_x
                    y_pdf = field.y_position * scale_y
                    width_pdf = (field.width or 200) * scale_x
                    height_pdf = (field.height or 80) * scale_y
                    
                    # Clamp to page bounds
                    x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                    y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                    
                    # Decode and embed signature
                    sig_image_data = base64.b64decode(sig.signature_image)
                    sig_img = Image.open(BytesIO(sig_image_data))
                    
                    img_bytes = BytesIO()
                    sig_img.save(img_bytes, format='PNG')
                    img_bytes.seek(0)
                    
                    img_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                    page.insert_image(img_rect, stream=img_bytes.getvalue())
                except Exception as e:
                    print(f"Error embedding signature {sig.id}: {e}")
                    continue
            
            # Embed typed field values as text
            try:
                for typed_field_id, field_value in typed_value_map.items():
                    try:
                        typed_field = DocumentTypedField.query.get(typed_field_id)
                        if not typed_field:
                            continue
                        
                        page_num = typed_field.page_number - 1
                        if page_num < 0 or page_num >= len(pdf_doc):
                            continue
                        
                        page = pdf_doc[page_num]
                        page_rect = page.rect
                        page_width = page_rect.width
                        page_height = page_rect.height
                        
                        # Convert coordinates
                        viewer_height_px = 800.0
                        scale_y = page_height / viewer_height_px
                        viewer_width_px = viewer_height_px * (page_width / page_height)
                        scale_x = page_width / viewer_width_px
                        
                        x_pdf = typed_field.x_position * scale_x
                        y_pdf = typed_field.y_position * scale_y
                        width_pdf = (typed_field.width or 200) * scale_x
                        height_pdf = (typed_field.height or 30) * scale_y
                        
                        # Clamp to page bounds
                        x_pdf = max(0, min(x_pdf, page_width - width_pdf))
                        y_pdf = max(0, min(y_pdf, page_height - height_pdf))
                        
                        # Create text rectangle
                        text_rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width_pdf, y_pdf + height_pdf)
                        
                        # Calculate font size
                        font_size = int(height_pdf * 0.7)
                        if font_size < 8:
                            font_size = 8
                        elif font_size > 72:
                            font_size = 72
                        
                        # Insert text using insert_textbox
                        try:
                            if text_rect.width > 0 and text_rect.height > 0:
                                rc = page.insert_textbox(
                                    text_rect,
                                    field_value,
                                    fontsize=font_size,
                                    align=0,
                                    color=(0, 0, 0),
                                    render_mode=0
                                )
                                if rc < 0:
                                    # Fallback to insert_text
                                    text_y = y_pdf + font_size + 2
                                    page.insert_text(
                                        (x_pdf + 2, text_y),
                                        field_value[:100],
                                        fontsize=font_size,
                                        color=(0, 0, 0)
                                    )
                        except Exception as text_error:
                            # Fallback to insert_text
                            try:
                                text_y = y_pdf + font_size + 2
                                page.insert_text(
                                    (x_pdf + 2, text_y),
                                    field_value[:100],
                                    fontsize=font_size,
                                    color=(0, 0, 0)
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"Error embedding typed field {typed_field_id}: {e}")
                        continue
            except Exception as e:
                print(f"Error processing typed fields: {e}")
            
            # Save the PDF
            pdf_doc.save(temp_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            pdf_doc.close()
            
            # Generate download filename with user's name
            base_name = os.path.splitext(document.original_filename)[0]
            ext = os.path.splitext(document.original_filename)[1]
            download_filename = f"{base_name}_signed_by_{username}{ext}"
            
            # inline=1: open in browser for printing; otherwise download
            as_attachment = not request.args.get('inline')
            return send_file(
                temp_path,
                as_attachment=as_attachment,
                download_name=download_filename,
                mimetype=document.file_type or 'application/pdf'
            )
        else:
            # No signatures or typed fields, or PyMuPDF not available
            if not FITZ_AVAILABLE:
                flash('PDF processing library not available. Please install PyMuPDF.', 'error')
            else:
                flash('No signatures or typed fields found for this user.', 'error')
            return _error_redirect()
        
    except Exception as e:
        print(f"Error generating signed PDF: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error generating signed PDF: {str(e)}', 'error')
        return _error_redirect()


@app.route('/admin/new-hire/<username>/details')
@admin_required
def view_new_hire_details(username):
    """View detailed information about a new hire including quiz results and signed forms"""
    try:
        new_hire = NewHire.query.filter_by(username=username).first()
        if not new_hire:
            flash('New hire not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        
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
        
        # Get signed documents
        signed_documents = []
        try:
            all_signatures = DocumentSignature.query.filter_by(username=username).all()
            
            # Group signatures by document
            doc_signatures = {}
            for sig in all_signatures:
                try:
                    doc_id = sig.document_id
                    if doc_id not in doc_signatures:
                        doc = Document.query.get(doc_id)
                        if doc:
                            doc_signatures[doc_id] = {
                                'document': doc,
                                'signatures': []
                            }
                    # Only append if document exists in doc_signatures
                    if doc_id in doc_signatures:
                        doc_signatures[doc_id]['signatures'].append(sig)
                except Exception as e:
                    # Skip signatures that cause errors
                    continue
            
            signed_documents = list(doc_signatures.values())
        except Exception as e:
            # If there's an error getting signatures, use empty list
            signed_documents = []
        
        # Get user tasks
        try:
            user_tasks = UserTask.query.filter_by(username=username).all()
        except Exception as e:
            # If there's an error getting tasks, use empty list
            user_tasks = []
        
        # Get user account (for Cancel / Restore access)
        user_record = None
        user_is_revoked = False
        try:
            user_record = UserModel.query.filter_by(username=username).first()
            if user_record:
                from datetime import date
                revoked_at = getattr(user_record, 'access_revoked_at', None)
                user_is_revoked = bool(revoked_at is not None and date.today() >= revoked_at)
        except Exception:
            pass
        
        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ new_hire.first_name }} {{ new_hire.last_name }} - Details</title>
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .user-header {
                background: #FE0100;
                color: white;
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 30px;
            }
            .user-header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .user-info-table {
                width: 100%;
                margin-top: 20px;
                border-collapse: collapse;
            }
            .user-info-table tr {
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }
            .user-info-table tr:last-child {
                border-bottom: none;
            }
            .user-info-table td {
                padding: 15px;
                vertical-align: middle;
            }
            .user-info-table td:first-child {
                width: 150px;
                font-weight: 600;
                font-size: 0.95em;
                opacity: 0.95;
            }
            .user-info-table td:last-child {
                width: auto;
            }
            .info-value {
                font-size: 1.1em;
                font-weight: 600;
            }
            .user-info-table input,
            .user-info-table select {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 0.5rem;
                background: rgba(255,255,255,0.2);
                color: white;
                font-size: 16px; /* Prevents zoom on iOS */
                font-weight: 500;
                font-family: inherit;
                min-height: 44px; /* Touch-friendly */
            }
            .user-info-table input::placeholder {
                color: rgba(255,255,255,0.7);
            }
            .user-info-table input:focus,
            .user-info-table select:focus {
                outline: none;
                border-color: rgba(255,255,255,0.6);
                background: rgba(255,255,255,0.3);
            }
            .user-info-table select option {
                background: #FE0100;
                color: white;
            }
            .video-item {
                background: #f8f9fa;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 0.5rem;
                border-left: 4px solid #dc3545;
            }
            .video-item.completed {
                border-left-color: #28a745;
            }
            .video-item.failed {
                border-left-color: #FE0100;
            }
            .video-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .video-title {
                font-size: 1.2em;
                font-weight: 600;
                color: #000000;
            }
            .badge {
                padding: 5px 12px;
                border-radius: 15px;
                font-size: 0.85em;
                font-weight: 600;
            }
            .badge-completed {
                background: #d4edda;
                color: #155724;
            }
            .badge-failed {
                background: #FE0100;
                color: white;
            }
            .badge-in-progress {
                background: #808080;
                color: white;
            }
            .badge-not-started {
                background: #d1ecf1;
                color: #0c5460;
            }
            .quiz-results {
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #e0e0e0;
            }
            .quiz-question {
                background: white;
                padding: 15px;
                margin-bottom: 10px;
                border-radius: 0.5rem;
                border-left: 3px solid #007bff;
            }
            .quiz-question.correct {
                border-left-color: #28a745;
            }
            .quiz-question.incorrect {
                border-left-color: #FE0100;
            }
            .question-text {
                font-weight: 600;
                margin-bottom: 8px;
            }
            .answer-item {
                padding: 8px;
                margin: 5px 0;
                border-radius: 0.5rem;
            }
            .answer-item.selected {
                background: #e7f3ff;
            }
            .answer-item.correct {
                background: #d4edda;
            }
            .answer-item.incorrect {
                background: #f8d7da;
            }
            .document-item {
                background: #f8f9fa;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 0.5rem;
                border-left: 4px solid #007bff;
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
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #e0e0e0;
            }
            th {
                background: #f8f9fa;
                font-weight: 600;
                color: #000000;
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
                .user-header {
                    padding: 20px;
                }
                .user-header h1 {
                    font-size: 1.8em;
                }
                .user-info-table {
                    font-size: 0.9em;
                }
                .user-info-table td {
                    padding: 10px;
                }
                .user-info-table input,
                .user-info-table select {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
                }
                .section {
                    padding: 20px;
                }
                .section-title {
                    font-size: 1.3em;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
                    font-size: 1em;
                    width: 100%;
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
                .user-header {
                    padding: 15px;
                }
                .user-header h1 {
                    font-size: 1.5em;
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="user-header">
                <h1>{{ new_hire.first_name }} {{ new_hire.last_name }}</h1>
                <form id="newHireForm" method="POST" action="{{ url_for('update_new_hire_details', username=username) }}">
                    <table class="user-info-table">
                        <tr>
                            <td>Username</td>
                            <td><div class="info-value">{{ new_hire.username }}</div></td>
                        </tr>
                        <tr>
                            <td>Email</td>
                            <td><input type="email" name="email" value="{{ new_hire.email or '' }}" placeholder="Not set"></td>
                        </tr>
                        <tr>
                            <td>Department</td>
                            <td><input type="text" name="department" value="{{ new_hire.department or '' }}" placeholder="Not set"></td>
                        </tr>
                        <tr>
                            <td>Position</td>
                            <td><input type="text" name="position" value="{{ new_hire.position or '' }}" placeholder="Not set"></td>
                        </tr>
                        <tr>
                            <td>Start Date</td>
                            <td><input type="date" name="start_date" value="{{ new_hire.start_date.strftime('%Y-%m-%d') if new_hire.start_date else '' }}"></td>
                        </tr>
                        <tr>
                            <td>Status</td>
                            <td>
                                <select name="status">
                                    <option value="pending" {% if new_hire.status == 'pending' %}selected{% endif %}>Pending</option>
                                    <option value="active" {% if new_hire.status == 'active' %}selected{% endif %}>Active</option>
                                    <option value="completed" {% if new_hire.status == 'completed' %}selected{% endif %}>Completed</option>
                                    <option value="removed" {% if new_hire.status == 'removed' %}selected{% endif %}>Removed</option>
                                </select>
                            </td>
                        </tr>
                    </table>
                    <div style="margin-top: 25px; text-align: center;">
                        <button type="submit" class="btn" style="background: rgba(255,255,255,0.2); border: 2px solid white; font-size: 1.1em; padding: 12px 30px;">💾 Save Changes</button>
                        {% if new_hire.status != 'removed' %}
                        {% if user_record and user_record.role != 'admin' %}
                        {% if user_is_revoked %}
                        <form method="POST" action="{{ url_for('new_hire_restore_access', username=username) }}" style="display: inline;" onsubmit="return confirm('Restore access for {{ username }}? They will be able to log in again.');">
                            <button type="submit" class="btn" style="background: #28a745; border: 2px solid rgba(255,255,255,0.5); font-size: 0.95em; padding: 10px 20px; margin-left: 10px;">Restore access</button>
                        </form>
                        {% else %}
                        <form method="POST" action="{{ url_for('new_hire_cancel_access', username=username) }}" style="display: inline;" onsubmit="return confirm('Cancel access for {{ username }}? They will no longer be able to log in. You can restore access later from here or Manage Users.');">
                            <button type="submit" class="btn" style="background: #dc3545; border: 2px solid rgba(255,255,255,0.5); font-size: 0.95em; padding: 10px 20px; margin-left: 10px;">Cancel access</button>
                        </form>
                        {% endif %}
                        {% endif %}
                        <a href="{{ url_for('remove_new_hire_user', username=username) }}" class="btn" style="background: #333; border: 2px solid rgba(255,255,255,0.5); font-size: 0.95em; padding: 10px 20px; margin-left: 10px;">Remove user</a>
                        {% endif %}
                    </div>
                </form>
            </div>
            
            <div class="section">
                <h2 class="section-title">Training Video Progress & Quiz Results</h2>
                {% if video_progress %}
                    {% for item in video_progress %}
                    <div class="video-item {% if item.progress and item.progress.is_completed and item.progress.is_passed %}completed{% elif item.progress and item.progress.is_completed and not item.progress.is_passed %}failed{% elif item.progress %}in-progress{% else %}not-started{% endif %}">
                        <div class="video-header">
                            <div class="video-title">{{ item.video.title }}</div>
                            <div>
                                {% if item.progress %}
                                    {% if item.progress.is_completed and item.progress.is_passed %}
                                        <span class="badge badge-completed">✓ Passed ({{ "%.0f"|format(item.progress.score or 0) }}%)</span>
                                    {% elif item.progress.is_completed and not item.progress.is_passed %}
                                        <span class="badge badge-failed">✗ Failed ({{ "%.0f"|format(item.progress.score or 0) }}%)</span>
                                    {% else %}
                                        <span class="badge badge-in-progress">In Progress</span>
                                    {% endif %}
                                {% else %}
                                    <span class="badge badge-not-started">Not Started</span>
                                {% endif %}
                            </div>
                        </div>
                        {% if item.progress %}
                            <div style="color: #666; margin-bottom: 10px;">
                                <p><strong>Score:</strong> {{ "%.0f"|format(item.progress.score or 0) }}%</p>
                                <p><strong>Time Watched:</strong> {{ "%.0f"|format(item.progress.time_watched or 0) }} seconds</p>
                                <p><strong>Completed:</strong> {{ item.progress.completed_at.strftime('%B %d, %Y at %I:%M %p') if item.progress.completed_at else 'Not completed' }}</p>
                                <p><strong>Attempt:</strong> #{{ item.progress.attempt_number }}</p>
                            </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color: #666;">No training videos assigned.</p>
                {% endif %}
            </div>
            
            <div class="section">
                <h2 class="section-title">Signed Documents</h2>
                {% if signed_documents %}
                    {% for doc_data in signed_documents %}
                    <div class="document-item">
                        <h3 style="margin-bottom: 10px;">{{ doc_data.document.name_for_users }}</h3>
                        <p style="color: #666; margin-bottom: 10px;">Signed {{ doc_data.signatures|length }} field(s)</p>
                        {% if doc_data.signatures %}
                        <div class="signature-preview">
                            {% for sig in doc_data.signatures %}
                            {% if sig.signature_image %}
                            <img src="data:image/png;base64,{{ sig.signature_image }}" alt="Signature">
                            {% endif %}
                            {% endfor %}
                        </div>
                        <p style="color: #666; font-size: 0.9em; margin-top: 10px;">
                            Signed on: {{ doc_data.signatures[0].signed_at.strftime('%B %d, %Y at %I:%M %p') if doc_data.signatures and doc_data.signatures[0] and doc_data.signatures[0].signed_at else 'Unknown date' }}
                        </p>
                        {% endif %}
                        <a href="{{ url_for('download_signed_document', doc_id=doc_data.document.id, username=username) }}" class="btn" style="margin-top: 10px;">📥 Download Signed Copy</a>
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color: #666;">No documents signed yet.</p>
                {% endif %}
            </div>
            
            <div class="section">
                <h2 class="section-title">Assigned Tasks</h2>
                {% if user_tasks %}
                    <table>
                        <thead>
                            <tr>
                                <th>Task</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Assigned Date</th>
                                <th>Due Date</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for task in user_tasks %}
                            <tr>
                                <td><strong>{{ task.task_title }}</strong></td>
                                <td>{{ task.task_type or 'General' }}</td>
                                <td>
                                    <span class="badge badge-{{ task.status.replace('_', '-') }}">
                                        {{ task.status.replace('_', ' ').title() }}
                                    </span>
                                </td>
                                <td>{{ task.assigned_at.strftime('%B %d, %Y') if task.assigned_at else '-' }}</td>
                                <td>{{ task.due_date.strftime('%B %d, %Y') if task.due_date else '-' }}</td>
                                <td>
                                    <form method="POST" action="{{ url_for('remove_user_task', task_id=task.id) }}" style="display: inline;" onsubmit="return confirm('Remove this task for {{ username }}? They will no longer see it in their Tasks list.');">
                                        <button type="submit" class="btn" style="padding: 6px 12px; font-size: 0.85em; background: #dc3545; color: white; border: none; border-radius: 0.35rem;">Remove</button>
                                    </form>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <p style="color: #666;">No tasks assigned.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', new_hire=new_hire, video_progress=video_progress, signed_documents=signed_documents, 
         user_tasks=user_tasks, username=username, user_record=user_record, user_is_revoked=user_is_revoked)
    except Exception as e:
        # Log the error for debugging
        import traceback
        app.logger.error(f'Error in view_new_hire_details for {username}: {str(e)}')
        app.logger.error(traceback.format_exc())
        flash(f'Error loading new hire details: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))


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
        flash(f'Could not remove task: {str(e)}', 'error')
    return redirect(url_for('view_new_hire_details', username=username))


@app.route('/admin/new-hire/<username>/update', methods=['POST'])
@admin_required
def update_new_hire_details(username):
    """Update new hire details"""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('New hire not found.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Update email
        email = request.form.get('email', '').strip()
        if email:
            new_hire.email = email
        
        # Update department
        department = request.form.get('department', '').strip()
        if department:
            new_hire.department = department
        else:
            new_hire.department = None
        
        # Update position
        position = request.form.get('position', '').strip()
        if position:
            new_hire.position = position
        else:
            new_hire.position = None
        
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
        if status in ['pending', 'active', 'completed', 'removed']:
            new_hire.status = status
        
        db.session.commit()
        flash('New hire details updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating new hire details: {str(e)}', 'error')
    
    return redirect(url_for('view_new_hire_details', username=username))


@app.route('/admin/new-hire/<username>/cancel-access', methods=['POST'])
@admin_required
def new_hire_cancel_access(username):
    """Cancel (revoke) access for this new hire so they can no longer log in. Reversible via Restore access."""
    user = UserModel.query.filter_by(username=username).first()
    if not user:
        flash('No login account found for this user.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))
    if getattr(user, 'role', None) == 'admin':
        flash('Cannot cancel access for an admin.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))
    if user.username == current_user.username:
        flash('You cannot revoke your own access.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))
    from datetime import date
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
                flash(f'Error: {str(e)}', 'error')
        else:
            flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('view_new_hire_details', username=username))


@app.route('/admin/new-hire/<username>/restore-access', methods=['POST'])
@admin_required
def new_hire_restore_access(username):
    """Restore access for this new hire so they can log in again."""
    user = UserModel.query.filter_by(username=username).first()
    if not user:
        flash('No login account found for this user.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))
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
                flash(f'Error: {str(e)}', 'error')
        else:
            flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('view_new_hire_details', username=username))


@app.route('/admin/new-hire/<username>/remove-user', methods=['GET', 'POST'])
@admin_required
def remove_new_hire_user(username):
    """GET: show confirmation. POST: remove new hire's user account (e.g. withdrew or did not complete onboarding)."""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('New hire not found.', 'error')
        return redirect(url_for('view_all_new_hires'))
    if new_hire.status == 'removed':
        flash('This user has already been removed.', 'info')
        return redirect(url_for('view_all_new_hires'))
    user_record = UserModel.query.filter_by(username=username).first()
    if user_record and getattr(user_record, 'role', None) == 'admin':
        flash('Cannot remove an admin user.', 'error')
        return redirect(url_for('view_new_hire_details', username=username))

    if request.method == 'POST':
        try:
            if user_record:
                db.session.delete(user_record)
            new_hire.status = 'removed'
            db.session.commit()
            flash(f'User removed. {new_hire.first_name} {new_hire.last_name} can no longer log in and has been removed from the active list.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error removing user: {str(e)}', 'error')
        return redirect(url_for('view_all_new_hires'))

    # GET: show confirmation page
    no_account_msg = 'No login account exists for this new hire. You may still mark their record as removed.' if not user_record else ''
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Confirm User Removal - {{ new_hire.first_name }} {{ new_hire.last_name }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'URW Form', Arial, sans-serif; }
            body { background: #fff; color: #000; padding: 20px; }
            .top-header { background: #000; padding: 12px 30px; display: flex; justify-content: space-between; align-items: center; margin: -20px -20px 20px -20px; }
            .logo-section { color: #fff; font-weight: 800; }
            .back-btn { background: rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; border-radius: 0.5rem; text-decoration: none; border: 1px solid rgba(255,255,255,0.3); }
            .back-btn:hover { background: rgba(255,255,255,0.3); color: #fff; }
            .container { max-width: 600px; margin: 0 auto; }
            .card { background: #f8f9fa; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #e0e0e0; }
            .card h2 { margin-bottom: 12px; color: #000; }
            .card p { color: #333; margin-bottom: 16px; }
            .btn { display: inline-block; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: 600; border: none; cursor: pointer; font-size: 1em; }
            .btn-danger { background: #FE0100; color: white; }
            .btn-danger:hover { background: #c00; color: white; }
            .btn-secondary { background: #6c757d; color: white; }
            .btn-secondary:hover { background: #5a6268; color: white; }
            .actions { display: flex; gap: 12px; margin-top: 20px; }
            form { display: inline; }
            .info-msg { color: #0c5460; background: #d1ecf1; padding: 10px; border-radius: 0.5rem; margin-bottom: 16px; }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">Confirm User Removal</div>
            <a href="{{ url_for('view_new_hire_details', username=username) }}" class="back-btn">← Cancel</a>
        </div>
        <div class="container">
            <div class="card">
                <h2>Confirm removal: {{ new_hire.first_name }} {{ new_hire.last_name }}</h2>
                {% if no_account_msg %}<p class="info-msg">{{ no_account_msg }}</p>{% endif %}
                <p>This will revoke their login access so they can no longer sign in. Use this when a new hire withdraws or does not complete onboarding.</p>
                <p><strong>Username:</strong> {{ new_hire.username }}</p>
                <p>Their new hire record will be retained and marked as removed so they no longer appear in the active list.</p>
                <div class="actions">
                    <form method="post" action="{{ url_for('remove_new_hire_user', username=username) }}" onsubmit="return confirm('Confirm removal? This user will no longer be able to sign in.');">
                        <button type="submit" class="btn btn-danger">Remove user</button>
                    </form>
                    <a href="{{ url_for('view_new_hire_details', username=username) }}" class="btn btn-secondary">Cancel</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', new_hire=new_hire, username=username, no_account_msg=no_account_msg)


@app.route('/admin/checklist')
@admin_required
def manage_checklist():
    """Manage new hire checklist items"""
    checklist_items = ChecklistItem.query.order_by(ChecklistItem.order, ChecklistItem.id).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Checklist - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
            .btn-primary {
                background: #007bff;
            }
            .btn-danger {
                background: #FE0100;
            }
            .btn-small {
                padding: 5px 10px;
                font-size: 0.85em;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group input,
            .form-group textarea,
            .form-group select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 14px;
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .form-row {
                display: grid;
                grid-template-columns: 2fr 1fr 100px;
                gap: 15px;
            }
            .checklist-items {
                margin-top: 20px;
            }
            .checklist-item {
                background: #f8f9fa;
                padding: 15px;
                margin-bottom: 10px;
                border-radius: 5px;
                border-left: 4px solid #007bff;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .item-info {
                flex: 1;
            }
            .item-info h3 {
                margin-bottom: 5px;
                color: #000000;
            }
            .item-info p {
                color: #808080;
                font-size: 0.9em;
                margin: 5px 0;
            }
            .item-meta {
                display: flex;
                gap: 15px;
                align-items: center;
                color: #808080;
                font-size: 0.9em;
            }
            .item-actions {
                display: flex;
                gap: 5px;
            }
            .order-controls {
                display: flex;
                flex-direction: column;
                gap: 5px;
                margin-right: 15px;
            }
            .order-btn {
                background: #6c757d;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 0.8em;
            }
            .order-btn:hover {
                background: #5a6268;
            }
            .badge {
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                background: #6c757d;
                color: white;
            }
            .badge-active {
                background: #28a745;
            }
            .badge-inactive {
                background: #6c757d;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>✅ Manage New Hire Checklist</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Add New Checklist Item</h2>
                <form method="POST" action="{{ url_for('add_checklist_item') }}">
                    <div class="form-group">
                        <label for="task_name">Task Name *</label>
                        <input type="text" name="task_name" id="task_name" required placeholder="e.g., Complete I-9 Form">
                    </div>
                    <div class="form-group">
                        <label for="description">Description</label>
                        <textarea name="description" id="description" placeholder="Optional description of the task..."></textarea>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="assigned_to">Assigned To</label>
                            <input type="text" name="assigned_to" id="assigned_to" placeholder="e.g., HR, IT, Manager, or username">
                        </div>
                        <div class="form-group">
                            <label for="order">Order</label>
                            <input type="number" name="order" id="order" value="0" min="0" placeholder="Display order">
                        </div>
                        <div class="form-group" style="display: flex; align-items: flex-end;">
                            <label style="display: flex; align-items: center; gap: 5px;">
                                <input type="checkbox" name="is_active" value="1" checked style="width: auto;">
                                Active
                            </label>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success">Add Checklist Item</button>
                </form>
            </div>
            
            <div class="admin-panel">
                <h2>Checklist Items ({{ checklist_items|length }} total)</h2>
                <div class="checklist-items">
                    {% if checklist_items %}
                        {% for item in checklist_items %}
                        <div class="checklist-item">
                            <div class="order-controls">
                                <form method="POST" action="{{ url_for('move_checklist_item') }}" style="display: inline;">
                                    <input type="hidden" name="item_id" value="{{ item.id }}">
                                    <input type="hidden" name="direction" value="up">
                                    <button type="submit" class="order-btn" {% if loop.first %}disabled{% endif %}>↑</button>
                                </form>
                                <form method="POST" action="{{ url_for('move_checklist_item') }}" style="display: inline;">
                                    <input type="hidden" name="item_id" value="{{ item.id }}">
                                    <input type="hidden" name="direction" value="down">
                                    <button type="submit" class="order-btn" {% if loop.last %}disabled{% endif %}>↓</button>
                                </form>
                            </div>
                            <div class="item-info">
                                <h3>{{ item.task_name }}</h3>
                                {% if item.description %}
                                <p>{{ item.description }}</p>
                                {% endif %}
                                <div class="item-meta">
                                    <span><strong>Assigned to:</strong> {{ item.assigned_to or 'Not assigned' }}</span>
                                    <span><strong>Order:</strong> {{ item.order }}</span>
                                    <span class="badge badge-{{ 'active' if item.is_active else 'inactive' }}">
                                        {{ 'Active' if item.is_active else 'Inactive' }}
                                    </span>
                                </div>
                            </div>
                            <div class="item-actions">
                                <a href="{{ url_for('edit_checklist_item', item_id=item.id) }}" class="btn btn-primary btn-small">Edit</a>
                                <form method="POST" action="{{ url_for('delete_checklist_item') }}" style="display: inline;">
                                    <input type="hidden" name="item_id" value="{{ item.id }}">
                                    <button type="submit" class="btn btn-danger btn-small" 
                                            onclick="return confirm('Delete this checklist item?')">
                                        Delete
                                    </button>
                                </form>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <p>No checklist items yet. Add one above to get started.</p>
                    {% endif %}
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', checklist_items=checklist_items)


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
        flash(f'Error adding checklist item: {str(e)}', 'error')
    
    return redirect(url_for('manage_checklist'))


@app.route('/admin/checklist/<int:item_id>/edit')
@admin_required
def edit_checklist_item(item_id):
    """Edit checklist item page"""
    item = ChecklistItem.query.get(item_id)
    
    if not item:
        flash('Checklist item not found.', 'error')
        return redirect(url_for('manage_checklist'))
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Checklist Item - Onboarding App</title>
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
                max-width: 800px;
                margin: 30px auto;
                padding: 0 20px;
            }
            .admin-panel {
                background: white;
                padding: 25px;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group input,
            .form-group textarea {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 14px;
            }
            .form-group textarea {
                min-height: 80px;
            }
            .form-row {
                display: grid;
                grid-template-columns: 2fr 1fr 100px;
                gap: 15px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>Edit Checklist Item</h1>
            </div>
            <a href="{{ url_for('manage_checklist') }}" class="back-btn">← Back to Checklist</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Edit Checklist Item</h2>
                <form method="POST" action="{{ url_for('update_checklist_item', item_id=item.id) }}">
                    <div class="form-group">
                        <label for="task_name">Task Name *</label>
                        <input type="text" name="task_name" id="task_name" value="{{ item.task_name }}" required>
                    </div>
                    <div class="form-group">
                        <label for="description">Description</label>
                        <textarea name="description" id="description">{{ item.description or '' }}</textarea>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="assigned_to">Assigned To</label>
                            <input type="text" name="assigned_to" id="assigned_to" value="{{ item.assigned_to or '' }}" placeholder="e.g., HR, IT, Manager">
                        </div>
                        <div class="form-group">
                            <label for="order">Order</label>
                            <input type="number" name="order" id="order" value="{{ item.order }}" min="0">
                        </div>
                        <div class="form-group" style="display: flex; align-items: flex-end;">
                            <label style="display: flex; align-items: center; gap: 5px;">
                                <input type="checkbox" name="is_active" value="1" {% if item.is_active %}checked{% endif %} style="width: auto;">
                                Active
                            </label>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success">Update Checklist Item</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    ''', item=item)


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
        flash(f'Error updating checklist item: {str(e)}', 'error')
    
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
        flash(f'Error deleting checklist item: {str(e)}', 'error')
    
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
        flash(f'Error updating order: {str(e)}', 'error')
    
    return redirect(url_for('manage_checklist'))


@app.route('/admin/view-checklist')
@admin_required
def view_checklist():
    """View checklist and check off completed tasks"""
    checklist_items = ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order, ChecklistItem.id).all()
    
    # Get completion status for each item (for now, we'll track globally or per admin)
    # For simplicity, we'll create a simple completion tracking
    completed_items = request.args.getlist('completed')  # Get completed items from query params
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>View Checklist - Onboarding App</title>
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
                max-width: 1000px;
                margin: 30px auto;
                padding: 0 20px;
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
            .checklist-view {
                margin-top: 20px;
            }
            .checklist-item {
                background: #f8f9fa;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 0.5rem;
                border-left: 4px solid #007bff;
                display: flex;
                align-items: flex-start;
                gap: 15px;
                transition: all 0.3s;
            }
            .checklist-item.completed {
                background: #d4edda;
                border-left-color: #28a745;
                opacity: 0.8;
            }
            .checkbox-container {
                margin-top: 5px;
            }
            .checkbox-container input[type="checkbox"] {
                width: 24px;
                height: 24px;
                cursor: pointer;
                accent-color: #28a745;
            }
            .item-content {
                flex: 1;
            }
            .item-content h3 {
                margin-bottom: 8px;
                color: #000000;
                font-size: 1.1em;
            }
            .item-content.completed h3 {
                text-decoration: line-through;
                color: #6c757d;
            }
            .item-meta {
                display: flex;
                gap: 20px;
                margin-top: 10px;
                color: #808080;
                font-size: 0.9em;
            }
            .badge {
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.85em;
                background: #6c757d;
                color: white;
            }
            .badge-assigned {
                background: #007bff;
            }
            .progress-bar {
                background: #e9ecef;
                height: 30px;
                border-radius: 15px;
                overflow: hidden;
                margin: 20px 0;
                position: relative;
            }
            .progress-fill {
                background: linear-gradient(90deg, #28a745 0%, #20c997 100%);
                height: 100%;
                transition: width 0.3s;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 0.9em;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 0.5rem;
                text-align: center;
            }
            .stat-card .number {
                font-size: 2em;
                font-weight: bold;
                color: #007bff;
            }
            .stat-card .label {
                color: #808080;
                font-size: 0.9em;
                margin-top: 5px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>✅ New Hire Checklist</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Onboarding Checklist</h2>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="number" id="totalTasks">{{ checklist_items|length }}</div>
                        <div class="label">Total Tasks</div>
                    </div>
                    <div class="stat-card">
                        <div class="number" id="completedTasks">0</div>
                        <div class="label">Completed</div>
                    </div>
                    <div class="stat-card">
                        <div class="number" id="remainingTasks">{{ checklist_items|length }}</div>
                        <div class="label">Remaining</div>
                    </div>
                </div>
                
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div class="progress-bar" style="flex: 1; min-width: 0;">
                        <div class="progress-fill" id="progressFill" style="width: 0%;"></div>
                    </div>
                    <span id="progressPct" style="font-size: 0.9em; font-weight: 600; flex-shrink: 0;">0%</span>
                </div>
                
                <div class="checklist-view">
                    {% if checklist_items %}
                        <form id="checklistForm" method="POST" action="{{ url_for('update_checklist_completion') }}">
                            {% for item in checklist_items %}
                            <div class="checklist-item" id="item-{{ item.id }}">
                                <div class="checkbox-container">
                                    <input type="checkbox" 
                                           name="completed_items" 
                                           value="{{ item.id }}" 
                                           id="check-{{ item.id }}"
                                           onchange="updateProgress()">
                                </div>
                                <div class="item-content" id="content-{{ item.id }}">
                                    <h3>{{ item.task_name }}</h3>
                                    {% if item.description %}
                                    <p style="color: #666; margin-top: 5px;">{{ item.description }}</p>
                                    {% endif %}
                                    <div class="item-meta">
                                        {% if item.assigned_to %}
                                        <span class="badge badge-assigned">Assigned to: {{ item.assigned_to }}</span>
                                        {% endif %}
                                        <span>Order: {{ item.order }}</span>
                                    </div>
                                </div>
                            </div>
                            {% endfor %}
                            <input type="hidden" name="form_submitted" value="1">
                            <button type="submit" class="btn btn-success" style="margin-top: 20px;">Save Checklist Status</button>
                        </form>
                    {% else %}
                        <p>No checklist items available. <a href="{{ url_for('manage_checklist') }}">Add some tasks</a> to get started.</p>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <script>
            // Load saved completion status from localStorage
            function loadSavedStatus() {
                var saved = localStorage.getItem('checklist_completed');
                if (saved) {
                    var completed = JSON.parse(saved);
                    completed.forEach(function(itemId) {
                        var checkbox = document.getElementById('check-' + itemId);
                        if (checkbox) {
                            checkbox.checked = true;
                            var item = document.getElementById('item-' + itemId);
                            var content = document.getElementById('content-' + itemId);
                            if (item && content) {
                                item.classList.add('completed');
                                content.classList.add('completed');
                            }
                        }
                    });
                }
                updateProgress();
            }
            
            // Update progress bar and stats
            function updateProgress() {
                var checkboxes = document.querySelectorAll('input[type="checkbox"][name="completed_items"]');
                var total = checkboxes.length;
                var completed = 0;
                var completedIds = [];
                
                checkboxes.forEach(function(checkbox) {
                    if (checkbox.checked) {
                        completed++;
                        completedIds.push(checkbox.value);
                        var itemId = checkbox.value;
                        var item = document.getElementById('item-' + itemId);
                        var content = document.getElementById('content-' + itemId);
                        if (item && content) {
                            item.classList.add('completed');
                            content.classList.add('completed');
                        }
                    } else {
                        var itemId = checkbox.value;
                        var item = document.getElementById('item-' + itemId);
                        var content = document.getElementById('content-' + itemId);
                        if (item && content) {
                            item.classList.remove('completed');
                            content.classList.remove('completed');
                        }
                    }
                });
                
                var percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
                document.getElementById('progressFill').style.width = percentage + '%';
                var pctEl = document.getElementById('progressPct');
                if (pctEl) pctEl.textContent = percentage + '%';
                document.getElementById('completedTasks').textContent = completed;
                document.getElementById('remainingTasks').textContent = total - completed;
                
                // Save to localStorage
                localStorage.setItem('checklist_completed', JSON.stringify(completedIds));
            }
            
            // Load saved status on page load
            window.onload = function() {
                loadSavedStatus();
            };
            
            // Handle form submission
            document.getElementById('checklistForm').addEventListener('submit', function(e) {
                e.preventDefault();
                var formData = new FormData(this);
                fetch(this.action, {
                    method: 'POST',
                    body: formData
                })
                .then(response => {
                    if (response.ok) {
                        alert('Checklist status saved successfully!');
                    } else {
                        alert('Error saving checklist status.');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error saving checklist status.');
                });
            });
        </script>
    </body>
    </html>
    ''', checklist_items=checklist_items)


@app.route('/admin/checklist/update-completion', methods=['POST'])
@admin_required
def update_checklist_completion():
    """Update checklist completion status"""
    completed_items = request.form.getlist('completed_items')
    
    # For now, we'll just acknowledge the save
    # In the future, this could be stored in the database per new hire
    flash(f'Checklist status saved. {len(completed_items)} items marked as completed.', 'success')
    
    return redirect(url_for('view_checklist'))


@app.route('/admin/user-checklists')
@admin_required
def view_user_checklists():
    """List all active users and allow admin to select one to view/update their checklist"""
    from datetime import date as _date
    today = _date.today()
    candidates = NewHire.query.filter(NewHire.status != 'removed').order_by(NewHire.first_name, NewHire.last_name).all()
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

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Checklists - Onboarding App</title>
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .user-list {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                gap: 15px;
            }
            .user-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 0.5rem;
                border: 2px solid transparent;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                color: inherit;
                display: block;
            }
            .user-card:hover {
                border-color: #dc3545;
                background: #fff;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            .user-card h3 {
                margin-bottom: 8px;
                color: #000000;
            }
            .user-card p {
                color: #808080;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="section">
                <h2 class="section-title">Select User to View/Update Checklist</h2>
                {% if all_new_hires %}
                    <div class="user-list">
                        {% for new_hire in all_new_hires %}
                        <a href="{{ url_for('view_user_checklist', username=new_hire.username) }}" class="user-card">
                            <h3>{{ new_hire.first_name }} {{ new_hire.last_name }}</h3>
                            <p>{{ new_hire.username }}</p>
                            {% if new_hire.department %}
                            <p style="margin-top: 5px; color: #999;">{{ new_hire.department }}</p>
                            {% endif %}
                        </a>
                        {% endfor %}
                    </div>
                {% else %}
                    <p style="color: #666;">No new hires found.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', all_new_hires=all_new_hires)


@app.route('/admin/user-checklists/<username>')
@admin_required
def view_user_checklist(username):
    """View and update checklist for a specific user"""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('User not found.', 'error')
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
    default_finale_message = ''
    default_finale_document_id = ''
    try:
        _ensure_admin_settings_table()
        r = db.session.execute(text("SELECT value FROM admin_settings WHERE key = 'default_finale_message'")).fetchone()
        if r is not None and r[0] is not None:
            default_finale_message = (str(r[0]) or '').strip()
        r = db.session.execute(text("SELECT value FROM admin_settings WHERE key = 'default_finale_document_id'")).fetchone()
        if r is not None and r[0] is not None:
            v = str(r[0]).strip()
            if v.isdigit():
                default_finale_document_id = v
    except Exception:
        db.session.rollback()
        pass

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ new_hire.first_name }} {{ new_hire.last_name }} - Checklist</title>
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
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn:hover {
                background: #FE0100;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-success:hover {
                background: #218838;
            }
            .container {
                max-width: 1000px;
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .user-header {
                background: #FE0100;
                color: white;
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 20px;
            }
            .user-header h1 {
                font-size: 2em;
                margin-bottom: 5px;
            }
            .checklist-item {
                background: #f8f9fa;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 0.5rem;
                border-left: 4px solid #007bff;
                display: flex;
                align-items: flex-start;
                gap: 15px;
                transition: all 0.3s;
            }
            .checklist-item.completed {
                background: #d4edda;
                border-left-color: #28a745;
            }
            .checkbox-container {
                margin-top: 5px;
            }
            .checkbox-container input[type="checkbox"] {
                width: 24px;
                height: 24px;
                cursor: pointer;
                accent-color: #28a745;
            }
            .item-content {
                flex: 1;
            }
            .item-content h3 {
                margin-bottom: 8px;
                color: #000000;
                font-size: 1.1em;
            }
            .item-content.completed h3 {
                text-decoration: line-through;
                color: #6c757d;
            }
            .item-meta {
                display: flex;
                gap: 20px;
                margin-top: 10px;
                color: #808080;
                font-size: 0.9em;
            }
            .progress-bar {
                background: #e9ecef;
                height: 30px;
                border-radius: 15px;
                overflow: hidden;
                margin: 20px 0;
                position: relative;
            }
            .progress-fill {
                background: linear-gradient(90deg, #28a745 0%, #20c997 100%);
                height: 100%;
                transition: width 0.3s;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 0.9em;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: rgba(255,255,255,0.2);
                padding: 15px;
                border-radius: 0.5rem;
                text-align: center;
            }
            .stat-card .number {
                font-size: 2em;
                font-weight: bold;
                color: white;
            }
            .stat-card .label {
                color: rgba(255,255,255,0.9);
                font-size: 0.9em;
                margin-top: 5px;
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('view_user_checklists') }}" class="back-btn">← Back to User List</a>
        </div>
        
        <div class="container">
            <div class="user-header">
                <h1>{{ new_hire.first_name }} {{ new_hire.last_name }}</h1>
                <p style="opacity: 0.9;">{{ new_hire.username }}</p>
            </div>
            
            <div class="section">
                <h2 class="section-title">Onboarding Checklist</h2>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="number" id="totalTasks">{{ checklist_items|length }}</div>
                        <div class="label">Total Tasks</div>
                    </div>
                    <div class="stat-card">
                        <div class="number" id="completedTasks">0</div>
                        <div class="label">Completed</div>
                    </div>
                    <div class="stat-card">
                        <div class="number" id="remainingTasks">{{ checklist_items|length }}</div>
                        <div class="label">Remaining</div>
                    </div>
                </div>
                
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div class="progress-bar" style="flex: 1; min-width: 0;">
                        <div class="progress-fill" id="progressFill" style="width: 0%;"></div>
                    </div>
                    <span id="progressPct" style="font-size: 0.9em; font-weight: 600; flex-shrink: 0;">0%</span>
                </div>
                
                <form id="checklistForm" method="POST" action="{{ url_for('update_user_checklist', username=username) }}">
                    {% if checklist_items %}
                        {% for item in checklist_items %}
                        {% set completion = user_completions.get(item.id) %}
                        <div class="checklist-item {% if completion and completion.is_completed %}completed{% endif %}" id="item-{{ item.id }}">
                            <div class="checkbox-container">
                                <input type="checkbox" 
                                       name="completed_items" 
                                       value="{{ item.id }}" 
                                       id="check-{{ item.id }}"
                                       {% if completion and completion.is_completed %}checked{% endif %}
                                       onchange="updateProgress()">
                            </div>
                            <div class="item-content {% if completion and completion.is_completed %}completed{% endif %}" id="content-{{ item.id }}">
                                <h3>{{ item.task_name }}</h3>
                                {% if item.description %}
                                <p style="color: #666; margin-top: 5px;">{{ item.description }}</p>
                                {% endif %}
                                <div class="item-meta">
                                    {% if item.assigned_to %}
                                    <span>Assigned to: {{ item.assigned_to }}</span>
                                    {% endif %}
                                    {% if completion and completion.completed_at %}
                                    <span>Completed: {{ completion.completed_at.strftime('%B %d, %Y') }}</span>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                        <button type="submit" class="btn btn-success" style="margin-top: 20px;">💾 Save Checklist Status</button>
                        <button type="button" class="btn" style="margin-top: 20px; margin-left: 10px; background: #17a2b8;" onclick="openFinaleModal()">📩 Send Finale Message</button>
                    {% else %}
                        <p style="color: #666;">No checklist items available. <a href="{{ url_for('manage_checklist') }}">Add some tasks</a> to get started.</p>
                        <button type="button" class="btn" style="margin-top: 20px; background: #17a2b8;" onclick="openFinaleModal()">📩 Send Finale Message</button>
                    {% endif %}
                </form>
            </div>
        </div>

        <div id="finaleModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000; align-items: center; justify-content: center;">
            <div style="background: #fff; border-radius: 12px; padding: 24px; max-width: 500px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.2);">
                <h3 style="margin-bottom: 16px;">Send Finale Message</h3>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 16px;">This message will appear in the center of the user's dashboard the next time they log in. You can optionally attach a document.</p>
                <form method="POST" action="{{ url_for('send_finale_message', username=username) }}">
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; font-weight: 600; margin-bottom: 6px;">Message</label>
                        <textarea name="finale_message" id="finaleMessageText" rows="4" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-family: inherit;" placeholder="e.g. Congratulations on completing onboarding! ..." required>{{ default_finale_message }}</textarea>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; font-weight: 600; margin-bottom: 6px;">Attach document (optional)</label>
                        <select name="finale_document_id" id="finaleDocumentSelect" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                            <option value="">— None —</option>
                            {% for doc in documents %}
                            <option value="{{ doc.id }}" {% if default_finale_document_id and doc.id == default_finale_document_id|int %}selected{% endif %}>{{ doc.name_for_users or doc.original_filename }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                            <input type="checkbox" name="save_as_default" value="1" style="width: 18px; height: 18px;">
                            <span>Save this message as default for future finale messages</span>
                        </label>
                    </div>
                    <div style="display: flex; gap: 10px; justify-content: flex-end;">
                        <button type="button" class="btn btn-secondary" style="background: #6c757d; color: white;" onclick="closeFinaleModal()">Cancel</button>
                        <button type="submit" class="btn btn-success">Send Message</button>
                    </div>
                </form>
            </div>
        </div>
        <script>
            function openFinaleModal() {
                document.getElementById('finaleModal').style.display = 'flex';
            }
            function closeFinaleModal() {
                document.getElementById('finaleModal').style.display = 'none';
            }
        </script>
        
        <script>
            function updateProgress() {
                var checkboxes = document.querySelectorAll('input[type="checkbox"][name="completed_items"]');
                var total = checkboxes.length;
                var completed = 0;
                
                checkboxes.forEach(function(checkbox) {
                    if (checkbox.checked) {
                        completed++;
                        var itemId = checkbox.value;
                        var item = document.getElementById('item-' + itemId);
                        var content = document.getElementById('content-' + itemId);
                        if (item && content) {
                            item.classList.add('completed');
                            content.classList.add('completed');
                        }
                    } else {
                        var itemId = checkbox.value;
                        var item = document.getElementById('item-' + itemId);
                        var content = document.getElementById('content-' + itemId);
                        if (item && content) {
                            item.classList.remove('completed');
                            content.classList.remove('completed');
                        }
                    }
                });
                
                var percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
                document.getElementById('progressFill').style.width = percentage + '%';
                var pctEl = document.getElementById('progressPct');
                if (pctEl) pctEl.textContent = percentage + '%';
                document.getElementById('completedTasks').textContent = completed;
                document.getElementById('remainingTasks').textContent = total - completed;
            }
            
            // Initialize progress on page load
            window.onload = function() {
                updateProgress();
            };
        </script>
    </body>
    </html>
    ''', new_hire=new_hire, checklist_items=checklist_items, user_completions=user_completions, username=username, documents=documents, default_finale_message=default_finale_message, default_finale_document_id=default_finale_document_id)


@app.route('/admin/user-checklists/<username>/send-finale', methods=['POST'])
@admin_required
def send_finale_message(username):
    """Save and send finale message to the new hire (shown on their dashboard)."""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('User not found.', 'error')
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
        flash(f'Error saving message: {str(e)}', 'error')
        return redirect(url_for('view_user_checklist', username=username))

    # Optionally save as default for future finale messages (after commit so message send is not rolled back)
    if request.form.get('save_as_default'):
        try:
            _ensure_admin_settings_table()
            doc_val = doc_id if doc_id and doc_id.isdigit() else ''
            for key, value in [('default_finale_message', message), ('default_finale_document_id', doc_val)]:
                existing = db.session.execute(text("SELECT key FROM admin_settings WHERE key = :k"), {"k": key}).fetchone()
                if existing:
                    db.session.execute(text("UPDATE admin_settings SET value = :v WHERE key = :k"), {"v": value, "k": key})
                else:
                    db.session.execute(text("INSERT INTO admin_settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value})
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Message was sent, but saving as default failed. You can set a default again next time.', 'warning')
    return redirect(url_for('view_user_checklist', username=username))


@app.route('/admin/user-checklists/<username>/update', methods=['POST'])
@admin_required
def update_user_checklist(username):
    """Update checklist completion status for a specific user"""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('User not found.', 'error')
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
        flash(f'Error updating checklist: {str(e)}', 'error')
    
    return redirect(url_for('view_user_checklist', username=username))


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
        flash(f'Error loading links: {str(e)}', 'error')
        links = []
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage External Links - Onboarding App</title>
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
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn:hover {
                background: #FE0100;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-success:hover {
                background: #218838;
            }
            .btn-danger {
                background: #FE0100;
            }
            .btn-danger:hover {
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #000000;
            }
            .form-group input,
            .form-group textarea {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 16px; /* Prevents zoom on iOS */
                font-family: inherit;
                min-height: 44px; /* Touch-friendly */
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
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
            .badge {
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.8em;
                font-weight: 600;
            }
            .badge-active {
                background: #d4edda;
                color: #155724;
            }
            .badge-inactive {
                background: #f8d7da;
                color: #842029;
            }
            .action-buttons {
                display: flex;
                gap: 8px;
            }
            .btn-small {
                padding: 6px 12px;
                font-size: 0.85em;
            }
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #999;
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
                .section {
                    padding: 20px;
                }
                .section-title {
                    font-size: 1.3em;
                }
                .form-row {
                    grid-template-columns: 1fr;
                    gap: 15px;
                }
                .form-group input,
                .form-group textarea {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
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
                .action-buttons {
                    flex-direction: column;
                    width: 100%;
                }
                .action-buttons .btn {
                    width: 100%;
                    margin: 5px 0;
                }
                .btn, .btn-success {
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="section">
                <h2 class="section-title">Add New External Link</h2>
                <form method="POST" action="{{ url_for('add_external_link') }}" enctype="multipart/form-data">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="title">Link Title *</label>
                            <input type="text" name="title" id="title" required placeholder="e.g., Company Portal">
                        </div>
                        <div class="form-group">
                            <label for="url">URL *</label>
                            <input type="url" name="url" id="url" required placeholder="https://example.com">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="icon">Icon (Emoji) - Use if no image</label>
                            <input type="text" name="icon" id="icon" placeholder="🔗" value="🔗" maxlength="2">
                        </div>
                        <div class="form-group">
                            <label for="order">Display Order</label>
                            <input type="number" name="order" id="order" value="0" min="0">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="image">Image (optional) - Recommended size: 100x100px</label>
                        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 10px;">
                            <input type="file" name="image" id="image" accept="image/*" style="flex: 1;">
                            <button type="button" onclick="openImageCropper()" class="btn" style="background: #007bff; white-space: nowrap;">Crop Image</button>
                        </div>
                        <small style="color: #666;">Allowed: JPG, PNG, GIF, SVG (Max 5MB). Upload an image, then click "Crop Image" to select a square area.</small>
                        <input type="hidden" name="cropped_image" id="cropped_image">
                        <div id="imagePreview" style="margin-top: 10px; display: none;">
                            <p style="font-weight: 600; margin-bottom: 5px;">Preview:</p>
                            <img id="previewImg" style="max-width: 200px; max-height: 200px; border: 1px solid #ddd; border-radius: 8px; padding: 5px;">
                        </div>
                    </div>
                    <!-- Image Cropper Modal -->
                    <div id="imageCropperModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 10000; align-items: center; justify-content: center;">
                        <div style="background: white; padding: 20px; border-radius: 12px; max-width: 90%; max-height: 90%; overflow: auto;">
                            <h3 style="margin-bottom: 15px;">Crop Image (Select Square Area)</h3>
                            <div style="position: relative; margin-bottom: 15px;">
                                <img id="cropImagePreview" style="max-width: 100%; max-height: 500px; display: block;">
                                <canvas id="cropCanvas" style="display: none;"></canvas>
                            </div>
                            <div style="display: flex; gap: 10px; justify-content: flex-end;">
                                <button type="button" onclick="cancelCrop()" class="btn" style="background: #6c757d;">Cancel</button>
                                <button type="button" onclick="applyCrop()" class="btn btn-success">Apply Crop</button>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="description">Description (optional)</label>
                        <textarea name="description" id="description" placeholder="Brief description of the link..."></textarea>
                    </div>
                    <button type="submit" class="btn btn-success">Add Link</button>
                </form>
            </div>
            
            <script>
                var cropper = null;
                var originalImage = null;
                var cropData = null;
                
                function handleImageSelect(event) {
                    var file = event.target.files[0];
                    if (!file) return;
                    
                    // Skip SVG files (they don't need cropping)
                    if (file.name.toLowerCase().endsWith('.svg')) {
                        document.getElementById('cropped_image').value = '';
                        return;
                    }
                    
                    var reader = new FileReader();
                    reader.onload = function(e) {
                        var img = document.getElementById('cropImagePreview');
                        img.src = e.target.result;
                        originalImage = e.target.result;
                        
                        // Show cropper modal
                        document.getElementById('imageCropperModal').style.display = 'flex';
                        
                        // Initialize simple crop interface
                        setTimeout(function() {
                            initCropInterface(img);
                        }, 100);
                    };
                    reader.readAsDataURL(file);
                }
                
                function initCropInterface(img) {
                    // Create a simple crop interface using canvas
                    var canvas = document.getElementById('cropCanvas');
                    var ctx = canvas.getContext('2d');
                    
                    // Set canvas size to match image
                    var imgElement = new Image();
                    imgElement.onload = function() {
                        var maxSize = 800;
                        var scale = Math.min(maxSize / imgElement.width, maxSize / imgElement.height, 1);
                        canvas.width = imgElement.width * scale;
                        canvas.height = imgElement.height * scale;
                        
                        ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
                        
                        // Draw crop overlay
                        drawCropOverlay();
                    };
                    imgElement.src = img.src;
                }
                
                var cropX = 0, cropY = 0, cropSize = 200;
                var isDragging = false;
                var dragStartX = 0, dragStartY = 0;
                var startCropX = 0, startCropY = 0;
                
                function drawCropOverlay() {
                    var canvas = document.getElementById('cropCanvas');
                    var ctx = canvas.getContext('2d');
                    var img = document.getElementById('cropImagePreview');
                    
                    // Redraw image
                    var imgElement = new Image();
                    imgElement.onload = function() {
                        var maxSize = 800;
                        var scale = Math.min(maxSize / imgElement.width, maxSize / imgElement.height, 1);
                        canvas.width = imgElement.width * scale;
                        canvas.height = imgElement.height * scale;
                        
                        ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
                        
                        // Initialize crop size to fit image
                        cropSize = Math.min(canvas.width, canvas.height) * 0.8;
                        cropX = (canvas.width - cropSize) / 2;
                        cropY = (canvas.height - cropSize) / 2;
                        
                        // Draw semi-transparent overlay
                        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
                        ctx.fillRect(0, 0, canvas.width, canvas.height);
                        
                        // Clear crop area
                        ctx.save();
                        ctx.globalCompositeOperation = 'destination-out';
                        ctx.fillRect(cropX, cropY, cropSize, cropSize);
                        ctx.restore();
                        
                        // Draw crop border
                        ctx.strokeStyle = '#fff';
                        ctx.lineWidth = 2;
                        ctx.strokeRect(cropX, cropY, cropSize, cropSize);
                        
                        // Draw corner handles
                        var handleSize = 10;
                        ctx.fillStyle = '#fff';
                        // Top-left
                        ctx.fillRect(cropX - handleSize/2, cropY - handleSize/2, handleSize, handleSize);
                        // Top-right
                        ctx.fillRect(cropX + cropSize - handleSize/2, cropY - handleSize/2, handleSize, handleSize);
                        // Bottom-left
                        ctx.fillRect(cropX - handleSize/2, cropY + cropSize - handleSize/2, handleSize, handleSize);
                        // Bottom-right
                        ctx.fillRect(cropX + cropSize - handleSize/2, cropY + cropSize - handleSize/2, handleSize, handleSize);
                        
                        // Show canvas instead of image
                        img.style.display = 'none';
                        canvas.style.display = 'block';
                        canvas.style.maxWidth = '100%';
                        canvas.style.maxHeight = '500px';
                        canvas.style.cursor = 'move';
                        
                        // Add mouse events
                        canvas.onmousedown = startDrag;
                        canvas.onmousemove = onDrag;
                        canvas.onmouseup = endDrag;
                        canvas.onmouseleave = endDrag;
                    };
                    imgElement.src = originalImage;
                }
                
                function startDrag(e) {
                    var canvas = document.getElementById('cropCanvas');
                    var rect = canvas.getBoundingClientRect();
                    var x = (e.clientX - rect.left) * (canvas.width / rect.width);
                    var y = (e.clientY - rect.top) * (canvas.height / rect.height);
                    
                    // Check if clicking on corner (resize) or inside (move)
                    var handleSize = 20;
                    var isCorner = (
                        (x >= cropX - handleSize && x <= cropX + handleSize && y >= cropY - handleSize && y <= cropY + handleSize) ||
                        (x >= cropX + cropSize - handleSize && x <= cropX + cropSize + handleSize && y >= cropY - handleSize && y <= cropY + handleSize) ||
                        (x >= cropX - handleSize && x <= cropX + handleSize && y >= cropY + cropSize - handleSize && y <= cropY + cropSize + handleSize) ||
                        (x >= cropX + cropSize - handleSize && x <= cropX + cropSize + handleSize && y >= cropY + cropSize - handleSize && y <= cropY + cropSize + handleSize)
                    );
                    
                    if (isCorner) {
                        // Resize mode
                        isDragging = 'resize';
                    } else if (x >= cropX && x <= cropX + cropSize && y >= cropY && y <= cropY + cropSize) {
                        // Move mode
                        isDragging = 'move';
                        dragStartX = x - cropX;
                        dragStartY = y - cropY;
                    }
                    
                    startCropX = cropX;
                    startCropY = cropY;
                }
                
                function onDrag(e) {
                    if (!isDragging) return;
                    
                    var canvas = document.getElementById('cropCanvas');
                    var rect = canvas.getBoundingClientRect();
                    var x = (e.clientX - rect.left) * (canvas.width / rect.width);
                    var y = (e.clientY - rect.top) * (canvas.height / rect.height);
                    
                    if (isDragging === 'move') {
                        cropX = Math.max(0, Math.min(canvas.width - cropSize, x - dragStartX));
                        cropY = Math.max(0, Math.min(canvas.height - cropSize, y - dragStartY));
                    } else if (isDragging === 'resize') {
                        var newSize = Math.max(50, Math.min(canvas.width, canvas.height, Math.abs(x - startCropX), Math.abs(y - startCropY)));
                        cropSize = newSize;
                        cropX = Math.max(0, Math.min(canvas.width - cropSize, startCropX));
                        cropY = Math.max(0, Math.min(canvas.height - cropSize, startCropY));
                    }
                    
                    drawCropOverlay();
                }
                
                function endDrag() {
                    isDragging = false;
                }
                
                function applyCrop() {
                    var canvas = document.getElementById('cropCanvas');
                    var img = document.getElementById('cropImagePreview');
                    
                    // Create a new canvas for the cropped image
                    var croppedCanvas = document.createElement('canvas');
                    croppedCanvas.width = 200; // Output size
                    croppedCanvas.height = 200;
                    var ctx = croppedCanvas.getContext('2d');
                    
                    // Load original image to get full resolution
                    var imgElement = new Image();
                    imgElement.onload = function() {
                        // Calculate scale factor
                        var scaleX = imgElement.width / canvas.width;
                        var scaleY = imgElement.height / canvas.height;
                        
                        // Calculate actual crop coordinates in original image
                        var srcX = cropX * scaleX;
                        var srcY = cropY * scaleY;
                        var srcSize = cropSize * Math.min(scaleX, scaleY);
                        
                        // Draw cropped and resized image
                        ctx.drawImage(imgElement, srcX, srcY, srcSize, srcSize, 0, 0, 200, 200);
                        
                        // Convert to base64
                        var croppedData = croppedCanvas.toDataURL('image/png');
                        document.getElementById('cropped_image').value = croppedData;
                        
                        // Update preview
                        img.src = croppedData;
                        img.style.display = 'block';
                        canvas.style.display = 'none';
                        
                        // Show preview in form
                        var previewDiv = document.getElementById('imagePreview');
                        var previewImg = document.getElementById('previewImg');
                        if (previewDiv && previewImg) {
                            previewImg.src = croppedData;
                            previewDiv.style.display = 'block';
                        }
                        
                        // Hide modal
                        document.getElementById('imageCropperModal').style.display = 'none';
                        
                        // Show success message
                        alert('Crop applied! Click "Add Link" to save.');
                    };
                    imgElement.src = originalImage;
                }
                
                function cancelCrop() {
                    document.getElementById('imageCropperModal').style.display = 'none';
                    document.getElementById('image').value = '';
                    document.getElementById('cropped_image').value = '';
                }
            </script>
            
            <div class="section">
                <h2 class="section-title">External Links ({{ links|length }} total)</h2>
                {% if links %}
                <table>
                    <thead>
                        <tr>
                            <th>Icon</th>
                            <th>Title</th>
                            <th>URL</th>
                            <th>Description</th>
                            <th>Order</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for link in links %}
                        <tr>
                            <td>
                                {% if link.image_filename %}
                                <img src="{{ url_for('serve_quick_link_image', filename=link.image_filename) }}" alt="{{ link.title }}" style="width: 50px; height: 50px; object-fit: contain; border-radius: 8px;">
                                {% else %}
                                <span style="font-size: 1.5em;">{{ link.icon or '🔗' }}</span>
                                {% endif %}
                            </td>
                            <td><strong>{{ link.title }}</strong></td>
                            <td><a href="{{ link.url }}" target="_blank" style="color: #007bff; text-decoration: none;">{{ link.url[:50] }}{% if link.url|length > 50 %}...{% endif %}</a></td>
                            <td>{{ link.description or '-' }}</td>
                            <td>{{ link.order }}</td>
                            <td>
                                <span class="badge badge-{{ 'active' if link.is_active else 'inactive' }}">
                                    {{ 'Active' if link.is_active else 'Inactive' }}
                                </span>
                            </td>
                            <td>
                                <div class="action-buttons">
                                    <a href="{{ url_for('edit_external_link', link_id=link.id) }}" class="btn btn-small" style="background: #007bff;">Edit</a>
                                    <form method="POST" action="{{ url_for('toggle_external_link', link_id=link.id) }}" style="display: inline;">
                                        <button type="submit" class="btn btn-small" style="background: {{ '#6c757d' if link.is_active else '#28a745' }};">
                                            {{ 'Deactivate' if link.is_active else 'Activate' }}
                                        </button>
                                    </form>
                                    <form method="POST" action="{{ url_for('delete_external_link', link_id=link.id) }}" style="display: inline;">
                                        <button type="submit" class="btn btn-small btn-danger" onclick="return confirm('Delete this link?')">Delete</button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div class="empty-state">
                    <p>No external links yet. Add one above to get started.</p>
                </div>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', links=links)


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
            traceback.print_exc()
            flash(f'Error processing cropped image: {str(e)}', 'error')
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
        flash(f'Error adding link: {str(e)}', 'error')
    
    return redirect(url_for('manage_external_links'))


@app.route('/admin/external-links/<int:link_id>/edit')
@admin_required
def edit_external_link(link_id):
    """Edit an external link"""
    link = ExternalLink.query.get(link_id)
    if not link:
        flash('Link not found.', 'error')
        return redirect(url_for('manage_external_links'))
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit External Link - Onboarding App</title>
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
                border: none;
                cursor: pointer;
                font-size: 14px;
            }
            .btn:hover {
                background: #FE0100;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-success:hover {
                background: #218838;
            }
            .container {
                max-width: 800px;
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #000000;
            }
            .form-group input,
            .form-group textarea {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 14px;
                font-family: inherit;
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('manage_external_links') }}" class="back-btn">← Back to Links</a>
        </div>
        
        <div class="container">
            <div class="section">
                <h2 class="section-title">Edit External Link</h2>
                <form method="POST" action="{{ url_for('update_external_link', link_id=link.id) }}" enctype="multipart/form-data">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="title">Link Title *</label>
                            <input type="text" name="title" id="title" value="{{ link.title }}" required>
                        </div>
                        <div class="form-group">
                            <label for="url">URL *</label>
                            <input type="url" name="url" id="url" value="{{ link.url }}" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="icon">Icon (Emoji) - Use if no image</label>
                            <input type="text" name="icon" id="icon" value="{{ link.icon or '🔗' }}" maxlength="2">
                        </div>
                        <div class="form-group">
                            <label for="order">Display Order</label>
                            <input type="number" name="order" id="order" value="{{ link.order }}" min="0">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Current Image:</label>
                        {% if link.image_filename %}
                        <div style="margin: 10px 0;">
                            <img id="currentImageDisplay" src="{{ url_for('serve_quick_link_image', filename=link.image_filename) }}" alt="{{ link.title }}" style="width: 80px; height: 80px; object-fit: contain; border-radius: 8px; border: 1px solid #ddd; padding: 5px;">
                            <div style="margin-top: 5px; display: flex; gap: 10px;">
                                <button type="button" onclick="cropExistingImage()" class="btn btn-small" style="background: #007bff;">Crop Image</button>
                                <button type="button" onclick="removeCurrentImage()" class="btn btn-small" style="background: #FE0100;">Remove Image</button>
                            </div>
                        </div>
                        {% else %}
                        <p style="color: #999; font-style: italic;">No image uploaded</p>
                        {% endif %}
                        <label for="image" style="margin-top: 10px; display: block;">Upload New Image (optional):</label>
                        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 10px;">
                            <input type="file" name="image" id="image" accept="image/*" style="flex: 1;">
                            <button type="button" onclick="openImageCropper()" class="btn" style="background: #007bff; white-space: nowrap;">Crop Image</button>
                        </div>
                        <small style="color: #666;">Allowed: JPG, PNG, GIF, SVG (Max 5MB). Upload an image, then click "Crop Image" to select a square area.</small>
                        <input type="hidden" name="cropped_image" id="cropped_image">
                        <div id="imagePreview" style="margin-top: 10px; display: none;">
                            <p style="font-weight: 600; margin-bottom: 5px;">Preview:</p>
                            <img id="previewImg" style="max-width: 200px; max-height: 200px; border: 1px solid #ddd; border-radius: 8px; padding: 5px;">
                        </div>
                    </div>
                    <!-- Image Cropper Modal -->
                    <div id="imageCropperModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 10000; align-items: center; justify-content: center;">
                        <div style="background: white; padding: 20px; border-radius: 12px; max-width: 90%; max-height: 90%; overflow: auto;">
                            <h3 style="margin-bottom: 15px;">Crop Image (Select Square Area)</h3>
                            <div style="position: relative; margin-bottom: 15px;">
                                <img id="cropImagePreview" style="max-width: 100%; max-height: 500px; display: block;">
                                <canvas id="cropCanvas" style="display: none;"></canvas>
                            </div>
                            <div style="display: flex; gap: 10px; justify-content: flex-end;">
                                <button type="button" onclick="cancelCrop()" class="btn" style="background: #6c757d;">Cancel</button>
                                <button type="button" onclick="applyCrop()" class="btn btn-success">Apply Crop</button>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="description">Description (optional)</label>
                        <textarea name="description" id="description">{{ link.description or '' }}</textarea>
                    </div>
                    <button type="submit" class="btn btn-success">Update Link</button>
                </form>
            </div>
        </div>
        
        <script>
            var cropper = null;
            var originalImage = null;
            var cropData = null;
            
            function openImageCropper() {
                var fileInput = document.getElementById('image');
                var file = fileInput.files[0];
                
                if (!file) {
                    alert('Please select an image file first.');
                    return;
                }
                
                // Skip SVG files (they don't need cropping)
                if (file.name.toLowerCase().endsWith('.svg')) {
                    alert('SVG files do not need cropping. They will be used as-is.');
                    document.getElementById('cropped_image').value = '';
                    return;
                }
                
                var reader = new FileReader();
                reader.onload = function(e) {
                    var img = document.getElementById('cropImagePreview');
                    img.src = e.target.result;
                    originalImage = e.target.result;
                    
                    // Show cropper modal
                    document.getElementById('imageCropperModal').style.display = 'flex';
                    
                    // Initialize simple crop interface
                    setTimeout(function() {
                        initCropInterface(img);
                    }, 100);
                };
                reader.readAsDataURL(file);
            }
            
            function removeCurrentImage() {
                if (confirm('Remove the current image? This cannot be undone.')) {
                    // Submit form with remove_image flag
                    var form = document.querySelector('form');
                    var removeInput = document.createElement('input');
                    removeInput.type = 'hidden';
                    removeInput.name = 'remove_image';
                    removeInput.value = '1';
                    form.appendChild(removeInput);
                    form.submit();
                }
            }
            
            function initCropInterface(img) {
                // Create a simple crop interface using canvas
                var canvas = document.getElementById('cropCanvas');
                var ctx = canvas.getContext('2d');
                
                // Set canvas size to match image
                var imgElement = new Image();
                imgElement.onload = function() {
                    var maxSize = 800;
                    var scale = Math.min(maxSize / imgElement.width, maxSize / imgElement.height, 1);
                    canvas.width = imgElement.width * scale;
                    canvas.height = imgElement.height * scale;
                    
                    ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
                    
                    // Draw crop overlay
                    drawCropOverlay();
                };
                imgElement.src = img.src;
            }
            
            var cropX = 0, cropY = 0, cropSize = 200;
            var isDragging = false;
            var dragStartX = 0, dragStartY = 0;
            var startCropX = 0, startCropY = 0;
            
            function drawCropOverlay() {
                var canvas = document.getElementById('cropCanvas');
                var ctx = canvas.getContext('2d');
                var img = document.getElementById('cropImagePreview');
                
                // Redraw image
                var imgElement = new Image();
                imgElement.onload = function() {
                    var maxSize = 800;
                    var scale = Math.min(maxSize / imgElement.width, maxSize / imgElement.height, 1);
                    canvas.width = imgElement.width * scale;
                    canvas.height = imgElement.height * scale;
                    
                    ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
                    
                    // Initialize crop size to fit image
                    cropSize = Math.min(canvas.width, canvas.height) * 0.8;
                    cropX = (canvas.width - cropSize) / 2;
                    cropY = (canvas.height - cropSize) / 2;
                    
                    // Draw semi-transparent overlay
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    
                    // Clear crop area
                    ctx.save();
                    ctx.globalCompositeOperation = 'destination-out';
                    ctx.fillRect(cropX, cropY, cropSize, cropSize);
                    ctx.restore();
                    
                    // Draw crop border
                    ctx.strokeStyle = '#fff';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(cropX, cropY, cropSize, cropSize);
                    
                    // Draw corner handles
                    var handleSize = 10;
                    ctx.fillStyle = '#fff';
                    // Top-left
                    ctx.fillRect(cropX - handleSize/2, cropY - handleSize/2, handleSize, handleSize);
                    // Top-right
                    ctx.fillRect(cropX + cropSize - handleSize/2, cropY - handleSize/2, handleSize, handleSize);
                    // Bottom-left
                    ctx.fillRect(cropX - handleSize/2, cropY + cropSize - handleSize/2, handleSize, handleSize);
                    // Bottom-right
                    ctx.fillRect(cropX + cropSize - handleSize/2, cropY + cropSize - handleSize/2, handleSize, handleSize);
                    
                    // Show canvas instead of image
                    img.style.display = 'none';
                    canvas.style.display = 'block';
                    canvas.style.maxWidth = '100%';
                    canvas.style.maxHeight = '500px';
                    canvas.style.cursor = 'move';
                    
                    // Add mouse events
                    canvas.onmousedown = startDrag;
                    canvas.onmousemove = onDrag;
                    canvas.onmouseup = endDrag;
                    canvas.onmouseleave = endDrag;
                };
                imgElement.src = originalImage;
            }
            
            function startDrag(e) {
                var canvas = document.getElementById('cropCanvas');
                var rect = canvas.getBoundingClientRect();
                var x = (e.clientX - rect.left) * (canvas.width / rect.width);
                var y = (e.clientY - rect.top) * (canvas.height / rect.height);
                
                // Check if clicking on corner (resize) or inside (move)
                var handleSize = 20;
                var isCorner = (
                    (x >= cropX - handleSize && x <= cropX + handleSize && y >= cropY - handleSize && y <= cropY + handleSize) ||
                    (x >= cropX + cropSize - handleSize && x <= cropX + cropSize + handleSize && y >= cropY - handleSize && y <= cropY + handleSize) ||
                    (x >= cropX - handleSize && x <= cropX + handleSize && y >= cropY + cropSize - handleSize && y <= cropY + cropSize + handleSize) ||
                    (x >= cropX + cropSize - handleSize && x <= cropX + cropSize + handleSize && y >= cropY + cropSize - handleSize && y <= cropY + cropSize + handleSize)
                );
                
                if (isCorner) {
                    // Resize mode
                    isDragging = 'resize';
                } else if (x >= cropX && x <= cropX + cropSize && y >= cropY && y <= cropY + cropSize) {
                    // Move mode
                    isDragging = 'move';
                    dragStartX = x - cropX;
                    dragStartY = y - cropY;
                }
                
                startCropX = cropX;
                startCropY = cropY;
            }
            
            function onDrag(e) {
                if (!isDragging) return;
                
                var canvas = document.getElementById('cropCanvas');
                var rect = canvas.getBoundingClientRect();
                var x = (e.clientX - rect.left) * (canvas.width / rect.width);
                var y = (e.clientY - rect.top) * (canvas.height / rect.height);
                
                if (isDragging === 'move') {
                    cropX = Math.max(0, Math.min(canvas.width - cropSize, x - dragStartX));
                    cropY = Math.max(0, Math.min(canvas.height - cropSize, y - dragStartY));
                } else if (isDragging === 'resize') {
                    var newSize = Math.max(50, Math.min(canvas.width, canvas.height, Math.abs(x - startCropX), Math.abs(y - startCropY)));
                    cropSize = newSize;
                    cropX = Math.max(0, Math.min(canvas.width - cropSize, startCropX));
                    cropY = Math.max(0, Math.min(canvas.height - cropSize, startCropY));
                }
                
                drawCropOverlay();
            }
            
            function endDrag() {
                isDragging = false;
            }
            
            function applyCrop() {
                var canvas = document.getElementById('cropCanvas');
                var img = document.getElementById('cropImagePreview');
                
                // Create a new canvas for the cropped image
                var croppedCanvas = document.createElement('canvas');
                croppedCanvas.width = 200; // Output size
                croppedCanvas.height = 200;
                var ctx = croppedCanvas.getContext('2d');
                
                // Load original image to get full resolution
                var imgElement = new Image();
                imgElement.onload = function() {
                    // Calculate scale factor
                    var scaleX = imgElement.width / canvas.width;
                    var scaleY = imgElement.height / canvas.height;
                    
                    // Calculate actual crop coordinates in original image
                    var srcX = cropX * scaleX;
                    var srcY = cropY * scaleY;
                    var srcSize = cropSize * Math.min(scaleX, scaleY);
                    
                    // Draw cropped and resized image
                    ctx.drawImage(imgElement, srcX, srcY, srcSize, srcSize, 0, 0, 200, 200);
                    
                    // Convert to base64
                    var croppedData = croppedCanvas.toDataURL('image/png');
                    document.getElementById('cropped_image').value = croppedData;
                    
                    // Clear the file input so it doesn't submit the original file
                    document.getElementById('image').value = '';
                    
                    // Update preview
                    img.src = croppedData;
                    img.style.display = 'block';
                    canvas.style.display = 'none';
                    
                    // Show preview in form
                    var previewDiv = document.getElementById('imagePreview');
                    var previewImg = document.getElementById('previewImg');
                    if (previewDiv && previewImg) {
                        previewImg.src = croppedData;
                        previewDiv.style.display = 'block';
                    }
                    
                    // Update current image display if it exists
                    var currentImg = document.getElementById('currentImageDisplay');
                    if (currentImg) {
                        currentImg.src = croppedData;
                    }
                    
                    // Hide modal
                    document.getElementById('imageCropperModal').style.display = 'none';
                    
                    // Show success message
                    alert('Crop applied! Click "Update Link" to save.');
                };
                imgElement.src = originalImage;
            }
            
            function cancelCrop() {
                document.getElementById('imageCropperModal').style.display = 'none';
                document.getElementById('image').value = '';
                document.getElementById('cropped_image').value = '';
            }
            
            function cropExistingImage() {
                // Get the current image URL
                var currentImg = document.getElementById('currentImageDisplay');
                if (!currentImg) {
                    alert('No current image found.');
                    return;
                }
                
                // Load the existing image
                var imgUrl = currentImg.src;
                originalImage = imgUrl;
                
                // Show cropper modal
                var img = document.getElementById('cropImagePreview');
                img.src = imgUrl;
                document.getElementById('imageCropperModal').style.display = 'flex';
                
                // Initialize simple crop interface
                setTimeout(function() {
                    initCropInterface(img);
                }, 100);
            }
            
            function removeCurrentImage() {
                if (confirm('Remove the current image? This cannot be undone.')) {
                    // Submit form with remove_image flag
                    var form = document.querySelector('form');
                    var removeInput = document.createElement('input');
                    removeInput.type = 'hidden';
                    removeInput.name = 'remove_image';
                    removeInput.value = '1';
                    form.appendChild(removeInput);
                    form.submit();
                }
            }
        </script>
    </body>
    </html>
    ''', link=link)


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
            traceback.print_exc()
            flash(f'Error processing cropped image: {str(e)}', 'error')
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
        flash(f'Error updating link: {str(e)}', 'error')
    
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
        flash(f'Error toggling link: {str(e)}', 'error')
    
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
        flash(f'Error deleting link: {str(e)}', 'error')
    
    return redirect(url_for('manage_external_links'))


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
        
        return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reports - Onboarding App</title>
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
                font-family: 'URW Form', Arial, sans-serif;
                margin-bottom: 20px;
                color: #000000;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
                background: white;
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
            .progress-bar {
                width: 120px;
                height: 22px;
                background: #e5e5e5;
                border-radius: 0.5rem;
                overflow: hidden;
                display: inline-block;
                vertical-align: middle;
            }
            .progress-fill {
                height: 100%;
                background: #28a745;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 0.75em;
                font-weight: 600;
                min-width: 0;
            }
            .progress-fill[style*="width: 0%"] {
                display: none;
            }
            .progress-fill.failed {
                background: #dc3545;
            }
            .progress-fill.in-progress {
                background: #ffc107;
            }
            .section-title {
                font-size: 1.4em;
                font-weight: 600;
                margin-bottom: 20px;
                color: #000000;
                border-bottom: 2px solid #dc3545;
                padding-bottom: 10px;
            }
            .status-badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.85em;
                font-weight: 600;
            }
            .status-badge.passed {
                background: #28a745;
                color: white;
            }
            .status-badge.failed {
                background: #dc3545;
                color: white;
            }
            .status-badge.in-progress {
                background: #ffc107;
                color: #000;
            }
            .status-badge.not-watched {
                background: #6c757d;
                color: white;
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="section">
                <h2 class="section-title">Summary Statistics</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>Value</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>Total New Hires</strong></td>
                            <td>{{ total_new_hires }}</td>
                            <td>Active onboarding records</td>
                        </tr>
                        <tr>
                            <td><strong>Training Videos</strong></td>
                            <td>{{ total_training_videos }}</td>
                            <td>Active training modules</td>
                        </tr>
                        <tr>
                            <td><strong>Documents</strong></td>
                            <td>{{ total_documents }}</td>
                            <td>{{ visible_documents }} visible to users</td>
                        </tr>
                        <tr>
                            <td><strong>Checklist Items</strong></td>
                            <td>{{ total_checklist_items }}</td>
                            <td>Active onboarding tasks</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">Training Completion Report</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Count</th>
                            <th>Percentage</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Completed & Passed</td>
                            <td>{{ completed_trainings }}</td>
                            <td>
                                {% if total_training_progress > 0 %}
                                {{ "%.1f"|format((completed_trainings / total_training_progress * 100)) }}%
                                {% else %}
                                0%
                                {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <td>Failed</td>
                            <td>{{ failed_trainings }}</td>
                            <td>
                                {% if total_training_progress > 0 %}
                                {{ "%.1f"|format((failed_trainings / total_training_progress * 100)) }}%
                                {% else %}
                                0%
                                {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <td>In Progress</td>
                            <td>{{ in_progress_trainings }}</td>
                            <td>
                                {% if total_training_progress > 0 %}
                                {{ "%.1f"|format((in_progress_trainings / total_training_progress * 100)) }}%
                                {% else %}
                                0%
                                {% endif %}
                            </td>
                        </tr>
                        <tr style="background: #f8f9fa; font-weight: 600;">
                            <td>Total Attempts</td>
                            <td>{{ total_training_progress }}</td>
                            <td>100%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">Document Signing Report</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>Count</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Visible Documents</td>
                            <td>{{ visible_documents }}</td>
                        </tr>
                        <tr>
                            <td>Documents with Signature Fields</td>
                            <td>{{ documents_with_signatures }}</td>
                        </tr>
                        <tr>
                            <td>Total Signatures Collected</td>
                            <td>{{ total_signatures }}</td>
                        </tr>
                        <tr>
                            <td>Unique Users Who Signed</td>
                            <td>{{ unique_signed_users }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">Checklist Completion Report</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>Count</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Active Checklist Items</td>
                            <td>{{ total_checklist_items }}</td>
                        </tr>
                        <tr>
                            <td>Total Checklist Completions</td>
                            <td>{{ total_checklist_completions }}</td>
                        </tr>
                        <tr>
                            <td>Average Completions per Item</td>
                            <td>
                                {% if total_checklist_items > 0 %}
                                {{ "%.1f"|format(total_checklist_completions / total_checklist_items) }}
                                {% else %}
                                0
                                {% endif %}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">User Progress Report</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Employee Name</th>
                            <th>Username</th>
                            <th>Department</th>
                            <th>Training Progress</th>
                            <th>Tasks Completed</th>
                            <th>Checklist Progress</th>
                            <th>Overall Completion</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for stats in user_progress_stats %}
                        <tr>
                            <td><strong>{{ stats.new_hire.first_name }} {{ stats.new_hire.last_name }}</strong></td>
                            <td>{{ stats.new_hire.username }}</td>
                            <td>{{ stats.new_hire.department or '-' }}</td>
                            <td>
                                {% if stats.training.total > 0 %}
                                {{ stats.training.completed }}/{{ stats.training.total }} 
                                ({{ "%.0f"|format((stats.training.completed / stats.training.total * 100)) }}%)
                                {% else %}
                                N/A
                                {% endif %}
                            </td>
                            <td>
                                {% if stats.tasks.total > 0 %}
                                {{ stats.tasks.completed }}/{{ stats.tasks.total }}
                                {% else %}
                                0/0
                                {% endif %}
                            </td>
                            <td>
                                {% if stats.checklist.total > 0 %}
                                {{ stats.checklist.completed }}/{{ stats.checklist.total }}
                                ({{ "%.0f"|format((stats.checklist.completed / stats.checklist.total * 100)) }}%)
                                {% else %}
                                N/A
                                {% endif %}
                            </td>
                            <td>
                                <div class="progress-bar" style="display: inline-block; vertical-align: middle;">
                                    {% if stats.overall_progress > 0 %}
                                    <div class="progress-fill" style="width: {{ stats.overall_progress }}%;"></div>
                                    {% else %}
                                    <div class="progress-fill" style="width: 0%;"></div>
                                    {% endif %}
                                </div>
                                <span style="font-size: 0.85em; color: #666; margin-left: 8px; vertical-align: middle;">{{ stats.overall_progress }}%</span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">Department Performance</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Department</th>
                            <th>Total Employees</th>
                            <th>Fully Completed</th>
                            <th>Completion Rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for dept, stats in department_stats.items() %}
                        <tr>
                            <td><strong>{{ dept }}</strong></td>
                            <td>{{ stats.count }}</td>
                            <td>{{ stats.completed }}</td>
                            <td>
                                <div class="progress-bar" style="display: inline-block; vertical-align: middle;">
                                    {% set completion_rate = (stats.completed / stats.count * 100) if stats.count > 0 else 0 %}
                                    {% if completion_rate > 0 %}
                                    <div class="progress-fill" style="width: {{ completion_rate }}%;"></div>
                                    {% else %}
                                    <div class="progress-fill" style="width: 0%;"></div>
                                    {% endif %}
                                </div>
                                <span style="font-size: 0.85em; color: #666; margin-left: 8px; vertical-align: middle;">{{ "%.0f"|format(completion_rate) }}%</span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2 class="section-title">Detailed Training Information</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Employee Name</th>
                            <th>Username</th>
                            <th>Training Video</th>
                            <th>Watched</th>
                            <th>Watch Progress</th>
                            <th>Time Watched</th>
                            <th>Video Duration</th>
                            <th>Score</th>
                            <th>Status</th>
                            <th>Attempts</th>
                            <th>Completed Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for detail in training_details %}
                        <tr>
                            <td><strong>{{ detail.user.first_name }} {{ detail.user.last_name }}</strong></td>
                            <td>{{ detail.user.username }}</td>
                            <td>{{ detail.video.title }}</td>
                            <td>
                                {% if detail.watched %}
                                    <span class="status-badge {% if detail.is_completed and detail.is_passed %}passed{% elif detail.is_completed and not detail.is_passed %}failed{% else %}in-progress{% endif %}">
                                        {% if detail.is_completed and detail.is_passed %}Yes ✓{% elif detail.is_completed and not detail.is_passed %}Yes ✗{% else %}In Progress{% endif %}
                                    </span>
                                {% else %}
                                    <span class="status-badge not-watched">No</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if detail.watched %}
                                    <div style="display: inline-flex; align-items: center; gap: 8px;">
                                        <div class="progress-bar" style="width: 100px;">
                                            <div class="progress-fill {% if detail.is_completed and not detail.is_passed %}failed{% elif not detail.is_completed %}in-progress{% endif %}" style="width: {{ detail.watch_percentage }}%;"></div>
                                        </div>
                                        <span style="font-size: 0.85em; color: #666;">{{ "%.0f"|format(detail.watch_percentage) }}%</span>
                                    </div>
                                {% else %}
                                    <span style="color: #999;">-</span>
                                {% endif %}
                            </td>
                            <td>{{ detail.time_watched }}</td>
                            <td>{{ detail.video_duration }}</td>
                            <td>
                                {% if detail.score is not none %}
                                    <strong>{{ "%.1f"|format(detail.score) }}%</strong>
                                {% else %}
                                    <span style="color: #999;">-</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if detail.watched %}
                                    {% if detail.is_completed and detail.is_passed %}
                                        <span class="status-badge passed">Passed</span>
                                    {% elif detail.is_completed and not detail.is_passed %}
                                        <span class="status-badge failed">Failed</span>
                                    {% else %}
                                        <span class="status-badge in-progress">In Progress</span>
                                    {% endif %}
                                {% else %}
                                    <span class="status-badge not-watched">Not Started</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if detail.attempt_number > 0 %}
                                    {{ detail.attempt_number }}
                                {% else %}
                                    <span style="color: #999;">-</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if detail.completed_at %}
                                    {{ detail.completed_at.strftime('%Y-%m-%d %H:%M') }}
                                {% else %}
                                    <span style="color: #999;">-</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    ''', total_new_hires=total_new_hires, total_users=total_users, total_documents=total_documents,
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
        flash(f'Error loading reports: {str(e)}. Some data may be missing.', 'error')
        
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


@app.route('/admin/training')
@admin_required
def manage_training():
    """Manage harassment training videos and quizzes"""
    videos = TrainingVideo.query.order_by(TrainingVideo.created_at.desc()).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Training Management - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
            .btn-primary {
                background: #007bff;
            }
            .btn-danger {
                background: #FE0100;
            }
            .btn-small {
                padding: 5px 10px;
                font-size: 0.85em;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group input,
            .form-group textarea,
            .form-group select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 14px;
            }
            .form-group textarea {
                min-height: 80px;
                resize: vertical;
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
            table {
                width: 100%;
                background: white;
                border-radius: 0.5rem;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-top: 20px;
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            th {
                background: #f8f9fa;
                font-weight: bold;
            }
            .badge {
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                background: #6c757d;
                color: white;
            }
            .badge-active {
                background: #28a745;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>🎓 Training Management</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Upload Training Video</h2>
                <form method="POST" action="{{ url_for('upload_training_video') }}" enctype="multipart/form-data">
                    <div class="form-group">
                        <label for="title">Video Title *</label>
                        <input type="text" name="title" id="title" required placeholder="e.g., Harassment Prevention Training 2024">
                    </div>
                    <div class="form-group">
                        <label for="description">Description</label>
                        <textarea name="description" id="description" placeholder="Video description..."></textarea>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="video_file">Video File *</label>
                            <input type="file" name="video_file" id="video_file" accept="video/*" required>
                            <small style="color: #666;">Allowed: MP4, WebM, OGG, MOV, AVI (Max 500MB)</small>
                        </div>
                        <div class="form-group">
                            <label for="passing_score">Passing Score (%)</label>
                            <input type="number" name="passing_score" id="passing_score" value="80" min="0" max="100">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success">Upload Video</button>
                </form>
            </div>
            
            <div class="admin-panel">
                <h2>Training Videos ({{ videos|length }} total)</h2>
                {% if videos %}
                <table>
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Description</th>
                            <th>Questions</th>
                            <th>Passing Score</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for video in videos %}
                        <tr>
                            <td><strong>{{ video.title }}</strong></td>
                            <td>{{ video.description[:50] if video.description else '-' }}...</td>
                            <td>{{ video.questions|length }} questions</td>
                            <td>{{ video.passing_score }}%</td>
                            <td>
                                <span class="badge badge-{{ 'active' if video.is_active else 'inactive' }}">
                                    {{ 'Active' if video.is_active else 'Inactive' }}
                                </span>
                            </td>
                            <td>
                                <a href="{{ url_for('manage_video_quiz', video_id=video.id) }}" class="btn btn-primary btn-small">Manage Quiz</a>
                                <a href="{{ url_for('view_training_video', video_id=video.id) }}" class="btn btn-primary btn-small">View/Test</a>
                                <form method="POST" action="{{ url_for('delete_training_video') }}" style="display: inline;">
                                    <input type="hidden" name="video_id" value="{{ video.id }}">
                                    <button type="submit" class="btn btn-danger btn-small" 
                                            onclick="return confirm('Delete this training video?')">
                                        Delete
                                    </button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p>No training videos uploaded yet.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', videos=videos)


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
    
    if not allowed_video_file(file.filename):
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
        flash(f'Error uploading video: {str(e)}', 'error')
    
    return redirect(url_for('manage_training'))


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
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Quiz - {{ video.title }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                margin: 5px;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-primary {
                background: #007bff;
            }
            .btn-danger {
                background: #FE0100;
            }
            .btn-small {
                padding: 5px 10px;
                font-size: 0.85em;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .form-group input,
            .form-group textarea,
            .form-group select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                font-size: 16px; /* Prevents zoom on iOS */
                min-height: 44px; /* Touch-friendly */
            }
            .form-group textarea {
                min-height: 80px;
            }
            .question-item {
                background: #f8f9fa;
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 5px;
                border-left: 4px solid #007bff;
            }
            .answer-item {
                background: white;
                padding: 10px;
                margin: 5px 0;
                border-radius: 3px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .answer-item.correct {
                border-left: 3px solid #28a745;
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
                .admin-panel h2 {
                    font-size: 1.3em;
                }
                .form-group input,
                .form-group textarea,
                .form-group select {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
                }
                .answer-input {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    margin-bottom: 10px;
                }
                .answer-input input[type="text"] {
                    font-size: 16px; /* Prevents zoom on iOS */
                    min-height: 44px;
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
                    font-size: 1em;
                }
                .btn-small {
                    min-height: 44px;
                    padding: 10px 15px;
                }
            }
            
            @media (max-width: 480px) {
                .header-content h1 {
                    font-size: 1em;
                }
                .admin-panel {
                    padding: 12px;
                }
                .admin-panel h2 {
                    font-size: 1.2em;
                }
                .question-item {
                    padding: 12px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>📝 Manage Quiz: {{ video.title }}</h1>
            </div>
            <a href="{{ url_for('manage_training') }}" class="back-btn">← Back to Training</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>Add Quiz Question</h2>
                <form method="POST" action="{{ url_for('add_quiz_question', video_id=video.id) }}">
                    <div class="form-group">
                        <label for="question_text">Question Text *</label>
                        <textarea name="question_text" id="question_text" required></textarea>
                    </div>
                    <div class="form-group">
                        <label for="question_type">Question Type *</label>
                        <select name="question_type" id="question_type" required onchange="toggleTimestamp()">
                            <option value="mid">Mid-Video (pauses at specific time)</option>
                            <option value="end">End of Video</option>
                        </select>
                    </div>
                    <div class="form-group" id="timestampGroup">
                        <label for="video_timestamp">Video Timestamp (seconds) *</label>
                        <input type="number" name="video_timestamp" id="video_timestamp" step="0.1" min="0" placeholder="e.g., 120.5">
                        <small>Video will pause at this time to show the question</small>
                    </div>
                    <div class="form-group">
                        <label>Answers (check the correct one) *</label>
                        <div id="answersContainer">
                            <div class="answer-input">
                                <input type="text" name="answer_text[]" placeholder="Answer option 1" required>
                                <input type="radio" name="correct_answer" value="0" required> Correct
                            </div>
                            <div class="answer-input">
                                <input type="text" name="answer_text[]" placeholder="Answer option 2" required>
                                <input type="radio" name="correct_answer" value="1"> Correct
                            </div>
                        </div>
                        <button type="button" onclick="addAnswerOption()" style="margin-top: 10px; padding: 5px 10px;">+ Add Answer Option</button>
                    </div>
                    <button type="submit" class="btn btn-success">Add Question</button>
                </form>
            </div>
            
            <div class="admin-panel">
                <h2>Mid-Video Questions ({{ mid_questions|length }})</h2>
                {% for question in mid_questions %}
                <div class="question-item">
                    <h3>{{ question.question_text }}</h3>
                    <p><strong>Timestamp:</strong> {{ "%.1f"|format(question.video_timestamp) }} seconds</p>
                    <div style="margin-top: 10px;">
                        <strong>Answers:</strong>
                        {% for answer in question.answers %}
                        <div class="answer-item {% if answer.is_correct %}correct{% endif %}">
                            {{ answer.answer_text }}
                            {% if answer.is_correct %}<span style="color: #28a745;">✓ Correct</span>{% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    <div style="margin-top: 10px;">
                        <a href="{{ url_for('delete_quiz_question', question_id=question.id) }}" class="btn btn-danger btn-small" 
                           onclick="return confirm('Delete this question?')">Delete</a>
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <div class="admin-panel">
                <h2>End of Video Questions ({{ end_questions|length }})</h2>
                {% for question in end_questions %}
                <div class="question-item">
                    <h3>{{ question.question_text }}</h3>
                    <div style="margin-top: 10px;">
                        <strong>Answers:</strong>
                        {% for answer in question.answers %}
                        <div class="answer-item {% if answer.is_correct %}correct{% endif %}">
                            {{ answer.answer_text }}
                            {% if answer.is_correct %}<span style="color: #28a745;">✓ Correct</span>{% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    <div style="margin-top: 10px;">
                        <a href="{{ url_for('delete_quiz_question', question_id=question.id) }}" class="btn btn-danger btn-small" 
                           onclick="return confirm('Delete this question?')">Delete</a>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <script>
            var answerCount = 2;
            
            function toggleTimestamp() {
                var type = document.getElementById('question_type').value;
                var timestampGroup = document.getElementById('timestampGroup');
                timestampGroup.style.display = type === 'mid' ? 'block' : 'none';
                if (type === 'mid') {
                    document.getElementById('video_timestamp').required = true;
                } else {
                    document.getElementById('video_timestamp').required = false;
                }
            }
            
            function addAnswerOption() {
                var container = document.getElementById('answersContainer');
                var div = document.createElement('div');
                div.className = 'answer-input';
                div.innerHTML = '<input type="text" name="answer_text[]" placeholder="Answer option ' + (answerCount + 1) + '" required> ' +
                               '<input type="radio" name="correct_answer" value="' + answerCount + '"> Correct';
                container.appendChild(div);
                answerCount++;
            }
        </script>
    </body>
    </html>
    ''', video=video, mid_questions=mid_questions, end_questions=end_questions)


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
        flash(f'Error adding question: {str(e)}', 'error')
    
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
        flash(f'Error deleting question: {str(e)}', 'error')
    
    return redirect(url_for('manage_video_quiz', video_id=video_id))


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
        # Delete file
        if os.path.exists(video.file_path):
            os.remove(video.file_path)
        
        # Delete questions and answers
        for question in video.questions:
            QuizAnswer.query.filter_by(question_id=question.id).delete()
        QuizQuestion.query.filter_by(video_id=video_id).delete()
        
        # Delete user progress
        UserTrainingProgress.query.filter_by(video_id=video_id).delete()
        
        # Delete video
        db.session.delete(video)
        db.session.commit()
        
        flash(f'Training video "{video.title}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting video: {str(e)}', 'error')
    
    return redirect(url_for('manage_training'))


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
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ video.title }} - Harassment Training</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #1a1a1a;
                color: white;
            }
            .header {
                background: #2a2a2a;
                padding: 15px;
                text-align: center;
            }
            .container {
                max-width: 1600px;
                margin: 20px auto;
                padding: 0 20px;
            }
            .video-container {
                background: #000;
                border-radius: 0.5rem;
                overflow: hidden;
                margin-bottom: 20px;
                position: relative;
            }
            video {
                width: 100%;
                max-height: 70vh;
                pointer-events: auto;
            }
            /* Hide timeline scrubber to prevent seeking */
            video::-webkit-media-controls-timeline {
                display: none !important;
            }
            video::-webkit-media-controls-current-time-display {
                pointer-events: none;
            }
            /* Hide playback rate controls */
            video::-webkit-media-controls-playback-rate-button {
                display: none !important;
            }
            video::-webkit-media-controls-playback-rate-value {
                display: none !important;
            }
            .quiz-overlay {
                display: none;
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.95);
                z-index: 1000;
                padding: 40px;
                overflow-y: auto;
            }
            .quiz-overlay.show {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            .quiz-content {
                background: white;
                color: #000000;
                padding: 30px;
                border-radius: 0.5rem;
                max-width: 800px;
                width: 100%;
            }
            .quiz-content h2 {
                margin-bottom: 20px;
                color: #FE0100;
            }
            .quiz-content .question {
                font-size: 1.2em;
                margin-bottom: 20px;
                font-weight: bold;
            }
            .answer-option {
                background: #f8f9fa;
                padding: 15px;
                margin: 10px 0;
                border-radius: 5px;
                cursor: pointer;
                border: 2px solid transparent;
                transition: all 0.3s;
            }
            .answer-option:hover {
                border-color: #007bff;
                background: #e9ecef;
            }
            .answer-option.selected {
                border-color: #007bff;
                background: #cfe2ff;
            }
            .btn {
                padding: 12px 24px;
                background: #FE0100;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 1em;
                margin-top: 20px;
            }
            .btn:hover {
                background: #FE0100;
            }
            .btn-success {
                background: #28a745;
            }
            .btn-success:hover {
                background: #218838;
            }
            .progress-info {
                background: #2a2a2a;
                padding: 15px;
                border-radius: 0.5rem;
                margin-bottom: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .score-display {
                text-align: center;
                padding: 40px;
            }
            .score-display h1 {
                font-size: 3em;
                margin: 20px 0;
            }
            .score-pass {
                color: #28a745;
            }
            .score-fail {
                color: #FE0100;
            }
            
            /* Mobile Responsive Styles */
            @media (max-width: 768px) {
                .header {
                    padding: 12px 15px;
                }
                .header h1 {
                    font-size: 1.2em;
                }
                .container {
                    padding: 15px;
                }
                .video-container {
                    margin-bottom: 15px;
                }
                video {
                    max-height: 50vh;
                }
                .progress-info {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 10px;
                    padding: 12px;
                }
                .quiz-overlay {
                    padding: 20px;
                }
                .quiz-content {
                    padding: 20px;
                }
                .quiz-content h2 {
                    font-size: 1.2em;
                }
                .quiz-content .question {
                    font-size: 1em;
                }
                .answer-option {
                    padding: 12px;
                    min-height: 44px; /* Touch-friendly */
                }
                .btn {
                    min-height: 44px;
                    padding: 12px 20px;
                    font-size: 1em;
                    width: 100%;
                }
                .score-display {
                    padding: 20px;
                }
                .score-display h1 {
                    font-size: 2em;
                }
            }
            
            @media (max-width: 480px) {
                .header h1 {
                    font-size: 1em;
                }
                .header p {
                    font-size: 0.9em;
                }
                video {
                    max-height: 40vh;
                }
                .quiz-content {
                    padding: 15px;
                }
                .quiz-content h2 {
                    font-size: 1em;
                }
                .answer-option {
                    padding: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ video.title }}</h1>
            {% if video.description %}
            <p>{{ video.description }}</p>
            {% endif %}
        </div>
        
        <div class="container">
            <div class="progress-info">
                <div>
                    <strong>Attempt:</strong> {{ progress.attempt_number }} / {{ video.max_attempts }}
                    <strong>Time Watched:</strong> <span id="timeWatched">0</span> seconds
                </div>
                <div>
                    <strong>Passing Score:</strong> {{ video.passing_score }}%
                </div>
            </div>
            
            <div class="video-container">
                <video id="trainingVideo" controls controlsList="nodownload noplaybackrate" disablePictureInPicture>
                    <source src="{{ url_for('serve_training_video', video_id=video.id) }}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                
                <div class="quiz-overlay" id="quizOverlay">
                    <div class="quiz-content" id="quizContent">
                        <!-- Quiz content will be inserted here -->
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            var video = document.getElementById('trainingVideo');
            var quizOverlay = document.getElementById('quizOverlay');
            var quizContent = document.getElementById('quizContent');
            var timeWatched = 0;
            var maxWatchedTime = {{ progress.time_watched or 0 }};
            var watchTimeInterval;
            var currentQuestion = null;
            var userAnswers = {};
            var midQuestions = {{ mid_questions|tojson }};
            var endQuestions = {{ end_questions|tojson }};
            var videoId = {{ video.id }};
            var progressId = {{ progress.id }};
            var passingScore = {{ video.passing_score }};
            var midQuestionIndex = 0;
            var isSeeking = false;
            
            // Disable right-click context menu
            video.addEventListener('contextmenu', function(e) {
                e.preventDefault();
                return false;
            });
            
            // Disable keyboard shortcuts for seeking
            video.addEventListener('keydown', function(e) {
                // Prevent arrow keys, space bar seeking, etc.
                if ([37, 38, 39, 40, 32].indexOf(e.keyCode) > -1) {
                    // Allow space for play/pause only
                    if (e.keyCode === 32) {
                        e.preventDefault();
                        if (video.paused) {
                            video.play();
                        } else {
                            video.pause();
                        }
                    } else {
                        e.preventDefault();
                        return false;
                    }
                }
            });
            
            // Prevent seeking by disabling the seek bar interaction
            video.addEventListener('seeking', function(e) {
                if (!isSeeking) {
                    // If user tries to seek ahead of max watched time, reset to max
                    if (video.currentTime > maxWatchedTime + 1) {
                        e.preventDefault();
                        video.currentTime = maxWatchedTime;
                        alert('You cannot skip ahead. Please watch the video from where you left off.');
                    }
                }
            });
            
            // Prevent seeking when user tries to click on progress bar
            video.addEventListener('seeked', function(e) {
                if (!isSeeking) {
                    // If user seeks ahead, reset to max watched time
                    if (video.currentTime > maxWatchedTime + 1) {
                        video.currentTime = maxWatchedTime;
                        alert('You cannot skip ahead. Please watch the video from where you left off.');
                    } else {
                        // Update max watched time if they seek backwards (allowed)
                        if (video.currentTime < maxWatchedTime) {
                            maxWatchedTime = video.currentTime;
                        }
                    }
                }
            });
            
            // Track watch time and prevent skipping
            video.addEventListener('timeupdate', function() {
                var currentTime = video.currentTime;
                
                // Prevent skipping ahead - if current time exceeds max watched by more than 1 second, reset
                if (currentTime > maxWatchedTime + 1 && !isSeeking) {
                    video.currentTime = maxWatchedTime;
                    alert('You cannot skip ahead. Please watch the video in order.');
                    return;
                }
                
                // Update max watched time only if playing forward naturally
                if (video.paused === false && currentTime > maxWatchedTime) {
                    maxWatchedTime = currentTime;
                    timeWatched = maxWatchedTime;
                    document.getElementById('timeWatched').textContent = Math.floor(timeWatched);
                }
            });
            
            // Track watch time
            video.addEventListener('play', function() {
                // Reset to max watched time if trying to play ahead
                if (video.currentTime > maxWatchedTime + 1) {
                    video.currentTime = maxWatchedTime;
                }
                
                watchTimeInterval = setInterval(function() {
                    timeWatched = video.currentTime;
                    document.getElementById('timeWatched').textContent = Math.floor(timeWatched);
                    // Update in database every 10 seconds
                    if (Math.floor(timeWatched) % 10 === 0) {
                        updateWatchTime();
                    }
                }, 1000);
            });
            
            video.addEventListener('pause', function() {
                if (watchTimeInterval) {
                    clearInterval(watchTimeInterval);
                }
                updateWatchTime();
            });
            
            // Set initial position to max watched time
            video.addEventListener('loadedmetadata', function() {
                video.currentTime = maxWatchedTime;
                // Disable playback rate changes
                video.playbackRate = 1.0;
            });
            
            // Prevent playback rate changes
            video.addEventListener('ratechange', function() {
                if (video.playbackRate !== 1.0) {
                    video.playbackRate = 1.0;
                    alert('Playback speed cannot be changed. Please watch at normal speed.');
                }
            });
            
            // Additional protection: monitor for any seeking attempts
            var lastValidTime = maxWatchedTime;
            setInterval(function() {
                if (!video.paused && video.currentTime > lastValidTime + 2) {
                    // If video jumped ahead more than 2 seconds, reset
                    video.currentTime = lastValidTime;
                    alert('You cannot skip ahead. Please watch the video in order.');
                } else if (video.currentTime <= lastValidTime + 2) {
                    // Update last valid time if playing forward normally
                    if (video.currentTime > lastValidTime) {
                        lastValidTime = video.currentTime;
                        maxWatchedTime = lastValidTime;
                    }
                }
            }, 500);
            
            // Check for mid-video questions (using separate listener)
            var questionCheckInterval = setInterval(function() {
                if (midQuestionIndex < midQuestions.length && !video.paused) {
                    var question = midQuestions[midQuestionIndex];
                    if (video.currentTime >= question.video_timestamp && !userAnswers['mid_' + question.id]) {
                        video.pause();
                        showQuestion(question, 'mid');
                    }
                }
            }, 500);
            
            // Check for end questions when video ends
            video.addEventListener('ended', function() {
                if (watchTimeInterval) {
                    clearInterval(watchTimeInterval);
                }
                updateWatchTime();
                if (endQuestions.length > 0 && !userAnswers['end_completed']) {
                    showEndQuiz();
                } else {
                    calculateScore();
                }
            });
            
            function showQuestion(question, type) {
                currentQuestion = question;
                var html = '<h2>Quiz Question</h2>';
                html += '<div class="question">' + question.question_text + '</div>';
                html += '<div id="answersContainer">';
                
                question.answers.forEach(function(answer, index) {
                    html += '<div class="answer-option" onclick="selectAnswer(' + answer.id + ', ' + index + ')">';
                    html += '<input type="radio" name="answer" value="' + answer.id + '" id="answer' + answer.id + '">';
                    html += '<label for="answer' + answer.id + '">' + answer.answer_text + '</label>';
                    html += '</div>';
                });
                
                html += '<button class="btn" onclick="submitAnswer()">Submit Answer</button>';
                quizContent.innerHTML = html;
                quizOverlay.classList.add('show');
            }
            
            function selectAnswer(answerId, index) {
                document.querySelectorAll('.answer-option').forEach(function(el) {
                    el.classList.remove('selected');
                });
                event.currentTarget.classList.add('selected');
                document.getElementById('answer' + answerId).checked = true;
            }
            
            function submitAnswer() {
                var selected = document.querySelector('input[name="answer"]:checked');
                if (!selected) {
                    alert('Please select an answer.');
                    return;
                }
                
                var answerId = parseInt(selected.value);
                var questionId = currentQuestion.id;
                
                // Find if answer is correct
                var isCorrect = currentQuestion.answers.find(function(a) {
                    return a.id === answerId && a.is_correct;
                });
                
                userAnswers[(currentQuestion.question_type === 'mid' ? 'mid_' : 'end_') + questionId] = {
                    answerId: answerId,
                    isCorrect: !!isCorrect
                };
                
                // Save to server
                saveAnswer(questionId, answerId, !!isCorrect);
                
                // Hide quiz overlay
                quizOverlay.classList.remove('show');
                
                if (currentQuestion.question_type === 'mid') {
                    midQuestionIndex++;
                    video.play();
                }
            }
            
            var endQuestionIndex = 0;
            
            function showEndQuiz() {
                if (endQuestions.length === 0) {
                    calculateScore();
                    return;
                }
                
                endQuestionIndex = 0;
                showNextEndQuestion();
            }
            
            function showNextEndQuestion() {
                if (endQuestionIndex >= endQuestions.length) {
                    userAnswers['end_completed'] = true;
                    calculateScore();
                    return;
                }
                
                var question = endQuestions[endQuestionIndex];
                currentQuestion = question;
                
                var html = '<h2>Final Quiz - Question ' + (endQuestionIndex + 1) + ' of ' + endQuestions.length + '</h2>';
                html += '<div class="question">' + question.question_text + '</div>';
                html += '<div id="answersContainer">';
                
                question.answers.forEach(function(answer, index) {
                    html += '<div class="answer-option" onclick="selectAnswer(' + answer.id + ', ' + index + ')">';
                    html += '<input type="radio" name="answer" value="' + answer.id + '" id="answer' + answer.id + '">';
                    html += '<label for="answer' + answer.id + '">' + answer.answer_text + '</label>';
                    html += '</div>';
                });
                
                html += '<button class="btn" onclick="submitEndAnswer()">Submit Answer</button>';
                quizContent.innerHTML = html;
                quizOverlay.classList.add('show');
            }
            
            function submitEndAnswer() {
                var selected = document.querySelector('input[name="answer"]:checked');
                if (!selected) {
                    alert('Please select an answer.');
                    return;
                }
                
                var answerId = parseInt(selected.value);
                var questionId = currentQuestion.id;
                
                var isCorrect = currentQuestion.answers.find(function(a) {
                    return a.id === answerId && a.is_correct;
                });
                
                userAnswers['end_' + questionId] = {
                    answerId: answerId,
                    isCorrect: !!isCorrect
                };
                
                saveAnswer(questionId, answerId, !!isCorrect);
                
                quizOverlay.classList.remove('show');
                
                // Move to next question
                endQuestionIndex++;
                setTimeout(function() {
                    showNextEndQuestion();
                }, 500);
            }
            
            function saveAnswer(questionId, answerId, isCorrect) {
                fetch("{{ url_for('save_quiz_answer') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        progress_id: progressId,
                        question_id: questionId,
                        answer_id: answerId,
                        is_correct: isCorrect
                    })
                });
            }
            
            function updateWatchTime() {
                fetch("{{ url_for('update_watch_time') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        progress_id: progressId,
                        time_watched: maxWatchedTime
                    })
                });
            }
            
            function calculateScore() {
                var totalQuestions = midQuestions.length + endQuestions.length;
                var correct = 0;
                
                Object.keys(userAnswers).forEach(function(key) {
                    if (key !== 'end_completed' && userAnswers[key].isCorrect) {
                        correct++;
                    }
                });
                
                var score = totalQuestions > 0 ? Math.round((correct / totalQuestions) * 100) : 0;
                var passed = score >= passingScore;
                
                // Save final score
                fetch("{{ url_for('save_training_score') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        progress_id: progressId,
                        score: score,
                        total_questions: totalQuestions,
                        correct_answers: correct,
                        is_passed: passed
                    })
                }).then(function() {
                    showScore(score, passed, totalQuestions, correct);
                });
            }
            
            function showScore(score, passed, total, correct) {
                var html = '<div class="score-display">';
                html += '<h1 class="' + (passed ? 'score-pass' : 'score-fail') + '">' + score + '%</h1>';
                html += '<h2>' + (passed ? 'Congratulations! You passed!' : 'You did not pass.') + '</h2>';
                html += '<p>You answered ' + correct + ' out of ' + total + ' questions correctly.</p>';
                
                if (!passed) {
                    html += '<p style="color: #dc3545; margin-top: 20px;">You need to score at least ' + passingScore + '% to pass.</p>';
                    html += '<p>Please review the training and try again.</p>';
                    html += '<a href="{{ url_for("view_training_video", video_id=video.id) }}" class="btn" style="display: inline-block; margin-top: 20px;">Retake Training</a>';
                } else {
                    html += '<p style="color: #28a745; margin-top: 20px;">Training completed successfully!</p>';
                    html += '<a href="{{ url_for("dashboard") }}" class="btn btn-success" style="display: inline-block; margin-top: 20px;">Return to Dashboard</a>';
                }
                
                html += '</div>';
                quizContent.innerHTML = html;
                quizOverlay.classList.add('show');
            }
        </script>
    </body>
    </html>
    ''', video=video, progress=progress, mid_questions=[q.to_dict() for q in mid_questions], 
         end_questions=[q.to_dict() for q in end_questions])


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
    
    if not os.path.exists(video.file_path):
        return "Video file not found", 404
    
    return send_file(video.file_path, mimetype='video/mp4')


@app.route('/uploads/ziebart.svg')
def serve_ziebart_logo():
    """Serve the Ziebart logo SVG file"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], 'ziebart.svg', mimetype='image/svg+xml')


@app.route('/uploads/quick-links/<filename>')
def serve_quick_link_image(filename):
    """Serve quick link images"""
    try:
        quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
        if not quick_links_folder.exists():
            quick_links_folder.mkdir(exist_ok=True)
        return send_from_directory(quick_links_folder, filename)
    except Exception as e:
        from flask import abort
        abort(404)


@app.route('/uploads/dashboard-hero/<filename>')
def serve_dashboard_hero(filename):
    """Serve dashboard hero animation (GIF or video) from uploads/dashboard_hero/"""
    try:
        hero_folder = app.config['UPLOAD_FOLDER'] / 'dashboard_hero'
        if not hero_folder.exists():
            from flask import abort
            abort(404)
        return send_from_directory(hero_folder, filename)
    except Exception:
        from flask import abort
        abort(404)


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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
    
    # Check for test notifications (for admins)
    if current_user.is_admin() and current_user.username.lower() == 'aka':
        test_notification = UserNotification.query.filter_by(
            username=current_user.username,
            notification_type='test',
            notification_id='999'
        ).first()
        if not test_notification or not test_notification.is_read:
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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        
        # Handle test notifications (for admins)
        if current_user.is_admin() and current_user.username.lower() == 'aka':
            test_notification = UserNotification.query.filter_by(
                username=current_user.username,
                notification_type='test',
                notification_id='999'
            ).first()
            if test_notification:
                test_notification.is_read = True
                test_notification.read_at = datetime.utcnow()
            else:
                test_notification = UserNotification(
                    username=current_user.username,
                    notification_type='test',
                    notification_id='999',
                    is_read=True,
                    read_at=datetime.utcnow()
                )
                db.session.add(test_notification)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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
        videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.created_at.desc()).all()

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

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Harassment Training - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #f5f5f5;
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
            .nav-links {
                display: flex;
                gap: 30px;
                align-items: center;
            }
            .nav-links a {
                color: #ffffff;
                text-decoration: none;
                font-size: 1em;
                font-weight: 500;
                font-family: 'URW Form', Arial, sans-serif;
                transition: color 0.2s;
            }
            .nav-links a:hover {
                color: #FE0100;
            }
            .nav-links a.active {
                color: #FE0100;
            }
            .user-section {
                display: flex;
                align-items: center;
                gap: 15px;
                position: relative;
            }
            .user-dropdown {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                padding: 5px 10px;
                border-radius: 20px;
                transition: background 0.2s;
                color: #ffffff;
            }
            .user-dropdown:hover {
                background: rgba(255,255,255,0.1);
            }
            .user-icon {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: #FE0100;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-radius: 0.5rem;
                margin-top: 10px;
                z-index: 1000;
                overflow: hidden;
            }
            .dropdown-menu.show {
                display: block;
            }
            .dropdown-item {
                padding: 12px 20px;
                color: #000000;
                text-decoration: none;
                display: block;
                transition: background 0.2s;
            }
            .dropdown-item:hover {
                background: #f5f5f5;
            }
            .dropdown-divider {
                height: 1px;
                background: #eee;
            }
            .container, .main-content {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px 20px;
            }
            .page-title {
                font-size: 2em;
                font-weight: 800;
                font-family: 'URW Form', Arial, sans-serif;
                color: #000000;
                margin-bottom: 8px;
            }
            .page-subtitle {
                color: #808080;
                font-size: 1em;
                margin-bottom: 24px;
            }
            .section-title-dash {
                font-size: 0.95em;
                font-weight: 700;
                font-family: 'URW Form', Arial, sans-serif;
                color: #333;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 16px;
                padding-bottom: 10px;
                border-bottom: 2px solid #E0E0E0;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                margin: 5px 5px 5px 0;
                font-weight: 600;
                font-family: 'URW Form', Arial, sans-serif;
            }
            .btn:hover {
                background: #cc0000;
                color: white;
            }
            .training-list {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 0;
            }
            .training-card {
                background: #FFFFFF;
                border-radius: 1rem;
                border: 1px solid #E0E0E0;
                padding: 1.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .training-card h3 {
                margin-bottom: 10px;
                color: #000000;
                font-family: 'URW Form', Arial, sans-serif;
                font-weight: 800;
            }
            .training-card p {
                color: #808080;
                margin-bottom: 15px;
            }
            .progress-info {
                background: #f8f9fa;
                padding: 12px;
                border-radius: 0.5rem;
                margin-bottom: 15px;
                font-size: 0.9em;
            }
            .badge {
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                background: #6c757d;
                color: white;
            }
            .badge-passed {
                background: #28a745;
            }
            .badge-failed {
                background: #FE0100;
            }
            .badge-in-progress {
                background: #ffc107;
                color: #000;
            }
            .mobile-menu-toggle {
                display: none;
                background: none;
                border: none;
                color: #ffffff;
                font-size: 1.5em;
                cursor: pointer;
                padding: 8px;
            }
            .mobile-nav {
                display: none;
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #000000;
                flex-direction: column;
                padding: 20px;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .mobile-nav.show {
                display: flex;
            }
            .mobile-nav a {
                color: #ffffff;
                text-decoration: none;
                padding: 12px 0;
                font-size: 1.1em;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .mobile-nav a:last-child {
                border-bottom: none;
            }
            .mobile-nav a:hover {
                color: #FE0100;
            }
            
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
                .nav-links {
                    display: none;
                }
                .mobile-menu-toggle {
                    display: block;
                }
                .user-section {
                    gap: 10px;
                }
                .user-dropdown span:not(.user-icon) {
                    display: none;
                }
                .main-content {
                    padding: 20px 15px;
                }
                .training-list {
                    grid-template-columns: 1fr;
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
                .training-card {
                    padding: 1rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                <span class="logo-text">Ziebart Onboarding</span>
            </div>
            <button class="mobile-menu-toggle" onclick="toggleMobileMenu()" style="display: none; background: none; border: none; color: #ffffff; font-size: 1.5em; cursor: pointer; padding: 8px;">☰</button>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('list_training_videos') }}" class="active">Videos</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="mobile-nav" id="mobileNav" style="display: none; position: absolute; top: 100%; left: 0; right: 0; background: #000000; flex-direction: column; padding: 20px; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                <a href="{{ url_for('dashboard') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em; border-bottom: 1px solid rgba(255,255,255,0.1);">Home</a>
                <a href="{{ url_for('user_tasks') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em; border-bottom: 1px solid rgba(255,255,255,0.1);">Tasks</a>
                <a href="{{ url_for('view_documents') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em; border-bottom: 1px solid rgba(255,255,255,0.1);">Files</a>
                <a href="{{ url_for('list_training_videos') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em; border-bottom: 1px solid rgba(255,255,255,0.1);">Videos</a>
                <a href="{{ url_for('profile') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em; border-bottom: 1px solid rgba(255,255,255,0.1);">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="color: #ffffff; text-decoration: none; padding: 12px 0; font-size: 1.1em;">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_first_name[0].upper() if user_first_name else 'U' }}</div>
                    <span>{{ user_full_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('dashboard') }}" class="dropdown-item">Dashboard</a>
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                <div class="flash flash-{{ category }}" style="padding: 12px 20px; margin-bottom: 20px; border-radius: 0.5rem; background: {% if category == 'error' %}#f8d7da; color: #721c24{% else %}#d4edda; color: #155724{% endif %};">{{ msg }}</div>
                {% endfor %}
            {% endif %}
            {% endwith %}
            <h1 class="page-title">Videos</h1>
            <p class="page-subtitle">Required training videos</p>
            
            <div class="training-list">
                {% for video in videos %}
                <div class="training-card">
                    <h3>{{ video.title }}</h3>
                    {% if video.description %}
                    <p>{{ video.description[:100] }}{% if video.description|length > 100 %}...{% endif %}</p>
                    {% endif %}
                    
                    {% set progress = user_progress[video.id] %}
                    {% if progress %}
                        <div class="progress-info">
                            {% if progress.is_completed %}
                                <p><strong>Status:</strong> 
                                    <span class="badge badge-{{ 'passed' if progress.is_passed else 'failed' }}">
                                        {{ 'Passed' if progress.is_passed else 'Failed' }}
                                    </span>
                                </p>
                                <p><strong>Score:</strong> {{ "%.0f"|format(progress.score or 0) }}%</p>
                                <p><strong>Attempt:</strong> {{ progress.attempt_number }}</p>
                                <p><strong>Time Watched:</strong> {{ "%.0f"|format(progress.time_watched or 0) }} seconds</p>
                            {% else %}
                                <p><strong>Status:</strong> <span class="badge badge-in-progress">In Progress</span></p>
                                <p><strong>Attempt:</strong> {{ progress.attempt_number }}</p>
                            {% endif %}
                        </div>
                    {% else %}
                        <div class="progress-info">
                            <p><strong>Status:</strong> Not Started</p>
                            <p><strong>Passing Score:</strong> {{ video.passing_score }}%</p>
                        </div>
                    {% endif %}
                    
                    <a href="{{ url_for('view_training_video', video_id=video.id) }}" class="btn">
                        {% if progress and progress.is_completed and not progress.is_passed %}
                            Retake Training
                        {% elif progress and not progress.is_completed %}
                            Continue Training
                        {% else %}
                            Start Training
                        {% endif %}
                    </a>
                </div>
                {% endfor %}
            </div>
            
            {% if not videos %}
            <p>No training videos available at this time.</p>
            {% endif %}
        </div>
        
        <script>
            function toggleUserDropdown() {
                var dropdown = document.getElementById('userDropdown');
                dropdown.classList.toggle('show');
            }
            
            function toggleMobileMenu() {
                var mobileNav = document.getElementById('mobileNav');
                if (mobileNav) {
                    mobileNav.classList.toggle('show');
                }
            }
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
                if (!event.target.closest('.mobile-menu-toggle') && !event.target.closest('.mobile-nav')) {
                    var mobileNav = document.getElementById('mobileNav');
                    if (mobileNav && mobileNav.classList.contains('show')) {
                        mobileNav.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name, videos=videos, user_progress=user_progress)


# Task Management Routes
@app.route('/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    """Mark a task as completed"""
    task = UserTask.query.get_or_404(task_id)
    
    # Verify task belongs to current user
    if task.username != current_user.username:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    task.status = 'completed'
    task.completed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/tasks/<int:task_id>/in-progress', methods=['POST'])
@login_required
def start_task(task_id):
    """Mark a task as in progress"""
    task = UserTask.query.get_or_404(task_id)
    
    # Verify task belongs to current user
    if task.username != current_user.username:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    task.status = 'in_progress'
    task.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})


# API Routes
@app.route('/api/user')
@login_required
def api_user():
    """Get current user info"""
    return jsonify({
        'username': current_user.username,
        'domain': current_user.domain,
        'role': current_user.role,
        'is_admin': current_user.is_admin()
    })


# WSGI application - required for IIS/wfastcgi
# The 'app' object is the Flask application instance
application = app

if __name__ == '__main__':
    # For local development
    app.run(debug=True, host='0.0.0.0', port=5000)
