"""Runtime schema ensure-* helpers (idempotent ALTER/CREATE on MSSQL)."""
from __future__ import annotations

import re

from flask import current_app
from sqlalchemy import text, func

from models import db, Department


_users_access_revoked_at_migrated = False
_users_role_migrated = False
_users_domain_migrated = False
_users_last_login_migrated = False
_users_must_change_password_migrated = False
_users_saved_signature_migrated = False
_document_signatures_savedflag_migrated = False
_signature_audit_logs_migrated = False
_new_hires_finale_migrated = False
_admin_settings_table_migrated = False
_stores_migrated = False
_departments_migrated = False
_document_typed_field_cols_migrated = False


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


_users_role_migrated = False


def _ensure_users_role_column():
    """Ensure users.role exists (one-time migration). Default 'user' for existing rows."""
    global _users_role_migrated
    if _users_role_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 role FROM users"))
        _users_role_migrated = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE users ADD role NVARCHAR(20) NULL"))
            db.session.commit()
            db.session.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        _users_role_migrated = True


_users_domain_migrated = False


def _ensure_users_domain_column():
    """Ensure users.domain exists (one-time migration)."""
    global _users_domain_migrated
    if _users_domain_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 domain FROM users"))
        _users_domain_migrated = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE users ADD domain NVARCHAR(100) NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        _users_domain_migrated = True


_users_last_login_migrated = False


def _ensure_users_last_login_column():
    """Ensure users.last_login exists (one-time migration)."""
    global _users_last_login_migrated
    if _users_last_login_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 last_login FROM users"))
        _users_last_login_migrated = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE users ADD last_login DATETIME NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        _users_last_login_migrated = True


_users_saved_signature_migrated = False
_users_must_change_password_migrated = False


def _ensure_users_must_change_password_column():
    """Ensure users.must_change_password exists for forced password change after reset email."""
    global _users_must_change_password_migrated
    if _users_must_change_password_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 must_change_password FROM users"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE users ADD must_change_password BIT NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    _users_must_change_password_migrated = True


