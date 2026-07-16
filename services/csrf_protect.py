"""CSRFProtect setup and HTML auto-inject for forms + fetch."""
from __future__ import annotations

from flask import Flask
from flask_wtf.csrf import CSRFProtect, generate_csrf

csrf = CSRFProtect()

_CSRF_INJECT_SNIPPET = """
<meta name="csrf-token" content="__CSRF_TOKEN__">
<script id="app-csrf-bootstrap">
(function () {
  var token = "__CSRF_TOKEN_JS__";
  if (!token) return;
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.tagName || form.tagName.toLowerCase() !== "form") return;
    var method = (form.getAttribute("method") || "get").toLowerCase();
    if (method !== "post") return;
    if (form.querySelector('input[name="csrf_token"]')) return;
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = token;
    form.appendChild(input);
  }, true);
  if (typeof window.fetch !== "function") return;
  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    var method = (init.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
      var headers = new Headers(init.headers || {});
      if (!headers.has("X-CSRFToken") && !headers.has("X-CSRF-Token")) {
        headers.set("X-CSRFToken", token);
      }
      init.headers = headers;
      if (typeof FormData !== "undefined" && init.body instanceof FormData && !init.body.has("csrf_token")) {
        init.body.append("csrf_token", token);
      }
    }
    return origFetch.call(this, input, init);
  };
})();
</script>
"""


def init_csrf(app: Flask) -> CSRFProtect:
    """Attach CSRFProtect and inject token bootstrap into HTML responses."""
    app.config.setdefault('WTF_CSRF_TIME_LIMIT', None)  # session-lifetime tokens
    app.config.setdefault('WTF_CSRF_HEADERS', ['X-CSRFToken', 'X-CSRF-Token'])
    csrf.init_app(app)

    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': generate_csrf}

    @app.after_request
    def inject_csrf_bootstrap(response):
        try:
            if response.status_code != 200:
                return response
            content_type = response.content_type or ''
            if 'text/html' not in content_type:
                return response
            data = response.get_data(as_text=True)
            if 'app-csrf-bootstrap' in data or '</head>' not in data:
                return response
            token = generate_csrf()
            # Escape for HTML attribute and JS string
            token_html = (
                token.replace('&', '&amp;')
                .replace('"', '&quot;')
                .replace('<', '&lt;')
            )
            token_js = (
                token.replace('\\', '\\\\')
                .replace('"', '\\"')
                .replace('</', '<\\/')
            )
            snippet = (
                _CSRF_INJECT_SNIPPET
                .replace('__CSRF_TOKEN__', token_html)
                .replace('__CSRF_TOKEN_JS__', token_js)
            )
            response.set_data(data.replace('</head>', snippet + '</head>', 1))
        except Exception:
            pass
        return response

    return csrf
