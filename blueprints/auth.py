"""Login, logout, change-password, index, and GraphQL entry routes."""
from __future__ import annotations

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from auth import authenticate_by_email_password
from models import User as UserModel
from models import db


def register(app: Flask) -> None:
    """Register auth routes on the main Flask app (endpoint names unchanged)."""

    @app.route("/")
    def index():
        """Home: redirect to dashboard if logged in, else to login."""
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/api/graphql", methods=["GET", "POST"])
    @login_required
    def graphql_api():
        """GraphQL API: all database access for the API goes through this endpoint."""
        import app as main

        graphql_schema = getattr(main, "graphql_schema", None)
        if request.method == "GET":
            return """
        <!DOCTYPE html>
        <html><head><title>GraphQL API</title></head>
        <body>
        <h1>GraphQL API</h1>
        <p>Send a POST request with JSON body: <code>{"query": "query { ... }"}</code></p>
        <p>Example query:</p>
        <pre>
query {
  newHires(limit: 5) {
    username
    firstName
    lastName
    email
    status
  }
  roles { id name }
}
        </pre>
        <form method="post" action="/api/graphql">
        <textarea name="query" rows="12" cols="80" placeholder="query { newHires(limit: 2) { username firstName lastName } }"></textarea><br>
        <button type="submit">Execute</button>
        </form>
        </body></html>
        """
        data = request.get_json(silent=True) or {}
        query = data.get("query") or request.form.get("query") or ""
        variables = data.get("variables") or {}
        operation_name = data.get("operationName")
        if not query:
            return jsonify({"errors": [{"message": "Missing query"}]}), 400
        if not graphql_schema:
            return jsonify({"errors": [{"message": "GraphQL not available"}]}), 503
        result = graphql_schema.execute(
            query,
            context_value={"request": request, "current_user": current_user},
            variable_values=variables,
            operation_name=operation_name,
        )
        status = 200
        if result and result.errors:
            status = 400
        return jsonify(
            {
                "data": result.data if result else None,
                "errors": [{"message": e.message} for e in (result.errors or [])],
            }
        ), status

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """Login with email and password."""
        import app as main

        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        next_url = request.args.get("next") or url_for("dashboard")
        if request.method == "POST":
            try:
                email = (request.form.get("email") or "").strip()
                password = request.form.get("password") or ""
                user = authenticate_by_email_password(email, password)
                if user:
                    login_user(user, remember=True)
                    main.update_last_login(user.username)
                    if main.user_must_change_password(user.username):
                        return redirect(url_for("change_password"))
                    next_after = (
                        request.form.get("next")
                        or request.args.get("next")
                        or url_for("dashboard")
                    )
                    return redirect(url_for("welcome", next=next_after))
                flash("Invalid email or password. Please try again.", "error")
            except Exception as e:
                main._log_exception_to_file(e)
                raise
        return render_template("auth/login.html", next_url=next_url)

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        """Let users set a new password after logging in with a temporary password."""
        import app as main

        main._ensure_users_must_change_password_column()
        user_record = UserModel.query.filter_by(username=current_user.username).first()
        if not user_record:
            flash("User profile not found.", "error")
            return redirect(url_for("logout"))
        forced = main.user_must_change_password(current_user.username)
        if request.method == "POST":
            current_pw = request.form.get("current_password") or ""
            new_pw = (request.form.get("new_password") or "").strip()
            confirm_pw = (request.form.get("confirm_password") or "").strip()
            if not user_record.password_hash or not check_password_hash(
                user_record.password_hash, current_pw
            ):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("change_password"))
            if new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
                return redirect(url_for("change_password"))
            if len(new_pw) < 6:
                flash("Password must be at least 6 characters.", "error")
                return redirect(url_for("change_password"))
            if check_password_hash(user_record.password_hash, new_pw):
                flash(
                    "Choose a password that is different from your temporary password.",
                    "error",
                )
                return redirect(url_for("change_password"))
            user_record.password_hash = generate_password_hash(new_pw)
            user_record.must_change_password = False
            try:
                db.session.commit()
                flash("Your password has been updated.", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                db.session.rollback()
                flash(f"Could not update password: {str(e)}", "error")
                return redirect(url_for("change_password"))
        return render_template("auth/change_password.html", forced=forced)

    @app.route("/logout")
    @login_required
    def logout():
        """Logout and redirect to login."""
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))
