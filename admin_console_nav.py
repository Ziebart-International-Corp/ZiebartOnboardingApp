"""Collapsible left navigation for admin / staff console pages."""
from __future__ import annotations

from typing import Any, Callable, Optional

from flask import url_for
from markupsafe import Markup, escape

# Endpoints that use the staff console layout (admin or manager tools).
_STAFF_CONSOLE_EXACT = frozenset({
    'admin_dashboard',
    'manager_dashboard',
    'view_all_new_hires',
    'add_new_hire',
    'manage_documents',
    'manage_training',
    'manage_checklist',
    'admin_assign_task',
    'manage_users',
    'manage_admins',
    'manage_stores',
    'manage_departments',
    'admin_test_form',
    'admin_test_form_fill',
    'admin_test_form_review',
    'manage_roles',
    'admin_reports',
    'admin_jobs',
    'manage_external_links',
    'manage_onboarding_messages',
    'admin_asana_feedback',
    'assign_document',
    'assign_document_submit',
    'upload_document',
    'manage_store_edit',
    'admin_settings',
    'manager_new_hires',
    'view_user_checklists',
})

_STAFF_CONSOLE_PREFIXES = ('admin_', 'manage_')


def is_staff_console_page(endpoint: Optional[str]) -> bool:
    if not endpoint:
        return False
    if endpoint in _STAFF_CONSOLE_EXACT:
        return True
    return any(endpoint.startswith(p) for p in _STAFF_CONSOLE_PREFIXES)


def _endpoint_active(active: Optional[str], endpoints: tuple[str, ...]) -> bool:
    if not active or not endpoints:
        return False
    return active in endpoints


def build_staff_nav_items(
    *,
    is_admin: bool,
    has_permission: Callable[[str], bool],
    staff_console: str = 'admin',
    manager_new_hires_url: str = '',
) -> list[dict[str, Any]]:
    """Build nav links for admin or manager console."""
    sc = staff_console if staff_console in ('admin', 'manager') else 'admin'
    if sc == 'manager':
        return build_manager_nav_items(
            has_permission=has_permission,
            manager_new_hires_url=manager_new_hires_url,
        )
    return build_admin_nav_items(
        is_admin=is_admin,
        has_permission=has_permission,
    )


def build_manager_nav_items(
    *,
    has_permission: Callable[[str], bool],
    manager_new_hires_url: str,
) -> list[dict[str, Any]]:
    """Manager Console menu — matches dashboard cards."""
    sc = 'manager'
    items: list[dict[str, Any]] = [
        {
            'label': 'Dashboard',
            'icon': '🏠',
            'url': url_for('manager_dashboard', staff_console=sc),
            'endpoints': ('manager_dashboard',),
        },
    ]

    if has_permission('start_onboarding'):
        items.append({
            'label': 'Start onboarding',
            'icon': '➕',
            'url': url_for('add_new_hire', staff_console=sc),
            'endpoints': ('add_new_hire',),
        })

    items.append({
        'label': 'New hires',
        'icon': '👥',
        'url': manager_new_hires_url or url_for('manager_new_hires'),
        'endpoints': ('manager_new_hires', 'view_all_new_hires'),
    })

    if has_permission('manage_documents'):
        items.append({
            'label': 'Forms / documents',
            'icon': '📄',
            'url': url_for('manage_documents', staff_console=sc),
            'endpoints': ('manage_documents', 'assign_document', 'assign_document_submit', 'upload_document'),
        })

    if has_permission('manage_training'):
        items.append({
            'label': 'Training library',
            'icon': '▶️',
            'url': url_for('manage_training', staff_console=sc),
            'endpoints': ('manage_training',),
        })

    if has_permission('manage_checklist') or has_permission('manage_user_checklists'):
        items.append({
            'label': 'Onboarding checklists',
            'icon': '📋',
            'url': url_for('view_user_checklists', staff_console=sc),
            'endpoints': ('view_user_checklists',),
        })

    return items


