"""Manager console routes."""
from __future__ import annotations

from flask import Flask, render_template
from flask_login import current_user

from auth import manager_required
from models import NewHire, Store


def register(app: Flask) -> None:
    """Register manager routes on the main Flask app (endpoint names unchanged)."""

    @app.route("/manager")
    @manager_required
    def manager_dashboard():
        """Manager Console: store-scoped onboarding, new hires, and documents."""
        import app as main

        main.touch_staff_console_home("manager")
        store_id = main.get_current_user_store_id()
        if store_id:
            store = Store.query.get(store_id)
            store_name = store.name if store else f"Store #{store_id}"
        else:
            store_name = "Not assigned"

        new_hires_count = 0
        documents_count = 0
        try:
            q = NewHire.query.filter(NewHire.status != "removed")
            if store_id is not None:
                q = q.filter(NewHire.store_id == store_id)
            new_hires_count = q.count()
        except Exception:
            pass
        try:
            q = main.documents_visible_to_store_query(store_id)
            documents_count = q.count()
        except Exception:
            pass

        _mgr_un = (current_user.username if current_user else "") or ""
        manager_name = (
            main.staff_header_display_name(_mgr_un) if _mgr_un else "Manager"
        )
        can_start = main.manager_has_permission("start_onboarding")
        can_documents = main.manager_has_permission("manage_documents")
        can_training = main.manager_has_permission("manage_training")
        can_checklist = main.manager_has_permission("manage_checklist")
        can_user_checklists = main.manager_has_permission("manage_user_checklists")

        return render_template(
            "manager/dashboard.html",
            store_id=store_id,
            store_name=store_name,
            new_hires_count=new_hires_count,
            documents_count=documents_count,
            manager_name=manager_name,
            can_start=can_start,
            can_documents=can_documents,
            can_training=can_training,
            can_checklist=can_checklist,
            can_user_checklists=can_user_checklists,
        )
