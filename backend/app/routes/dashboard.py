from flask import Blueprint, redirect, render_template, url_for

from .auth import _signed_in_user


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for(f"dashboard.{user.home_endpoint()}"))


@dashboard_bp.route("/patron")
def patron_dashboard():
    user = _signed_in_user("patron")
    if user is None:
        return redirect(url_for("auth.login"))
    return render_template("dashboard/patron_dashboard.html", username=user.username)


@dashboard_bp.route("/librarian")
def librarian_dashboard():
    user = _signed_in_user("librarian")
    if user is None:
        return redirect(url_for("auth.login"))
    return render_template("dashboard/librarian_dashboard.html", username=user.username)