def build_admin_nav_items(
    *,
    is_admin: bool,
    has_permission: Callable[[str], bool],
) -> list[dict[str, Any]]:
    """Admin Console menu — full admin quick links."""
    sc = 'admin'
    items: list[dict[str, Any]] = [
        {
            'label': 'Dashboard',
            'icon': '🏠',
            'url': url_for('admin_dashboard', staff_console=sc),
            'endpoints': ('admin_dashboard',),
        },
    ]

    if is_admin or has_permission('start_onboarding'):
        items.append({
            'label': 'New hires (all stores)',
            'icon': '👥',
            'url': url_for('view_all_new_hires', staff_console=sc),
            'endpoints': ('view_all_new_hires',),
        })

    if is_admin or has_permission('manage_checklist'):
        items.append({
            'label': 'Onboarding Tasks',
            'icon': '📋',
            'url': url_for('manage_checklist', staff_console=sc),
            'endpoints': ('manage_checklist',),
        })

    if is_admin or has_permission('manage_training'):
        items.append({
            'label': 'Training Library',
            'icon': '▶️',
            'url': url_for('manage_training', staff_console=sc),
            'endpoints': ('manage_training',),
        })

    if is_admin or has_permission('manage_documents'):
        items.append({
            'label': 'Manage Forms',
            'icon': '📄',
            'url': url_for('manage_documents', staff_console=sc),
            'endpoints': ('manage_documents', 'assign_document', 'assign_document_submit', 'upload_document'),
        })

    if is_admin or has_permission('start_onboarding'):
        items.append({
            'label': 'Start Onboarding',
            'icon': '➕',
            'url': url_for('add_new_hire', staff_console=sc),
            'endpoints': ('add_new_hire',),
        })

    if is_admin:
        items.extend([
            {
                'label': 'Assign task to user',
                'icon': '✅',
                'url': url_for('admin_assign_task', staff_console='admin'),
                'endpoints': ('admin_assign_task',),
            },
            {
                'label': 'Manage Users',
                'icon': '👤',
                'url': url_for('manage_users'),
                'endpoints': ('manage_users',),
            },
            {
                'label': 'Manage Admins',
                'icon': '🛡️',
                'url': url_for('manage_admins'),
                'endpoints': ('manage_admins',),
            },
            {
                'label': 'Manage Stores',
                'icon': '🏪',
                'url': url_for('manage_stores'),
                'endpoints': ('manage_stores', 'manage_store_edit'),
            },
            {
                'label': 'Manage Departments',
                'icon': '🏢',
                'url': url_for('manage_departments'),
                'endpoints': ('manage_departments',),
            },
        ])
        from flask import current_app
        if current_app.config.get('ENABLE_TEST_FORM_WIZARD'):
            items.append({
                'label': 'Test Form Wizard',
                'icon': '🧪',
                'url': url_for('admin_test_form'),
                'endpoints': (
                    'admin_test_form', 'admin_test_form_fill',
                    'admin_test_form_review', 'admin_test_form_analyze',
                ),
            })

    admin_tail = [
        {
            'label': 'Manage Position/Title',
            'icon': '🎭',
            'url': url_for('manage_roles'),
            'endpoints': ('manage_roles',),
        },
        {
            'label': 'Reports',
            'icon': '📊',
            'url': url_for('admin_reports'),
            'endpoints': ('admin_reports',),
        },
        {
            'label': 'Background Jobs',
            'icon': '⚙️',
            'url': url_for('admin_jobs'),
            'endpoints': ('admin_jobs', 'admin_jobs_requeue'),
        },
        {
            'label': 'External Links',
            'icon': '🔗',
            'url': url_for('manage_external_links'),
            'endpoints': ('manage_external_links',),
        },
        {
            'label': 'Onboarding Messages',
            'icon': '💬',
            'url': url_for('manage_onboarding_messages'),
            'endpoints': ('manage_onboarding_messages',),
        },
        {
            'label': 'Asana Feedback',
            'icon': '📋',
            'url': url_for('admin_asana_feedback'),
            'endpoints': ('admin_asana_feedback',),
        },
    ]
    if is_admin:
        items.extend(admin_tail)

    return items


