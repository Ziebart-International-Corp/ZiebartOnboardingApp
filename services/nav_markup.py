"""User mobile tab bar and staff dropdown markup."""
from __future__ import annotations

from flask import request, url_for, session
from flask_login import current_user
from markupsafe import Markup

USER_MOBILE_TABBAR_SHOW = frozenset({
    'dashboard', 'user_tasks', 'view_documents', 'list_training_videos', 'profile',
})



def user_mobile_bottom_nav_markup():
    if not getattr(request, 'endpoint', None):
        return Markup('')
    ep = request.endpoint
    if ep not in USER_MOBILE_TABBAR_SHOW:
        return Markup('')
    ar = ep
    h = (
        '<path d="M4.5 10.5 12 4.5l7.5 6V19a1 1 0 01-1 1h-4.25v-5.5h-2.5V20H6a1 1 0 01-1-1v-8.5z" '
        'stroke="currentColor" stroke-width="1.35" stroke-linejoin="round" fill="none"/>'
    )
    c = (
        '<rect x="6" y="5" width="12" height="15" rx="1.75" stroke="currentColor" stroke-width="1.35" fill="none"/>'
        '<path d="M9 5V4a1 1 0 011-1h4a1 1 0 011 1v1" stroke="currentColor" stroke-width="1.35" fill="none"/>'
        '<path d="M8.5 10h7M8.5 13h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>'
    )
    f = (
        '<path d="M4.5 8.5a1.5 1.5 0 011.5-1.5h4.2l1.6 2.2h6.2a1.5 1.5 0 011.5 1.5v7.8a1.5 1.5 0 01-1.5 1.5H6a1.5 1.5 0 01-1.5-1.5v-8.5z" '
        'stroke="currentColor" stroke-width="1.35" stroke-linejoin="round" fill="none"/>'
    )
    v = (
        '<rect x="4.5" y="5.5" width="15" height="13" rx="2.5" stroke="currentColor" stroke-width="1.35" fill="none"/>'
        '<path d="M10.2 9.2v5.6L15.4 12l-5.2-2.8z" stroke="currentColor" stroke-width="1.35" '
        'stroke-linejoin="round" fill="none"/>'
    )
    p = (
        '<circle cx="12" cy="8.25" r="3.15" stroke="currentColor" stroke-width="1.35" fill="none"/>'
        '<path d="M5.5 19.5v-.8a6.5 6.5 0 0113 0v.8" stroke="currentColor" stroke-width="1.35" '
        'stroke-linecap="round" fill="none"/>'
    )
    def svg(inner):
        return (
            f'<svg class="mobile-tab-svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{inner}</svg>'
        )
    def link(route, label, inner_svg):
        cls = 'mobile-tab mobile-tab-active' if ar == route else 'mobile-tab'
        return (
            f'<a href="{url_for(route)}" class="{cls}">'
            f'<span class="mobile-tab-icon">{svg(inner_svg)}</span>'
            f'<span class="mobile-tab-label">{label}</span></a>'
        )
    parts = [
        link('dashboard', 'Home', h),
        link('user_tasks', 'Tasks', c),
        link('view_documents', 'Files', f),
        link('list_training_videos', 'Videos', v),
        link('profile', 'Profile', p),
    ]
    return Markup(
        '<nav class="mobile-bottom-nav" aria-label="Primary navigation">' + ''.join(parts) + '</nav>'
    )

def staff_console_dropdown_links_markup():
    """User / Admin / Manager / Logout links for staff headers (visibility follows current_user role)."""
    try:
        from flask_login import current_user as _cu
    except Exception:
        return Markup('')
    if not getattr(_cu, 'is_authenticated', False):
        return Markup('')
    parts = [f'<a href="{url_for("dashboard")}" class="dropdown-item">User Dashboard</a>']
    try:
        if _cu.is_admin():
            parts.append(
                f'<a href="{url_for("admin_dashboard", staff_console="admin")}" class="dropdown-item">Admin Console</a>'
            )
        if _cu.is_manager():
            parts.append(
                f'<a href="{url_for("manager_dashboard", staff_console="manager")}" class="dropdown-item">Manager Console</a>'
            )
    except Exception:
        pass
    parts.append(f'<a href="{url_for("logout")}" class="dropdown-item">Logout</a>')
    return Markup(''.join(parts))

