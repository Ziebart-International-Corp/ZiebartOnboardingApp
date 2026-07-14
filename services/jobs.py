"""Background job queue for heavy PDF work (DB-backed, no Redis required)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, current_app
from sqlalchemy import text

from models import db

STUCK_AFTER_MINUTES = 15
MAX_JOB_ATTEMPTS = 3


class BackgroundJob(db.Model):
    """Simple durable queue for signed-PDF builds and similar work."""
    __tablename__ = "background_jobs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(80), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    # pending | running | done | failed
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    def payload(self) -> dict:
        try:
            return json.loads(self.payload_json or "{}")
        except Exception:
            return {}


_worker_started = False
_worker_lock = threading.Lock()


def job_is_stuck(started_at, now=None, stuck_after_minutes: int = STUCK_AFTER_MINUTES) -> bool:
    """True when a running job's started_at is older than the stuck threshold."""
    if not started_at:
        return True
    now = now or datetime.utcnow()
    return started_at < (now - timedelta(minutes=stuck_after_minutes))


def can_retry_job(attempts: int, max_attempts: int = MAX_JOB_ATTEMPTS) -> bool:
    """True when a failed/stuck job may be requeued."""
    return (attempts or 0) < max_attempts


def ensure_jobs_table() -> None:
    """Create background_jobs if missing (MSSQL-safe best effort)."""
    try:
        db.session.execute(text("SELECT TOP 1 id FROM background_jobs"))
        return
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(
            text(
                """
                CREATE TABLE background_jobs (
                    id INT PRIMARY KEY IDENTITY(1,1),
                    job_type NVARCHAR(80) NOT NULL,
                    payload_json NVARCHAR(MAX) NOT NULL,
                    status NVARCHAR(20) NOT NULL,
                    attempts INT NOT NULL DEFAULT 0,
                    last_error NVARCHAR(MAX) NULL,
                    created_at DATETIME NOT NULL,
                    started_at DATETIME NULL,
                    finished_at DATETIME NULL
                )
                """
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def enqueue_job(job_type: str, **payload) -> BackgroundJob | None:
    """Insert a pending job and kick the in-process worker."""
    try:
        ensure_jobs_table()
        job = BackgroundJob(
            job_type=job_type,
            payload_json=json.dumps(payload),
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.session.add(job)
        db.session.commit()
        start_worker(current_app._get_current_object())
        return job
    except Exception as exc:
        db.session.rollback()
        try:
            current_app.logger.warning("enqueue_job failed: %s", exc)
        except Exception:
            pass
        return None


def enqueue_signed_pdf(document_id: int, username: str) -> BackgroundJob | None:
    return enqueue_job("persist_signed_pdf", document_id=document_id, username=username)


def enqueue_or_persist_signed_pdf(document, username: str):
    """
    Prefer async signed-PDF build; fall back to sync persist if enqueue fails.
    Returns (job_or_None, signed_copy_rel_path_or_None).
    """
    from services.documents_pdf import _persist_signed_pdf_copy

    if document is None or not username:
        return None, None
    try:
        job = enqueue_signed_pdf(document.id, username)
        if job is not None:
            return job, None
    except Exception as exc:
        try:
            current_app.logger.warning("Failed to enqueue signed PDF: %s", exc)
        except Exception:
            pass
    try:
        path = _persist_signed_pdf_copy(document, username)
        return None, path
    except Exception as exc:
        try:
            current_app.logger.warning("Sync signed PDF persist failed: %s", exc)
        except Exception:
            pass
        raise


def list_recent_jobs(limit: int = 100) -> list[BackgroundJob]:
    ensure_jobs_table()
    return (
        BackgroundJob.query.order_by(BackgroundJob.id.desc())
        .limit(max(1, min(int(limit or 100), 500)))
        .all()
    )


def requeue_job(job_id: int) -> BackgroundJob | None:
    """Reset a failed/running/stuck job to pending if under max attempts."""
    ensure_jobs_table()
    job = BackgroundJob.query.get(int(job_id))
    if not job:
        return None
    if job.status == "done":
        return None
    if job.status == "pending":
        return job
    if not can_retry_job(job.attempts):
        return None
    job.status = "pending"
    job.started_at = None
    job.finished_at = None
    job.last_error = None
    db.session.commit()
    try:
        start_worker(current_app._get_current_object())
    except Exception:
        pass
    return job


def recover_stuck_jobs(
    stuck_after_minutes: int = STUCK_AFTER_MINUTES,
    max_attempts: int = MAX_JOB_ATTEMPTS,
) -> int:
    """
    Requeue running jobs older than the stuck threshold.
    Permanently fail those that already hit max attempts.
    Returns number of jobs touched.
    """
    ensure_jobs_table()
    cutoff = datetime.utcnow() - timedelta(minutes=stuck_after_minutes)
    stuck = (
        BackgroundJob.query.filter_by(status="running")
        .filter(
            (BackgroundJob.started_at.is_(None)) | (BackgroundJob.started_at < cutoff)
        )
        .all()
    )
    touched = 0
    for job in stuck:
        if can_retry_job(job.attempts, max_attempts):
            job.status = "pending"
            job.started_at = None
            job.finished_at = None
            job.last_error = (job.last_error or "")[:3500] + "\n[recovered: stuck running]"
        else:
            job.status = "failed"
            job.finished_at = datetime.utcnow()
            job.last_error = (job.last_error or "stuck")[:3500] + "\n[failed: exceeded max attempts]"
        touched += 1
    if touched:
        db.session.commit()
    return touched


def claim_next_pending_job() -> BackgroundJob | None:
    """
    Atomically claim the oldest pending job (pending -> running).
    Safe across multiple IIS workers via conditional UPDATE.
    """
    ensure_jobs_table()
    candidate = (
        BackgroundJob.query.filter_by(status="pending")
        .order_by(BackgroundJob.id.asc())
        .first()
    )
    if not candidate:
        return None
    now = datetime.utcnow()
    result = db.session.execute(
        text(
            """
            UPDATE background_jobs
            SET status = 'running',
                started_at = :started_at,
                attempts = attempts + 1
            WHERE id = :id AND status = 'pending'
            """
        ),
        {"id": candidate.id, "started_at": now},
    )
    db.session.commit()
    if not result.rowcount:
        return None
    return BackgroundJob.query.get(candidate.id)


def _process_one(app: Flask) -> bool:
    """Claim and run one pending job. Returns True if work was done."""
    with app.app_context():
        recover_stuck_jobs()
        job = claim_next_pending_job()
        if not job:
            return False
        payload = job.payload()
        try:
            if job.job_type == "persist_signed_pdf":
                from models import Document
                from services.documents_pdf import _persist_signed_pdf_copy

                doc = Document.query.get(int(payload["document_id"]))
                username = payload.get("username") or ""
                if doc and username:
                    _persist_signed_pdf_copy(doc, username)
                    db.session.commit()
            else:
                raise ValueError(f"Unknown job_type: {job.job_type}")
            job.status = "done"
            job.finished_at = datetime.utcnow()
            job.last_error = None
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            job = BackgroundJob.query.get(job.id)
            if job:
                if can_retry_job(job.attempts):
                    job.status = "pending"
                    job.started_at = None
                    job.finished_at = None
                    job.last_error = str(exc)[:4000]
                else:
                    job.status = "failed"
                    job.finished_at = datetime.utcnow()
                    job.last_error = str(exc)[:4000]
                db.session.commit()
            app.logger.exception("background job %s failed", job.id if job else "?")
        return True


def _worker_loop(app: Flask) -> None:
    idle_rounds = 0
    while True:
        try:
            did = _process_one(app)
            if did:
                idle_rounds = 0
                continue
            idle_rounds += 1
            if idle_rounds > 120:
                break
            time.sleep(1)
        except Exception:
            try:
                app.logger.exception("background worker loop error")
            except Exception:
                pass
            time.sleep(2)
    global _worker_started
    with _worker_lock:
        _worker_started = False


def start_worker(app: Flask) -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        t = threading.Thread(target=_worker_loop, args=(app,), daemon=True, name="pdf-job-worker")
        t.start()
