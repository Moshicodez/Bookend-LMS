from flask import Blueprint, abort, redirect, render_template, url_for

from ..repositories.notification_repository import NotificationRepository
from .auth import _signed_in_user


notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/notifications",
)
notification_repository = NotificationRepository()


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
    return redirect(notification.link or url_for("notifications.index"))


@notifications_bp.route("/read-all", methods=["POST"])
def mark_all_read():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    notification_repository.mark_all_read(user.user_id)
    return redirect(url_for("notifications.index"))
