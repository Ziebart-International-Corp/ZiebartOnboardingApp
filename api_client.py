"""
HTTP client for the Data API. Use when config.USE_DATA_API is True (API_BASE_URL set).
No direct DB access in the main app when using this.
"""
import requests
import config

_BASE = config.API_BASE_URL
_HEADERS = {}
if config.DATA_API_KEY:
    _HEADERS["X-API-Key"] = config.DATA_API_KEY


def _get(path, params=None):
    r = requests.get(f"{_BASE}{path}", params=params, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else None


def _get_list(path, params=None):
    out = _get(path, params=params)
    return out if isinstance(out, list) else []


def get_user_by_email(email):
    """Return user dict (including password_hash) or None. For server-side login only."""
    try:
        return _get("/users/by-email", params={"email": email})
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_user_by_username(username):
    """Return user dict or None."""
    try:
        return _get(f"/users/by-username/{username}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_user_by_id(user_id):
    """Return user dict or None."""
    try:
        return _get(f"/users/{user_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_new_hire_by_username(username):
    """Return new_hire dict or None."""
    try:
        return _get(f"/new-hires/by-username/{username}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def list_documents(is_visible=None, deleted_at_null=True, store_id=None, document_store_id=None):
    """Return list of document dicts. deleted_at_null=False for archived only. document_store_id = docs where document.store_id = this."""
    params = {}
    if is_visible is not None:
        params["is_visible"] = str(is_visible).lower()
    params["deleted_at_null"] = str(deleted_at_null).lower()
    if store_id is not None:
        params["store_id"] = store_id
    if document_store_id is not None:
        params["document_store_id"] = document_store_id
    return _get_list("/documents", params=params)


def count_documents(deleted_at_null=True, store_id=None, document_store_id=None, is_visible=None):
    """Return count of documents. deleted_at_null=False for archived count."""
    params = {"deleted_at_null": str(deleted_at_null).lower()}
    if store_id is not None:
        params["store_id"] = store_id
    if document_store_id is not None:
        params["document_store_id"] = document_store_id
    if is_visible is not None:
        params["is_visible"] = str(is_visible).lower()
    try:
        out = _get("/documents/count", params=params)
        return out.get("count", 0) if isinstance(out, dict) else 0
    except Exception:
        return 0


def list_documents_with_signature_fields(deleted_at_null=True):
    """Documents that have at least one signature field."""
    return _get_list("/documents/with-signature-fields", params={"deleted_at_null": str(deleted_at_null).lower()})


def list_document_signatures(document_id=None, signature_field_id=None, username=None):
    """Return list of signature dicts. Pass one or more of document_id, signature_field_id, username."""
    params = {}
    if document_id is not None:
        params["document_id"] = document_id
    if signature_field_id is not None:
        params["signature_field_id"] = signature_field_id
    if username is not None:
        params["username"] = username
    return _get_list("/document-signatures", params=params if params else None)


def list_user_notifications(username, notification_type=None, notification_id=None):
    """Return list of user notification dicts."""
    params = {"username": username}
    if notification_type is not None:
        params["notification_type"] = notification_type
    if notification_id is not None:
        params["notification_id"] = notification_id
    return _get_list("/user-notifications", params=params)


def get_user_notification_by_id(notification_id):
    try:
        return _get(f"/user-notifications/{notification_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def list_external_links(is_active=True):
    """Return list of external link dicts. is_active=True for dashboard, None for all."""
    params = {}
    if is_active is not None:
        params["is_active"] = str(is_active).lower()
    return _get_list("/external-links", params=params if params else None)


def get_external_link(link_id):
    try:
        return _get(f"/external-links/{link_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_document(doc_id):
    """Return document dict or None."""
    try:
        return _get(f"/documents/{doc_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def list_stores():
    """Return list of store dicts."""
    return _get_list("/stores")


def get_store(store_id):
    """Return store dict or None."""
    try:
        return _get(f"/stores/{store_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def list_users(store_id=None, role=None):
    """Return list of user dicts. Optional store_id and role filters."""
    params = {}
    if store_id is not None:
        params["store_id"] = store_id
    if role is not None:
        params["role"] = role
    return _get_list("/users", params=params if params else None)


def list_new_hires():
    """Return list of new_hire dicts."""
    return _get_list("/new-hires")


def list_training_videos():
    """Return list of training video dicts."""
    return _get_list("/training-videos")


def get_training_video(video_id):
    """Return training video dict or None."""
    try:
        return _get(f"/training-videos/{video_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_new_hire_required_video_ids(new_hire_id):
    """Return list of video_id for required training for a new hire."""
    try:
        return _get(f"/new-hires/{new_hire_id}/required-video-ids") or []
    except Exception:
        return []


def list_user_tasks(username):
    """Return list of user task dicts for username."""
    return _get_list("/user-tasks", params={"username": username})


def list_user_training_progress(username=None, video_id=None):
    """Return list of user training progress dicts. Pass username and/or video_id."""
    params = {}
    if username is not None:
        params["username"] = username
    if video_id is not None:
        params["video_id"] = video_id
    return _get_list("/user-training-progress", params=params if params else None)


def get_user_training_progress_by_id(progress_id):
    """Return one progress record by id or None."""
    try:
        return _get(f"/user-training-progress/{progress_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_user_training_progress_stats():
    """Return {total, completed_passed, completed_failed, in_progress} for admin reports."""
    try:
        out = _get("/user-training-progress/stats")
        if isinstance(out, dict):
            return out
        return {"total": 0, "completed_passed": 0, "completed_failed": 0, "in_progress": 0}
    except Exception:
        return {"total": 0, "completed_passed": 0, "completed_failed": 0, "in_progress": 0}


def list_document_assignments(username=None, document_id=None):
    """Return list of document assignment dicts."""
    params = {}
    if username is not None:
        params["username"] = username
    if document_id is not None:
        params["document_id"] = document_id
    return _get_list("/document-assignments", params=params)


def list_document_signature_fields(document_id):
    """Return list of document signature field dicts for document_id."""
    return _get_list("/document-signature-fields", params={"document_id": document_id})


def list_checklist_items():
    """Return list of checklist item dicts (is_active=true, ordered by order)."""
    return _get_list("/checklist-items")


def list_roles():
    """Return list of role dicts (id, name)."""
    return _get_list("/roles")


def count_users(store_id=None, role=None):
    """Return count of users. Optional store_id and role filters."""
    try:
        params = {}
        if store_id is not None:
            params["store_id"] = store_id
        if role is not None:
            params["role"] = role
        out = _get("/users/count", params=params if params else None)
        return out.get("count", 0) if isinstance(out, dict) else 0
    except Exception:
        return 0


def count_new_hires(status_filter=None):
    """Return count of new hires. status_filter e.g. 'removed' to exclude."""
    try:
        params = {"status_filter": status_filter} if status_filter else None
        out = _get("/new-hires/count", params=params)
        return out.get("count", 0) if isinstance(out, dict) else 0
    except Exception:
        return 0


def list_manager_permissions(user_id):
    """Return list of manager permission dicts for user_id."""
    return _get_list("/manager-permissions", params={"user_id": user_id})


def get_user_task(task_id):
    try:
        return _get(f"/user-tasks/{task_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_document_assignment(assignment_id):
    try:
        return _get(f"/document-assignments/{assignment_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_document_signature_field(field_id):
    try:
        return _get(f"/document-signature-fields/{field_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_checklist_item(item_id):
    try:
        return _get(f"/checklist-items/{item_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def get_role(role_id):
    try:
        return _get(f"/roles/{role_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
    except Exception:
        return None


def list_documents_visible_to_store(store_id=None):
    """Documents visible to store (or all visible if store_id is None)."""
    params = {"store_id": store_id} if store_id is not None else None
    return _get_list("/documents/visible-to-store", params=params)


def list_new_hires_filtered(status_exclude=None):
    """List new hires, optionally excluding a status (e.g. 'removed')."""
    params = {"status_exclude": status_exclude} if status_exclude else None
    return _get_list("/new-hires/list", params=params)
