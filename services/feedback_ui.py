"""Feedback header button markup and display helpers."""
from __future__ import annotations

from flask import current_app, request, url_for
from flask_login import current_user
from markupsafe import Markup

from models import NewHire, User as UserModel


def _feedback_header_button_html(is_active=False):
    active_cls = ' is-active' if is_active else ''
    return (
        f'<a href="{url_for("feedback")}" id="app-feedback-header-btn" '
        f'class="feedback-header-btn{active_cls}" title="Send feedback">'
        '<svg class="feedback-header-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
        '<path d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v7A2.5 2.5 0 0117.5 16H11l-4.5 4v-4H6.5A2.5 2.5 0 014 13.5v-7z" '
        'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>'
        '<path d="M8.5 9h7M8.5 12.5h4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        '</svg>'
        '<span class="feedback-header-label">Feedback</span></a>'
    )


def _feedback_allowed_image(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config['FEEDBACK_ALLOWED_IMAGE_EXTENSIONS']


_FEEDBACK_BTN_CSS = (
    '<style id="app-feedback-header-style">'
    '.feedback-header-btn{display:inline-flex!important;align-items:center!important;'
    'justify-content:center!important;gap:6px!important;padding:7px 12px!important;'
    'border-radius:999px!important;font-size:0.82em!important;font-weight:600!important;'
    'line-height:1.2!important;text-decoration:none!important;color:#f2f5fb!important;'
    'background:rgba(255,255,255,0.08)!important;border:1px solid rgba(255,255,255,0.2)!important;'
    'white-space:nowrap!important;flex-shrink:0;z-index:50;}'
    '.feedback-header-btn:hover{background:rgba(254,1,0,0.18)!important;'
    'border-color:rgba(254,1,0,0.45)!important;color:#fff!important;}'
    '.feedback-header-btn .feedback-header-svg{width:16px;height:16px;flex-shrink:0;}'
    '.feedback-header-btn.is-active{background:rgba(254,1,0,0.22)!important;'
    'border-color:rgba(254,1,0,0.55)!important;color:#fff!important;}'
    '.feedback-header-btn.is-floating{position:fixed!important;top:14px;right:14px;'
    'z-index:10050!important;box-shadow:0 8px 24px rgba(0,0,0,0.28)!important;'
    'background:rgba(12,16,23,0.92)!important;}'
    '@media (max-width:768px){.feedback-header-btn .feedback-header-label{'
    'position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;'
    'clip:rect(0,0,0,0);white-space:nowrap;border:0;}'
    '.feedback-header-btn{padding:8px!important;min-width:36px;min-height:36px;}}'
    '</style>'
)


def feedback_global_inject_markup():
    """Inject feedback header button on every authenticated HTML page."""
    try:
        if not current_user.is_authenticated:
            return Markup('')
    except Exception:
        return Markup('')
    is_active = getattr(request, 'endpoint', None) == 'feedback'
    active_cls = ' is-active' if is_active else ''
    feedback_url = url_for('feedback')
    svg = (
        '<svg class="feedback-header-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
        '<path d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v7A2.5 2.5 0 0117.5 16H11l-4.5 4v-4H6.5A2.5 2.5 0 014 13.5v-7z" '
        'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>'
        '<path d="M8.5 9h7M8.5 12.5h4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        '</svg><span class="feedback-header-label">Feedback</span>'
    )
    script = (
        '<script>(function(){'
        'if(document.getElementById("app-feedback-header-btn"))return;'
        'if(!document.getElementById("app-feedback-header-style")){'
        'document.head.insertAdjacentHTML("beforeend",' + repr(_FEEDBACK_BTN_CSS) + ');'
        '}'
        'var selectors=['
        '".top-header .user-section",'
        '".top-header .header-right",'
        '".top-header .header-actions",'
        '".header .header-actions",'
        '".header .user-section",'
        '".top-header",'
        '".header"'
        '];'
        'var target=null;'
        'for(var i=0;i<selectors.length;i++){'
        'target=document.querySelector(selectors[i]);'
        'if(target)break;'
        '}'
        'var a=document.createElement("a");'
        'a.id="app-feedback-header-btn";'
        f'var base={feedback_url!r};'
        'a.href=base+"?from="+encodeURIComponent(window.location.pathname+window.location.search);'
        f'a.className="feedback-header-btn{active_cls}";'
        'a.title="Send feedback";'
        f'a.innerHTML={svg!r};'
        'if(target){'
        'if(target.firstChild){target.insertBefore(a,target.firstChild);}'
        'else{target.appendChild(a);}'
        '}else{'
        'a.className+=" is-floating";'
        'document.body.appendChild(a);'
        '}'
        '})();</script>'
    )
    return Markup(_FEEDBACK_BTN_CSS + script)


def _feedback_user_display_context():
    """Name and email for feedback submissions."""
    username = current_user.username if current_user.is_authenticated else ''
    full_name = username
    email = ''
    try:
        user_record = UserModel.query.filter_by(username=username).first()
        if user_record:
            full_name = (user_record.full_name or '').strip() or username
            email = (user_record.email or '').strip()
        new_hire = NewHire.query.filter_by(username=username).first()
        if new_hire:
            _fn = (new_hire.first_name or '').strip()
            _ln = (new_hire.last_name or '').strip()
            nh_name = f'{_fn} {_ln}'.strip()
            if nh_name:
                full_name = nh_name
            if not email:
                email = (new_hire.email or '').strip()
    except Exception:
        pass
    return {
        'username': username,
        'full_name': full_name or username,
        'email': email,
    }
