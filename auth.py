"""
Windows Domain Authentication Module
Handles authentication using Windows domain credentials
Based on the domain login guide implementation
"""
import os
from flask import request, session
from flask_login import UserMixin
from functools import wraps
import config


class User(UserMixin):
    """User class for Flask-Login"""
    def __init__(self, username, domain=None, role='user'):
        self.id = username
        self.username = username
        self.domain = domain
        self.role = role  # 'admin' or 'user'
        self.full_username = f"{domain}\\{username}" if domain else username
    
    def is_admin(self):
        """Check if user is an admin"""
        return self.role == 'admin'

    def is_manager(self):
        """Check if user is a manager"""
        return self.role == 'manager'

    def __repr__(self):
        return f'<User {self.full_username} ({self.role})>'


def get_current_user():
    """
    Get current Windows domain user
    Based on the domain login guide implementation
    
    Returns: DOMAIN\\username format (e.g., ZIEBART\\asymons)
    """
    # Try to get the authenticated user from IIS (Windows Authentication)
    remote_user = request.environ.get('REMOTE_USER')
    if remote_user:
        return remote_user
    
    # Fallback to Windows API for development/testing
    try:
        import win32api
        return win32api.GetUserNameEx(win32api.NameSamCompatible)
    except Exception:
        try:
            import getpass
            return getpass.getuser()
        except Exception as e:
            print(f"Error getting Windows username: {str(e)}")
            return None


def get_windows_user():
    """
    Get Windows authenticated user and parse domain\\username format
    Returns: (username, domain) tuple
    """
    full_username = get_current_user()
    
    if not full_username:
        return None, None
    
    # Parse domain\username format
    if '\\' in full_username:
        domain, username = full_username.split('\\', 1)
        return username, domain
    else:
        # No domain prefix, use configured domain
        return full_username, config.DOMAIN_NAME


def get_user_role(username, domain=None, check_db=True):
    """
    Determine user role (admin or regular user)
    Checks database first, then falls back to config
    """
    # Check database for user role if requested
    if check_db:
        try:
            from models import User as UserModel
            from app import app
            with app.app_context():
                user_record = UserModel.query.filter_by(username=username).first()
                if user_record and user_record.role == 'admin':
                    return 'admin'
        except Exception:
            pass  # Fall back to config if DB check fails
    
    # Check if username is in admin list from config
    if username.lower() in [admin.lower() for admin in config.ADMIN_USERS if admin]:
        return 'admin'
    
    # Default to 'user'
    return 'user'


def check_user_can_login_as_admin(username, domain=None):
    """
    Check if user can login as admin
    Returns True if user has admin role in database or config
    """
    role = get_user_role(username, domain, check_db=True)
    return role == 'admin'


def authenticate_user(role_override=None):
    """
    Authenticate user using Windows domain authentication
    Args:
        role_override: Optional role to use ('admin' or 'user')
                      If provided, validates that user can use that role
    Returns User object if authenticated, None otherwise
    """
    username, domain = get_windows_user()
    
    if not username:
        return None
    
    # Determine user role
    if role_override:
        # Validate that user can use the requested role
        if role_override == 'admin':
            if not check_user_can_login_as_admin(username, domain):
                return None  # User cannot login as admin
            role = 'admin'
        else:
            role = 'user'
    else:
        # Auto-detect role from database/config
        role = get_user_role(username, domain, check_db=True)
    
    # Create user object
    user = User(username, domain, role)
    
    return user


def login_required(f):
    """
    Decorator to require authentication
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        
        if not current_user.is_authenticated:
            # Try to authenticate using Windows auth
            user = authenticate_user()
            if user:
                from flask_login import login_user
                login_user(user, remember=True)
                return f(*args, **kwargs)
            else:
                from flask import redirect, url_for
                return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    
    return decorated_function


def admin_required(f):
    """
    Decorator to require admin role
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        
        if not current_user.is_admin():
            from flask import abort
            abort(403)  # Forbidden
        
        return f(*args, **kwargs)
    
    return decorated_function


def manager_required(f):
    """
    Decorator to require manager or admin role
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        
        if not (getattr(current_user, 'is_manager', lambda: False)() or current_user.is_admin()):
            from flask import abort
            abort(403)  # Forbidden
        
        return f(*args, **kwargs)
    
    return decorated_function


def authenticate_by_email_password(email, password):
    """
    Authenticate by email and password. Returns auth.User if valid, None otherwise.
    """
    if not email or not password:
        return None
    from werkzeug.security import check_password_hash
    from models import User as UserModel
    from app import app
    from datetime import date
    with app.app_context():
        user = UserModel.query.filter_by(email=email.strip().lower()).first()
        if not user or not user.password_hash:
            return None
        if user.access_revoked_at and date.today() >= user.access_revoked_at:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        return User(
            username=user.username,
            domain=getattr(user, 'domain', None),
            role=(user.role or 'user')
        )
