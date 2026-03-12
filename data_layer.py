"""
Single data access layer: uses Data API when API_BASE_URL is set, else direct DB.
When config.USE_DATA_API is True, the main app should ONLY use this module (no models/db imports).
Returned values are dict-like objects with attribute access (e.g. .role, .store_id) for compatibility.
"""
import config
from types import SimpleNamespace


def _obj(d):
    """Turn dict into object with attribute access."""
    if d is None:
        return None
    if isinstance(d, SimpleNamespace):
        return d
    return SimpleNamespace(**{k: v for k, v in (d or {}).items() if k is not None})


def _objs(list_of_dicts):
    return [_obj(d) for d in (list_of_dicts or [])]


# ---- User ----
def list_users(store_id=None, role=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_users as api_list
            return _objs(api_list(store_id=store_id, role=role))
        except Exception:
            return []
    from models import User as UserModel
    q = UserModel.query
    if store_id is not None:
        q = q.filter_by(store_id=store_id)
    if role is not None:
        q = q.filter_by(role=role)
    return q.order_by(UserModel.username).all()


def get_user_by_id(user_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_by_id as api_get
            return _obj(api_get(user_id))
        except Exception:
            return None
    from models import User as UserModel
    return UserModel.query.get(user_id)


def get_user(username):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_by_username
            return _obj(get_user_by_username(username))
        except Exception:
            return None
    from models import User as UserModel
    r = UserModel.query.filter_by(username=username).first()
    return r


def get_current_user_store_id():
    """Return store_id for current user. Requires flask_login.current_user."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return None
    u = get_user(current_user.username)
    return getattr(u, 'store_id', None) if u else None


# ---- New hire ----
def get_new_hire(username):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_new_hire_by_username
            return _obj(get_new_hire_by_username(username))
        except Exception:
            return None
    from models import NewHire
    return NewHire.query.filter_by(username=username).first()


def list_new_hires():
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_new_hires as api_list
            return _objs(api_list())
        except Exception:
            return []
    from models import NewHire
    return NewHire.query.order_by(NewHire.created_at.desc()).all()


# ---- Documents ----
def list_documents(active_only=True, is_visible=None, store_id=None, document_store_id=None):
    """active_only=False returns archived. store_id=visible-to-store; document_store_id=documents where document.store_id=this."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_documents as api_list
            return _objs(api_list(is_visible=is_visible, deleted_at_null=active_only, store_id=store_id, document_store_id=document_store_id))
        except Exception:
            return []
    from models import Document
    from models import document_stores
    from sqlalchemy import exists, or_, and_
    q = Document.query
    if active_only:
        q = q.filter(Document.deleted_at.is_(None))
    else:
        q = q.filter(Document.deleted_at.isnot(None))
    if is_visible is not None:
        q = q.filter(Document.is_visible == is_visible)
    if store_id is not None:
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id))
        q = q.filter(or_(no_stores, in_store))
    if document_store_id is not None:
        q = q.filter(Document.store_id == document_store_id)
    return q.order_by(Document.created_at.desc()).all()


def count_documents(archived_only=False, store_id=None, document_store_id=None, is_visible=None):
    """archived_only=True counts only soft-deleted documents."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import count_documents as api_count
            return api_count(deleted_at_null=not archived_only, store_id=store_id, document_store_id=document_store_id, is_visible=is_visible)
        except Exception:
            return 0
    from models import Document
    from models import document_stores
    from sqlalchemy import exists, or_, and_
    q = Document.query
    if archived_only:
        q = q.filter(Document.deleted_at.isnot(None))
    else:
        q = q.filter(Document.deleted_at.is_(None))
    if is_visible is not None:
        q = q.filter(Document.is_visible == is_visible)
    if store_id is not None:
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id))
        q = q.filter(or_(no_stores, in_store))
    if document_store_id is not None:
        q = q.filter(Document.store_id == document_store_id)
    return q.count()


def list_documents_with_signature_fields(active_only=True):
    """Documents that have at least one signature field."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_documents_with_signature_fields as api_list
            return _objs(api_list(deleted_at_null=active_only))
        except Exception:
            return []
    from models import Document
    from models import DocumentSignatureField
    q = Document.query.join(DocumentSignatureField).distinct()
    if active_only:
        q = q.filter(Document.deleted_at.is_(None))
    return q.order_by(Document.created_at.desc()).all()


