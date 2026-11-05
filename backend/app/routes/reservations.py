from flask import Blueprint, redirect, render_template, request, url_for

from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..repositories.user_repository import UserRepository
from ..services.librarian_service import LibrarianService
from ..services.loan_service import LoanService
from .auth import _signed_in_user


reservations_bp = Blueprint("reservations", __name__)
loan_service = LoanService(BookRepository(), LoanRepository())
librarian_service = LibrarianService(
    BookRepository(),
    LoanRepository(),
    UserRepository(),
)


@reservations_bp.route("/reservations")
def index():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    user.require("view_loans")
    return render_template(
        "reservations/index.html",
        user=user,
        reservation_cards=loan_service.reservation_cards(user),
    )


@reservations_bp.route("/librarian/reservations")
def manage():
    user = _signed_in_user()
    if user is None:
        return redirect(url_for("auth.login"))
    user.require("manage_loans")
    status = request.args.get("status", "")
    search = request.args.get("q", "")
    return render_template(
        "reservations/manage.html",
        user=user,
        reservations=librarian_service.reservation_management(
            user,
            status=status,
            search=search,
        ),
        status=status,
        search=search,
    )
