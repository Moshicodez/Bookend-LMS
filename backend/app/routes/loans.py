from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..repositories.user_repository import UserRepository
from ..services.loan_service import LoanService
from ..utils.date_utils import add_days, today
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
    q = request.args.get("q", "")
    status = request.args.get("status", "")
    member_id = request.args.get("member_id", "")
    book_id = request.args.get("book_id", "")
    if user.is_librarian():
        user.require("manage_loans")
        loans = []
        loan_cards = loan_service.management_cards(
            user,
            search=q,
            status="on-loan" if status == "active" else status,
            member_id=member_id,
            book_id=book_id,
        )
        summary = loan_service.management_summary(user)
        patrons = UserRepository().find_patrons()
        books = BookRepository().find_all(include_archived=True)
    else:
        loans = []
        loan_cards = loan_service.loan_cards(user)
        summary = None
        patrons = []
        books = []
    reservation_cards = (
        loan_service.reservation_cards(user) if user.is_patron() else []
    )
    return render_template(
        "loans/loans.html",
        loans=loans,
        loan_cards=loan_cards,
        reservation_cards=reservation_cards,
        user=user,
        q=q,
        status=status,
        member_id=member_id,
        book_id=book_id,
        summary=summary,
        patrons=patrons,
        books=books,
    )


@loans_bp.route("/issue", methods=["GET", "POST"])
def issue():
    user, response = _require_user()
    if response:
        return response
    if user.is_librarian():
        user.require("manage_loans")
        patrons = UserRepository().find_patrons()
        books = list(BookRepository().find_all())
        if request.method == "POST":
            try:
                loan = loan_service.issue_for_patron(
                    user,
                    request.form.get("patron_id"),
                    request.form.get("book_id"),
                    request.form.get("borrowed_at"),
                    request.form.get("due_date"),
                )
            except ValidationError as error:
                flash(str(error), "error")
            else:
                flash("Loan created successfully.", "success")
                return redirect(url_for("loans.detail", loan_id=loan.loan_id))
        return render_template(
            "loans/issue_loan.html",
            books=books,
            patrons=patrons,
            user=user,
            borrowed_at=request.form.get("borrowed_at", today().isoformat()),
            due_date=request.form.get("due_date", add_days(today(), 14).isoformat()),
        )
    user.require("borrow_book")
    books = BookRepository().find_all()
    return render_template("loans/issue_loan.html", books=books, user=user)


@loans_bp.route("/<int:loan_id>")
def detail(loan_id):
    user, response = _require_user()
    if response:
        return response
    card = loan_service.loan_detail_card(user, loan_id)
    return render_template("loans/loan_detail.html", card=card, user=user)


@loans_bp.route("/borrow/<int:book_id>", methods=["POST"])
def borrow(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.borrow_book(user, book_id)
    return redirect(url_for("books.detail", book_id=book_id))


@loans_bp.route("/reserve/<int:book_id>", methods=["POST"])
def reserve(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.reserve_book(user, book_id)
    return redirect(url_for("books.detail", book_id=book_id))


@loans_bp.route("/return/<int:book_id>", methods=["POST"])
def return_book(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.return_book(user, book_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/manage/<int:book_id>/return", methods=["POST"])
def librarian_return_book(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.process_return(user, book_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/manage/<int:book_id>/lost", methods=["POST"])
def librarian_mark_lost(book_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.process_return(user, book_id, lost=True)
    return redirect(url_for("loans.index"))


@loans_bp.route("/manage/loan/<int:loan_id>/return", methods=["POST"])
def librarian_return_loan(loan_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.process_return_loan(user, loan_id)
    return redirect(url_for("loans.index"))


@loans_bp.route("/manage/loan/<int:loan_id>/lost", methods=["POST"])
def librarian_mark_loan_lost(loan_id):
    user, response = _require_user()
    if response:
        return response
    loan_service.process_return_loan(user, loan_id, lost=True)
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
    loans = []
    return render_template(
        "loans/loans.html",
        loans=loans,
        loan_cards=loan_service.management_cards(user, overdue_only=True),
        user=user,
        overdue=True,
        q="",
        status="overdue",
        member_id="",
        book_id="",
        summary=loan_service.management_summary(user),
        patrons=UserRepository().find_patrons(),
        books=list(BookRepository().find_all(include_archived=True)),
        reservation_cards=[],
    )