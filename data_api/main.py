"""
Data API: REST API over the app database.
Run separately (e.g. uvicorn data_api.main:app) so only this process holds DB connections.
Main Flask app should set API_BASE_URL and use api_client instead of direct DB.
"""
import os
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_api.database import get_db, engine, get_table

app = FastAPI(title="New Hire Data API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_KEY = os.environ.get("DATA_API_KEY", "").strip()


def check_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Invalid or missing X-API-Key")
    return True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_users(
    store_id: int = Query(None),
    role: str = Query(None, description="Filter by role: user, manager, admin"),
    db: Session = Depends(get_db),
):
    q = "SELECT id, username, domain, full_name, email, role, store_id, access_revoked_at FROM users WHERE 1=1"
    params = {}
    if store_id is not None:
        q += " AND store_id = :sid"
        params["sid"] = store_id
    if role is not None:
        q += " AND role = :role"
        params["role"] = role
    q += " ORDER BY username"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    keys = r.keys()
    return [dict(zip(keys, row)) for row in rows]


@app.get("/users/by-email", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_by_email(email: str = Query(..., description="User email"), db: Session = Depends(get_db)):
    """Return user by email including password_hash for server-side login (main app only)."""
    r = db.execute(
        text(
            "SELECT id, username, domain, full_name, email, role, store_id, access_revoked_at, password_hash "
            "FROM users WHERE LOWER(email) = LOWER(:email)"
        ),
        {"email": email.strip()},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return dict(zip(r.keys(), row))


@app.get("/users/by-username/{username}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_by_username(username: str, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, domain, full_name, email, role, store_id, access_revoked_at FROM users WHERE username = :u"),
        {"u": username},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return dict(zip(r.keys(), row))


@app.get("/users/{user_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, domain, full_name, email, role, store_id, access_revoked_at FROM users WHERE id = :id"),
        {"id": user_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return dict(zip(r.keys(), row))


@app.get("/new-hires", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_new_hires(db: Session = Depends(get_db)):
    r = db.execute(text(
        "SELECT id, username, first_name, last_name, email, department, position, role_id, start_date, "
        "access_revoked_at, status, store_id, created_by, created_at, updated_at, notes FROM new_hires"
    ))
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/new-hires/by-username/{username}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_new_hire_by_username(username: str, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, first_name, last_name, email, department, position, role_id, start_date, "
             "access_revoked_at, status, store_id, created_by, created_at, updated_at, notes, "
             "finale_message, finale_message_sent_at, finale_document_id, finale_message_dismissed_at "
             "FROM new_hires WHERE username = :u"),
        {"u": username},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "New hire not found")
    return dict(zip(r.keys(), row))


@app.get("/documents", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_documents(
    is_visible: bool = Query(None),
    deleted_at_null: bool = Query(True, description="Exclude soft-deleted when True"),
    store_id: int = Query(None, description="Optional; filter to documents visible to this store"),
    document_store_id: int = Query(None, description="Optional; filter to documents where document.store_id = this"),
    db: Session = Depends(get_db),
):
    params = {}
    if store_id is not None or document_store_id is not None:
        # Use alias d
        q = (
            "SELECT d.id, d.filename, d.original_filename, d.display_name, d.file_path, d.file_size, d.file_type, "
            "d.description, d.is_visible, d.store_id, d.uploaded_by, d.created_at, d.updated_at, d.deleted_at "
            "FROM documents d WHERE 1=1"
        )
        if is_visible is not None:
            q += " AND d.is_visible = :iv"
            params["iv"] = is_visible
        if deleted_at_null:
            q += " AND d.deleted_at IS NULL"
        else:
            q += " AND d.deleted_at IS NOT NULL"
        if store_id is not None:
            q += " AND (NOT EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id) OR EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id AND ds.store_id = :sid))"
            params["sid"] = store_id
        if document_store_id is not None:
            q += " AND d.store_id = :doc_sid"
            params["doc_sid"] = document_store_id
        q += " ORDER BY d.created_at DESC"
    else:
        q = "SELECT id, filename, original_filename, display_name, file_path, file_size, file_type, description, is_visible, store_id, uploaded_by, created_at, updated_at, deleted_at FROM documents WHERE 1=1"
        if is_visible is not None:
            q += " AND is_visible = :iv"
            params["iv"] = is_visible
        if deleted_at_null:
            q += " AND deleted_at IS NULL"
        else:
            q += " AND deleted_at IS NOT NULL"
        q += " ORDER BY created_at DESC"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/documents/count", dependencies=[Depends(check_api_key)] if API_KEY else [])
def count_documents(
    deleted_at_null: bool = Query(True, description="False = archived only"),
    store_id: int = Query(None),
    document_store_id: int = Query(None),
    is_visible: bool = Query(None),
    db: Session = Depends(get_db),
):
    params = {}
    if store_id is not None or document_store_id is not None:
        q = "SELECT COUNT(*) AS c FROM documents d WHERE 1=1"
        if is_visible is not None:
            q += " AND d.is_visible = :iv"
            params["iv"] = is_visible
        if deleted_at_null:
            q += " AND d.deleted_at IS NULL"
        else:
            q += " AND d.deleted_at IS NOT NULL"
        if store_id is not None:
            q += " AND (NOT EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id) OR EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id AND ds.store_id = :sid))"
            params["sid"] = store_id
        if document_store_id is not None:
            q += " AND d.store_id = :doc_sid"
            params["doc_sid"] = document_store_id
    else:
        q = "SELECT COUNT(*) AS c FROM documents WHERE 1=1"
        if is_visible is not None:
            q += " AND is_visible = :iv"
            params["iv"] = is_visible
        if deleted_at_null:
            q += " AND deleted_at IS NULL"
        else:
            q += " AND deleted_at IS NOT NULL"
    r = db.execute(text(q), params)
    row = r.fetchone()
    return {"count": row[0] if row else 0}


@app.get("/documents/with-signature-fields", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_documents_with_signature_fields(
    deleted_at_null: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Documents that have at least one document_signature_fields row."""
    if deleted_at_null:
        q = (
            "SELECT DISTINCT d.id, d.filename, d.original_filename, d.display_name, d.file_path, d.file_size, d.file_type, "
            "d.description, d.is_visible, d.store_id, d.uploaded_by, d.created_at, d.updated_at, d.deleted_at "
            "FROM documents d INNER JOIN document_signature_fields dsf ON dsf.document_id = d.id WHERE d.deleted_at IS NULL ORDER BY d.created_at DESC"
        )
    else:
        q = (
            "SELECT DISTINCT d.id, d.filename, d.original_filename, d.display_name, d.file_path, d.file_size, d.file_type, "
            "d.description, d.is_visible, d.store_id, d.uploaded_by, d.created_at, d.updated_at, d.deleted_at "
            "FROM documents d INNER JOIN document_signature_fields dsf ON dsf.document_id = d.id ORDER BY d.created_at DESC"
        )
    r = db.execute(text(q))
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/document-signatures", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_document_signatures(
    document_id: int = Query(None, description="Filter by document_id"),
    signature_field_id: int = Query(None, description="Filter by signature_field_id"),
    username: str = Query(None, description="Filter by username"),
    db: Session = Depends(get_db),
):
    q = "SELECT id, document_id, signature_field_id, username, signed_at FROM document_signatures WHERE 1=1"
    params = {}
    if document_id is not None:
        q += " AND document_id = :doc_id"
        params["doc_id"] = document_id
    if signature_field_id is not None:
        q += " AND signature_field_id = :sfid"
        params["sfid"] = signature_field_id
    if username is not None:
        q += " AND username = :u"
        params["u"] = username
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/user-notifications", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_user_notifications(
    username: str = Query(..., description="Filter by username"),
    notification_type: str = Query(None),
    notification_id: str = Query(None),
    db: Session = Depends(get_db),
):
    q = "SELECT id, username, notification_type, notification_id, is_read, read_at, created_at FROM user_notifications WHERE username = :u"
    params = {"u": username}
    if notification_type is not None:
        q += " AND notification_type = :nt"
        params["nt"] = notification_type
    if notification_id is not None:
        q += " AND notification_id = :nid"
        params["nid"] = notification_id
    q += " ORDER BY created_at DESC"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/user-notifications/{notification_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_notification_by_id(notification_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, notification_type, notification_id, is_read, read_at, created_at FROM user_notifications WHERE id = :id"),
        {"id": notification_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Notification not found")
    return dict(zip(r.keys(), row))


@app.get("/external-links", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_external_links(
    is_active: bool = Query(None, description="Filter by is_active; None = all"),
    db: Session = Depends(get_db),
):
    q = "SELECT id, title, url, description, icon, image_filename, order, is_active, created_by, created_at, updated_at FROM external_links WHERE 1=1"
    params = {}
    if is_active is not None:
        q += " AND is_active = :active"
        params["active"] = is_active
    q += " ORDER BY \"order\", created_at"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/external-links/{link_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_external_link(link_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, title, url, description, icon, image_filename, \"order\", is_active, created_by, created_at, updated_at FROM external_links WHERE id = :id"),
        {"id": link_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "External link not found")
    return dict(zip(r.keys(), row))


@app.get("/documents/{doc_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_document(doc_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, filename, original_filename, display_name, file_path, file_size, file_type, description, is_visible, store_id, uploaded_by, created_at, updated_at, deleted_at FROM documents WHERE id = :id"),
        {"id": doc_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return dict(zip(r.keys(), row))


@app.get("/stores", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_stores(db: Session = Depends(get_db)):
    r = db.execute(text("SELECT id, name, code FROM stores ORDER BY name"))
    return [dict(zip(r.keys(), row)) for row in r.fetchall()]


@app.get("/stores/{store_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_store(store_id: int, db: Session = Depends(get_db)):
    r = db.execute(text("SELECT id, name, code FROM stores WHERE id = :id"), {"id": store_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Store not found")
    return dict(zip(r.keys(), row))


# ---- Training videos ----
@app.get("/training-videos", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_training_videos(db: Session = Depends(get_db)):
    r = db.execute(text(
        "SELECT id, title, description, filename, original_filename, file_path, file_size, duration, "
        "video_type, is_active, passing_score, max_attempts, uploaded_by, created_at, updated_at FROM training_videos"
    ))
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/training-videos/{video_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_training_video(video_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, title, description, filename, original_filename, file_path, file_size, duration, "
             "video_type, is_active, passing_score, max_attempts, uploaded_by, created_at, updated_at "
             "FROM training_videos WHERE id = :id"),
        {"id": video_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Training video not found")
    return dict(zip(r.keys(), row))


@app.get("/new-hires/{new_hire_id}/required-video-ids", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_new_hire_required_video_ids(new_hire_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT video_id FROM new_hire_required_training WHERE new_hire_id = :id"),
        {"id": new_hire_id},
    )
    rows = r.fetchall()
    return [row[0] for row in rows]


# ---- User tasks ----
@app.get("/user-tasks", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_user_tasks(username: str = Query(..., description="Filter by username"), db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, task_title, task_description, task_type, document_id, priority, status, "
             "due_date, assigned_by, assigned_at, completed_at, notes, created_at, updated_at "
             "FROM user_tasks WHERE username = :u ORDER BY created_at DESC"),
        {"u": username},
    )
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


# ---- User training progress ----
@app.get("/user-training-progress", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_user_training_progress(
    username: str = Query(None, description="Filter by username"),
    video_id: int = Query(None, description="Optional filter by video_id; if only video_id set, returns all users' progress for that video"),
    db: Session = Depends(get_db),
):
    q = ("SELECT id, username, video_id, attempt_number, score, total_questions, correct_answers, "
         "time_watched, is_passed, is_completed, started_at, completed_at, last_updated "
         "FROM user_training_progress WHERE 1=1")
    params = {}
    if username is not None:
        q += " AND username = :u"
        params["u"] = username
    if video_id is not None:
        q += " AND video_id = :vid"
        params["vid"] = video_id
    q += " ORDER BY username, attempt_number DESC"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


@app.get("/user-training-progress/{progress_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_training_progress_by_id(progress_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, video_id, attempt_number, score, total_questions, correct_answers, "
             "time_watched, is_passed, is_completed, started_at, completed_at, last_updated "
             "FROM user_training_progress WHERE id = :id"),
        {"id": progress_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Progress not found")
    return dict(zip(r.keys(), row))


@app.get("/user-training-progress/stats", dependencies=[Depends(check_api_key)] if API_KEY else [])
def user_training_progress_stats(db: Session = Depends(get_db)):
    """Return counts for admin reports: total, completed_passed, completed_failed, in_progress."""
    r = db.execute(text(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN is_completed = 1 AND is_passed = 1 THEN 1 ELSE 0 END) AS completed_passed, "
        "SUM(CASE WHEN is_completed = 1 AND (is_passed = 0 OR is_passed IS NULL) THEN 1 ELSE 0 END) AS completed_failed, "
        "SUM(CASE WHEN is_completed = 0 OR is_completed IS NULL THEN 1 ELSE 0 END) AS in_progress "
        "FROM user_training_progress"
    ))
    row = r.fetchone()
    keys = r.keys()
    if not row:
        return {"total": 0, "completed_passed": 0, "completed_failed": 0, "in_progress": 0}
    return dict(zip(keys, row))


# ---- Document assignments ----
@app.get("/document-assignments", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_document_assignments(
    username: str = Query(None),
    document_id: int = Query(None),
    db: Session = Depends(get_db),
):
    q = ("SELECT id, document_id, username, assigned_by, assigned_at, due_date, is_completed, completed_at, notes "
         "FROM document_assignments WHERE 1=1")
    params = {}
    if username is not None:
        q += " AND username = :u"
        params["u"] = username
    if document_id is not None:
        q += " AND document_id = :doc_id"
        params["doc_id"] = document_id
    q += " ORDER BY assigned_at DESC"
    r = db.execute(text(q), params)
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


# ---- Document signature fields ----
@app.get("/document-signature-fields", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_document_signature_fields(document_id: int = Query(..., description="Filter by document_id"), db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, document_id, page_number, x_position, y_position, width, height, field_label, "
             "is_required, signature_type, created_by, created_at FROM document_signature_fields WHERE document_id = :doc_id "
             "ORDER BY page_number, id"),
        {"doc_id": document_id},
    )
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


# ---- Checklist items (order by column index 5 to avoid reserved word) ----
@app.get("/checklist-items", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_checklist_items(db: Session = Depends(get_db)):
    # Use column position in ORDER BY for DB-agnostic reserved word 'order'
    r = db.execute(
        text("SELECT id, task_name, description, assigned_to, [order], is_active, created_by, created_at, updated_at "
             "FROM checklist_items WHERE is_active = 1 ORDER BY 5, id")
    )
    rows = r.fetchall()
    keys = list(r.keys())
    out = []
    for row in rows:
        d = dict(zip(keys, row))
        if "order" not in d:
            d["order"] = d.get("Order") or d.get("[order]", 0)
        out.append(d)
    return out


# ---- Roles ----
@app.get("/roles", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_roles(db: Session = Depends(get_db)):
    r = db.execute(text("SELECT id, name FROM roles ORDER BY name"))
    return [dict(zip(r.keys(), row)) for row in r.fetchall()]


# ---- Counts (admin dashboard) ----
@app.get("/users/count", dependencies=[Depends(check_api_key)] if API_KEY else [])
def count_users(
    store_id: int = Query(None),
    role: str = Query(None),
    db: Session = Depends(get_db),
):
    q = "SELECT COUNT(*) AS c FROM users WHERE 1=1"
    params = {}
    if store_id is not None:
        q += " AND store_id = :sid"
        params["sid"] = store_id
    if role is not None:
        q += " AND role = :role"
        params["role"] = role
    r = db.execute(text(q), params)
    row = r.fetchone()
    return {"count": row[0] if row else 0}


@app.get("/new-hires/count", dependencies=[Depends(check_api_key)] if API_KEY else [])
def count_new_hires(status_filter: str = Query(None, description="Exclude status, e.g. 'removed'"), db: Session = Depends(get_db)):
    if status_filter:
        r = db.execute(text("SELECT COUNT(*) AS c FROM new_hires WHERE status != :s"), {"s": status_filter})
    else:
        r = db.execute(text("SELECT COUNT(*) AS c FROM new_hires"))
    row = r.fetchone()
    return {"count": row[0] if row else 0}


# ---- Manager permissions (for manager_has_permission) ----
@app.get("/manager-permissions", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_manager_permissions(user_id: int = Query(..., description="Filter by user_id"), db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, user_id, permission_key FROM manager_permissions WHERE user_id = :uid"),
        {"uid": user_id},
    )
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


# ---- Get by id ----
@app.get("/user-tasks/{task_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_user_task(task_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, username, task_title, task_description, task_type, document_id, priority, status, "
             "due_date, assigned_by, assigned_at, completed_at, notes, created_at, updated_at "
             "FROM user_tasks WHERE id = :id"), {"id": task_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "User task not found")
    return dict(zip(r.keys(), row))


@app.get("/document-assignments/{assignment_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_document_assignment_by_id(assignment_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, document_id, username, assigned_by, assigned_at, due_date, is_completed, completed_at, notes "
             "FROM document_assignments WHERE id = :id"), {"id": assignment_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Document assignment not found")
    return dict(zip(r.keys(), row))


@app.get("/document-signature-fields/{field_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_document_signature_field(field_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, document_id, page_number, x_position, y_position, width, height, field_label, "
             "is_required, signature_type, created_by, created_at FROM document_signature_fields WHERE id = :id"),
        {"id": field_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Signature field not found")
    return dict(zip(r.keys(), row))


@app.get("/checklist-items/{item_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_checklist_item(item_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("SELECT id, task_name, description, assigned_to, [order], is_active, created_by, created_at, updated_at "
             "FROM checklist_items WHERE id = :id"), {"id": item_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Checklist item not found")
    d = dict(zip(r.keys(), row))
    if "order" not in d:
        d["order"] = d.get("Order") or d.get("[order]", 0)
    return d


@app.get("/roles/{role_id}", dependencies=[Depends(check_api_key)] if API_KEY else [])
def get_role(role_id: int, db: Session = Depends(get_db)):
    r = db.execute(text("SELECT id, name, description, created_at FROM roles WHERE id = :id"), {"id": role_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Role not found")
    return dict(zip(r.keys(), row))


# ---- Documents visible to store (no rows in document_stores = all stores, else must have store_id) ----
@app.get("/documents/visible-to-store", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_documents_visible_to_store(
    store_id: int = Query(None, description="None = all visible; int = filter by store"),
    db: Session = Depends(get_db),
):
    if store_id is None:
        q = (
            "SELECT id, filename, original_filename, display_name, file_path, file_size, file_type, "
            "description, is_visible, store_id, uploaded_by, created_at, updated_at, deleted_at "
            "FROM documents WHERE is_visible = 1 AND deleted_at IS NULL ORDER BY created_at DESC"
        )
        r = db.execute(text(q))
    else:
        q = (
            "SELECT d.id, d.filename, d.original_filename, d.display_name, d.file_path, d.file_size, d.file_type, "
            "d.description, d.is_visible, d.store_id, d.uploaded_by, d.created_at, d.updated_at, d.deleted_at "
            "FROM documents d WHERE d.is_visible = 1 AND d.deleted_at IS NULL AND ("
            "NOT EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id) OR "
            "EXISTS (SELECT 1 FROM document_stores ds WHERE ds.document_id = d.id AND ds.store_id = :sid)"
            ") ORDER BY d.created_at DESC"
        )
        r = db.execute(text(q), {"sid": store_id})
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]


# ---- New hires list with optional status exclude ----
@app.get("/new-hires/list", dependencies=[Depends(check_api_key)] if API_KEY else [])
def list_new_hires_filtered(
    status_exclude: str = Query(None, description="Exclude this status, e.g. 'removed'"),
    db: Session = Depends(get_db),
):
    if status_exclude:
        r = db.execute(text(
            "SELECT id, username, first_name, last_name, email, department, position, role_id, start_date, "
            "access_revoked_at, status, store_id, created_by, created_at, updated_at, notes, "
            "finale_message, finale_message_sent_at, finale_document_id, finale_message_dismissed_at "
            "FROM new_hires WHERE status != :s ORDER BY created_at DESC"), {"s": status_exclude})
    else:
        r = db.execute(text(
            "SELECT id, username, first_name, last_name, email, department, position, role_id, start_date, "
            "access_revoked_at, status, store_id, created_by, created_at, updated_at, notes, "
            "finale_message, finale_message_sent_at, finale_document_id, finale_message_dismissed_at "
            "FROM new_hires ORDER BY created_at DESC"))
    rows = r.fetchall()
    return [dict(zip(r.keys(), row)) for row in rows]
