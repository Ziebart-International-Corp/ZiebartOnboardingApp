"""User feedback form route."""
from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required


def register(app: Flask) -> None:
    """Register feedback routes on the main Flask app (endpoint names unchanged)."""

    @app.route("/feedback", methods=["GET", "POST"])
    @login_required
    def feedback():
        """Collect app feedback (Asana task creation will be wired up later)."""
        import app as main

        user_ctx = main._feedback_user_display_context()
        is_admin = current_user.is_admin() if current_user else False
        user_first_name = (
            (user_ctx["full_name"].split()[0] if user_ctx["full_name"] else "U") or "U"
        )
        user_full_name = user_ctx["full_name"]
        default_page_url = (
            request.form.get("page_url")
            or request.args.get("from")
            or request.referrer
            or ""
        ).strip()
        if (
            default_page_url
            and default_page_url.startswith("http")
            and request.host not in default_page_url
        ):
            default_page_url = ""
        if default_page_url and default_page_url.startswith("/") and request.host:
            default_page_url = request.url_root.rstrip("/") + default_page_url

        form_values = {
            "feedback_type": "comment",
            "title": "",
            "description": "",
            "page_url": default_page_url,
        }

        if request.method == "POST":
            form_values["feedback_type"] = (
                request.form.get("feedback_type") or "comment"
            ).strip()
            form_values["title"] = (request.form.get("title") or "").strip()
            form_values["description"] = (request.form.get("description") or "").strip()
            form_values["page_url"] = (request.form.get("page_url") or "").strip()

            valid_types = {t[0] for t in main.FEEDBACK_TYPES}
            if form_values["feedback_type"] not in valid_types:
                form_values["feedback_type"] = "comment"
            if not form_values["description"]:
                flash("Please enter a comment or description.", "error")
            else:
                photo = request.files.get("photo")
                try:
                    _path, asana_task_id, asana_error = main._save_feedback_submission(
                        {
                            "feedback_type": form_values["feedback_type"],
                            "title": form_values["title"],
                            "description": form_values["description"],
                            "page_url": form_values["page_url"],
                            "username": user_ctx["username"],
                            "full_name": user_ctx["full_name"],
                            "email": user_ctx["email"],
                        },
                        photo_file=photo if photo and photo.filename else None,
                    )
                    if asana_task_id:
                        flash(
                            "Thanks for your feedback! A task was created in Asana for the team to review.",
                            "success",
                        )
                    elif asana_error:
                        flash(
                            "Thanks — we saved your feedback, but could not create the Asana task. An admin may need to reconnect Asana.",
                            "success",
                        )
                    else:
                        flash(
                            "Thanks for your feedback! We received it and will review it soon.",
                            "success",
                        )
                    return redirect(url_for("feedback"))
                except ValueError as exc:
                    flash(str(exc), "error")
                except Exception as exc:
                    main._log_exception_to_file(exc)
                    flash(
                        "Something went wrong while sending your feedback. Please try again.",
                        "error",
                    )

        return render_template(
            "feedback/index.html",
            is_admin=is_admin,
            user_first_name=user_first_name,
            user_full_name=user_full_name,
            feedback_type_options=main.FEEDBACK_TYPES,
            form_values=form_values,
            feedback_header_button=main._feedback_header_button_html(is_active=True),
        )
