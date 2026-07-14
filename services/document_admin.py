"""Admin document maintenance helpers (orphans, field editor redirects)."""
from __future__ import annotations

from flask import flash, get_flashed_messages, redirect, request, session, url_for
from sqlalchemy import and_, or_

from models import (
    Document, QuizAnswer, QuizQuestion, UserNotification, UserQuizResponse,
    UserTask, UserTrainingProgress, db, new_hire_required_training, training_video_stores,
)

def _delete_user_tasks_for_document(document) -> int:
    """Delete UserTask rows tied to a document so they disappear from users' Tasks pages."""
    if not document or not document.id:
        return 0
    doc_id = document.id
    sign_title = f"Sign Document: {document.name_for_users}"
    task_ids = [
        row[0] for row in
        UserTask.query.filter(
            or_(
                UserTask.document_id == doc_id,
                and_(
                    UserTask.task_type == 'document',
                    UserTask.task_title == sign_title,
                ),
            )
        ).with_entities(UserTask.id).all()
    ]
    if task_ids:
        UserTask.query.filter(UserTask.depends_on_task_id.in_(task_ids)).update(
            {UserTask.depends_on_task_id: None},
            synchronize_session=False,
        )
        return UserTask.query.filter(UserTask.id.in_(task_ids)).delete(synchronize_session=False)
    return 0

def _orphaned_document_user_tasks_query():
    """Document tasks whose form was deleted (old code nulled document_id) or document row is gone."""
    existing_doc_ids = db.session.query(Document.id)
    return UserTask.query.filter(
        UserTask.task_type == 'document',
        or_(
            UserTask.document_id.is_(None),
            ~UserTask.document_id.in_(existing_doc_ids),
        ),
    )

def count_orphaned_document_user_tasks() -> int:
    try:
        return _orphaned_document_user_tasks_query().count()
    except Exception:
        return 0

def cleanup_orphaned_document_user_tasks() -> int:
    """Remove stale Sign Document tasks left after forms were deleted before the fix."""
    try:
        task_ids = [
            row[0] for row in
            _orphaned_document_user_tasks_query().with_entities(UserTask.id).all()
        ]
    except Exception:
        return 0
    if not task_ids:
        return 0
    UserTask.query.filter(UserTask.depends_on_task_id.in_(task_ids)).update(
        {UserTask.depends_on_task_id: None},
        synchronize_session=False,
    )
    return UserTask.query.filter(UserTask.id.in_(task_ids)).delete(synchronize_session=False)

def _signature_fields_redirect(doc_id, page=None):
    """Redirect back to set signature fields, preserving the active PDF page."""
    if page is None:
        page = request.form.get('return_page') or request.args.get('page')
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    return redirect(url_for('set_signature_fields', doc_id=doc_id, page=page))


_FIELD_EDITOR_NOISE_FLASH_PREFIXES = (
    'Field updated successfully',
    'Field converted to signature successfully',
    'Typed field deleted successfully',
    'Typed field added successfully',
    'Signature field added successfully',
    'Signature field deleted successfully',
)

def _drop_field_editor_noise_flashes():
    """Consume leftover field-editor success flashes so they don't stack on Manage Documents."""
    from flask import get_flashed_messages
    messages = get_flashed_messages(with_categories=True)
    keep = []
    for category, msg in messages:
        text = (msg or '').strip()
        if category == 'success' and any(text.startswith(p) for p in _FIELD_EDITOR_NOISE_FLASH_PREFIXES):
            continue
        keep.append((category, msg))
    for category, msg in keep:
        flash(msg, category)

def _purge_training_video_dependencies(video_id):
    """Remove related rows so a training video can be deleted."""
    video_id = int(video_id)
    video = TrainingVideo.query.get(video_id)
    if not video:
        return

    question_ids = [
        row[0] for row in db.session.query(QuizQuestion.id).filter_by(video_id=video_id).all()
    ]
    progress_ids = [
        row[0] for row in db.session.query(UserTrainingProgress.id).filter_by(video_id=video_id).all()
    ]
    answer_ids = []
    if question_ids:
        answer_ids = [
            row[0] for row in db.session.query(QuizAnswer.id).filter(
                QuizAnswer.question_id.in_(question_ids)
            ).all()
        ]

    response_filters = []
    if question_ids:
        response_filters.append(UserQuizResponse.question_id.in_(question_ids))
    if progress_ids:
        response_filters.append(UserQuizResponse.progress_id.in_(progress_ids))
    if answer_ids:
        response_filters.append(UserQuizResponse.answer_id.in_(answer_ids))
    if response_filters:
        db.session.query(UserQuizResponse).filter(or_(*response_filters)).delete(
            synchronize_session=False
        )
    db.session.flush()

    UserTrainingProgress.query.filter_by(video_id=video_id).delete(synchronize_session=False)

    if answer_ids:
        QuizAnswer.query.filter(QuizAnswer.id.in_(answer_ids)).delete(synchronize_session=False)
    QuizQuestion.query.filter_by(video_id=video_id).delete(synchronize_session=False)
    db.session.flush()

    db.session.execute(
        new_hire_required_training.delete().where(
            new_hire_required_training.c.video_id == video_id
        )
    )
    db.session.execute(
        training_video_stores.delete().where(
            training_video_stores.c.video_id == video_id
        )
    )
    UserTask.query.filter(
        UserTask.task_type == 'training',
        UserTask.notes.like(f'video_id:{video_id}%'),
    ).delete(synchronize_session=False)
    UserNotification.query.filter_by(
        notification_type='training',
        notification_id=str(video_id),
    ).delete(synchronize_session=False)