ADMIN_NAV_CSS = """
#adminNavSidebar.admin-nav-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: min(300px, 88vw);
    height: 100vh;
    z-index: 12000;
    background: linear-gradient(165deg, #1a1f2b 0%, #0f141d 62%, #090d14 100%);
    border-right: 1px solid rgba(255,255,255,0.14);
    box-shadow: 8px 0 32px rgba(0,0,0,0.45);
    transform: translateX(-105%);
    transition: transform 0.24s ease;
    display: flex;
    flex-direction: column;
}
#adminNavSidebar.admin-nav-sidebar.is-open {
    transform: translateX(0);
}
.admin-nav-sidebar-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    flex-shrink: 0;
}
.admin-nav-sidebar-head strong {
    color: #f2f5fb;
    font-size: 1.05em;
    font-weight: 800;
}
.admin-nav-close {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.18);
    color: #f2f5fb;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1.35em;
    line-height: 1;
}
.admin-nav-close:hover { background: rgba(255,255,255,0.14); }
.admin-nav-list {
    overflow-y: auto;
    padding: 10px 10px 24px;
    flex: 1;
    -webkit-overflow-scrolling: touch;
}
.admin-nav-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    margin-bottom: 4px;
    border-radius: 8px;
    color: #d8dee9;
    text-decoration: none;
    font-size: 0.95em;
    font-weight: 600;
    border: 1px solid transparent;
}
.admin-nav-link:hover {
    background: rgba(255,255,255,0.06);
    color: #fff;
}
.admin-nav-link-active {
    background: rgba(254,1,0,0.18);
    border-color: rgba(254,1,0,0.35);
    color: #fff;
}
.admin-nav-icon { font-size: 1.15em; width: 1.4em; text-align: center; flex-shrink: 0; }
.admin-nav-backdrop {
    position: fixed;
    inset: 0;
    z-index: 11990;
    background: rgba(0,0,0,0.45);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.24s ease;
}
.admin-nav-backdrop.is-visible {
    opacity: 1;
    pointer-events: auto;
}
.admin-nav-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 42px;
    height: 42px;
    margin-right: 12px;
    flex-shrink: 0;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.22);
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    font-size: 1.25em;
    line-height: 1;
}
.admin-nav-toggle:hover { background: rgba(255,255,255,0.2); }
body.admin-nav-open { overflow: hidden; }
@media (min-width: 1100px) {
    body.admin-nav-pinned #adminNavSidebar.admin-nav-sidebar {
        transform: translateX(0);
    }
    body.admin-nav-pinned .admin-nav-backdrop { display: none; }
    body.admin-nav-pinned.admin-console-layout {
        padding-left: min(300px, 88vw);
    }
}
"""


ADMIN_NAV_JS = """
(function() {
    if (window.__adminNavInit) return;
    window.__adminNavInit = true;
    var sidebar = document.getElementById('adminNavSidebar');
    if (!sidebar) return;
    var backdrop = document.getElementById('adminNavBackdrop');
    var toggle = document.getElementById('adminNavToggle');
    var closeBtn = document.getElementById('adminNavClose');
    var pinKey = 'adminNavPinned';
    function isPinned() {
        try { return localStorage.getItem(pinKey) === '1'; } catch (e) { return false; }
    }
    function setPinned(val) {
        try { localStorage.setItem(pinKey, val ? '1' : '0'); } catch (e) {}
    }
    function openNav() {
        sidebar.classList.add('is-open');
        if (backdrop) backdrop.classList.add('is-visible');
        document.body.classList.add('admin-nav-open');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
    }
    function closeNav() {
        if (document.body.classList.contains('admin-nav-pinned')) return;
        sidebar.classList.remove('is-open');
        if (backdrop) backdrop.classList.remove('is-visible');
        document.body.classList.remove('admin-nav-open');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
    }
    function applyPinned() {
        if (window.innerWidth >= 1100 && isPinned()) {
            document.body.classList.add('admin-nav-pinned', 'admin-console-layout');
            sidebar.classList.add('is-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        } else {
            document.body.classList.remove('admin-nav-pinned', 'admin-console-layout');
            if (!sidebar.classList.contains('is-open') || !isPinned()) {
                closeNav();
            }
        }
    }
    if (toggle) {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            if (sidebar.classList.contains('is-open') && !document.body.classList.contains('admin-nav-pinned')) {
                closeNav();
            } else {
                openNav();
            }
        });
    }
    if (closeBtn) closeBtn.addEventListener('click', function() {
        setPinned(false);
        document.body.classList.remove('admin-nav-pinned', 'admin-console-layout');
        closeNav();
    });
    if (backdrop) backdrop.addEventListener('click', closeNav);
    var pinBtn = document.getElementById('adminNavPin');
    if (pinBtn) pinBtn.addEventListener('click', function() {
        var next = !document.body.classList.contains('admin-nav-pinned');
        setPinned(next);
        applyPinned();
        if (next) openNav();
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeNav();
    });
    applyPinned();
    window.addEventListener('resize', applyPinned);
})();
"""


