from datetime import date
from io import BytesIO

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..repositories.user_repository import UserRepository
from ..services.backup_service import BackupService, MAX_BACKUP_BYTES
from ..services.librarian_service import LibrarianService
from .auth import _signed_in_user


dashboard_bp = Blueprint("dashboard", __name__)
librarian_service = LibrarianService(
    BookRepository(),
    LoanRepository(),
    UserRepository(),
)


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
    dashboard = librarian_service.dashboard_data(user)
    return render_template(
        "dashboard/librarian_dashboard.html",
        username=user.username,
        dashboard=dashboard,
    )


@dashboard_bp.route("/librarian/backup/export")
def export_backup():
    user = _signed_in_user("librarian")
    if user is None:
        return redirect(url_for("auth.login"))

    response = send_file(
        BytesIO(BackupService.create_backup()),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"bookend-backup-{date.today().isoformat()}.json",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@dashboard_bp.route("/librarian/backup/import", methods=["POST"])
def import_backup():
    user = _signed_in_user("librarian")
    if user is None:
        return redirect(url_for("auth.login"))

    try:
        if request.content_length and request.content_length > MAX_BACKUP_BYTES + 65536:
            raise ValidationError("Backup files must be no larger than 20 MB.")
        upload = request.files.get("backup_file")
        if upload is None or not upload.filename:
            raise ValidationError("Choose a backup file to restore.")
        BackupService.restore_backup(upload.stream)
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("Backup restored. Current library data has been replaced.", "success")
    return redirect(url_for("dashboard.librarian_dashboard"))
