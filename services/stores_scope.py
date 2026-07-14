"""Store-scoped document/training visibility and manager permissions."""
from __future__ import annotations

from flask_login import current_user
from sqlalchemy import and_, exists, or_, select

from models import (
    Document, DocumentAssignment, DocumentSignatureField, DocumentTypedField,
    ManagerPermission, Store, TrainingVideo,
    User as UserModel, db, document_stores, training_video_stores,
)

def get_current_user_store_id():
    """Return store_id for current user (from User record), or None."""
    if not current_user.is_authenticated:
        return None
    try:
        u = UserModel.query.filter_by(username=current_user.username).first()
        return getattr(u, 'store_id', None) if u else None
    except Exception:
        return None


def documents_visible_to_store_query(store_id, base_filter=None):
    """Return Document query for the optional user document library: is_visible and store scope.
    If store_id is None, only is_visible is applied (admin view). base_filter is an optional extra filter."""
    q = Document.query.filter(Document.is_visible == True)
    if store_id is not None:
        # Document visible to this store if: no rows in document_stores (all stores) OR has row with this store_id
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id))
        q = q.filter(or_(no_stores, in_store))
    if base_filter is not None:
        q = q.filter(base_filter)
    return q


def documents_assignable_to_store_query(store_id, base_filter=None):
    """Return Document query for staff assignment (onboarding, assign task, role defaults).

    Unlike documents_visible_to_store_query, does NOT require is_visible / In library —
    assigned forms must be selectable even when Not in library. Store scope still applies
    when store_id is set (no document_stores rows = all stores).
    """
    q = Document.query
    if store_id is not None:
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id))
        q = q.filter(or_(no_stores, in_store))
    if base_filter is not None:
        q = q.filter(base_filter)
    return q


def _document_has_assignable_fields_filter():
    """Forms that can be filled/signed: signature fields and/or typed fields."""
    return or_(
        exists().where(DocumentSignatureField.document_id == Document.id),
        exists().where(DocumentTypedField.document_id == Document.id),
    )


def _stores_for_document(document_id):
    """Store rows linked to a document via document_stores (empty = all stores)."""
    if not document_id:
        return []
    try:
        store_ids = [
            row[0] for row in db.session.execute(
                select(document_stores.c.store_id).where(
                    document_stores.c.document_id == document_id
                )
            ).fetchall()
        ]
    except Exception:
        db.session.rollback()
        return []
    if not store_ids:
        return []
    return Store.query.filter(Store.id.in_(store_ids)).order_by(Store.name).all()


def _attach_document_store_lists(documents):
    """Set doc.store_ids for admin Manage Forms store dropdown."""
    if not documents:
        return
    doc_ids = [d.id for d in documents if d.id]
    by_doc = {doc_id: [] for doc_id in doc_ids}
    if doc_ids:
        try:
            rows = db.session.execute(
                select(document_stores.c.document_id, document_stores.c.store_id).where(
                    document_stores.c.document_id.in_(doc_ids)
                )
            ).fetchall()
            for doc_id, store_id in rows:
                by_doc.setdefault(doc_id, []).append(store_id)
        except Exception:
            db.session.rollback()
    all_store_ids = {sid for ids in by_doc.values() for sid in ids}
    stores_by_id = {}
    if all_store_ids:
        stores_by_id = {s.id: s for s in Store.query.filter(Store.id.in_(all_store_ids)).all()}
    for doc in documents:
        doc.store_ids = [stores_by_id[sid] for sid in by_doc.get(doc.id, []) if sid in stores_by_id]


def document_visible_to_store(document, store_id):
    """True if document is in the user library for the given store (is_visible + store scope)."""
    if not document or not getattr(document, 'is_visible', False):
        return False
    store_ids = getattr(document, 'store_ids', None)
    if store_ids is None:
        store_ids = _stores_for_document(document.id)
    if not store_ids:
        return True  # all stores
    if store_id is None:
        return True  # no store filter
    return any(getattr(s, 'id', None) == store_id for s in store_ids)


def training_videos_visible_to_store_query(store_id, base_filter=None):
    """Return TrainingVideo query scoped to a store. No rows in training_video_stores = all stores."""
    q = TrainingVideo.query
    if base_filter is not None:
        q = q.filter(base_filter)
    if store_id is not None:
        no_stores = ~exists().where(training_video_stores.c.video_id == TrainingVideo.id)
        in_store = exists().where(
            and_(training_video_stores.c.video_id == TrainingVideo.id, training_video_stores.c.store_id == store_id)
        )
        q = q.filter(or_(no_stores, in_store))
    return q


