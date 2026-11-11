import secrets
from hmac import compare_digest
from urllib.parse import urlsplit

from flask import current_app, flash, jsonify, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException


class CSRFProtect:
    def init_app(self, app):
        app.context_processor(self._context_processor)
        app.before_request(self._protect)

    @staticmethod
    def _context_processor():
        return {"csrf_token": CSRFProtect.generate_token}

    @staticmethod
    def generate_token():
        token = session.get("_csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    @staticmethod
    def _protect():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return

        expected = session.get("_csrf_token")
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not expected or not submitted or not compare_digest(expected, submitted):
            message = "Your session expired. Please sign in again."
            session.clear()
            flash(message, "error")
            next_url = CSRFProtect._safe_get_target()
            login_url = url_for("auth.login", next=next_url) if next_url else url_for("auth.login")
            fetch_mode = request.headers.get("Sec-Fetch-Mode", "")
            is_fetch = (
                request.is_json
                or request.headers.get("X-Requested-With", "").casefold()
                == "xmlhttprequest"
                or request.accept_mimetypes.best == "application/json"
                or (fetch_mode and fetch_mode != "navigate")
            )
            if is_fetch:
                return jsonify(error=message, redirect_url=login_url), 401
            return redirect(login_url)

    @staticmethod
    def _safe_get_target():
        referer = request.referrer
        if not referer:
            return None
        parsed = urlsplit(referer)
        if parsed.netloc and parsed.netloc.casefold() != request.host.casefold():
            return None
        path = parsed.path or "/"
        if not path.startswith("/") or path.startswith("//"):
            return None
        try:
            rule, _ = current_app.url_map.bind_to_environ(request.environ).match(
                path,
                method="GET",
                return_rule=True,
            )
        except HTTPException:
            return None
        if rule.endpoint in {"auth.login", "auth.register"}:
            return None
        return f"{path}?{parsed.query}" if parsed.query else path
