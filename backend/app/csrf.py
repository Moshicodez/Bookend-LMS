import secrets
from hmac import compare_digest

from flask import abort, request, session


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
            abort(400, description="The CSRF token is missing or invalid.")