def _ensure_users_saved_signature_columns():
    """Ensure users has saved signature columns for reusable signature feature."""
    global _users_saved_signature_migrated
    if _users_saved_signature_migrated:
        return
    for col, sql_type in [
        ('saved_signature_image', 'NVARCHAR(MAX) NULL'),
        ('saved_signature_kind', 'NVARCHAR(20) NULL'),
        ('saved_signature_updated_at', 'DATETIME NULL'),
    ]:
        try:
            db.session.execute(text(f"SELECT TOP 1 {col} FROM users"))
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text(f"ALTER TABLE users ADD {col} {sql_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    _users_saved_signature_migrated = True


_document_signatures_savedflag_migrated = False


def _ensure_document_signatures_savedflag_column():
    """Ensure document_signatures.used_saved_signature exists."""
    global _document_signatures_savedflag_migrated
    if _document_signatures_savedflag_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 used_saved_signature FROM document_signatures"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE document_signatures ADD used_saved_signature BIT NULL"))
            db.session.commit()
            db.session.execute(text("UPDATE document_signatures SET used_saved_signature = 0 WHERE used_saved_signature IS NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    _document_signatures_savedflag_migrated = True


_signature_audit_logs_migrated = False


def _ensure_signature_audit_logs_table():
    """Create signature_audit_logs table if it does not exist."""
    global _signature_audit_logs_migrated
    if _signature_audit_logs_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 id FROM signature_audit_logs"))
        _signature_audit_logs_migrated = True
        return
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text(
            "CREATE TABLE signature_audit_logs ("
            "id INT PRIMARY KEY IDENTITY(1,1), "
            "document_id INT NOT NULL, "
            "username NVARCHAR(100) NOT NULL, "
            "event_type NVARCHAR(80) NOT NULL, "
            "details NVARCHAR(MAX) NULL, "
            "used_saved_signature BIT NULL, "
            "signed_copy_path NVARCHAR(500) NULL, "
            "ip_address NVARCHAR(50) NULL, "
            "user_agent NVARCHAR(MAX) NULL, "
            "created_at DATETIME NULL"
            ")"
        ))
        db.session.commit()
        try:
            db.session.execute(text(
                "CREATE INDEX ix_signature_audit_logs_doc_user "
                "ON signature_audit_logs (document_id, username)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        _signature_audit_logs_migrated = True
    except Exception:
        db.session.rollback()


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
        ('all_tasks_completed_email_sent_at', 'DATETIME NULL'),
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
        db.session.execute(text("SELECT TOP 1 [key] FROM admin_settings"))
        _admin_settings_table_migrated = True
        return
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text(
            "CREATE TABLE admin_settings ([key] NVARCHAR(100) PRIMARY KEY, value NVARCHAR(MAX) NULL)"
        ))
        db.session.commit()
        _admin_settings_table_migrated = True
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning("admin_settings table create failed: %s", e)
        # Do not set migrated=True so we retry on next request



def _ensure_stores_and_store_id():
    """Create stores table and add store_id to users, new_hires, documents; create manager_permissions."""
    global _stores_migrated
    if _stores_migrated:
        return
    try:
        db.session.execute(text("SELECT TOP 1 id FROM stores"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                "CREATE TABLE stores (id INT PRIMARY KEY IDENTITY(1,1), name NVARCHAR(200) NOT NULL, code NVARCHAR(50) NULL, created_at DATETIME NULL)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
    for table, col in [('users', 'store_id'), ('new_hires', 'store_id'), ('documents', 'store_id')]:
        try:
            db.session.execute(text(f"SELECT TOP 1 {col} FROM {table}"))
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text(f"ALTER TABLE {table} ADD {col} INT NULL"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    try:
        db.session.execute(text("SELECT TOP 1 id FROM manager_permissions"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                "CREATE TABLE manager_permissions (id INT PRIMARY KEY IDENTITY(1,1), user_id INT NOT NULL, permission_key NVARCHAR(80) NOT NULL)"
            ))
            db.session.commit()
            try:
                db.session.execute(text("CREATE UNIQUE INDEX uq_manager_permission ON manager_permissions (user_id, permission_key)"))
                db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text("SELECT TOP 1 document_id FROM document_stores"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                "CREATE TABLE document_stores (document_id INT NOT NULL, store_id INT NOT NULL, "
                "PRIMARY KEY (document_id, store_id), "
                "FOREIGN KEY (document_id) REFERENCES documents(id), "
                "FOREIGN KEY (store_id) REFERENCES stores(id))"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(text(
                "INSERT INTO document_stores (document_id, store_id) SELECT id, store_id FROM documents WHERE store_id IS NOT NULL"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text("SELECT TOP 1 video_id FROM training_video_stores"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                "CREATE TABLE training_video_stores (video_id INT NOT NULL, store_id INT NOT NULL, "
                "PRIMARY KEY (video_id, store_id), "
                "FOREIGN KEY (video_id) REFERENCES training_videos(id), "
                "FOREIGN KEY (store_id) REFERENCES stores(id))"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
    _stores_migrated = True


_departments_migrated = False


def _ensure_departments_table():
    """Create departments table and seed from existing new_hires.department strings."""
    global _departments_migrated
    if _departments_migrated:
        return
    try:
        db.session.execute(text('SELECT TOP 1 id FROM departments'))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                'CREATE TABLE departments (id INT PRIMARY KEY IDENTITY(1,1), '
                'name NVARCHAR(150) NOT NULL UNIQUE, created_at DATETIME NULL)'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text('SELECT TOP 1 department_id FROM new_hires'))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text('ALTER TABLE new_hires ADD department_id INT NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        rows = db.session.execute(text(
            "SELECT DISTINCT LTRIM(RTRIM(department)) AS dept_name FROM new_hires "
            "WHERE department IS NOT NULL AND LTRIM(RTRIM(department)) <> ''"
        )).fetchall()
        for row in rows:
            dept_name = (row[0] or '').strip()
            if not dept_name:
                continue
            existing = Department.query.filter(
                func.lower(Department.name) == dept_name.lower()
            ).first()
            if not existing:
                db.session.add(Department(name=dept_name))
        db.session.commit()
        nh_rows = db.session.execute(text(
            'SELECT id, department FROM new_hires WHERE department IS NOT NULL '
            "AND LTRIM(RTRIM(department)) <> '' AND department_id IS NULL"
        )).fetchall()
        for nh_id, dept_str in nh_rows:
            dept_name = (dept_str or '').strip()
            if not dept_name:
                continue
            dept = Department.query.filter(func.lower(Department.name) == dept_name.lower()).first()
            if dept:
                db.session.execute(
                    text('UPDATE new_hires SET department_id = :did WHERE id = :nid'),
                    {'did': dept.id, 'nid': nh_id},
                )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('departments seed/migrate failed: %s', e)
    _departments_migrated = True


def _ensure_document_typed_field_columns():
    """Ensure document_typed_fields has choice_group for checkbox groups."""
    global _document_typed_field_cols_migrated
    if _document_typed_field_cols_migrated:
        return
    try:
        db.session.execute(text('SELECT TOP 1 choice_group FROM document_typed_fields'))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text('ALTER TABLE document_typed_fields ADD choice_group NVARCHAR(100) NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    _document_typed_field_cols_migrated = True


def _ensure_user_task_order_columns():
    """Ensure user_tasks has display_order and depends_on_task_id for ordering and dependencies."""
    try:
        db.session.execute(text("SELECT TOP 1 display_order FROM user_tasks"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE user_tasks ADD display_order INT NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text("SELECT TOP 1 depends_on_task_id FROM user_tasks"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE user_tasks ADD depends_on_task_id INT NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()


_help_tables_migrated = False
_password_reset_migrated = False


def _ensure_password_reset_schema():
    """Ensure users.password_changed_at and password_reset_tokens exist."""
    global _password_reset_migrated
    if _password_reset_migrated:
        return
    try:
        db.session.execute(text('SELECT TOP 1 password_changed_at FROM users'))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text('ALTER TABLE users ADD password_changed_at DATETIME NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text('SELECT TOP 1 id FROM password_reset_tokens'))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                'CREATE TABLE password_reset_tokens ('
                'id INT PRIMARY KEY IDENTITY(1,1), '
                'user_id INT NOT NULL, '
                'token_hash NVARCHAR(64) NOT NULL, '
                'expires_at DATETIME NOT NULL, '
                'used_at DATETIME NULL, '
                'created_at DATETIME NOT NULL, '
                'requested_ip NVARCHAR(50) NULL'
                ')'
            ))
            db.session.execute(text(
                'CREATE UNIQUE INDEX uq_password_reset_tokens_hash ON password_reset_tokens(token_hash)'
            ))
            db.session.execute(text(
                'CREATE INDEX ix_password_reset_tokens_user ON password_reset_tokens(user_id)'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            return
    _password_reset_migrated = True


def _ensure_help_tables():
    """Ensure help_articles and help_requests tables exist; seed starter articles."""
    global _help_tables_migrated
    if _help_tables_migrated:
        return
    articles_ok = False
    requests_ok = False
    try:
        db.session.execute(text('SELECT TOP 1 id FROM help_articles'))
        articles_ok = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                'CREATE TABLE help_articles ('
                'id INT PRIMARY KEY IDENTITY(1,1), '
                'title NVARCHAR(200) NOT NULL, '
                'slug NVARCHAR(220) NOT NULL, '
                'body NVARCHAR(MAX) NOT NULL, '
                'audience NVARCHAR(20) NOT NULL DEFAULT \'all\', '
                'permission_key NVARCHAR(80) NULL, '
                'related_path NVARCHAR(300) NULL, '
                'tags NVARCHAR(300) NULL, '
                'is_published BIT NOT NULL DEFAULT 1, '
                'sort_order INT NOT NULL DEFAULT 0, '
                'created_by NVARCHAR(100) NULL, '
                'created_at DATETIME NULL, '
                'updated_at DATETIME NULL'
                ')'
            ))
            db.session.execute(text(
                'CREATE UNIQUE INDEX uq_help_articles_slug ON help_articles(slug)'
            ))
            db.session.commit()
            articles_ok = True
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text('SELECT TOP 1 id FROM help_requests'))
        requests_ok = True
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text(
                'CREATE TABLE help_requests ('
                'id INT PRIMARY KEY IDENTITY(1,1), '
                'user_id INT NOT NULL, '
                'username NVARCHAR(100) NOT NULL, '
                'store_id INT NULL, '
                'role NVARCHAR(20) NULL, '
                'question NVARCHAR(MAX) NOT NULL, '
                'page_path NVARCHAR(500) NULL, '
                'status NVARCHAR(20) NOT NULL DEFAULT \'open\', '
                'admin_reply NVARCHAR(MAX) NULL, '
                'answered_by NVARCHAR(100) NULL, '
                'answered_at DATETIME NULL, '
                'created_at DATETIME NULL'
                ')'
            ))
            db.session.commit()
            requests_ok = True
        except Exception:
            db.session.rollback()
    if articles_ok:
        try:
            from services.help_content import ensure_seed_help_articles
            ensure_seed_help_articles()
        except Exception as e:
            current_app.logger.warning('help articles seed failed: %s', e)
    if articles_ok and requests_ok:
        _help_tables_migrated = True


def _run_users_migration_if_needed():
    """Run schema checks/migrations (safe at startup or on demand)."""
    try:
        _ensure_users_access_revoked_at_column()
        _ensure_users_role_column()
        _ensure_users_domain_column()
        _ensure_users_last_login_column()
        _ensure_users_saved_signature_columns()
        _ensure_users_must_change_password_column()
        _ensure_document_signatures_savedflag_column()
        _ensure_new_hires_finale_columns()
        _ensure_admin_settings_table()
        _ensure_stores_and_store_id()
        _ensure_departments_table()
        _ensure_signature_audit_logs_table()
        _ensure_help_tables()
        _ensure_password_reset_schema()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Schema migration failed')
        raise

