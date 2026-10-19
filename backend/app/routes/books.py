from flask import Blueprint, redirect, render_template, request, url_for

from ..models.book import Book
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..services.book_service import BookService
from ..services.loan_service import LoanService
from .auth import _signed_in_user


books_bp = Blueprint("books", __name__, url_prefix="/books")
book_service = BookService(BookRepository())
loan_repository = LoanRepository()
loan_service = LoanService(BookRepository(), loan_repository)


def _require_user():
    user = _signed_in_user()
    if user is None:
        return None, redirect(url_for("auth.login"))
    return user, None


@books_bp.route("/")
def catalog():
    user, response = _require_user()
    if response:
        return response
    search_term = request.args.get("q", "")
    books = book_service.search_books(search_term)
    return render_template(
        "books/catalog.html",
        books=books,
        search_term=search_term,
        user=user,
    )


@books_bp.route("/<int:book_id>")
def detail(book_id):
    user, response = _require_user()
    if response:
        return response
    book = book_service.get_book(book_id)
    active_loan = loan_repository.find_active_loan_by_book(book_id)
    return render_template(
        "books/book_detail.html",
        book=book,
        active_loan=active_loan,
        user=user,
    )


@books_bp.route("/new", methods=["GET", "POST"])
def add():
    user, response = _require_user()
    if response:
        return response
    user.require("add_book")
    if request.method == "GET":
        return render_template("books/add_book.html", user=user)

    book = book_service.add_book(
        user,
        request.form.get("title"),
        request.form.get("author"),
        request.form.get("genre"),
        request.form.get("description"),
        request.form.get("kind", Book.KIND),
    )
    return redirect(url_for("books.detail", book_id=book.book_id))


@books_bp.route("/<int:book_id>/edit", methods=["GET", "POST"])
def edit(book_id):
    user, response = _require_user()
    if response:
        return response
    user.require("edit_book")
    book = book_service.get_book(book_id)
    if request.method == "GET":
        return render_template("books/edit_book.html", book=book, user=user)

    book = book_service.edit_book(
        user,
        book_id,
        request.form.get("title"),
        request.form.get("author"),
        request.form.get("genre"),
        request.form.get("description"),
    )
    return redirect(url_for("books.detail", book_id=book.book_id))


@books_bp.route("/<int:book_id>/archive", methods=["POST"])
def archive(book_id):
    user, response = _require_user()
    if response:
        return response
    book_service.archive_book(user, book_id)
    return redirect(url_for("books.catalog"))
