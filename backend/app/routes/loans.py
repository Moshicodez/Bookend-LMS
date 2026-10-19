from flask import Blueprint, redirect, render_template, request, url_for

from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..services.loan_service import LoanService
from .auth import _signed_in_user


loans_bp = Blueprint("loans", __name__, url_prefix="/loans")
loan_repository = LoanRepository()
loan_service = LoanService(BookRepository(), loan_repository)


def _require_user():
    user = _signed_in_user()
    if user is None:
        return None, redirect(url_for("auth.login"))
    return user, None


@loans_bp.route("/")
def index():
    user, response = _require_user()
    if response:
        return response
    if user.is_librarian():
        user.require("manage_loans")
        loans = loan_repository.find_all()
    else:
        loans = loan_service.view_loans(user)
    return render_template("loans/loans.html", loans=loans, user=user)


@loans_bp.route("/issue")
def issue():
    user, response = _require_user()
    if response:
        return response
    user.require("borrow_book")
    books = BookRepository().find_all()
    return render_template("loans/issue_loan.html", books=books)


@loans_bp.route("/borrow/<int:book_id>", methods=["POST"])
def borrow(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.borrow_book(user, book_id)
    return redirect(url_for("books.detail", book_id=book_id))


@loans_bp.route("/return/<int:book_id>", methods=["POST"])
def return_book(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.return_book(user, book_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/<int:loan_id>/pay-late-fee", methods=["POST"])
def pay_late_fee(loan_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.pay_late_fee(user, loan_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/<int:loan_id>/pay-loss-fee", methods=["POST"])
def pay_loss_fee(loan_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.pay_loss_fee(user, loan_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/overdue")
def overdue():
    user, response = _require_user()
    if response:
        return response
    user.require("manage_loans")
    loans = loan_repository.find_overdue()
    return render_template("loans/loans.html", loans=loans, user=user, overdue=True)
