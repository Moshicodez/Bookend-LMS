from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..services.basket_service import BasketService
from ..services.patron_service import PatronService
from .auth import _signed_in_user


patron_bp = Blueprint("patron", __name__)
basket_service = BasketService(BookRepository(), LoanRepository())
patron_service = PatronService(BookRepository(), LoanRepository())


def _require_patron():
    user = _signed_in_user()
    if user is None:
        return None
    user.require("borrow_book")
    return user


def _safe_return_path():
    destination = request.form.get("next", "")
    parsed = urlsplit(destination)
    if (
        parsed.scheme == ""
        and parsed.netloc == ""
        and parsed.path.startswith("/")
        and "\\" not in parsed.path
    ):
        return destination
    return None


@patron_bp.route("/basket")
def basket_index():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    basket = basket_service.items(
        patron,
        session.get("basket_book_ids", []),
    )
    return render_template("patron/basket.html", basket=basket, user=patron)


@patron_bp.route("/basket/add/<int:book_id>", methods=["POST"])
def basket_add(book_id):
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    try:
        session["basket_book_ids"] = basket_service.add(
            patron,
            session.get("basket_book_ids", []),
            book_id,
        )
    except ValidationError as error:
        flash(str(error), "error")
    return redirect(_safe_return_path() or url_for("books.catalog"))


@patron_bp.route("/basket/remove", methods=["POST"])
def basket_remove():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    selected_ids = request.form.getlist("book_ids")
    session["basket_book_ids"] = basket_service.remove(
        session.get("basket_book_ids", []),
        selected_ids,
    )
    return redirect(url_for("patron.basket_index"))


@patron_bp.route("/basket/checkout", methods=["POST"])
def basket_checkout():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    basket_ids = session.get("basket_book_ids", [])
    try:
        loans = basket_service.checkout(patron, basket_ids)
    except ValidationError as error:
        flash(str(error), "error")
        return redirect(url_for("patron.basket_index"))
    session["basket_book_ids"] = []
    session["last_receipt_loan_ids"] = [loan.loan_id for loan in loans]
    return redirect(url_for("patron.receipt"))


@patron_bp.route("/basket/receipt")
def receipt():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    receipt_items = basket_service.receipt(
        patron,
        session.get("last_receipt_loan_ids", []),
    )
    if not receipt_items:
        return redirect(url_for("loans.index"))
    return render_template(
        "patron/receipt.html",
        receipt_items=receipt_items,
        user=patron,
    )


@patron_bp.route("/profile")
def profile():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    summary = patron_service.profile_summary(patron)
    return render_template(
        "patron/profile.html",
        patron=patron,
        summary=summary,
        user=patron,
    )
