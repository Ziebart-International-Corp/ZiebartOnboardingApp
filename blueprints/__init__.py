"""Route packages split out of app.py.

We use register(app) + @app.route (not Flask Blueprint name prefixes) so
existing url_for('admin_dashboard') / url_for('feedback') keep working.
"""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Attach extracted route modules. Call at the end of app.py after helpers exist."""
    from blueprints import auth, feedback, help as help_bp, manager, admin, documents, wizard, user

    auth.register(app)
    feedback.register(app)
    help_bp.register(app)
    manager.register(app)
    admin.register(app)
    documents.register(app)
    wizard.register(app)
    user.register(app)
