"""Static upload asset routes (logo, favicon, quick-links, hero)."""
from __future__ import annotations

from flask import Flask, abort, send_from_directory


def register(app: Flask) -> None:
    @app.route('/uploads/ziebart.svg')
    def serve_ziebart_logo():
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 'ziebart.svg', mimetype='image/svg+xml'
        )

    @app.route('/favicon.ico')
    def serve_favicon():
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 'ziebart.svg', mimetype='image/svg+xml'
        )

    @app.route('/uploads/quick-links/<filename>')
    def serve_quick_link_image(filename):
        try:
            quick_links_folder = app.config['UPLOAD_FOLDER'] / 'quick_links'
            if not quick_links_folder.exists():
                quick_links_folder.mkdir(exist_ok=True)
            return send_from_directory(quick_links_folder, filename)
        except Exception:
            abort(404)

    @app.route('/uploads/dashboard-hero/<filename>')
    def serve_dashboard_hero(filename):
        try:
            hero_folder = app.config['UPLOAD_FOLDER'] / 'dashboard_hero'
            if not hero_folder.exists():
                abort(404)
            return send_from_directory(hero_folder, filename)
        except Exception:
            abort(404)
