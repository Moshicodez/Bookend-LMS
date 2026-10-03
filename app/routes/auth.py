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
            session["user_id"] = user.user_id
            session["role"]    = user.role
            return redirect(url_for("books.index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
