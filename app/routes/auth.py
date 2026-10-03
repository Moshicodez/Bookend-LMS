from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app import auth_service

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        success, msg = auth_service.register(
            email=request.form.get("email"),
            username=request.form.get("username"),
            password=request.form.get("password"),
            confirm_pass=request.form.get("confirm_pass"),
            provided_code=request.form.get("staff_code", ""),
        )
        flash(msg, "success" if success else "danger")
        if success:
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth_service.login(
            username=request.form.get("username"),
            password=request.form.get("password"),
        )
        if user:
            session["user_id"]  = user.user_id
            session["role"]     = user.role
            session["username"] = user.username
            return redirect(url_for("books.index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/members")
def manage_members():
    from app.models import User
    members = User.query.all()
    return render_template("auth/members.html", members=members)


@auth_bp.route("/members/toggle/<int:user_id>")
def toggle_member(user_id):
    from app.models import User
    from app import db
    user = User.query.get_or_404(user_id)
    user.active = not user.active
    db.session.commit()
    flash(f"{'Activated' if user.active else 'Deactivated'} {user.username}.", "success")
    return redirect(url_for("auth.manage_members"))
