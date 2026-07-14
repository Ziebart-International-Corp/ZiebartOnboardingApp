"""Global metallic theme CSS injected via context processor."""
from __future__ import annotations

GLOBAL_METALLIC_THEME_CSS = """
/* Global metallic theme layer (balanced premium) */
:root {
    --bg-base: #0c1017;
    --bg-panel: linear-gradient(160deg, #1a202c 0%, #101622 62%, #0a0f18 100%);
    --metal-sheen: linear-gradient(110deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.03) 40%, rgba(255,255,255,0.1) 74%, rgba(255,255,255,0.02) 100%);
    --accent-red: #fe0100;
    --text-primary: #f2f5fb;
    --text-muted: #b7c1d3;
    --border-soft: rgba(255,255,255,0.17);
    --shadow-elev: 0 18px 42px rgba(0,0,0,0.36);
    --btn-radius: 0.5rem;
    --btn-padding-y: 10px;
    --btn-padding-x: 18px;
    --btn-padding-y-sm: 8px;
    --btn-padding-x-sm: 14px;
    --btn-font-size: 0.95em;
    --btn-font-size-sm: 0.82em;
    --btn-font-weight: 600;
    --btn-border: 1px solid rgba(255, 255, 255, 0.22);
    --btn-bg: rgba(255, 255, 255, 0.1);
    --btn-color: #ffffff;
    --btn-bg-hover: rgba(255, 255, 255, 0.18);
}
html {
    background-color: #090d14;
}
html, body {
    min-height: 100%;
    min-height: 100vh;
}
body {
    background:
        radial-gradient(circle at 20% 0%, rgba(255,255,255,0.07), transparent 46%),
        linear-gradient(180deg, #111824 0%, #090d14 100%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
}
.top-header {
    background: linear-gradient(160deg, #121821 0%, #090d14 100%) !important;
    border-bottom: 1px solid var(--border-soft);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.section, .card, .panel, .dashboard-card, .dashboard-tasks-card, .welcome-banner, .summary-card, .sidebar-section, .video-card, .task-card, .quick-link, .login-box, .welcome-card,
.admin-panel, .store-banner, .collapsible-upload-panel, .wizard-container, .modal-content,
.stat-card, .task-section, .task-item, .documents-list, .document-item, .training-card, .profile-header, .info-section, .empty-state,
.user-card {
    background: var(--bg-panel) !important;
    border: 1px solid var(--border-soft) !important;
    box-shadow: var(--shadow-elev), inset 0 1px 0 rgba(255,255,255,0.12) !important;
    color: var(--text-primary) !important;
}
.task-item.urgent-priority {
    background: rgba(254, 1, 0, 0.12) !important;
}
.training-card .progress-info {
    background: rgba(255, 255, 255, 0.08) !important;
    color: var(--text-muted) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
}
h1, h2, h3, h4, .section-title, .section-title-dash, .page-title, .sidebar-title, .profile-name, .summary-content .number,
.task-title, .document-info h3, .training-card h3 {
    color: var(--text-primary) !important;
}
.section-title-dash {
    border-bottom-color: rgba(255,255,255,0.22) !important;
}
.page-subtitle {
    color: var(--text-muted) !important;
}
p, .subtitle, .help-text, .info-label, .summary-content h3, .quick-link-description, .task-content p, .notification-message, .form-status-name,
.profile-position, .task-description, .task-meta, .document-info p, .document-meta, .training-card p, .empty-state, .stat-label {
    color: var(--text-muted) !important;
}
.badge-type {
    background: rgba(13, 110, 253, 0.22) !important;
    color: #dce9ff !important;
}
.stat-number {
    color: var(--accent-red) !important;
}
input, select, textarea {
    background: linear-gradient(150deg, rgba(255,255,255,0.09), rgba(255,255,255,0.04)) !important;
    border: 1px solid rgba(255,255,255,0.24) !important;
    color: var(--text-primary) !important;
}
select option,
select optgroup {
    background: #121a26 !important;
    color: #f2f5fb !important;
}
select option:checked,
select option:hover {
    background: #1e2a3d !important;
    color: #ffffff !important;
}
input::placeholder, textarea::placeholder {
    color: #9aa5b8 !important;
}
input:focus, select:focus, textarea:focus {
    border-color: rgba(254,1,0,0.7) !important;
    box-shadow: 0 0 0 3px rgba(254,1,0,0.18) !important;
}
button,
.btn,
a.btn,
.btn-login,
.task-btn,
.video-btn,
.dashboard-cta-link,
input[type="submit"],
input[type="button"] {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    padding: var(--btn-padding-y) var(--btn-padding-x) !important;
    border-radius: var(--btn-radius) !important;
    font-size: var(--btn-font-size) !important;
    font-weight: var(--btn-font-weight) !important;
    line-height: 1.25 !important;
    font-family: 'URW Form', Arial, sans-serif !important;
    text-decoration: none !important;
    cursor: pointer !important;
    white-space: nowrap !important;
    min-height: auto !important;
    background: var(--btn-bg) !important;
    color: var(--btn-color) !important;
    border: var(--btn-border) !important;
    box-shadow: none !important;
    transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
}
button:hover,
.btn:hover,
a.btn:hover,
.btn-login:hover,
.task-btn:hover,
.video-btn:hover,
.dashboard-cta-link:hover,
input[type="submit"]:hover,
input[type="button"]:hover {
    background: var(--btn-bg-hover) !important;
    color: #ffffff !important;
    box-shadow: none !important;
    filter: none !important;
    transform: none !important;
}
.dropdown-menu, .notification-dropdown {
    background: #151b28 !important;
    border: 1px solid var(--border-soft) !important;
    box-shadow: var(--shadow-elev) !important;
}
.dropdown-item, .notification-title, .quick-link-text, table th, table td, label, .info-value, .progress-name a {
    color: var(--text-primary) !important;
}
.dropdown-item:hover,
.dropdown-item:focus,
.dropdown-item:focus-visible {
    background: rgba(255, 255, 255, 0.1) !important;
    color: #ffffff !important;
}
.feedback-header-btn {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    padding: 7px 12px !important;
    border-radius: 999px !important;
    font-size: 0.82em !important;
    font-weight: 600 !important;
    line-height: 1.2 !important;
    text-decoration: none !important;
    color: #f2f5fb !important;
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    white-space: nowrap !important;
    transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
    flex-shrink: 0;
}
.feedback-header-btn:hover {
    background: rgba(254, 1, 0, 0.18) !important;
    border-color: rgba(254, 1, 0, 0.45) !important;
    color: #ffffff !important;
}
.feedback-header-btn .feedback-header-svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
}
.feedback-header-btn.is-active {
    background: rgba(254, 1, 0, 0.22) !important;
    border-color: rgba(254, 1, 0, 0.55) !important;
    color: #ffffff !important;
}
@media (max-width: 768px) {
    .feedback-header-btn .feedback-header-label {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
    }
    .feedback-header-btn {
        padding: 8px !important;
        min-width: 36px;
        min-height: 36px;
    }
}
.feedback-page-panel {
    max-width: 720px;
    margin: 0 auto;
    padding: 28px 24px 32px;
    border-radius: 1rem;
}
.feedback-page-panel h1 {
    margin-bottom: 8px;
}
.feedback-page-panel .feedback-intro {
    margin-bottom: 24px;
    line-height: 1.55;
}
.feedback-form .form-row {
    margin-bottom: 18px;
}
.feedback-form label {
    display: block;
    font-weight: 600;
    margin-bottom: 6px;
    font-size: 0.92em;
}
.feedback-form .field-hint {
    display: block;
    margin-top: 6px;
    font-size: 0.85em;
    line-height: 1.45;
}
.feedback-form select,
.feedback-form input[type="text"],
.feedback-form textarea {
    width: 100%;
    box-sizing: border-box;
    padding: 11px 12px;
    border-radius: 8px;
    font-size: 1rem;
}
.feedback-form textarea {
    min-height: 140px;
    resize: vertical;
}
.feedback-photo-preview {
    margin-top: 10px;
    max-width: 100%;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.18);
    display: none;
}
.feedback-form-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin-top: 8px;
}
.feedback-submit-btn {
    background: linear-gradient(180deg, #ff2624 0%, #d50000 65%, #9e0000 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.28) !important;
    color: #ffffff !important;
    padding: 12px 22px !important;
    font-weight: 600 !important;
}
.feedback-flash {
    padding: 12px 14px;
    border-radius: 8px;
    margin-bottom: 18px;
    font-size: 0.95em;
    line-height: 1.45;
}
.feedback-flash.success {
    background: rgba(52, 160, 90, 0.18);
    border: 1px solid rgba(62, 207, 106, 0.45);
    color: #d7ffe3;
}
.feedback-flash.error {
    background: rgba(254, 1, 0, 0.14);
    border: 1px solid rgba(254, 1, 0, 0.45);
    color: #ffd6d6;
}
table, .table, .table-container {
    background: var(--bg-panel) !important;
    border: 1px solid var(--border-soft) !important;
}
table tr:hover {
    background: rgba(255,255,255,0.04) !important;
}
/* User top nav: pill bar + dark-red active chip + red glow + bottom indicator (all pages via global_theme_css) */
.nav-links {
    gap: 8px !important;
    align-items: center !important;
    padding: 6px !important;
    border-radius: 999px !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    background: rgba(0, 0, 0, 0.38) !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12) !important;
    backdrop-filter: blur(8px);
}
.nav-links a {
    color: #ffffff !important;
    text-decoration: none !important;
    font-size: 0.95em !important;
    font-weight: 600 !important;
    font-family: 'URW Form', Arial, sans-serif !important;
    padding: 8px 16px !important;
    border-radius: 999px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    box-shadow: none !important;
    transition: background 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
}
.nav-links a:hover {
    color: #ffffff !important;
    background: rgba(255, 255, 255, 0.08) !important;
    border-color: transparent !important;
    box-shadow: none !important;
}
.nav-links a.nav-tab-active,
.nav-links a.active {
    position: relative !important;
    color: #ffffff !important;
    background: linear-gradient(
        180deg,
        rgba(95, 14, 18, 0.92) 0%,
        rgba(52, 8, 12, 0.95) 48%,
        rgba(32, 5, 8, 0.98) 100%
    ) !important;
    border-color: rgba(254, 55, 52, 0.55) !important;
    box-shadow:
        0 0 0 1px rgba(254, 40, 38, 0.75),
        0 0 20px rgba(254, 1, 0, 0.55),
        0 0 40px rgba(254, 1, 0, 0.22),
        inset 0 1px 0 rgba(255, 255, 255, 0.16) !important;
}
.quick-link-icon img {
    background: transparent !important;
}
.construction-banner {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    flex-wrap: wrap;
}
.construction-banner-icon {
    flex-shrink: 0;
    line-height: 1;
}
.logo-text-stack {
    display: none;
}
.finale-head-emoji {
    display: none;
}
.mobile-bottom-nav {
    display: none;
}
body.user-app-shell .mobile-menu-toggle,
body.user-app-shell .mobile-nav,
body.user-app-shell #mobileNav {
    display: none !important;
}
@media (max-width: 768px) {
    body.user-app-shell {
        padding-bottom: calc(58px + env(safe-area-inset-bottom, 0px));
    }
    body.user-app-shell .mobile-bottom-nav {
        display: flex;
    }
    body.user-app-shell .mobile-menu-toggle,
    body.user-app-shell #mobileNav.mobile-nav,
    body.user-app-shell .mobile-nav {
        display: none !important;
    }
    body.user-app-shell .logo-text.logo-text-desktop {
        display: none !important;
    }
    body.user-app-shell .logo-text-stack {
        display: flex !important;
        flex-direction: column;
        justify-content: center;
        line-height: 1.06;
        gap: 1px;
    }
    body.user-app-shell .logo-section .logo-title {
        font-size: 1.05rem;
        font-weight: 800;
        letter-spacing: 0.03em;
        color: #fff;
    }
    body.user-app-shell .logo-section .logo-subtitle {
        font-size: 0.64rem;
        font-weight: 500;
        letter-spacing: 0.07em;
        color: rgba(242, 245, 251, 0.86);
        text-transform: none;
    }
    body.user-app-shell .logo-section img {
        height: 42px !important;
        width: auto !important;
        margin-bottom: 0 !important;
        align-self: center !important;
    }
    body.user-app-shell .top-header {
        align-items: center !important;
        padding: max(10px, env(safe-area-inset-top, 0px)) 14px 10px !important;
        flex-wrap: nowrap !important;
        gap: 8px !important;
    }
    body.user-app-shell .top-header .logo-section {
        flex: 1 1 auto;
        min-width: 0;
    }
    body.user-app-shell .top-header .nav-links {
        display: none !important;
    }
    body.user-app-shell .user-section {
        gap: 10px !important;
        flex-shrink: 0;
        margin-left: auto;
    }
    body.user-app-shell .notification-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2px;
    }
    body.user-app-shell .notification-icon .notification-bell-svg {
        display: block;
        width: 22px;
        height: 22px;
        color: #d4af5b;
        filter: drop-shadow(0 0 5px rgba(212, 175, 91, 0.55))
            drop-shadow(0 0 10px rgba(212, 175, 91, 0.25));
    }
    body.user-app-shell .user-dropdown > span.user-dropdown-label {
        display: inline-flex !important;
        max-width: 34vw;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.78rem;
        font-weight: 600;
        color: #f2f5fb;
    }
    body.user-app-shell .user-dropdown > span.user-dropdown-caret {
        display: inline-flex !important;
        font-size: 0.55rem;
        opacity: 0.72;
        margin-left: 1px;
        color: #dbe2f0;
    }
    body.user-app-shell #notificationBadge.notification-badge-dot {
        width: 7px !important;
        height: 7px !important;
        min-width: 7px !important;
        padding: 0 !important;
        font-size: 0 !important;
        line-height: 0 !important;
        overflow: hidden !important;
        color: transparent !important;
    }
    body.user-app-shell .construction-banner {
        margin: 10px 14px 0 !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255, 210, 90, 0.5) !important;
        background: linear-gradient(135deg, rgba(38, 30, 10, 0.97), rgba(22, 18, 8, 0.98)) !important;
        color: #ffe08a !important;
        width: auto !important;
    }
    body.user-app-shell .main-content > .sidebar-right {
        order: 3 !important;
    }
    body.user-app-shell .main-content > .dashboard-tasks-col {
        order: 1 !important;
    }
    body.user-app-shell .finale-head-emoji {
        display: inline !important;
    }
    body.user-app-shell .finale-kicker {
        display: none !important;
    }
    body.user-app-shell .finale-logo {
        display: none !important;
    }
    body.user-app-shell .finale-headline {
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-size: 1.02rem !important;
    }
    body.user-app-shell .finale-divider {
        background: #fe0100 !important;
        max-width: 120px;
        height: 2px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    body.user-app-shell .dashboard-page-wrap .finale-card,
    body.user-app-shell .finale-card {
        border-radius: 16px !important;
        margin-left: 12px !important;
        margin-right: 12px !important;
        box-shadow:
            0 18px 42px rgba(0, 0, 0, 0.45),
            0 0 0 1px rgba(255, 255, 255, 0.14),
            0 0 56px rgba(254, 1, 0, 0.12),
            inset 0 1px 0 rgba(255, 255, 255, 0.16) !important;
    }
    body.user-app-shell .finale-doc-btn {
        box-shadow:
            0 10px 26px rgba(254, 1, 0, 0.4),
            0 0 24px rgba(254, 1, 0, 0.22),
            inset 0 1px 0 rgba(255, 255, 255, 0.38) !important;
    }
    body.user-app-shell .sidebar-right .external-links-title::after {
        height: 2px !important;
        margin-top: 10px !important;
        margin-bottom: 14px !important;
        border-radius: 1px !important;
        background: linear-gradient(
            90deg,
            #e31b23 0,
            #e31b23 92px,
            rgba(82, 88, 100, 0.85) 92px,
            rgba(140, 147, 160, 0.28) 100%
        ) !important;
    }
    body.user-app-shell .sidebar-right .section.dashboard-card,
    body.user-app-shell .sidebar-right .section {
        border-radius: 16px !important;
        margin-left: 2px !important;
        margin-right: 2px !important;
    }
    body.user-app-shell .mobile-bottom-nav {
        position: fixed;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 10050;
        justify-content: space-around;
        align-items: flex-end;
        padding: 5px 2px calc(11px + env(safe-area-inset-bottom, 0px));
        background: linear-gradient(180deg, #141922 0%, #090c12 100%);
        border-top: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 -12px 32px rgba(0, 0, 0, 0.55);
        box-sizing: border-box;
    }
    body.user-app-shell .mobile-tab {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-end;
        gap: 4px;
        min-width: 0;
        max-width: 88px;
        padding: 6px 2px 7px;
        text-decoration: none !important;
        color: #7d8696 !important;
        font-size: 0.58rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        position: relative;
        box-sizing: border-box;
    }
    body.user-app-shell .mobile-tab-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        color: inherit;
        line-height: 0;
        min-height: 24px;
    }
    body.user-app-shell .mobile-tab-svg {
        display: block;
        overflow: visible;
    }
    body.user-app-shell .mobile-tab-label {
        line-height: 1.1;
        text-align: center;
        position: relative;
        width: 100%;
    }
    body.user-app-shell .mobile-tab-label::after {
        content: "";
        display: block;
        height: 0;
        margin: 0 auto;
    }
    body.user-app-shell .mobile-tab.mobile-tab-active {
        color: #fe0100 !important;
    }
    body.user-app-shell .mobile-tab.mobile-tab-active .mobile-tab-icon {
        color: #fe0100 !important;
    }
    body.user-app-shell .mobile-tab.mobile-tab-active .mobile-tab-label::after {
        height: 3px;
        width: 26px;
        margin-top: 4px;
        border-radius: 2px;
        background: #fe0100;
        box-shadow: 0 0 10px rgba(254, 1, 0, 0.75);
    }
    html:has(body.user-app-shell),
    body.user-app-shell {
        overflow-x: hidden;
        max-width: 100vw;
    }
    body.user-app-shell .main-content {
        padding: 12px 14px 16px !important;
        max-width: 100%;
        box-sizing: border-box;
    }
    body.user-app-shell .page-title,
    body.user-app-shell .section,
    body.user-app-shell .task-card,
    body.user-app-shell .document-item,
    body.user-app-shell .training-card,
    body.user-app-shell .documents-list,
    body.user-app-shell .training-list {
        min-width: 0;
        max-width: 100%;
        box-sizing: border-box;
    }
    body.user-app-shell .page-title,
    body.user-app-shell .document-info h3,
    body.user-app-shell .task-title,
    body.user-app-shell .training-card h3 {
        word-break: break-word;
        overflow-wrap: break-word;
    }
    body.user-app-shell .btn,
    body.user-app-shell .task-btn,
    body.user-app-shell a.btn {
        min-height: 44px;
        box-sizing: border-box;
    }
    body.user-app-shell input[type="text"],
    body.user-app-shell input[type="email"],
    body.user-app-shell input[type="password"],
    body.user-app-shell input[type="date"],
    body.user-app-shell input[type="number"],
    body.user-app-shell select,
    body.user-app-shell textarea {
        font-size: 16px;
        max-width: 100%;
        box-sizing: border-box;
    }
    body.user-app-shell .notification-dropdown {
        max-width: calc(100vw - 24px) !important;
        right: 0 !important;
        left: auto !important;
    }
    /* Finale + external links: on mobile allow natural page scroll (avoid clipped content) */
    html:has(body.dashboard-home-compact) {
        height: auto;
    }
    html:has(body.dashboard-home-compact),
    html:has(body.dashboard-home-compact) body.dashboard-home-compact.user-app-shell {
        max-height: none;
    }
    body.dashboard-home-compact.user-app-shell {
        display: block;
        overflow-x: hidden;
        overflow-y: auto;
        height: auto;
        max-height: none;
        min-height: 100dvh;
        padding-bottom: calc(58px + env(safe-area-inset-bottom, 0px)) !important;
    }
    body.dashboard-home-compact .top-header {
        flex-shrink: 0;
        padding: max(4px, env(safe-area-inset-top, 0px)) 10px 5px !important;
    }
    body.dashboard-home-compact .logo-section img {
        height: 34px !important;
    }
    body.dashboard-home-compact .logo-section .logo-title {
        font-size: 0.9rem !important;
    }
    body.dashboard-home-compact .logo-section .logo-subtitle {
        font-size: 0.56rem !important;
    }
    body.dashboard-home-compact .user-dropdown > span.user-dropdown-label {
        font-size: 0.7rem !important;
        max-width: 26vw !important;
    }
    body.dashboard-home-compact .notification-icon .notification-bell-svg {
        width: 20px !important;
        height: 20px !important;
    }
    body.dashboard-home-compact .construction-banner {
        flex-shrink: 0;
        margin: 3px 8px 0 !important;
        padding: 3px 8px !important;
        font-size: 0.58rem !important;
        line-height: 1.15 !important;
        border-radius: 8px !important;
        gap: 6px !important;
    }
    body.dashboard-home-compact .construction-banner-icon {
        font-size: 0.9em !important;
    }
    body.dashboard-home-compact .dashboard-view {
        display: block;
        overflow: visible;
    }
    body.dashboard-home-compact .dashboard-container,
    body.dashboard-home-compact .dashboard-page-wrap {
        display: block;
        overflow: visible;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        padding-left: 8px !important;
        padding-right: 8px !important;
    }
    body.dashboard-home-compact .main-content {
        display: flex;
        flex-direction: column;
        gap: 12px !important;
        margin-top: 0 !important;
        overflow: visible;
        padding-bottom: 8px;
    }
    body.dashboard-home-compact .dashboard-tasks-col {
        flex: 0 1 auto;
        min-height: 0;
    }
    body.dashboard-home-compact .finale-card {
        min-height: 0 !important;
        justify-content: flex-start !important;
        padding: 16px 14px !important;
        margin-left: 8px !important;
        margin-right: 8px !important;
        border-radius: 14px !important;
    }
    body.dashboard-home-compact .finale-inner {
        max-width: none;
        width: 100%;
    }
    body.dashboard-home-compact .finale-inner > p {
        margin-bottom: 0 !important;
    }
    body.dashboard-home-compact .finale-headline {
        margin: 0 0 6px !important;
        font-size: clamp(1rem, 4.2vw, 1.2rem) !important;
        letter-spacing: 0.05em !important;
        line-height: 1.2 !important;
    }
    body.dashboard-home-compact .finale-divider {
        margin-bottom: 10px !important;
        max-width: 120px !important;
        height: 3px !important;
    }
    body.dashboard-home-compact .finale-message {
        font-size: clamp(0.95rem, 3.8vw, 1.08rem) !important;
        line-height: 1.5 !important;
        margin-bottom: 12px !important;
    }
    body.dashboard-home-compact .finale-doc-btn {
        padding: 12px 18px !important;
        font-size: clamp(0.88rem, 3.2vw, 1rem) !important;
        border-radius: 12px !important;
        gap: 8px !important;
    }
    body.dashboard-home-compact .sidebar-right {
        flex: 0 1 auto;
        min-height: 0;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    body.dashboard-home-compact .sidebar-right .section {
        flex: 0 1 auto;
        flex-grow: 0 !important;
        min-height: 0 !important;
        padding: 10px 12px 12px !important;
        display: flex !important;
        flex-direction: column !important;
    }
    body.dashboard-home-compact .sidebar-right .external-links-title {
        margin-bottom: 0 !important;
        font-size: clamp(0.82rem, 3vw, 0.95rem) !important;
        letter-spacing: 0.12em !important;
    }
    body.dashboard-home-compact .sidebar-right .external-links-title::after {
        margin-top: 6px !important;
        margin-bottom: 10px !important;
        height: 3px !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-links {
        flex: 0 1 auto;
        flex-grow: 0 !important;
        min-height: 0;
        gap: 8px !important;
        overflow: visible;
    }
    body.dashboard-home-compact .sidebar-right .quick-link {
        grid-template-columns: 44px minmax(0, 1fr) 32px !important;
        column-gap: 12px !important;
        padding: 10px 12px !important;
        border-radius: 12px !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-link-icon {
        width: 44px !important;
        height: 44px !important;
        min-width: 44px !important;
        padding: 5px !important;
        border-radius: 10px !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-link-text {
        font-size: clamp(0.92rem, 3.5vw, 1.05rem) !important;
        line-height: 1.35 !important;
        font-weight: 600 !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-link-description {
        display: none !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-link-external {
        width: 32px !important;
        height: 32px !important;
    }
    body.dashboard-home-compact .sidebar-right .quick-link-external svg {
        width: 18px !important;
        height: 18px !important;
    }
    body.dashboard-home-compact .mobile-bottom-nav {
        padding: 3px 2px calc(8px + env(safe-area-inset-bottom, 0px)) !important;
    }
    body.dashboard-home-compact .mobile-tab {
        padding: 3px 2px 4px !important;
        gap: 2px !important;
        font-size: 0.54rem !important;
    }
    body.dashboard-home-compact .mobile-tab-icon {
        min-height: 20px !important;
    }
    body.dashboard-home-compact .mobile-tab-svg {
        width: 20px !important;
        height: 20px !important;
    }
}
@media (max-width: 480px) {
    body.user-app-shell .main-content {
        padding: 10px 12px 14px !important;
    }
    body.user-app-shell .section-title,
    body.user-app-shell .page-title {
        font-size: 1.35rem !important;
    }
    body.user-app-shell .section {
        padding: 1rem !important;
    }
    body.user-app-shell .top-header {
        padding-left: 10px !important;
        padding-right: 10px !important;
    }
}

/* Admin & manager consoles: shared metallic panels, headers, tables, lists */
.header {
    background: linear-gradient(160deg, #121821 0%, #090d14 100%) !important;
    border-bottom: 1px solid var(--border-soft) !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
    color: var(--text-primary) !important;
}
.header h1,
.header .header-content h1 {
    color: var(--text-primary) !important;
}
.header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}
.admin-panel,
.store-banner,
.collapsible-upload-panel,
.wizard-container,
.modal-content {
    position: relative !important;
    overflow: hidden !important;
}
.admin-panel::before,
.store-banner::before,
.collapsible-upload-panel::before,
.wizard-container::before,
.modal-content::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--metal-sheen);
    pointer-events: none;
    z-index: 0;
    opacity: 0.35;
}
.admin-panel > *,
.store-banner > *,
.collapsible-upload-panel > *,
.wizard-container > *,
.modal-content > * {
    position: relative;
    z-index: 1;
}
.back-btn,
a.back-btn {
    padding: var(--btn-padding-y) var(--btn-padding-x) !important;
    border-radius: var(--btn-radius) !important;
    font-size: var(--btn-font-size) !important;
    font-weight: var(--btn-font-weight) !important;
    background: var(--btn-bg) !important;
    color: var(--btn-color) !important;
    border: var(--btn-border) !important;
    box-shadow: none !important;
    text-decoration: none !important;
}
.back-btn:hover,
a.back-btn:hover {
    background: var(--btn-bg-hover) !important;
    color: #ffffff !important;
    box-shadow: none !important;
    filter: none !important;
    transform: none !important;
}
.quick-link-item,
.form-status-item,
.progress-item {
    border-bottom-color: rgba(255, 255, 255, 0.1) !important;
}
.quick-link-item:hover,
.form-status-item:hover {
    background: rgba(255, 255, 255, 0.05) !important;
}
thead th,
table thead th {
    background: rgba(255, 255, 255, 0.08) !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12) !important;
}
table tbody td {
    border-bottom-color: rgba(255, 255, 255, 0.08) !important;
}
table a {
    color: #e8ecff !important;
    text-decoration: none !important;
}
table a:hover {
    color: #ffb4b3 !important;
    text-decoration: underline !important;
}
.btn-primary,
a.btn-primary {
    background: rgba(58, 142, 239, 0.2) !important;
    border: 1px solid rgba(120, 180, 255, 0.42) !important;
    box-shadow: none !important;
    color: #ffffff !important;
}
.btn-primary:hover,
a.btn-primary:hover {
    background: rgba(58, 142, 239, 0.32) !important;
    border-color: rgba(140, 195, 255, 0.55) !important;
    color: #ffffff !important;
    filter: none !important;
    transform: none !important;
}
.btn-success,
a.btn-success {
    background: rgba(40, 167, 69, 0.2) !important;
    border: 1px solid rgba(90, 200, 120, 0.42) !important;
    box-shadow: none !important;
    color: #ffffff !important;
}
.btn-success:hover,
a.btn-success:hover {
    background: rgba(40, 167, 69, 0.32) !important;
    border-color: rgba(110, 220, 140, 0.55) !important;
    color: #ffffff !important;
    filter: none !important;
    transform: none !important;
}
.btn-secondary,
a.btn-secondary {
    background: var(--btn-bg) !important;
    border: var(--btn-border) !important;
    box-shadow: none !important;
    color: var(--btn-color) !important;
}
.btn-secondary:hover,
a.btn-secondary:hover {
    background: var(--btn-bg-hover) !important;
    color: #ffffff !important;
    filter: none !important;
    transform: none !important;
}
.btn-danger,
a.btn-danger,
button.btn-danger {
    background: rgba(220, 53, 69, 0.2) !important;
    border: 1px solid rgba(255, 120, 130, 0.42) !important;
    box-shadow: none !important;
    color: #ffffff !important;
}
.btn-danger:hover,
a.btn-danger:hover,
button.btn-danger:hover {
    background: rgba(220, 53, 69, 0.32) !important;
    border-color: rgba(255, 140, 150, 0.55) !important;
    color: #ffffff !important;
    filter: none !important;
    transform: none !important;
}
.task-btn,
.video-btn,
.dashboard-cta-link,
.btn-login {
    background: rgba(254, 1, 0, 0.18) !important;
    border: 1px solid rgba(254, 80, 78, 0.48) !important;
    box-shadow: none !important;
    color: #ffffff !important;
}
.task-btn:hover,
.video-btn:hover,
.dashboard-cta-link:hover,
.btn-login:hover {
    background: rgba(254, 1, 0, 0.28) !important;
    border-color: rgba(255, 110, 108, 0.58) !important;
    color: #ffffff !important;
    filter: none !important;
    transform: none !important;
}
.badge,
span.badge {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: var(--btn-padding-y-sm) var(--btn-padding-x-sm) !important;
    border-radius: var(--btn-radius) !important;
    font-size: var(--btn-font-size-sm) !important;
    font-weight: var(--btn-font-weight) !important;
    line-height: 1.25 !important;
    border: var(--btn-border) !important;
    box-shadow: none !important;
    background: var(--btn-bg) !important;
    color: var(--text-primary) !important;
}
.badge-active,
.badge.badge-active {
    background: rgba(40, 167, 69, 0.28) !important;
    border-color: rgba(90, 200, 120, 0.5) !important;
    color: #ffffff !important;
}
.badge-inactive,
.badge.badge-inactive {
    background: var(--btn-bg) !important;
    border: var(--btn-border) !important;
    color: var(--text-muted) !important;
}
.card .hint {
    color: var(--text-muted) !important;
}
.admin-panel small,
.container small {
    color: var(--text-muted) !important;
}
.notification-item.unread {
    background: rgba(254, 1, 0, 0.09) !important;
}
.notification-item.unread:hover {
    background: rgba(254, 1, 0, 0.14) !important;
}
.search-all-toggle,
.search-all-toggle span {
    color: var(--text-muted) !important;
}
.legend {
    border-top-color: rgba(255, 255, 255, 0.12) !important;
}
.badge-visible {
    background: rgba(72, 190, 120, 0.28) !important;
    border-color: rgba(90, 200, 120, 0.5) !important;
    color: #e8fff0 !important;
}
.badge-hidden {
    background: var(--btn-bg) !important;
    border: var(--btn-border) !important;
    color: var(--text-primary) !important;
}
.badge-revoked {
    background: rgba(200, 60, 60, 0.28) !important;
    border-color: rgba(255, 120, 120, 0.45) !important;
    color: #ffe4e4 !important;
}
.badge-admin {
    background: rgba(254, 1, 0, 0.22) !important;
    border: 1px solid rgba(254, 80, 78, 0.48) !important;
    color: #ffffff !important;
}
.badge-user {
    background: rgba(255, 255, 255, 0.14) !important;
    color: var(--text-primary) !important;
}
.store-dropdown-btn {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    padding: var(--btn-padding-y-sm) var(--btn-padding-x-sm) !important;
    border-radius: var(--btn-radius) !important;
    font-size: var(--btn-font-size-sm) !important;
    font-weight: var(--btn-font-weight) !important;
    line-height: 1.25 !important;
    white-space: nowrap !important;
    cursor: pointer !important;
    background: var(--btn-bg) !important;
    color: var(--btn-color) !important;
    border: var(--btn-border) !important;
    box-shadow: none !important;
    min-height: auto !important;
}
.store-dropdown-btn:hover {
    background: var(--btn-bg-hover) !important;
    color: #ffffff !important;
    box-shadow: none !important;
    filter: none !important;
    transform: none !important;
}
.btn-small,
.btn.btn-small,
a.btn.btn-small,
button.btn-small {
    padding: var(--btn-padding-y-sm) var(--btn-padding-x-sm) !important;
    font-size: var(--btn-font-size-sm) !important;
    border-radius: var(--btn-radius) !important;
    margin: 2px 4px !important;
    box-shadow: none !important;
}

/* Strip remaining light-gray / white “cards” on admin & manager pages */
.wizard-steps {
    background: rgba(0, 0, 0, 0.4) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.14) !important;
}
.wizard-step:not(.active):not(.completed) {
    background: transparent !important;
    color: var(--text-muted) !important;
}
.wizard-step.active {
    background: linear-gradient(180deg, #ff2f2e 0%, #b80000 100%) !important;
    color: #ffffff !important;
}
.wizard-step.completed {
    background: linear-gradient(180deg, #2fa85c 0%, #1a6b38 100%) !important;
    color: #ffffff !important;
}
.step-header h2,
.form-group label,
.wizard-step-title {
    color: var(--text-primary) !important;
}
.step-header p,
.form-group .help,
.sub,
.count-muted {
    color: var(--text-muted) !important;
}
.count {
    color: var(--text-primary) !important;
}
.new-hire-item {
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
.new-hire-item:hover {
    background: rgba(255, 255, 255, 0.1) !important;
}
.user-card {
    position: relative !important;
    overflow: hidden !important;
}
.user-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--metal-sheen);
    pointer-events: none;
    z-index: 0;
}
.user-card > * {
    position: relative;
    z-index: 1;
}
.user-card:hover {
    background: rgba(255, 255, 255, 0.12) !important;
    border-color: rgba(254, 1, 0, 0.45) !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
}
.user-card h3,
.user-card p {
    color: var(--text-primary) !important;
}
.user-card p {
    color: var(--text-muted) !important;
}
.new-hire-name a {
    color: var(--text-primary) !important;
}
.new-hire-meta {
    color: var(--text-muted) !important;
}
.doc-item {
    background: transparent !important;
    border-bottom-color: rgba(255, 255, 255, 0.1) !important;
}
.progress-item {
    background: transparent !important;
}
tbody td {
    background: transparent !important;
    color: var(--text-primary) !important;
}
tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03) !important;
}
.flash.success {
    background: rgba(52, 160, 90, 0.22) !important;
    color: #d4f5e2 !important;
    border: 1px solid rgba(80, 200, 130, 0.45) !important;
}
.flash.error {
    background: rgba(200, 70, 70, 0.28) !important;
    color: #ffecec !important;
    border: 1px solid rgba(255, 120, 120, 0.45) !important;
}
.flash.warning {
    background: rgba(220, 170, 40, 0.2) !important;
    color: #fff6d6 !important;
    border: 1px solid rgba(255, 210, 100, 0.42) !important;
}
.info-msg {
    background: rgba(60, 140, 200, 0.2) !important;
    color: #d4ecff !important;
    border: 1px solid rgba(100, 180, 255, 0.38) !important;
}
.summary-icon.blue,
.summary-icon.green {
    background: rgba(255, 255, 255, 0.1) !important;
    border: 1px solid rgba(255, 255, 255, 0.14) !important;
}
.empty {
    color: var(--text-muted) !important;
    background: transparent !important;
}

/* Checklist admin + user views: rows used #f8f9fa while global h3/p forced light text → unreadable */
.checklist-item {
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.14) !important;
    border-left: 4px solid #4a9eff !important;
    color: var(--text-primary) !important;
}
.checklist-item.completed {
    background: rgba(52, 160, 90, 0.22) !important;
    border-left-color: #3ecf6a !important;
    opacity: 1 !important;
}
.checklist-item .item-info h3,
.item-content h3 {
    color: var(--text-primary) !important;
}
.checklist-item .item-info p {
    color: var(--text-muted) !important;
}
.item-content.completed h3 {
    color: var(--text-muted) !important;
}
.checklist-item .item-meta,
.checklist-view .item-meta {
    color: var(--text-muted) !important;
}

.store-dropdown-panel {
    background: #151b28 !important;
    border: 1px solid var(--border-soft) !important;
    box-shadow: var(--shadow-elev) !important;
    color: var(--text-primary) !important;
}

/* Assign document — user list is a nested div (not .admin-panel); keep it dark everywhere */
#assign-doc-users-list-root.assign-doc-users-list {
    background: #070b10 !important;
    background-color: #070b10 !important;
    background-image: none !important;
    color: #f2f5fb !important;
    border-color: rgba(255, 255, 255, 0.22) !important;
}
#assign-doc-users-list-root .assign-doc-user-row {
    background: #121a26 !important;
    background-color: #121a26 !important;
    background-image: none !important;
    color: #ffffff !important;
    border-color: rgba(255, 255, 255, 0.18) !important;
}
#assign-doc-users-list-root .assign-doc-user-row label,
#assign-doc-users-list-root .assign-doc-user-name {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
}
/* Outer shell around label + scroll list (covers any UA “light” scroll viewport) */
.assign-doc-users-shell {
    background: #03060a !important;
    background-color: #03060a !important;
    background-image: none !important;
    color: #f2f5fb !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 12px !important;
    padding: 14px !important;
    margin-top: 8px !important;
}
.assign-doc-users-shell > label {
    color: #f2f5fb !important;
}
"""

__all__ = ['GLOBAL_METALLIC_THEME_CSS']
