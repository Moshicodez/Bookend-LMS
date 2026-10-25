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


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html", page=request.args.get("page", "login"))

    try:
        user = auth_service.login(
            request.form.get("username"),
            request.form.get("password"),
        )
    except ValidationError as error:
        status_code = 403 if "deactivated" in str(error).lower() else 401
        return render_template(
            "auth/login.html",
            error_message=str(error),
            username=request.form.get("username", ""),
            page="login",
        ), status_code

    session.clear()
    session["user_id"] = user.user_id
    session["username"] = user.username
    session["role"] = user.role
    return redirect(url_for("landing.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
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
        return render_template(
            "auth/login.html",
            error_message=str(error),
            form_data={
                "email": request.form.get("email", ""),
                "username": request.form.get("username", ""),
            },
            page="register",
        ), 400

    return render_template(
        "auth/login.html",
        page="login",
        success_message="Account created. Please sign in.",
    )


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    error_message = None
    if request.method == "POST":
        try:
            auth_service.change_password(
                user.user_id,
                request.form.get("current_password"),
                request.form.get("password"),
                request.form.get("confirm_password"),
            )
        except ValidationError as error:
            error_message = str(error)
        else:
            return render_template(
                "auth/change_password.html",
                success_message="Your password has been changed successfully.",
            )

    return render_template("auth/change_password.html", error_message=error_message)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))