def list_document_signatures(document_id=None, signature_field_id=None, username=None):
    """Return list of signature objects. Pass one or more of document_id, signature_field_id, username."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_document_signatures as api_list
            return _objs(api_list(document_id=document_id, signature_field_id=signature_field_id, username=username))
        except Exception:
            return []
    from models import DocumentSignature
    q = DocumentSignature.query
    if document_id is not None:
        q = q.filter_by(document_id=document_id)
    if signature_field_id is not None:
        q = q.filter_by(signature_field_id=signature_field_id)
    if username is not None:
        q = q.filter_by(username=username)
    return q.all()


def list_user_notifications(username, notification_type=None, notification_id=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_user_notifications as api_list
            return _objs(api_list(username, notification_type=notification_type, notification_id=notification_id))
        except Exception:
            return []
    from models import UserNotification
    q = UserNotification.query.filter_by(username=username)
    if notification_type is not None:
        q = q.filter_by(notification_type=notification_type)
    if notification_id is not None:
        q = q.filter_by(notification_id=notification_id)
    return q.order_by(UserNotification.created_at.desc()).all()


def get_user_notification(username, notification_type, notification_id):
    """Get one notification by (username, type, notification_id). Returns first match or None."""
    lst = list_user_notifications(username, notification_type=notification_type, notification_id=notification_id)
    return lst[0] if lst else None


def get_user_notification_by_id(notification_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_notification_by_id as api_get
            return _obj(api_get(notification_id))
        except Exception:
            return None
    from models import UserNotification
    return UserNotification.query.get(notification_id)


def list_external_links(active_only=True):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_external_links as api_list
            return _objs(api_list(is_active=active_only))
        except Exception:
            return []
    from models import ExternalLink
    q = ExternalLink.query
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(ExternalLink.order, ExternalLink.created_at).all()


def get_external_link(link_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_external_link as api_get
            return _obj(api_get(link_id))
        except Exception:
            return None
    from models import ExternalLink
    return ExternalLink.query.get(link_id)


def get_document(doc_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_document as api_get
            return _obj(api_get(doc_id))
        except Exception:
            return None
    from models import Document
    return Document.query.get(doc_id)


# ---- Stores ----
def list_stores():
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_stores as api_list
            return _objs(api_list())
        except Exception:
            return []
    from models import Store
    return Store.query.order_by(Store.name).all()


def get_store(store_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_store as api_get
            return _obj(api_get(store_id))
        except Exception:
            return None
    from models import Store
    return Store.query.get(store_id)


# ---- Training videos ----
def list_training_videos(active_only=True):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_training_videos as api_list
            items = api_list()
            if active_only:
                items = [x for x in items if x.get("is_active") in (True, 1)]
            return _objs(items)
        except Exception:
            return []
    from models import TrainingVideo
    q = TrainingVideo.query
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(TrainingVideo.created_at.desc()).all()


def get_training_video(video_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_training_video as api_get
            return _obj(api_get(video_id))
        except Exception:
            return None
    from models import TrainingVideo
    return TrainingVideo.query.get(video_id)


def get_new_hire_required_video_ids(new_hire_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_new_hire_required_video_ids as api_get
            return api_get(new_hire_id) or []
        except Exception:
            return []
    from sqlalchemy import text
    from models import db
    r = db.session.execute(text("SELECT video_id FROM new_hire_required_training WHERE new_hire_id = :id"), {"id": new_hire_id})
    return [row[0] for row in r.fetchall()]


def list_user_tasks(username):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_user_tasks as api_list
            return _objs(api_list(username))
        except Exception:
            return []
    from models import UserTask
    return UserTask.query.filter_by(username=username).order_by(UserTask.created_at.desc()).all()


def list_user_training_progress(username=None, video_id=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_user_training_progress as api_list
            return _objs(api_list(username=username, video_id=video_id))
        except Exception:
            return []
    from models import UserTrainingProgress
    q = UserTrainingProgress.query
    if username is not None:
        q = q.filter_by(username=username)
    if video_id is not None:
        q = q.filter_by(video_id=video_id)
    return q.order_by(UserTrainingProgress.username, UserTrainingProgress.attempt_number.desc()).all()


def get_user_training_progress_latest(username, video_id):
    """Return latest progress record (by attempt_number desc) or None."""
    if getattr(config, 'USE_DATA_API', False):
        lst = list_user_training_progress(username=username, video_id=video_id)
        if not lst:
            return None
        lst = sorted(lst, key=lambda p: (getattr(p, 'attempt_number', p.get('attempt_number')) or 0), reverse=True)
        return lst[0]
    from models import UserTrainingProgress
    return UserTrainingProgress.query.filter_by(username=username, video_id=video_id).order_by(UserTrainingProgress.attempt_number.desc()).first()


def get_user_training_progress_by_id(progress_id):
    """Return one progress record by id or None."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_training_progress_by_id as api_get
            return _obj(api_get(progress_id))
        except Exception:
            return None
    from models import UserTrainingProgress
    return UserTrainingProgress.query.get(progress_id)


