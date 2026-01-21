"""
Onboarding App - Main Flask Application
Windows Domain Authentication with Admin and User roles
"""
from flask import Flask, render_template_string, redirect, url_for, request, flash, jsonify, send_file, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from auth import authenticate_user, login_required, admin_required, User, get_windows_user, check_user_can_login_as_admin
from models import (db, NewHire, User as UserModel, Document, ChecklistItem, NewHireChecklist,
                    TrainingVideo, QuizQuestion, QuizAnswer, UserTrainingProgress, UserQuizResponse, UserTask,
                    DocumentSignatureField, DocumentSignature, DocumentTypedField, DocumentTypedFieldValue, DocumentAssignment, UserNotification, ExternalLink)
from membership import get_token_groups, get_local_groups
from config import SECRET_KEY, SQLALCHEMY_DATABASE_URI, SQLALCHEMY_ENGINE_OPTIONS, BASE_DIR
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
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

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


@login_manager.user_loader
def load_user(user_id):
    """Load user from session"""
    # Try to get user from database
    user_record = UserModel.query.filter_by(username=user_id).first()
    if user_record:
        return User(user_record.username, user_record.domain, user_record.role)
    
    # Fallback: create user from session
    # This handles cases where user isn't in DB yet
    user = authenticate_user()
    if user and user.id == user_id:
        return user
    
    return None


@app.before_request
def check_authentication():
    """
    Automatically authenticate users using Windows domain authentication
    Based on domain login guide - no explicit login form needed
    """
    # Allow static files, login, logout, and home page
    if (request.path.startswith('/static') or 
        request.path == '/login' or 
        request.path == '/logout' or
        request.path == '/'):
        return
    
    # If user is not authenticated, try to authenticate using domain login
    if not current_user.is_authenticated:
        user = authenticate_user()
        if user:
            # Ensure user is in database
            ensure_user_in_db(user)
            # Log user in automatically
            login_user(user, remember=True)
        else:
            # No domain authentication available, redirect to index
            if request.path != '/':
                return redirect(url_for('index'))


