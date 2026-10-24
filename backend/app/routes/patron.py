from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from urllib.parse import urlsplit

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..services.basket_service import BasketService
from .auth import _signed_in_user


patron_bp = Blueprint("patron", __name__)
basket_service = BasketService(BookRepository(), LoanRepository())


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
    books = basket_service.books(patron, session.get("basket_book_ids", []))
    return render_template("patron/basket.html", books=books, user=patron)


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