def get_user_training_progress_stats():
    """Return dict with total, completed_passed, completed_failed, in_progress for admin reports."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_training_progress_stats as api_stats
            return api_stats()
        except Exception:
            return {"total": 0, "completed_passed": 0, "completed_failed": 0, "in_progress": 0}
    from models import UserTrainingProgress
    from sqlalchemy import case, func
    total = UserTrainingProgress.query.count()
    completed_passed = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=True).count()
    completed_failed = UserTrainingProgress.query.filter_by(is_completed=True, is_passed=False).count()
    in_progress = UserTrainingProgress.query.filter(UserTrainingProgress.is_completed == False).count()
    return {"total": total, "completed_passed": completed_passed, "completed_failed": completed_failed, "in_progress": in_progress}


def list_document_assignments(username=None, document_id=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_document_assignments as api_list
            return _objs(api_list(username=username, document_id=document_id))
        except Exception:
            return []
    from models import DocumentAssignment
    q = DocumentAssignment.query
    if username is not None:
        q = q.filter_by(username=username)
    if document_id is not None:
        q = q.filter_by(document_id=document_id)
    return q.order_by(DocumentAssignment.assigned_at.desc()).all()


def get_document_assignment(document_id, username):
    """Return first assignment for document_id + username, or None."""
    lst = list_document_assignments(document_id=document_id, username=username)
    return lst[0] if lst else None


def list_document_signature_fields(document_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_document_signature_fields as api_list
            return _objs(api_list(document_id))
        except Exception:
            return []
    from models import DocumentSignatureField
    return DocumentSignatureField.query.filter_by(document_id=document_id).order_by(
        DocumentSignatureField.page_number, DocumentSignatureField.id
    ).all()


def list_checklist_items():
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_checklist_items as api_list
            return _objs(api_list())
        except Exception:
            return []
    from models import ChecklistItem
    return ChecklistItem.query.filter_by(is_active=True).order_by(ChecklistItem.order, ChecklistItem.id).all()


def list_roles():
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_roles as api_list
            return _objs(api_list())
        except Exception:
            return []
    from models import Role
    return Role.query.order_by(Role.name).all()


def count_users(store_id=None, role=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import count_users as api_count
            return api_count(store_id=store_id, role=role)
        except Exception:
            return 0
    from models import User as UserModel
    q = UserModel.query
    if store_id is not None:
        q = q.filter_by(store_id=store_id)
    if role is not None:
        q = q.filter_by(role=role)
    return q.count()


def count_new_hires(status_filter=None):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import count_new_hires as api_count
            return api_count(status_filter=status_filter)
        except Exception:
            return 0
    from models import NewHire
    if status_filter:
        return NewHire.query.filter(NewHire.status != status_filter).count()
    return NewHire.query.count()


def get_manager_permissions(user_id):
    """Return list of permission objects (with .permission_key) for a manager."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_manager_permissions as api_list
            return _objs(api_list(user_id))
        except Exception:
            return []
    from models import ManagerPermission
    return ManagerPermission.query.filter_by(user_id=user_id).all()


def get_user_task(task_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_user_task as api_get
            return _obj(api_get(task_id))
        except Exception:
            return None
    from models import UserTask
    return UserTask.query.get(task_id)


def get_document_assignment_by_id(assignment_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_document_assignment as api_get
            return _obj(api_get(assignment_id))
        except Exception:
            return None
    from models import DocumentAssignment
    return DocumentAssignment.query.get(assignment_id)


def get_document_signature_field(field_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_document_signature_field as api_get
            return _obj(api_get(field_id))
        except Exception:
            return None
    from models import DocumentSignatureField
    return DocumentSignatureField.query.get(field_id)


def get_checklist_item(item_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_checklist_item as api_get
            return _obj(api_get(item_id))
        except Exception:
            return None
    from models import ChecklistItem
    return ChecklistItem.query.get(item_id)


def get_role(role_id):
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import get_role as api_get
            return _obj(api_get(role_id))
        except Exception:
            return None
    from models import Role
    return Role.query.get(role_id)


def list_documents_visible_to_store(store_id=None):
    """Documents visible to store (or all visible if store_id is None). Replaces documents_visible_to_store_query().all()."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_documents_visible_to_store as api_list
            return _objs(api_list(store_id))
        except Exception:
            return []
    from models import Document
    from models import document_stores
    from sqlalchemy import exists, or_, and_
    q = Document.query.filter(Document.is_visible == True, Document.deleted_at.is_(None))
    if store_id is not None:
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id))
        q = q.filter(or_(no_stores, in_store))
    return q.order_by(Document.created_at.desc()).all()


def list_new_hires_filtered(status_exclude=None):
    """List new hires, optionally excluding status (e.g. 'removed')."""
    if getattr(config, 'USE_DATA_API', False):
        try:
            from api_client import list_new_hires_filtered as api_list
            return _objs(api_list(status_exclude=status_exclude))
        except Exception:
            return []
    from models import NewHire
    q = NewHire.query
    if status_exclude:
        q = q.filter(NewHire.status != status_exclude)
    return q.order_by(NewHire.created_at.desc()).all()
