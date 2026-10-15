from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from ..exceptions import ValidationError
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


@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    try:
        user = auth_service.login(
            request.form.get("username"),
            request.form.get("password"),
        )
    except ValidationError as error:
        status_code = 403 if "deactivated" in str(error).lower() else 401
        return render_template("auth/login.html", error_message=str(error)), status_code

    session.clear()
    session["user_id"] = user.user_id
    session["username"] = user.username
    session["role"] = user.role
    return redirect(url_for(f"auth.{user.home_endpoint()}"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    try:
        user = auth_service.register(
            request.form.get("email"),
            request.form.get("username"),
            request.form.get("password"),
            request.form.get("confirm_password"),
            request.form.get("staff_code"),
            request.form.get("role"),
        )
    except ValidationError as error:
        return render_template(
            "auth/register.html",
            error_message=str(error),
        ), 400

    session.clear()
    session["user_id"] = user.user_id
    session["username"] = user.username
    session["role"] = user.role
    return redirect(url_for(f"auth.{user.home_endpoint()}"))


@auth_bp.route("/dashboard")
def dashboard():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for(f"auth.{user.home_endpoint()}"))


@auth_bp.route("/patron")
def patron_dashboard():
    user = _signed_in_user("patron")
    if user is None:
        return redirect(url_for("auth.login"))
    return render_template(
        "dashboard/patron_dashboard.html",
        username=user.username,
    )


@auth_bp.route("/librarian")
def librarian_dashboard():
    user = _signed_in_user("librarian")
    if user is None:
        return redirect(url_for("auth.login"))
    return render_template(
        "dashboard/librarian_dashboard.html",
        username=user.username,
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))