def _stores_for_training_video(video_id):
    """Stores linked to a training video (empty = all stores)."""
    if not video_id:
        return []
    try:
        store_ids = [
            row[0] for row in db.session.execute(
                select(training_video_stores.c.store_id).where(
                    training_video_stores.c.video_id == video_id
                )
            ).fetchall()
        ]
    except Exception:
        db.session.rollback()
        return []
    if not store_ids:
        return []
    return Store.query.filter(Store.id.in_(store_ids)).order_by(Store.name).all()


def _attach_training_video_store_lists(videos):
    """Set video.store_ids for admin Training Management store dropdown."""
    if not videos:
        return
    video_ids = [v.id for v in videos if v.id]
    by_video = {vid: [] for vid in video_ids}
    if video_ids:
        try:
            rows = db.session.execute(
                select(training_video_stores.c.video_id, training_video_stores.c.store_id).where(
                    training_video_stores.c.video_id.in_(video_ids)
                )
            ).fetchall()
            for vid, store_id in rows:
                by_video.setdefault(vid, []).append(store_id)
        except Exception:
            db.session.rollback()
    all_store_ids = {sid for ids in by_video.values() for sid in ids}
    stores_by_id = {}
    if all_store_ids:
        stores_by_id = {s.id: s for s in Store.query.filter(Store.id.in_(all_store_ids)).all()}
    for video in videos:
        video.store_ids = [
            stores_by_id[sid] for sid in by_video.get(video.id, []) if sid in stores_by_id
        ]


def training_video_visible_to_store(video, store_id):
    """True if training video is visible to the given store."""
    if not video:
        return False
    store_ids = getattr(video, 'store_ids', None)
    if store_ids is None:
        store_ids = _stores_for_training_video(video.id)
    if not store_ids:
        return True
    if store_id is None:
        return True
    return any(getattr(s, 'id', None) == store_id for s in store_ids)


def training_videos_for_store_detail(store_id):
    """Training videos explicitly scoped to one store (excludes global all-stores videos)."""
    try:
        video_ids = [
            row[0] for row in db.session.execute(
                select(training_video_stores.c.video_id).where(
                    training_video_stores.c.store_id == store_id
                )
            ).fetchall()
        ]
    except Exception:
        db.session.rollback()
        return []
    if not video_ids:
        return []
    return TrainingVideo.query.filter(TrainingVideo.id.in_(video_ids)).order_by(TrainingVideo.title).all()


def documents_for_user_files(username):
    """Documents for the user Files tab: explicitly assigned to user, scoped to user's store.

    Assigned documents always appear here even when is_visible is False (Not in library in admin).
    is_visible only controls whether a document appears in the general browse pool, not
    direct assignments the user must sign.
    """
    from sqlalchemy.orm import joinedload

    assigned_documents = (
        DocumentAssignment.query.filter_by(username=username)
        .options(joinedload(DocumentAssignment.document))
        .all()
    )
    assigned_doc_ids = [a.document_id for a in assigned_documents]
    if not assigned_doc_ids:
        return [], assigned_documents
    store_id = None
    try:
        u = UserModel.query.filter_by(username=username).first()
        store_id = getattr(u, 'store_id', None) if u else None
    except Exception:
        pass
    q = Document.query.filter(Document.id.in_(assigned_doc_ids))
    if store_id is not None:
        no_stores = ~exists().where(document_stores.c.document_id == Document.id)
        in_store = exists().where(
            and_(document_stores.c.document_id == Document.id, document_stores.c.store_id == store_id)
        )
        q = q.filter(or_(no_stores, in_store))
    documents = q.order_by(Document.created_at.desc()).all()
    return documents, assigned_documents


def manager_has_permission(permission_key):
    """True if current user is admin, or is manager and has the given permission."""
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin():
        return True
    if not current_user.is_manager():
        return False
    try:
        u = UserModel.query.filter_by(username=current_user.username).first()
        if not u:
            return False
        return ManagerPermission.query.filter_by(user_id=u.id, permission_key=permission_key).first() is not None
    except Exception:
        return False


# Permission keys for managers (used in Manage Users and when gating actions)
MANAGER_PERMISSION_KEYS = [
    ('start_onboarding', 'Start onboarding (add new hires)'),
    ('manage_documents', 'Manage documents'),
    ('manage_training', 'Manage training videos'),
    ('manage_checklist', 'Manage onboarding checklist'),
    ('view_reports', 'View reports'),
    ('manage_user_checklists', 'Manage user checklists'),
]

