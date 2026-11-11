from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import HTTPException

from ..exceptions import ValidationError
from ..csrf import CSRFProtect
from ..repositories.user_repository import UserRepository
from ..services.auth_service import AuthService


auth_bp = Blueprint("auth", __name__)
auth_service = AuthService(UserRepository())


def _signed_in_user(required_role=None):
    user_id = session.get("user_id")
    if user_id is None:
        return None

    user = UserRepository().find_by_id(user_id)
    if user is None or not user.active:
        session.clear()
        abort(403)
    if required_role is not None and user.role != required_role:
        abort(403)
    return user


def _safe_get_target(target):
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return None
    try:
        rule, _ = current_app.url_map.bind_to_environ(request.environ).match(
            parsed.path,
            method="GET",
            return_rule=True,
        )
    except HTTPException:
        return None
    if rule.endpoint in {"auth.login", "auth.register"}:
        return None
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_get_target(request.values.get("next"))
    if request.method == "GET":
        return render_template(
            "auth/login.html",
            page=request.args.get("page", "login"),
            next_url=next_url,
        )

    try:
        user = auth_service.login(
            request.form.get("username"),
            request.form.get("password"),
        )
    except ValidationError as error:
        status_code = 403 if "deactivated" in str(error).lower() else 401
        flash(str(error), "error")
        return render_template(
            "auth/login.html",
            error_message=str(error),
            username=request.form.get("username", ""),
            page="login",
            next_url=next_url,
        ), status_code

    session.clear()
    session["user_id"] = user.user_id
    session["username"] = user.username
    session["role"] = user.role
    CSRFProtect.generate_token()
    flash("You signed in successfully.", "success")
    return redirect(next_url or url_for("landing.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/signup", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/login.html", page="register")

    try:
        auth_service.register(
            request.form.get("email"),
            request.form.get("username"),
            request.form.get("password"),
            request.form.get("confirm_password"),
        )
    except ValidationError as error:
        flash(str(error), "error")
        field_errors = {}
        if str(error) == "Password must be at least 8 characters.":
            field_errors["password"] = str(error)
        elif str(error) == "Passwords don't match.":
            field_errors["confirm_password"] = str(error)
        return render_template(
            "auth/login.html",
            error_message=str(error),
            suppress_inline_message=True,
            field_errors=field_errors,
            form_data={
                "email": request.form.get("email", ""),
                "username": request.form.get("username", ""),
            },
            page="register",
        ), 400

    flash("Account created. Please sign in.", "success")
    return render_template(
        "auth/login.html",
        page="login",
        success_message="Account created. Please sign in.",
        suppress_inline_message=True,
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))