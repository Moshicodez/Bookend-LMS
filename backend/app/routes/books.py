from flask import Blueprint, redirect, render_template, request, url_for

from ..config import COVER_COLORS
from ..models.book import Book
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from ..repositories.favorite_repository import FavoriteRepository
from ..repositories.review_repository import ReviewRepository
from ..services.book_service import BookService
from ..services.loan_service import LoanService
from ..services.review_service import ReviewService
from .auth import _signed_in_user


books_bp = Blueprint("books", __name__, url_prefix="/books")
book_service = BookService(BookRepository())
loan_repository = LoanRepository()
loan_service = LoanService(BookRepository(), loan_repository)
review_service = ReviewService(ReviewRepository(), BookRepository())
favorite_repository = FavoriteRepository()


def _require_user():
    user = _signed_in_user()
    if user is None:
        return None, redirect(url_for("auth.login"))
    return user, None


@books_bp.route("/")
def catalog():
    user = _signed_in_user()
    search_term = request.args.get("q", "")
    genre = request.args.get("genre", "").strip()
    books = book_service.search_books(search_term, genre)
    ratings = review_service.summaries([book.book_id for book in books])
    favorite_ids = (
        set(favorite_repository.book_ids_for_user(user.user_id))
        if user is not None and user.is_patron()
        else set()
    )
    return render_template(
        "books/catalog.html",
        books=books,
        search_term=search_term,
        selected_genre=genre,
        genres=BookRepository().list_genres(),
        ratings=ratings,
        favorite_ids=favorite_ids,
        cover_colors=COVER_COLORS,
        user=user,
    )


@books_bp.route("/<int:book_id>")
def detail(book_id):
    user = _signed_in_user()
    book = book_service.get_book(book_id)
    active_loan = loan_repository.find_active_loan_by_book(book_id)
    reviews = review_service.for_book(book_id)
    rating = review_service.summary(book_id)
    more_books = book_service.more_in_genre(book)
    more_ratings = review_service.summaries(
        [more_book.book_id for more_book in more_books]
    )
    own_review = (
        review_service.own_review(user, book_id)
        if user is not None and user.is_patron()
        else None
    )
    return render_template(
        "books/book_detail.html",
        book=book,
        active_loan=active_loan,
        reviews=reviews,
        rating=rating,
        more_books=more_books,
        more_ratings=more_ratings,
        own_review=own_review,
        is_favorite=(
            favorite_repository.contains(user.user_id, book_id)
            if user is not None and user.is_patron()
            else False
        ),
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
        request.files.get("cover"),
    )
    return redirect(url_for("books.detail", book_id=book.book_id))


@books_bp.route("/manage")
def manage():
    user, response = _require_user()
    if response:
        return response
    books = book_service.management_books(user)
    return render_template("books/manage.html", books=books, user=user)


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
        request.files.get("cover"),
    )
    return redirect(url_for("books.detail", book_id=book.book_id))


@books_bp.route("/<int:book_id>/archive", methods=["POST"])
def archive(book_id):
    user, response = _require_user()
    if response:
        return response
    book_service.archive_book(user, book_id)
    return redirect(url_for("books.catalog"))


@books_bp.route("/<int:book_id>/delete", methods=["POST"])
def delete(book_id):
    user, response = _require_user()
    if response:
        return response
    book_service.archive_book(user, book_id)
    return redirect(url_for("books.manage"))


@books_bp.route("/archived")
def archived():
    user, response = _require_user()
    if response:
        return response
    user.require("archive_book")
    books = book_service.archived_books(user)
    return render_template("books/archived_books.html", books=books)


@books_bp.route("/<int:book_id>/restore", methods=["POST"])
def restore(book_id):
    user, response = _require_user()
    if response:
        return response
    book_service.restore_book(user, book_id)
    return redirect(url_for("books.archived"))
