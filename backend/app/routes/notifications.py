from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..exceptions import ValidationError
from ..repositories.notification_repository import NotificationRepository
from ..services.notification_service import NotificationService
from .auth import _signed_in_user


notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/notifications",
)
notification_repository = NotificationRepository()
notification_service = NotificationService(notification_repository)


def _safe_local_redirect(target, fallback):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return redirect(target)
    return redirect(fallback)


@notifications_bp.route("/")
def index():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    notifications = notification_repository.for_user(user.user_id)
    return render_template(
        "notifications/index.html",
        notifications=notifications,
        user=user,
    )


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
def mark_read(notification_id):
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    if not notification_repository.mark_read(user.user_id, notification_id):
        abort(404)
    notification = notification_repository.find_for_user(
        user.user_id, notification_id
    )
    next_page = request.form.get("next")
    if next_page:
        return _safe_local_redirect(next_page, url_for("notifications.index"))
    return redirect(notification.link or url_for("notifications.index"))


@notifications_bp.route("/read-all", methods=["POST"])
def mark_all_read():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    notification_repository.mark_all_read(user.user_id)
    return _safe_local_redirect(
        request.form.get("next"),
        url_for("notifications.index"),
    )


@notifications_bp.route("/announcement", methods=["GET", "POST"])
def announcement():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    user.require("manage_notifications")
    if request.method == "POST":
        try:
            notification_service.announce(
                user,
                request.form.get("title"),
                request.form.get("message"),
            )
        except ValidationError as error:
            flash(str(error), "error")
        else:
            flash("Announcement sent to active patrons.", "success")
            return redirect(url_for("notifications.announcement"))
    return render_template("notifications/announcement.html", user=user)
