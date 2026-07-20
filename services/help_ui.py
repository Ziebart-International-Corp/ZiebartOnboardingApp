"""Global Help (?) header button injected on authenticated HTML pages."""
from __future__ import annotations

from flask import request, url_for
from flask_login import current_user
from markupsafe import Markup


_HELP_BTN_CSS = (
    '<style id="app-help-header-style">'
    '.help-header-btn{display:inline-flex!important;align-items:center!important;'
    'justify-content:center!important;width:36px!important;height:36px!important;'
    'min-width:36px!important;min-height:36px!important;padding:0!important;'
    'border-radius:50%!important;font-size:1.15em!important;font-weight:800!important;'
    'line-height:1!important;text-decoration:none!important;color:#f2f5fb!important;'
    'background:rgba(255,255,255,0.1)!important;border:1px solid rgba(255,255,255,0.28)!important;'
    'flex-shrink:0;z-index:60;margin-right:10px!important;box-sizing:border-box!important;}'
    '.help-header-btn:hover{background:rgba(254,1,0,0.22)!important;'
    'border-color:rgba(254,1,0,0.5)!important;color:#fff!important;}'
    '.help-header-btn.is-active{background:rgba(254,1,0,0.28)!important;'
    'border-color:rgba(254,1,0,0.6)!important;color:#fff!important;}'
    '.help-header-btn.is-floating{position:fixed!important;top:14px;left:14px;'
    'z-index:10050!important;box-shadow:0 8px 24px rgba(0,0,0,0.28)!important;'
    'background:rgba(12,16,23,0.92)!important;margin-right:0!important;}'
    '.top-header,.header{position:relative;}'
    '</style>'
)


def help_global_inject_markup():
    """Inject a ? help button at the top-left of page headers."""
    try:
        if not current_user.is_authenticated:
            return Markup('')
    except Exception:
        return Markup('')
    endpoint = getattr(request, 'endpoint', None) or ''
    is_active = endpoint.startswith('help') or endpoint in (
        'help_center', 'help_article', 'help_search',
        'manage_help', 'manage_help_edit', 'manage_help_new',
    )
    active_cls = ' is-active' if is_active else ''
    help_url = url_for('help_center')
    script = (
        '<script>(function(){'
        'if(document.getElementById("app-help-header-btn"))return;'
        'if(!document.getElementById("app-help-header-style")){'
        'document.head.insertAdjacentHTML("beforeend",' + repr(_HELP_BTN_CSS) + ');'
        '}'
        'var selectors=['
        '".top-header .logo-section",'
        '".top-header",'
        '".header"'
        '];'
        'var target=null;'
        'for(var i=0;i<selectors.length;i++){'
        'target=document.querySelector(selectors[i]);'
        'if(target)break;'
        '}'
        'var a=document.createElement("a");'
        'a.id="app-help-header-btn";'
        f'var base={help_url!r};'
        'a.href=base+"?from="+encodeURIComponent(window.location.pathname+window.location.search);'
        f'a.className="help-header-btn{active_cls}";'
        'a.title="Help — search how-to articles";'
        'a.setAttribute("aria-label","Help");'
        'a.textContent="?";'
        'if(target){'
        'if(target.firstChild){target.insertBefore(a,target.firstChild);}'
        'else{target.appendChild(a);}'
        '}else{'
        'a.className+=" is-floating";'
        'document.body.appendChild(a);'
        '}'
        '})();</script>'
    )
    return Markup(_HELP_BTN_CSS + script)