def render_admin_nav_markup(
    items: list[dict[str, Any]],
    active_endpoint: Optional[str],
    *,
    menu_title: str = 'Admin menu',
) -> str:
    links = []
    for item in items:
        endpoints = item.get('endpoints') or ()
        active = _endpoint_active(active_endpoint, tuple(endpoints))
        cls = 'admin-nav-link admin-nav-link-active' if active else 'admin-nav-link'
        links.append(
            f'<a href="{escape(item["url"])}" class="{cls}">'
            f'<span class="admin-nav-icon" aria-hidden="true">{escape(item.get("icon") or "")}</span>'
            f'<span>{escape(item.get("label") or "")}</span></a>'
        )
    nav_body = '\n'.join(links)
    return (
        f'<aside id="adminNavSidebar" class="admin-nav-sidebar" aria-label="{escape(menu_title)}">'
        f'<div class="admin-nav-sidebar-head">'
        f'<strong>{escape(menu_title)}</strong>'
        f'<div style="display:flex;gap:8px;">'
        f'<button type="button" id="adminNavPin" class="admin-nav-close" title="Pin menu open on wide screens" aria-label="Pin menu">📌</button>'
        f'<button type="button" id="adminNavClose" class="admin-nav-close" aria-label="Close menu">&times;</button>'
        f'</div></div>'
        f'<nav class="admin-nav-list">{nav_body}</nav></aside>'
        f'<div id="adminNavBackdrop" class="admin-nav-backdrop" aria-hidden="true"></div>'
    )


def admin_nav_inject_block(
    items: list[dict[str, Any]],
    active_endpoint: Optional[str],
    *,
    menu_title: str = 'Admin menu',
) -> Markup:
    """HTML + CSS + JS to inject on staff console pages."""
    markup = render_admin_nav_markup(items, active_endpoint, menu_title=menu_title)
    menu_label = menu_title.replace('"', '&quot;')
    toggle_btn = (
        '<button type="button" id="adminNavToggle" class="admin-nav-toggle" '
        f'aria-label="Open {menu_label}" aria-expanded="false" aria-controls="adminNavSidebar">'
        '<span aria-hidden="true">☰</span></button>'
    )
    inject_toggle_js = (
        '(function(){'
        'if(document.getElementById("adminNavToggle"))return;'
        'var header=document.querySelector(".top-header")||document.querySelector(".header");'
        'if(!header)return;'
        'var wrap=header.querySelector(".logo-section")||header.querySelector(".header-content")||header;'
        f'wrap.insertAdjacentHTML("afterbegin",{toggle_btn!r});'
        'document.body.classList.add("admin-console-layout");'
        '})();'
    )
    script = (
        f'<style>{ADMIN_NAV_CSS}</style>'
        f'{markup}'
        f'<script>{inject_toggle_js}</script>'
        f'<script>{ADMIN_NAV_JS}</script>'
    )
    return Markup(script)
