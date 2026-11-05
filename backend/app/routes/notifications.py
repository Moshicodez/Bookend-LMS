from datetime import timezone
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..repositories.notification_repository import NotificationRepository
from ..services.notification_service import NotificationService
from .auth import _signed_in_user


notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/notifications",
)
notification_repository = NotificationRepository()


def _sync_notifications(user):
    loan_repository = LoanRepository()
    notification_service = NotificationService(
        notification_repository,
        loan_repository,
        BookRepository(),
    )
    if user.is_patron():
        notification_service.sync_due_date_reminders(user.user_id)
    elif user.is_librarian():
        notification_service.sync_overdue_notifications()


def _safe_local_link(link):
    if not link:
        return url_for("notifications.index")
    parsed = urlsplit(link)
    if (
        parsed.scheme
        or parsed.netloc
        or not link.startswith("/")
        or link.startswith(("//", "/\\"))
    ):
        return url_for("notifications.index")
    return link


def _wants_json():
    return request.accept_mimetypes.best == "application/json"


@notifications_bp.route("/")
def index():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    _sync_notifications(user)
    notifications = notification_repository.for_user(user.user_id)
    return render_template(
        "notifications/index.html",
        notifications=notifications,
        user=user,
    )


@notifications_bp.route("/recent")
def recent():
    user = _signed_in_user()
    if user is None:
        return jsonify({"error": "Authentication required."}), 401
    _sync_notifications(user)
    notifications = notification_repository.recent_for_user(user.user_id, limit=6)
    return jsonify(
        {
            "notifications": [
                {
                    "id": notification.notification_id,
                    "title": notification.title,
                    "message": notification.message,
                    "category": notification.category,
                    "created_at": (
                        notification.created_at.replace(tzinfo=timezone.utc)
                        if notification.created_at.tzinfo is None
                        else notification.created_at.astimezone(timezone.utc)
                    ).isoformat(),
                    "read": notification.read_at is not None,
                    "link": _safe_local_link(notification.link),
                    "read_url": url_for(
                        "notifications.mark_read",
                        notification_id=notification.notification_id,
                    ),
                }
                for notification in notifications
            ],
            "unread_count": notification_repository.unread_count(user.user_id),
        }
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
    if _wants_json():
        return jsonify(
            {
                "ok": True,
                "unread_count": notification_repository.unread_count(user.user_id),
                "link": _safe_local_link(notification.link),
            }
        )
    return redirect(notification.link or url_for("notifications.index"))


@notifications_bp.route("/read-all", methods=["POST"])
def mark_all_read():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    notification_repository.mark_all_read(user.user_id)
    if _wants_json():
        return jsonify(
            {
                "ok": True,
                "unread_count": notification_repository.unread_count(user.user_id),
            }
        )
    return redirect(url_for("notifications.index"))
