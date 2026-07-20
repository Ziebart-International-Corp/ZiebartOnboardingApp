"""Help Center routes: searchable how-tos and admin article management."""
from __future__ import annotations

from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth import admin_required
from models import HelpArticle, User as UserModel, db
from services.help_content import (
    HELP_AUDIENCES,
    article_visible_to_current_user,
    current_help_role,
    ensure_seed_help_articles,
    permission_label,
    render_article_body,
    search_articles,
    unique_slug,
    visible_articles_query,
)
from services.stores_scope import MANAGER_PERMISSION_KEYS


def _page_from_param() -> str:
    raw = (request.args.get('from') or '').strip()
    if not raw:
        return ''
    if raw.startswith('http'):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(raw)
            if request.host and parsed.netloc and request.host not in parsed.netloc:
                return ''
            return (parsed.path or '') + (('?' + parsed.query) if parsed.query else '')
        except Exception:
            return ''
    if raw.startswith('/'):
        return raw[:500]
    return ''


def _user_display_name() -> tuple[str, str]:
    first = 'U'
    full = current_user.username if current_user.is_authenticated else 'User'
    try:
        rec = UserModel.query.filter_by(username=current_user.username).first()
        if rec and (rec.full_name or '').strip():
            full = rec.full_name.strip()
            first = full.split()[0]
        else:
            first = (current_user.username or 'U')[0].upper()
    except Exception:
        pass
    return first, full


def _ensure_help_schema():
    try:
        from db.migrations_runtime import _ensure_help_tables
        _ensure_help_tables()
    except Exception:
        pass


def register(app: Flask) -> None:
    """Register help center and admin help article routes."""

    @app.route('/help')
    @login_required
    def help_center():
        _ensure_help_schema()
        try:
            ensure_seed_help_articles()
        except Exception:
            pass
        q = (request.args.get('q') or '').strip()
        page_from = _page_from_param()
        if q:
            articles = search_articles(q, limit=30)
        else:
            articles = visible_articles_query().limit(40).all()
        first, full = _user_display_name()
        return render_template(
            'help/index.html',
            articles=articles,
            query=q,
            page_from=page_from,
            help_role=current_help_role(),
            is_admin=current_user.is_admin(),
            user_first_name=first,
            user_full_name=full,
            permission_label=permission_label,
        )

    @app.route('/help/search')
    @login_required
    def help_search():
        q = (request.args.get('q') or '').strip()
        kwargs = {'q': q} if q else {}
        if request.args.get('from'):
            kwargs['from'] = request.args.get('from')
        return redirect(url_for('help_center', **kwargs))

    @app.route('/help/article/<slug>')
    @login_required
    def help_article(slug):
        _ensure_help_schema()
        article = HelpArticle.query.filter_by(slug=slug).first_or_404()
        if not article_visible_to_current_user(article) and not current_user.is_admin():
            abort(404)
        if not article.is_published and not current_user.is_admin():
            abort(404)
        first, full = _user_display_name()
        return render_template(
            'help/article.html',
            article=article,
            body_html=render_article_body(article.body),
            page_from=_page_from_param(),
            is_admin=current_user.is_admin(),
            user_first_name=first,
            user_full_name=full,
            permission_label=permission_label,
        )

    @app.route('/help/ask', methods=['GET', 'POST'])
    @login_required
    def help_ask():
        """Legacy URL — questions go through Feedback."""
        return redirect(url_for('feedback', **({'from': request.args.get('from')} if request.args.get('from') else {})))

    # ----- Admin -----

    @app.route('/admin/help')
    @admin_required
    def manage_help():
        _ensure_help_schema()
        articles = HelpArticle.query.order_by(
            HelpArticle.sort_order.asc(), HelpArticle.title.asc()
        ).all()
        return render_template(
            'admin/help_articles.html',
            articles=articles,
            permission_label=permission_label,
            audiences=HELP_AUDIENCES,
        )

    @app.route('/admin/help/new', methods=['GET', 'POST'])
    @admin_required
    def manage_help_new():
        return _help_article_form(article=None)

    @app.route('/admin/help/<int:article_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def manage_help_edit(article_id):
        article = HelpArticle.query.get_or_404(article_id)
        return _help_article_form(article=article)

    def _help_article_form(article: HelpArticle | None):
        _ensure_help_schema()
        if request.method == 'POST':
            title = (request.form.get('title') or '').strip()
            body = (request.form.get('body') or '').strip()
            audience = (request.form.get('audience') or 'all').strip().lower()
            if audience not in dict(HELP_AUDIENCES):
                audience = 'all'
            permission_key = (request.form.get('permission_key') or '').strip() or None
            related_path = (request.form.get('related_path') or '').strip() or None
            tags = (request.form.get('tags') or '').strip() or None
            sort_order = request.form.get('sort_order') or '0'
            try:
                sort_order_i = int(sort_order)
            except ValueError:
                sort_order_i = 0
            is_published = request.form.get('is_published') == '1'
            if not title or not body:
                flash('Title and body are required.', 'error')
            else:
                if article is None:
                    article = HelpArticle(created_by=current_user.username)
                    db.session.add(article)
                article.title = title
                article.slug = unique_slug(title, exclude_id=article.id if article.id else None)
                article.body = body
                article.audience = audience
                article.permission_key = permission_key
                article.related_path = related_path
                article.tags = tags
                article.sort_order = sort_order_i
                article.is_published = is_published
                article.updated_at = datetime.utcnow()
                db.session.commit()
                flash('Help article saved.', 'success')
                return redirect(url_for('manage_help'))
        return render_template(
            'admin/help_article_edit.html',
            article=article,
            audiences=HELP_AUDIENCES,
            permission_keys=MANAGER_PERMISSION_KEYS,
        )

    @app.route('/admin/help/<int:article_id>/delete', methods=['POST'])
    @admin_required
    def manage_help_delete(article_id):
        article = HelpArticle.query.get_or_404(article_id)
        db.session.delete(article)
        db.session.commit()
        flash('Article deleted.', 'success')
        return redirect(url_for('manage_help'))

    @app.route('/admin/help/requests', methods=['GET', 'POST'])
    @admin_required
    def manage_help_requests():
        """Legacy URL — feedback lives under Asana Feedback / Feedback button."""
        return redirect(url_for('admin_asana_feedback'))
