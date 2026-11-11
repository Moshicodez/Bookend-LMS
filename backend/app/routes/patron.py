from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..services.basket_service import BasketService
from ..repositories.basket_repository import BasketRepository
from ..services.patron_service import PatronService
from .auth import _signed_in_user


patron_bp = Blueprint("patron", __name__)
basket_service = BasketService(BookRepository(), LoanRepository())
basket_repository = BasketRepository()


def _basket_ids(patron):
    stored_ids = basket_repository.book_ids_for_user(patron.user_id)
    if stored_ids:
        return stored_ids
    legacy_ids = session.get("basket_book_ids", [])
    if not isinstance(legacy_ids, list):
        return []
    valid_ids = [
        book_id for book_id in legacy_ids
        if BookRepository().find_book(book_id) is not None
    ]
    if valid_ids:
        basket_repository.replace_for_user(patron.user_id, valid_ids)
    session["basket_book_ids"] = valid_ids
    return valid_ids
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
        _basket_ids(patron),
    )
    return render_template("patron/basket.html", basket=basket, user=patron)


@patron_bp.route("/basket/add/<int:book_id>", methods=["POST"])
def basket_add(book_id):
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    try:
        basket_ids = basket_service.add(
            patron,
            _basket_ids(patron),
            book_id,
        )
        basket_repository.replace_for_user(patron.user_id, basket_ids)
        session["basket_book_ids"] = basket_ids
    except ValidationError as error:
        flash(str(error), "error")
    return redirect(_safe_return_path() or url_for("books.catalog"))


@patron_bp.route("/basket/remove", methods=["POST"])
def basket_remove():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    selected_ids = request.form.getlist("book_ids")
    basket_ids = basket_service.remove(_basket_ids(patron), selected_ids)
    basket_repository.replace_for_user(patron.user_id, basket_ids)
    session["basket_book_ids"] = basket_ids
    flash("Selected books removed from your borrow basket.", "success")
    return redirect(url_for("patron.basket_index"))


@patron_bp.route("/basket/checkout", methods=["POST"])
def basket_checkout():
    patron = _require_patron()
    if patron is None:
        return redirect(url_for("auth.login"))
    basket_ids = _basket_ids(patron)
    try:
        loans = basket_service.checkout(patron, basket_ids)
    except ValidationError as error:
        flash(str(error), "error")
        return redirect(url_for("patron.basket_index"))
    basket_repository.clear_for_user(patron.user_id)
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