def ensure_user_in_db(user):
    """Ensure user exists in database"""
    user_record = UserModel.query.filter_by(username=user.username).first()
    if not user_record:
        user_record = UserModel(
            username=user.username,
            domain=user.domain,
            role=user.role
        )
        db.session.add(user_record)
    else:
        # Update last login and role if changed
        user_record.last_login = datetime.utcnow()
        if user_record.role != user.role:
            user_record.role = user.role
    
    db.session.commit()
    return user_record


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
    """Home page - automatically authenticate and go to dashboard"""
    # Try to authenticate using Windows auth
    user = authenticate_user()
    
    if user:
        # Ensure user is in database
        ensure_user_in_db(user)
        
        # Log user in automatically (use their role from database)
        login_user(user, remember=True)
        
        return redirect(url_for('dashboard'))
    
    # If no Windows auth, show error
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Onboarding App - Authentication Error</title>
        <style>
            body {
                font-family: 'URW Form', Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .error-container {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                max-width: 500px;
                text-align: center;
            }
            h1, h2, h3, h4, h5, h6 { 
                color: #000000; 
                font-weight: 800; 
                font-family: 'URW Form', Arial, sans-serif; 
            }
            .error { color: #c33; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>🔐 Onboarding App</h1>
            <div class="error">
                <p><strong>Windows Authentication Required</strong></p>
                <p>Unable to authenticate. Please ensure Windows Authentication is enabled.</p>
            </div>
        </div>
    </body>
    </html>
    ''')


# Login route removed - authentication happens automatically on index page


@app.route('/logout')
@login_required
def logout():
    """Logout route"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    is_admin = current_user.is_admin()
    
    # Get new hire record for current user
    user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
    user_first_name = user_new_hire.first_name if user_new_hire else current_user.username
    user_full_name = f"{user_new_hire.first_name} {user_new_hire.last_name}" if user_new_hire else current_user.username
    
    # Get required training videos for current user
    required_videos = []
    completed_required_videos = []
    
    if user_new_hire:
        required_videos = list(user_new_hire.required_training_videos)
        # Check which ones are completed
        for video in required_videos:
            progress = UserTrainingProgress.query.filter_by(
                username=current_user.username,
                video_id=video.id,
                is_completed=True,
                is_passed=True
            ).first()
            if progress:
                completed_required_videos.append(video.id)
    
    incomplete_training = [v for v in required_videos if v.id not in completed_required_videos]
    
    # Get user tasks assigned to current user
    all_user_tasks = UserTask.query.filter_by(username=current_user.username).all()
    
    # Check document tasks and update completion status
    for task in all_user_tasks:
        if task.task_type == 'document' and task.document_id:
            document = Document.query.get(task.document_id)
            if document:
                # Check if all required signature fields are signed
                required_fields = DocumentSignatureField.query.filter_by(
                    document_id=task.document_id,
                    is_required=True
                ).all()
                
                if required_fields:
                    user_signatures = DocumentSignature.query.filter_by(
                        document_id=task.document_id,
                        username=current_user.username
                    ).all()
                    signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
                    
                    # Check if all required fields are signed
                    all_signed = all(f.id in signed_field_ids for f in required_fields)
                    
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
    
    # Add incomplete user tasks as notifications
    for task in user_tasks:
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
    
    # Count unread notifications
    unread_count = len([n for n in notifications if not n['is_read']])
    pending_count = unread_count
    
    # Get all training videos (for the training videos section)
    all_videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.created_at.desc()).limit(6).all()
    
    # Get visible documents
    # Only show assigned documents to users (not just visible ones)
    assigned_doc_ids = set()
    if not is_admin:
        assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
        assigned_doc_ids = set(a.document_id for a in assigned_documents)
        visible_documents = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.created_at.desc()).limit(3).all()
    else:
        visible_documents = Document.query.filter_by(is_visible=True).order_by(Document.created_at.desc()).limit(3).all()
    
    # Get active external links for the dashboard
    external_links = ExternalLink.query.filter_by(is_active=True).order_by(ExternalLink.order, ExternalLink.created_at).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - Onboarding App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
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
            .main-content {
                max-width: 1600px;
                margin: 0 auto;
                padding: 30px 20px;
                display: grid;
                grid-template-columns: 1fr 350px;
                gap: 30px;
            }
            .main-content-left {
                display: flex;
                flex-direction: column;
                gap: 30px;
            }
            .sidebar-right {
                display: flex;
                flex-direction: column;
                gap: 20px;
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
                background: linear-gradient(90deg, #ff9800 0%, #ff6f00 100%);
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 600;
                font-size: 0.9em;
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
            @media (max-width: 768px) {
                .nav-links {
                    display: none;
                }
                .welcome-section h1 {
                    font-size: 2em;
                }
                .videos-grid {
                    grid-template-columns: 1fr;
                }
                .main-content {
                    grid-template-columns: 1fr;
                }
                .sidebar-right {
                    order: -1;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
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
                    {% if is_admin %}
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <div class="dropdown-divider"></div>
                    {% endif %}
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="main-content-left">
                <div class="welcome-section">
                    <h1>Welcome, {{ user_first_name }}!</h1>
                    <p>Let's get you started with onboarding.</p>
                </div>
                
                {% if required_videos or user_tasks %}
                <div class="section">
                    <h2 class="section-title">Your Onboarding Tasks</h2>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: {{ progress_percentage }}%;">
                            {{ progress_percentage }}%
                        </div>
                    </div>
                    <div style="text-align: center; margin-top: 10px; color: #808080; font-size: 0.9em;">
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
                {% endif %}
                
                {% if all_videos %}
                <div class="section">
                    <h2 class="section-title">Training Videos</h2>
                    <div class="videos-grid">
                        {% for video in all_videos %}
                        <div class="video-card">
                            <div class="video-thumbnail">📹</div>
                            <div class="video-info">
                                <h3>{{ video.title }}</h3>
                                <a href="{{ url_for('view_training_video', video_id=video.id) }}" class="video-btn">Watch ></a>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% endif %}
            </div>
            
            {% if external_links %}
            <div class="sidebar-right">
                <div class="section">
                    <h2 class="section-title" style="margin-bottom: 20px;">Quick Links</h2>
                    <div class="quick-links">
                        {% for link in external_links %}
                        <a href="{{ link.url }}" target="_blank" rel="noopener noreferrer" class="quick-link">
                            <div class="quick-link-icon">
                                {% if link.image_filename %}
                                <img src="{{ url_for('serve_quick_link_image', filename=link.image_filename) }}" alt="{{ link.title }}">
                                {% else %}
                                {{ link.icon or '🔗' }}
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
                            clickedElement.remove();
                        }
                        // Check if there are any notifications left
                        var notificationList = document.querySelector('.notification-list');
                        if (notificationList && notificationList.querySelectorAll('.notification-item').length === 0) {
                            notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                        }
                    }
                    // Navigate to the notification URL
                    window.location.href = url;
                })
                .catch(error => {
                    console.error('Error:', error);
                    // Still navigate even if marking as read fails
                    window.location.href = url;
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
            }
        </script>
    </body>
    </html>
    ''', is_admin=is_admin, user_first_name=user_first_name, user_full_name=user_full_name,
         required_videos=required_videos, completed_required_videos=completed_required_videos,
         incomplete_training=incomplete_training, all_tasks_completed=all_tasks_completed,
         progress_percentage=progress_percentage, all_videos=all_videos, visible_documents=visible_documents,
         user_tasks=user_tasks, total_tasks=total_tasks, completed_tasks=completed_tasks, 
         pending_count=pending_count, notifications=notifications, external_links=external_links)


@app.route('/tasks')
@login_required
def user_tasks():
    """User tasks page - shows tasks assigned to the current user"""
    is_admin = current_user.is_admin()
    
    # Get tasks assigned to current user
    user_tasks = UserTask.query.filter_by(username=current_user.username).order_by(
        UserTask.priority.desc(),
        UserTask.due_date.asc(),
        UserTask.created_at.desc()
    ).all()
    
    # Check document tasks and update completion status
    for task in user_tasks:
        if task.task_type == 'document' and task.document_id:
            document = Document.query.get(task.document_id)
            if document:
                # Check if all required signature fields are signed
                required_fields = DocumentSignatureField.query.filter_by(
                    document_id=task.document_id,
                    is_required=True
                ).all()
                
                if required_fields:
                    user_signatures = DocumentSignature.query.filter_by(
                        document_id=task.document_id,
                        username=current_user.username
                    ).all()
                    signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
                    
                    # Check if all required fields are signed
                    all_signed = all(f.id in signed_field_ids for f in required_fields)
                    
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
    
    # Get new hire record for current user
    user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
    user_first_name = user_new_hire.first_name if user_new_hire else current_user.username
    user_full_name = f"{user_new_hire.first_name} {user_new_hire.last_name}" if user_new_hire else current_user.username
    
    # Count tasks by status
    pending_tasks = [t for t in user_tasks if t.status == 'pending']
    in_progress_tasks = [t for t in user_tasks if t.status == 'in_progress']
    completed_tasks = [t for t in user_tasks if t.status == 'completed']
    
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
            .main-content {
                max-width: 1600px;
                margin: 0 auto;
                padding: 30px 20px;
            }
            .page-title {
                font-size: 3em;
                font-weight: 800;
                color: #000000;
                margin-bottom: 10px;
            }
            .page-subtitle {
                color: #808080;
                font-size: 1.2em;
                margin-bottom: 30px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
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
                background: white;
                border-radius: 12px;
                padding: 25px;
                margin-bottom: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .section-title {
                font-size: 1.6em;
                font-weight: 800;
                margin-bottom: 20px;
                color: #000000;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .task-list {
                display: grid;
                gap: 15px;
            }
            .task-item {
                background: #ffffff;
                border-radius: 0.5rem;
                padding: 20px;
                border-left: 4px solid #dc3545;
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
            @media (max-width: 768px) {
                .task-header {
                    flex-direction: column;
                    gap: 10px;
                }
                .task-badges {
                    width: 100%;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}" class="active">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
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
                    {% if is_admin %}
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <div class="dropdown-divider"></div>
                    {% endif %}
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
                            <div class="task-title">{{ task.task_title }}</div>
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
                                    {% if task.task_type == 'document' and task.document_id %}
                                        <a href="{{ url_for('sign_document', doc_id=task.document_id) }}" class="btn btn-success">✍️ Sign Document</a>
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
            
            window.onclick = function(event) {
                if (!event.target.closest('.user-dropdown')) {
                    var dropdown = document.getElementById('userDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
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
    """User profile page showing name, username, email, and domain groups"""
    is_admin = current_user.is_admin()
    
    # Get user info from database
    user_record = UserModel.query.filter_by(username=current_user.username).first()
    
    # Get user info
    user_name = user_record.full_name if user_record and user_record.full_name else current_user.username
    user_username = current_user.username
    user_email = user_record.email if user_record and user_record.email else 'Not set'
    user_domain = user_record.domain if user_record and user_record.domain else current_user.domain
    
    # Get domain groups
    domain_groups = get_user_domain_groups(user_username, user_domain)
    
    # Get new hire record for display name
    user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
    if user_new_hire:
        user_name = f"{user_new_hire.first_name} {user_new_hire.last_name}"
        if not user_email or user_email == 'Not set':
            user_email = user_new_hire.email if user_new_hire.email else 'Not set'
    
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
                max-width: 900px;
                margin: 0 auto;
                padding: 30px 20px;
            }
            .profile-header {
                background: white;
                border-radius: 12px;
                padding: 40px;
                margin-bottom: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                text-align: center;
            }
            .profile-avatar {
                width: 120px;
                height: 120px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
                color: #000000;
                margin-bottom: 10px;
            }
            .profile-username {
                color: #808080;
                font-size: 1.1em;
                margin-bottom: 5px;
            }
            .profile-email {
                color: #808080;
                font-size: 1em;
            }
            .info-section {
                background: white;
                border-radius: 12px;
                padding: 25px;
                margin-bottom: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .section-title {
                font-size: 1.6em;
                font-weight: 800;
                margin-bottom: 20px;
                color: #000000;
                display: flex;
                align-items: center;
                gap: 10px;
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
            .groups-list {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 15px;
            }
            .group-badge {
                background: #f8f8f8;
                color: #FE0100;
                padding: 8px 15px;
                border-radius: 20px;
                font-size: 0.9em;
                font-weight: 600;
            }
            .no-groups {
                color: #999;
                font-style: italic;
                margin-top: 15px;
            }
            @media (max-width: 768px) {
                .nav-links {
                    display: none;
                }
                .profile-header {
                    padding: 30px 20px;
                }
                .profile-name {
                    font-size: 1.5em;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
                {% endif %}
            </div>
            <div class="user-section">
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ user_name[0].upper() if user_name else 'U' }}</div>
                    <span>{{ user_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    {% if is_admin %}
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <div class="dropdown-divider"></div>
                    {% endif %}
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="profile-header">
                <div class="profile-avatar">{{ user_name[0].upper() if user_name else 'U' }}</div>
                <div class="profile-name">{{ user_name }}</div>
                <div class="profile-username">{{ user_domain }}\\{{ user_username }}</div>
                <div class="profile-email">{{ user_email }}</div>
            </div>
            
            <div class="info-section">
                <h2 class="section-title">📋 User Information</h2>
                <div class="info-item">
                    <span class="info-label">Full Name</span>
                    <span class="info-value">{{ user_name }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Username</span>
                    <span class="info-value">{{ user_username }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Email</span>
                    <span class="info-value">{{ user_email }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Domain</span>
                    <span class="info-value">{{ user_domain or 'N/A' }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Role</span>
                    <span class="info-value">{{ 'Administrator' if is_admin else 'User' }}</span>
                </div>
            </div>
            
            <div class="info-section">
                <h2 class="section-title">👥 Domain Groups</h2>
                {% if domain_groups %}
                <div class="groups-list">
                    {% for group in domain_groups %}
                    <span class="group-badge">{{ group }}</span>
                    {% endfor %}
                </div>
                {% else %}
                <div class="no-groups">No domain groups found or unable to retrieve group information.</div>
                {% endif %}
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
    ''', is_admin=is_admin, user_name=user_name, user_username=user_username, 
         user_email=user_email, user_domain=user_domain, domain_groups=domain_groups)


@app.route('/new-hires')
@login_required
def new_hire_list():
    """List all new hires"""
    new_hires = NewHire.query.order_by(NewHire.created_at.desc()).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>New Hires - Onboarding App</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'URW Form', Arial, sans-serif;
                background: #f5f5f5;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
            }
            .header-content {
                max-width: 1600px;
                margin: 0 auto;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .container {
                max-width: 1600px;
                margin: 30px auto;
                padding: 0 20px;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 0;
            }
            table {
                width: 100%;
                background: white;
                border-radius: 0.5rem;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
            .status {
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 0.85em;
            }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-active { background: #d4edda; color: #155724; }
            .status-completed { background: #d1ecf1; color: #0c5460; }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
                position: relative;
            }
            .badge {
                background: rgba(255,255,255,0.2);
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 0.9em;
            }
            .settings-dropdown {
                position: relative;
                display: inline-block;
            }
            .settings-icon {
                cursor: pointer;
                font-size: 1.5em;
                padding: 5px 10px;
                border-radius: 0.5rem;
                transition: background 0.3s;
            }
            .settings-icon:hover {
                background: rgba(255,255,255,0.2);
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                min-width: 200px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                border-radius: 0.5rem;
                margin-top: 5px;
                z-index: 1000;
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
                margin: 5px 0;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>📋 New Hires</h1>
                <div class="user-info">
                    <span>{{ current_user.username }}</span>
                    <span class="badge">{{ "Admin" if current_user.is_admin() else "User" }}</span>
                    <div class="settings-dropdown">
                        <span class="settings-icon" onclick="toggleDropdown()">⚙️</span>
                        <div class="dropdown-menu" id="settingsDropdown">
                            {% if current_user.is_admin() %}
                            <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                            <div class="dropdown-divider"></div>
                            {% endif %}
                            <a href="{{ url_for('dashboard') }}" class="dropdown-item">Dashboard</a>
                            <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                        </div>
                    </div>
                </div>
            </div>
            <a href="{{ url_for('dashboard') }}" class="back-btn">← Back</a>
        </div>
        
        <div class="container">
            
            {% if new_hires %}
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Department</th>
                        <th>Position</th>
                        <th>Start Date</th>
                        <th>Status</th>
                        <th>Created By</th>
                    </tr>
                </thead>
                <tbody>
                    {% for hire in new_hires %}
                    <tr>
                        <td><strong>{{ hire.username }}</strong></td>
                        <td>{{ hire.first_name }} {{ hire.last_name }}</td>
                        <td>{{ hire.email }}</td>
                        <td>{{ hire.department or '-' }}</td>
                        <td>{{ hire.position or '-' }}</td>
                        <td>{{ hire.start_date.strftime('%Y-%m-%d') if hire.start_date else '-' }}</td>
                        <td><span class="status status-{{ hire.status }}">{{ hire.status }}</span></td>
                        <td>{{ hire.required_training_videos.count() }} video(s)</td>
                        <td>{{ hire.created_by }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p>No new hires found.</p>
            {% endif %}
        </div>
        
        <script>
            function toggleDropdown() {
                var dropdown = document.getElementById('settingsDropdown');
                dropdown.classList.toggle('show');
            }
            
            window.onclick = function(event) {
                if (!event.target.matches('.settings-icon')) {
                    var dropdown = document.getElementById('settingsDropdown');
                    if (dropdown.classList.contains('show')) {
                        dropdown.classList.remove('show');
                    }
                }
            }
        </script>
    </body>
    </html>
    ''', new_hires=new_hires)


@app.route('/admin/new-hire/add')
@admin_required
def add_new_hire():
    """Add a new hire with username and required training"""
    videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.title).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Start Onboarding Process - Onboarding App</title>
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
            .checkbox-group {
                max-height: 300px;
                overflow-y: auto;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 0.5rem;
                background: #f8f9fa;
            }
            .checkbox-item {
                padding: 10px;
                margin: 5px 0;
                background: white;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .checkbox-item input[type="checkbox"] {
                width: auto;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>🚀 Start Onboarding Process</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="admin-panel">
                <h2>New Hire Onboarding</h2>
                        <p style="color: #808080; margin-bottom: 20px;">Enter the new hire's information and select the required training videos they need to complete.</p>
                <form method="POST" action="{{ url_for('create_new_hire') }}">
                    <div class="form-group">
                        <label for="username">Username (Domain Username) *</label>
                        <input type="text" name="username" id="username" required placeholder="e.g., jdoe (without domain)">
                        <small style="color: #666;">The username the new hire will use to login</small>
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
                        <label>Required Training Videos *</label>
                        <div class="checkbox-group">
                            {% if videos %}
                                {% for video in videos %}
                                <div class="checkbox-item">
                                    <input type="checkbox" name="required_videos" value="{{ video.id }}" id="video_{{ video.id }}">
                                    <label for="video_{{ video.id }}">{{ video.title }}</label>
                                </div>
                                {% endfor %}
                            {% else %}
                                <p>No training videos available. <a href="{{ url_for('manage_training') }}">Upload videos first</a>.</p>
                            {% endif %}
                        </div>
                        <small style="color: #808080;">Select which training videos this new hire must complete</small>
                    </div>
                    
                    <button type="submit" class="btn btn-success">Start Onboarding</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    ''', videos=videos)


@app.route('/admin/new-hire/create', methods=['POST'])
@admin_required
def create_new_hire():
    """Create a new hire with required training videos"""
    username = request.form.get('username', '').strip()
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    required_videos = request.form.getlist('required_videos')
    
    if not username or not first_name or not last_name:
        flash('Username, first name, and last name are required.', 'error')
        return redirect(url_for('add_new_hire'))
    
    if not required_videos:
        flash('At least one training video must be selected.', 'error')
        return redirect(url_for('add_new_hire'))
    
    try:
        # Generate a default email if not provided (model requires email)
        import config
        email_domain = config.EMAIL_DOMAIN if hasattr(config, 'EMAIL_DOMAIN') else 'ziebart.com'
        email = f"{username}@{email_domain}"
        
        # Create new hire
        new_hire = NewHire(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            created_by=current_user.username
        )
        db.session.add(new_hire)
        db.session.flush()  # Get the ID
        
        # Add required training videos
        for video_id in required_videos:
            video = TrainingVideo.query.get(int(video_id))
            if video:
                new_hire.required_training_videos.append(video)
        
        db.session.commit()
        flash(f'Onboarding started for "{first_name} {last_name}" ({username}) with {len(required_videos)} required training video(s).', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error starting onboarding: {str(e)}', 'error')
        return redirect(url_for('add_new_hire'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    total_users = UserModel.query.count()
    total_new_hires = NewHire.query.count()
    admin_users = UserModel.query.filter_by(role='admin').count()
    
    # Get forms completed count (documents that are visible)
    forms_completed = Document.query.filter_by(is_visible=True).count()
    
    # Get onboarding checklists count (total checklist items available)
    total_checklist_items = ChecklistItem.query.filter_by(is_active=True).count()
    
    # Get all new hires with their progress
    all_new_hires = NewHire.query.order_by(NewHire.created_at.desc()).all()
    new_hires_with_progress = []
    
    for new_hire in all_new_hires:
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
        
        progress_percentage = int((completed_videos / total_videos * 100)) if total_videos > 0 else 0
        new_hires_with_progress.append({
            'new_hire': new_hire,
            'progress': progress_percentage,
            'completed': completed_videos,
            'total': total_videos
        })
    
    # Get recent activity (new hires ordered by creation date)
    recent_activity = all_new_hires[:10]
    
    # Get form status stats - documents with signature fields
    documents_with_signatures = Document.query.join(DocumentSignatureField).distinct().all()
    form_status_data = []
    
    for doc in documents_with_signatures:
        # Get all required signature fields for this document
        required_fields = DocumentSignatureField.query.filter_by(
            document_id=doc.id,
            is_required=True
        ).all()
        
        total_required = len(required_fields)
        if total_required == 0:
            continue  # Skip documents with no required fields
        
        # Count how many unique users have signed all required fields
        # For admin dashboard, we'll show overall completion across all users
        signed_count = 0
        all_users = UserModel.query.all()
        
        for user in all_users:
            user_signatures = DocumentSignature.query.filter_by(
                document_id=doc.id,
                username=user.username
            ).all()
            signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
            
            # Check if user has signed all required fields
            all_signed = all(f.id in signed_field_ids for f in required_fields)
            if all_signed:
                signed_count += 1
        
        total_users = len(all_users)
        percentage = int((signed_count / total_users * 100)) if total_users > 0 else 0
        
        form_status_data.append({
            'doc_id': doc.id,
            'name': doc.original_filename or 'Untitled Document',
            'signed': signed_count,
            'total': total_users,
            'percentage': percentage
        })
    
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
        notifications.append({
            'type': 'test',
            'id': 999,
            'title': 'Test Notification',
            'message': 'This is a test notification to verify the notification system is working correctly.',
            'url': url_for('admin_dashboard'),
            'is_read': False
        })
    
    pending_count = len([n for n in notifications if not n['is_read']])
    
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
            .notification-icon, .search-icon {
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
            }
            .table-progress-fill {
                height: 100%;
                background: #4caf50;
                border-radius: 3px;
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
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
                min-width: 0;
                max-width: 200px;
            }
            .form-status-progress {
                width: 120px;
                height: 6px;
                background: #e0e0e0;
                border-radius: 3px;
                overflow: hidden;
            }
            .form-status-fill {
                height: 100%;
                background: #4caf50;
                border-radius: 3px;
            }
            .form-status-count {
                font-size: 0.85em;
                color: #808080;
                min-width: 50px;
                text-align: right;
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
            @media (max-width: 1200px) {
                .main-container {
                    grid-template-columns: 1fr;
                }
                .summary-cards {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">User Dashboard</a>
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
                <div class="search-icon">🔍</div>
                <div class="user-dropdown" onclick="toggleUserDropdown()">
                    <div class="user-icon">{{ admin_name[0].upper() if admin_name else 'A' }}</div>
                    <span>{{ admin_name }}</span>
                    <span>▼</span>
                </div>
                <div class="dropdown-menu" id="userDropdown">
                    <a href="{{ url_for('dashboard') }}" class="dropdown-item">Dashboard</a>
                    <div class="dropdown-divider"></div>
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
                    <div class="summary-card">
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
                                    <div class="progress-fill not-started" style="width: 100%;"></div>
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
                                <td><a href="{{ url_for('view_new_hire_details', username=item.new_hire.username) }}" style="color: #333; text-decoration: none; font-weight: 600;">{{ item.new_hire.first_name }} {{ item.new_hire.last_name }}</a></td>
                                <td>{{ item.new_hire.position or '-' }}</td>
                                <td>{{ item.new_hire.department or '-' }}</td>
                                <td>
                                    <div class="table-progress">
                                        <div class="table-progress-fill" style="width: {{ item.progress }}%;"></div>
                                    </div>
                                    <span style="font-size: 0.85em; color: #808080; margin-left: 8px;">{{ item.progress }}%</span>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <div class="section">
                    <div class="section-header">
                        <h2 class="section-title">New Hires List</h2>
                        <div style="display: flex; gap: 10px;">
                            <button style="background: none; border: none; font-size: 1.2em; cursor: pointer;">←</button>
                            <button style="background: none; border: none; font-size: 1.2em; cursor: pointer;">→</button>
                        </div>
                    </div>
                    <div class="new-hires-list">
                        {% for item in new_hires_with_progress[:5] %}
                        <div class="new-hire-item">
                            <div class="progress-avatar">{{ item.new_hire.first_name[0].upper() if item.new_hire.first_name else 'N' }}</div>
                            <div style="flex: 1;">
                                <div style="font-weight: 600;"><a href="{{ url_for('view_new_hire_details', username=item.new_hire.username) }}" style="color: #333; text-decoration: none; cursor: pointer;">{{ item.new_hire.first_name }} {{ item.new_hire.last_name }}</a></div>
                            </div>
                            <div style="font-weight: 600; color: #1976d2;">{{ item.progress }}%</div>
                        </div>
                        {% endfor %}
                    </div>
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
                                        <div class="form-status-fill" style="width: {{ form.percentage }}%;"></div>
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
                            clickedElement.remove();
                        }
                        // Check if there are any notifications left
                        var notificationList = document.querySelector('.notification-list');
                        if (notificationList && notificationList.querySelectorAll('.notification-item').length === 0) {
                            notificationList.innerHTML = '<div class="notification-empty"><p>No new notifications</p></div>';
                        }
                    }
                    // Navigate to the notification URL
                    window.location.href = url;
                })
                .catch(error => {
                    console.error('Error:', error);
                    // Still navigate even if marking as read fails
                    window.location.href = url;
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
    """Manage users and assign admin roles"""
    users = UserModel.query.order_by(UserModel.username).all()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Manage Users - Onboarding App</title>
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
            .btn-danger {
                background: #FE0100;
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
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 0.85em;
                font-weight: bold;
            }
            .badge-admin {
                background: #FE0100;
                color: white;
            }
            .badge-user {
                background: #6c757d;
                color: white;
            }
            .action-btn {
                padding: 5px 15px;
                border: none;
                border-radius: 0.5rem;
                cursor: pointer;
                font-size: 0.9em;
                text-decoration: none;
                display: inline-block;
            }
            .form-group {
                margin: 20px 0;
                background: white;
                padding: 20px;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .form-group input {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 0.5rem;
                width: 300px;
                margin-right: 10px;
            }
            .form-group button {
                padding: 10px 20px;
                background: #28a745;
                color: white;
                border: none;
                border-radius: 0.5rem;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>👥 Manage Users & Admins</h1>
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            
            <div class="form-group">
                <h3>Add User as Admin</h3>
                <form method="POST" action="{{ url_for('assign_admin') }}">
                    <input type="text" name="username" placeholder="Enter username (without domain)" required>
                    <button type="submit">Assign Admin Role</button>
                </form>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Domain</th>
                        <th>Role</th>
                        <th>Email</th>
                        <th>Last Login</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td>{{ user.username }}</td>
                        <td>{{ user.domain or '-' }}</td>
                        <td>
                            <span class="badge badge-{{ user.role }}">{{ user.role }}</span>
                        </td>
                        <td>{{ user.email or '-' }}</td>
                        <td>{{ user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never' }}</td>
                        <td>
                            {% if user.role == 'admin' %}
                                <form method="POST" action="{{ url_for('remove_admin') }}" style="display: inline;">
                                    <input type="hidden" name="user_id" value="{{ user.id }}">
                                    <button type="submit" class="action-btn btn-danger" 
                                            onclick="return confirm('Remove admin role from {{ user.username }}?')">
                                        Remove Admin
                                    </button>
                                </form>
                            {% else %}
                                <form method="POST" action="{{ url_for('assign_admin') }}" style="display: inline;">
                                    <input type="hidden" name="username" value="{{ user.username }}">
                                    <button type="submit" class="action-btn btn-success">
                                        Make Admin
                                    </button>
                                </form>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    ''', users=users)


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


@app.route('/admin/documents')
@admin_required
def manage_documents():
    """Manage documents - upload and manage new hire paperwork"""
    documents = Document.query.order_by(Document.created_at.desc()).all()
    
    # Get signature status for each document
    for doc in documents:
        signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
        doc.signature_fields_count = len(signature_fields)
        # Count how many users have signed
        signatures = DocumentSignature.query.filter_by(document_id=doc.id).all()
        doc.signatures_count = len(signatures)
        # Get unique users who signed
        signed_users = set(sig.username for sig in signatures)
        doc.signed_users_count = len(signed_users)
    
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
                            <td><strong>{{ doc.original_filename }}</strong></td>
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
                    }
                });
                
                // Toggle current menu
                menu.classList.toggle('show');
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
        document = Document(
            filename=filename,
            original_filename=original_filename,
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
    """Delete a document"""
    doc_id = request.form.get('doc_id')
    
    if not doc_id:
        flash('Document ID is required.', 'error')
        return redirect(url_for('manage_documents'))
    
    document = Document.query.get(doc_id)
    if not document:
        flash('Document not found.', 'error')
        return redirect(url_for('manage_documents'))
    
    try:
        # Delete file from filesystem
        file_path = document.file_path
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        db.session.delete(document)
        db.session.commit()
        
        flash(f'Document "{document.original_filename}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting document: {str(e)}', 'error')
    
    return redirect(url_for('manage_documents'))


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
        <title>Set Signature Fields - {{ document.original_filename }}</title>
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
                font-size: 14px;
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
                <h1>✍️ Set Signature Fields - {{ document.original_filename }}</h1>
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
    """Delete a signature field"""
    field = DocumentSignatureField.query.get(field_id)
    if not field:
        flash('Signature field not found.', 'error')
        return redirect(url_for('manage_documents'))
    
    doc_id = field.document_id
    
    try:
        # Delete associated signatures
        DocumentSignature.query.filter_by(signature_field_id=field_id).delete()
        # Delete the field
        db.session.delete(field)
        db.session.commit()
        
        flash('Signature field deleted successfully.', 'success')
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
    
    # Get all users
    all_users = UserModel.query.filter_by(role='user').order_by(UserModel.username).all()
    
    # Get current assignments for this document
    current_assignments = DocumentAssignment.query.filter_by(document_id=doc_id).all()
    assigned_usernames = set(a.username for a in current_assignments)
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Assign Document - {{ document.original_filename }}</title>
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
                font-size: 14px;
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
                                    <label for="user-{{ user.username }}">{{ user.username }}</label>
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
                            <strong>{{ assignment.username }}</strong>
                            {% if assignment.due_date %}
                            <span style="color: #666; margin-left: 10px;">Due: {{ assignment.due_date.strftime('%Y-%m-%d') }}</span>
                            {% endif %}
                            {% if assignment.is_completed %}
                            <span class="assigned-badge" style="margin-left: 10px;">✓ Completed</span>
                            {% endif %}
                        </div>
                        <form method="POST" action="{{ url_for('remove_document_assignment', assignment_id=assignment.id) }}" style="display: inline;">
                            <button type="submit" class="btn" style="padding: 5px 15px; font-size: 0.85em;" 
                                    onclick="return confirm('Remove assignment for {{ assignment.username }}?')">
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
    ''', document=document, all_users=all_users, assigned_usernames=assigned_usernames, current_assignments=current_assignments)


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
                    task_title=f"Sign Document: {document.original_filename}",
                    task_description=f"Please review and sign the document: {document.description or document.original_filename}",
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
            else:
                # Update existing assignment
                if due_date:
                    existing.due_date = due_date
                if notes:
                    existing.notes = notes
                assigned_count += 1
        
        db.session.commit()
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
    """View assigned documents (regular users) or all documents (admins)"""
    if current_user.is_admin():
        documents = Document.query.order_by(Document.created_at.desc()).all()
    else:
        # For regular users, ONLY show assigned documents
        assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
        assigned_doc_ids = [a.document_id for a in assigned_documents]
        if assigned_doc_ids:
            documents = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.created_at.desc()).all()
        else:
            documents = []
    
    # Get assigned documents for current user
    assigned_documents = DocumentAssignment.query.filter_by(username=current_user.username).all()
    assigned_doc_ids = set(a.document_id for a in assigned_documents)
    
    # Check signature status for each document
    for doc in documents:
        signature_fields = DocumentSignatureField.query.filter_by(document_id=doc.id).all()
        doc.has_signature_fields = len(signature_fields) > 0
        # Check if current user has signed all required fields
        user_signatures = DocumentSignature.query.filter_by(document_id=doc.id, username=current_user.username).all()
        signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
        required_fields = [f for f in signature_fields if f.is_required]
        doc.all_signed = len(required_fields) > 0 and all(f.id in signed_field_ids for f in required_fields)
        # Only require signature if document is assigned
        doc.is_assigned = doc.id in assigned_doc_ids
        doc.needs_signature = doc.is_assigned and len(required_fields) > 0 and not doc.all_signed
        if doc.is_assigned:
            doc.assignment = next((a for a in assigned_documents if a.document_id == doc.id), None)
    
    # Get user info for header
    is_admin = current_user.is_admin()
    user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
    user_first_name = user_new_hire.first_name if user_new_hire else current_user.username
    user_full_name = f"{user_new_hire.first_name} {user_new_hire.last_name}" if user_new_hire else current_user.username
    
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
            .container {
                max-width: 1600px;
                margin: 30px auto;
                padding: 0 20px;
            }
            .btn:hover {
                background: #d60000;
                opacity: 0.9;
            }
            .documents-list {
                background: white;
                padding: 25px;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-top: 20px;
            }
            .document-item {
                padding: 15px;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .document-item:last-child {
                border-bottom: none;
            }
            .document-info h3 {
                margin-bottom: 5px;
                color: #000000;
            }
            .document-info p {
                color: #808080;
                font-size: 0.9em;
                margin: 5px 0;
            }
            .document-actions {
                display: flex;
                gap: 10px;
                align-items: center;
            }
            .file-size {
                color: #808080;
                font-size: 0.85em;
            }
            .badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 1em;
                background: #28a745;
                color: white;
                text-decoration: none;
                font-weight: 500;
                line-height: 1.5;
                vertical-align: middle;
                white-space: nowrap;
            }
            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 10px 20px;
                background: #FE0100;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 0;
                font-size: 1em;
                font-weight: 500;
                line-height: 1.5;
                vertical-align: middle;
                white-space: nowrap;
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
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
                    {% if is_admin %}
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <div class="dropdown-divider"></div>
                    {% endif %}
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="container">
            
            <div class="documents-list">
                <h2>Available Documents</h2>
                {% if documents %}
                    {% for doc in documents %}
                    <div class="document-item" {% if doc.is_assigned %}style="border-left: 4px solid #007bff; background: #f0f7ff;"{% endif %}>
                        <div class="document-info">
                            <h3>
                                {{ doc.original_filename }}
                            </h3>
                            {% if doc.description %}
                            <p>{{ doc.description }}</p>
                            {% endif %}
                            {% if doc.is_assigned and doc.assignment %}
                            <p style="color: #007bff; font-weight: 600; margin: 5px 0;">
                                ⚠️ Required Signature
                                {% if doc.assignment.due_date %}
                                • Due: {{ doc.assignment.due_date.strftime('%B %d, %Y') }}
                                {% endif %}
                            </p>
                            {% endif %}
                            <p class="file-size">
                                {% if doc.file_size %}
                                    {% if doc.file_size < 1024 %}
                                        {{ doc.file_size }} B
                                    {% elif doc.file_size < 1048576 %}
                                        {{ "%.1f"|format(doc.file_size / 1024) }} KB
                                    {% else %}
                                        {{ "%.1f"|format(doc.file_size / 1048576) }} MB
                                    {% endif %}
                                {% endif %}
                                • Uploaded by {{ doc.uploaded_by }} on {{ doc.created_at.strftime('%Y-%m-%d') if doc.created_at else '-' }}
                            </p>
                        </div>
                        <div class="document-actions">
                            {% if doc.has_signature_fields %}
                                {% if doc.all_signed %}
                                    <span class="badge">✓ Signed</span>
                                {% else %}
                                    <a href="{{ url_for('sign_document', doc_id=doc.id) }}" class="btn" style="background: #28a745;">✍️ Sign Document</a>
                                {% endif %}
                            {% endif %}
                            <a href="{{ url_for('download_document', doc_id=doc.id) }}" class="btn">⬇️ Download</a>
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <p>No documents available.</p>
                {% endif %}
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
            user_signatures = DocumentSignature.query.filter_by(
                document_id=doc_id,
                username=username
            ).all()
            
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
    
    # Create a map of field_id -> signature
    sig_map = {sig.signature_field_id: sig for sig in user_signatures}
    
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


@app.route('/documents/<int:doc_id>/sign')
@login_required
def sign_document(doc_id):
    """Sign a document - only allowed if document is assigned to user"""
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
    user_signatures = DocumentSignature.query.filter_by(document_id=doc_id, username=current_user.username).all()
    signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
    
    # Get existing typed field values by current user (handle case where table might not exist yet)
    try:
        user_typed_values = DocumentTypedFieldValue.query.filter_by(document_id=doc_id, username=current_user.username).all()
        filled_typed_field_ids = {val.typed_field_id: val.field_value for val in user_typed_values}
    except Exception:
        filled_typed_field_ids = {}
    
    # Check if document is a PDF
    is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sign Document - {{ document.original_filename }}</title>
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
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>✍️ Sign Document - {{ document.original_filename }}</h1>
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
                    <div class="signature-field-item {% if field.id in signed_field_ids %}signed{% endif %}" id="field-{{ field.id }}">
                        <h4>{{ field.field_label or 'Signature Field' }}</h4>
                        <p>Page: {{ field.page_number }}</p>
                        {% if field.signature_type == 'cryptographic' %}
                            <p style="font-size: 0.85em; color: #0066cc; margin-bottom: 10px;">
                                <strong>🔒 Cryptographic Signature</strong><br>
                                This is a legally binding, tamper-evident signature.
                            </p>
                        {% endif %}
                        <div id="signature-field-container-{{ field.id }}">
                        {% if field.id in signed_field_ids %}
                            <p style="color: #28a745; font-weight: bold;">✓ Signed</p>
                            {% for sig in user_signatures %}
                                {% if sig.signature_field_id == field.id %}
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
                                {% endif %}
                            {% endfor %}
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
                    <div class="signature-field-item" style="border-left-color: #ffc107;">
                        <h4>{{ field.field_label or 'Typed Field' }}</h4>
                        <p>Type: {{ field.field_type|title }} • Page: {{ field.page_number }}</p>
                        <div id="typed-field-container-{{ field.id }}">
                        {% if field.id in filled_typed_field_ids %}
                            <p style="color: #28a745; font-weight: bold;">✓ Filled</p>
                            <div style="padding: 10px; background: #f8f9fa; border-radius: 4px; margin-top: 10px;">
                                <strong>Value:</strong> {{ filled_typed_field_ids[field.id] }}
                            </div>
                            <button type="button" onclick="redoTypedField({{ field.id }})" class="btn" style="width: 100%; margin-top: 10px; padding: 8px; background: #ffc107; color: #000;">Redo Field</button>
                        {% else %}
                            <div class="form-group" style="margin-top: 10px;">
                                {% if field.field_type == 'date' %}
                                    <input type="date" id="typed-field-{{ field.id }}" class="typed-field-input" 
                                           placeholder="{{ field.placeholder or 'Enter date' }}" 
                                           style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;"
                                           {% if field.is_required %}required{% endif %}>
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
                                <button type="button" onclick="saveTypedField({{ field.id }})" class="btn-success" style="width: 100%; margin-top: 10px; padding: 10px;">Save {{ field.field_label }}</button>
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
                            var fieldLabel = fieldContainer.closest('.signature-field-item').querySelector('h4').textContent;
                            fieldContainer.innerHTML = '<p style="color: #28a745; font-weight: bold;">✓ Filled</p>' +
                                '<div style="padding: 10px; background: #f8f9fa; border-radius: 4px; margin-top: 10px;"><strong>Value:</strong> ' + value + '</div>' +
                                '<button type="button" onclick="redoTypedField(' + fieldId + ')" class="btn" style="width: 100%; margin-top: 10px; padding: 8px; background: #ffc107; color: #000;">Redo Field</button>';
                            
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
         user_signatures=user_signatures, typed_fields=typed_fields, filled_typed_field_ids=filled_typed_field_ids, is_pdf=is_pdf)


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
    
    data = request.get_json()
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
        # Check if user already signed this field
        existing_signature = DocumentSignature.query.filter_by(
            document_id=doc_id,
            signature_field_id=signature_field_id,
            username=current_user.username
        ).first()
        
        if existing_signature:
            # Update existing signature
            if not is_cryptographic:
                existing_signature.signature_image = signature_image
            existing_signature.signed_at = datetime.utcnow()
            existing_signature.ip_address = request.remote_addr
            existing_signature.user_agent = request.headers.get('User-Agent', '')
            existing_signature.consent_given = consent_given
            sig_to_embed = existing_signature
        else:
            # Create new signature record
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
        
        # Check if all required fields are signed
        all_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()
        user_sigs = DocumentSignature.query.filter_by(document_id=doc_id, username=current_user.username).all()
        signed_field_ids = set(sig.signature_field_id for sig in user_sigs)
        
        all_signed = all(f.id in signed_field_ids for f in all_fields if f.is_required)
        
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
            
            # Mark user task as completed
            task = UserTask.query.filter_by(
                document_id=doc_id,
                username=current_user.username,
                task_type='sign_document'
            ).first()
            if task:
                task.is_completed = True
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
            # Find and delete the signature
            signature = DocumentSignature.query.filter_by(
                document_id=doc_id,
                signature_field_id=signature_field_id,
                username=current_user.username
            ).first()
            
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
    
    # Get all users who have signed this document
    signatures = DocumentSignature.query.filter_by(document_id=doc_id).all()
    
    # Group signatures by username
    signed_users = {}
    for sig in signatures:
        if sig.username not in signed_users:
            signed_users[sig.username] = []
        signed_users[sig.username].append(sig)
    
    # Get signature fields to check if all required fields are signed
    signature_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).all()
    required_fields = [f for f in signature_fields if f.is_required]
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Signed Copies - {{ document.original_filename }}</title>
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
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>📥 Signed Copies - {{ document.original_filename }}</h1>
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
                        <div>
                            <a href="{{ url_for('download_signed_document', doc_id=document.id, username=username) }}" class="btn btn-success">
                                📥 Download Signed Copy
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
            user_signatures = DocumentSignature.query.filter_by(
                document_id=doc_id,
                username=user.username
            ).all()
            signed_field_ids = set(sig.signature_field_id for sig in user_signatures)
            
            # Check if user has signed all required fields
            all_signed = all(f.id in signed_field_ids for f in required_fields)
            signed_count = len([f for f in required_fields if f.id in signed_field_ids])
            
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <a href="{{ url_for('admin_dashboard') }}" class="back-btn">← Back to Dashboard</a>
        </div>
        
        <div class="container">
            <div class="document-header">
                <h2>{{ document.original_filename }}</h2>
                <p>Form Signature Status - {{ required_fields|length }} required signature field(s)</p>
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
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% endif %}
            
            {% if unsigned_users %}
            <div class="section">
                <h2 class="section-title">✗ Users Who Have Not Signed</h2>
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
    
    # Check if file exists
    if not os.path.exists(document.file_path):
        flash('File not found on server.', 'error')
        return redirect(url_for('view_signed_documents', doc_id=doc_id))
    
    # Check if document is a PDF
    is_pdf = document.file_type == 'application/pdf' or document.original_filename.lower().endswith('.pdf')
    
    if not is_pdf:
        flash('Signed copies can only be generated for PDF documents.', 'error')
        return redirect(url_for('view_signed_documents', doc_id=doc_id))
    
    # Get all signatures by this user for this document
    user_signatures = DocumentSignature.query.filter_by(
        document_id=doc_id,
        username=username
    ).all()
    
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
        return redirect(url_for('view_signed_documents', doc_id=doc_id))
    
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
            
            # Send the signed PDF
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=download_filename,
                mimetype=document.file_type or 'application/pdf'
            )
        else:
            # No signatures or typed fields, or PyMuPDF not available
            if not FITZ_AVAILABLE:
                flash('PDF processing library not available. Please install PyMuPDF.', 'error')
            else:
                flash('No signatures or typed fields found for this user.', 'error')
            return redirect(url_for('view_signed_documents', doc_id=doc_id))
        
    except Exception as e:
        print(f"Error generating signed PDF: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error generating signed PDF: {str(e)}', 'error')
        return redirect(url_for('view_signed_documents', doc_id=doc_id))


@app.route('/admin/new-hire/<username>/details')
@admin_required
def view_new_hire_details(username):
    """View detailed information about a new hire including quiz results and signed forms"""
    new_hire = NewHire.query.filter_by(username=username).first()
    if not new_hire:
        flash('New hire not found.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Get training video progress and quiz results
    required_videos = list(new_hire.required_training_videos)
    video_progress = []
    
    for video in required_videos:
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
    
    # Get signed documents
    signed_documents = []
    all_signatures = DocumentSignature.query.filter_by(username=username).all()
    
    # Group signatures by document
    doc_signatures = {}
    for sig in all_signatures:
        doc_id = sig.document_id
        if doc_id not in doc_signatures:
            doc = Document.query.get(doc_id)
            if doc:
                doc_signatures[doc_id] = {
                    'document': doc,
                    'signatures': []
                }
        doc_signatures[doc_id]['signatures'].append(sig)
    
    signed_documents = list(doc_signatures.values())
    
    # Get user tasks
    user_tasks = UserTask.query.filter_by(username=username).all()
    
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
                font-size: 1em;
                font-weight: 500;
                font-family: inherit;
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
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
                                </select>
                            </td>
                        </tr>
                    </table>
                    <div style="margin-top: 25px; text-align: center;">
                        <button type="submit" class="btn" style="background: rgba(255,255,255,0.2); border: 2px solid white; font-size: 1.1em; padding: 12px 30px;">💾 Save Changes</button>
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
                        <h3 style="margin-bottom: 10px;">{{ doc_data.document.original_filename }}</h3>
                        <p style="color: #666; margin-bottom: 10px;">Signed {{ doc_data.signatures|length }} field(s)</p>
                        <div class="signature-preview">
                            {% for sig in doc_data.signatures %}
                            <img src="data:image/png;base64,{{ sig.signature_image }}" alt="Signature">
                            {% endfor %}
                        </div>
                        <p style="color: #666; font-size: 0.9em; margin-top: 10px;">
                            Signed on: {{ doc_data.signatures[0].signed_at.strftime('%B %d, %Y at %I:%M %p') if doc_data.signatures[0].signed_at else 'Unknown date' }}
                        </p>
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
         user_tasks=user_tasks, username=username)


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
        if status in ['pending', 'active', 'completed']:
            new_hire.status = status
        
        db.session.commit()
        flash('New hire details updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating new hire details: {str(e)}', 'error')
    
    return redirect(url_for('view_new_hire_details', username=username))


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
                
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%;">0%</div>
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
                document.getElementById('progressFill').textContent = percentage + '%';
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
    """List all users and allow admin to select one to view/update their checklist"""
    all_new_hires = NewHire.query.order_by(NewHire.first_name, NewHire.last_name).all()
    
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
                Ziebart Onboarding
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
                Ziebart Onboarding
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
                
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%;">0%</div>
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
                    {% else %}
                        <p style="color: #666;">No checklist items available. <a href="{{ url_for('manage_checklist') }}">Add some tasks</a> to get started.</p>
                    {% endif %}
                </form>
            </div>
        </div>
        
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
                document.getElementById('progressFill').textContent = percentage + '%';
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
    ''', new_hire=new_hire, checklist_items=checklist_items, user_completions=user_completions, username=username)


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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
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
                Ziebart Onboarding
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
    # Overall statistics
    total_new_hires = NewHire.query.count()
    total_users = UserModel.query.count()
    total_documents = Document.query.count()
    total_training_videos = TrainingVideo.query.filter_by(is_active=True).count()
    total_checklist_items = ChecklistItem.query.filter_by(is_active=True).count()
    
    # Training statistics
    total_training_progress = UserTrainingProgress.query.count()
    completed_trainings = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=True).count()
    failed_trainings = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=False).count()
    in_progress_trainings = UserTrainingProgress.query.filter_by(is_completed=False).count()
    
    # Document statistics
    visible_documents = Document.query.filter_by(is_visible=True).count()
    documents_with_signatures = Document.query.join(DocumentSignatureField).distinct().count()
    total_signatures = DocumentSignature.query.count()
    unique_signed_users = db.session.query(DocumentSignature.username).distinct().count()
    
    # Checklist statistics
    total_checklist_completions = NewHireChecklist.query.filter_by(is_completed=True).count()
    
    # User progress statistics
    all_new_hires = NewHire.query.all()
    user_progress_stats = []
    for new_hire in all_new_hires:
        # Training progress
        required_videos = list(new_hire.required_training_videos)
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
        
        # Task progress
        user_tasks = UserTask.query.filter_by(username=new_hire.username).all()
        completed_tasks = len([t for t in user_tasks if t.status == 'completed'])
        total_tasks = len(user_tasks)
        
        # Checklist progress
        checklist_completed = NewHireChecklist.query.filter_by(
            new_hire_id=new_hire.id,
            is_completed=True
        ).count()
        checklist_total = ChecklistItem.query.filter_by(is_active=True).count()
        
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
    
    # Sort by overall progress
    user_progress_stats.sort(key=lambda x: x['overall_progress'], reverse=True)
    
    # Department statistics
    department_stats = {}
    for new_hire in all_new_hires:
        dept = new_hire.department or 'Unassigned'
        if dept not in department_stats:
            department_stats[dept] = {'count': 0, 'completed': 0}
        department_stats[dept]['count'] += 1
        # Count completed users in this department
        user_stats = next((s for s in user_progress_stats if s['new_hire'].id == new_hire.id), None)
        if user_stats and user_stats['overall_progress'] == 100:
            department_stats[dept]['completed'] += 1
    
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
                min-width: 40px;
            }
            .section-title {
                font-size: 1.4em;
                font-weight: 600;
                margin-bottom: 20px;
                color: #000000;
                border-bottom: 2px solid #dc3545;
                padding-bottom: 10px;
            }
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
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
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {{ stats.overall_progress }}%;">
                                        {{ stats.overall_progress }}%
                                    </div>
                                </div>
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
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {{ (stats.completed / stats.count * 100) if stats.count > 0 else 0 }}%;">
                                        {{ "%.0f"|format((stats.completed / stats.count * 100) if stats.count > 0 else 0) }}%
                                    </div>
                                </div>
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
         user_progress_stats=user_progress_stats, department_stats=department_stats)


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
                font-size: 14px;
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
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/training')
@login_required
def list_training_videos():
    """List available training videos for users"""
    videos = TrainingVideo.query.filter_by(is_active=True).order_by(TrainingVideo.created_at.desc()).all()
    
    # Get user progress for each video
    user_progress = {}
    for video in videos:
        progress = UserTrainingProgress.query.filter_by(
            username=current_user.username,
            video_id=video.id
        ).order_by(UserTrainingProgress.attempt_number.desc()).first()
        user_progress[video.id] = progress
    
    # Get user info for header
    is_admin = current_user.is_admin()
    user_new_hire = NewHire.query.filter_by(username=current_user.username).first()
    user_first_name = user_new_hire.first_name if user_new_hire else current_user.username
    user_full_name = f"{user_new_hire.first_name} {user_new_hire.last_name}" if user_new_hire else current_user.username
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Harassment Training - Onboarding App</title>
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
            .container {
                max-width: 1600px;
                margin: 30px auto;
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
            }
            .training-list {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .training-card {
                background: white;
                padding: 20px;
                border-radius: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .training-card h3 {
                margin-bottom: 10px;
                color: #000000;
            }
            .training-card p {
                color: #808080;
                margin-bottom: 15px;
            }
            .progress-info {
                background: #f8f9fa;
                padding: 10px;
                border-radius: 5px;
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
        </style>
    </head>
    <body>
        <div class="top-header">
            <div class="logo-section">
                <img src="{{ url_for('serve_ziebart_logo') }}" alt="Ziebart Logo">
                Ziebart Onboarding
            </div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Home</a>
                <a href="{{ url_for('user_tasks') }}">Tasks</a>
                <a href="{{ url_for('view_documents') }}">Files</a>
                <a href="{{ url_for('profile') }}">Profile</a>
                {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}" style="background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 4px;">Admin Console</a>
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
                    {% if is_admin %}
                    <a href="{{ url_for('admin_dashboard') }}" class="dropdown-item">Admin Console</a>
                    <div class="dropdown-divider"></div>
                    {% endif %}
                    <a href="{{ url_for('logout') }}" class="dropdown-item">Logout</a>
                </div>
            </div>
        </div>
        
        <div class="container">
            
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
