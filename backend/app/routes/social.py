from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..exceptions import ValidationError
from ..repositories.book_repository import BookRepository
from ..repositories.favorite_repository import FavoriteRepository
from ..repositories.review_repository import ReviewRepository
from ..services.favorite_service import FavoriteService
from ..services.review_service import ReviewService
from .auth import _signed_in_user


social_bp = Blueprint("social", __name__)
favorite_service = FavoriteService(FavoriteRepository(), BookRepository())
review_service = ReviewService(ReviewRepository(), BookRepository())


def _login_redirect():
    return redirect(url_for("auth.login"))


def _safe_return_path():
    destination = request.form.get("next", "")
    if destination.startswith("/") and not destination.startswith("//"):
        return destination
    return None


@social_bp.route("/favorites")
def favorites():
    user = _signed_in_user()
    if user is None:
        return _login_redirect()
    user.require("save_favorites")
    books = favorite_service.books(user)
    ratings = review_service.summaries([book.book_id for book in books])
    favorite_ids = set(favorite_service.book_ids(user))
    return render_template(
        "favorites/index.html",
        books=books,
        ratings=ratings,
        favorite_ids=favorite_ids,
        user=user,
    )


@social_bp.route("/books/<int:book_id>/favorite", methods=["POST"])
def toggle_favorite(book_id):
    user = _signed_in_user()
    if user is None:
        return _login_redirect()
    favorite_service.toggle(user, book_id)
    return redirect(
        _safe_return_path() or url_for("books.detail", book_id=book_id)
    )


@social_bp.route("/books/<int:book_id>/reviews", methods=["POST"])
def create_review(book_id):
    user = _signed_in_user()
    if user is None:
        return _login_redirect()
    try:
        review_service.create(
            user,
            book_id,
            request.form.get("rating"),
            request.form.get("comment"),
        )
    except ValidationError as error:
        flash(str(error), "error")
    return redirect(url_for("books.detail", book_id=book_id))


@social_bp.route("/reviews/<int:review_id>/edit", methods=["POST"])
def update_review(review_id):
    user = _signed_in_user()
    if user is None:
        return _login_redirect()
    book_id = review_service.book_for_own_review(user, review_id)
    try:
        review_service.update(
            user,
            review_id,
            request.form.get("rating"),
            request.form.get("comment"),
        )
    except ValidationError as error:
        flash(str(error), "error")
    return redirect(url_for("books.detail", book_id=book_id))


@social_bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
def delete_review(review_id):
    user = _signed_in_user()
    if user is None:
        return _login_redirect()
    book_id = review_service.delete_own(user, review_id)
    return redirect(url_for("books.detail", book_id=book_id))


@social_bp.route("/librarian/reviews")
def moderate_reviews():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return _login_redirect()
    reviews = review_service.all_reviews(librarian)
    return render_template("reviews/index.html", reviews=reviews, user=librarian)


@social_bp.route("/librarian/reviews/<int:review_id>/delete", methods=["POST"])
def delete_review_as_librarian(review_id):
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return _login_redirect()
    review_service.delete_any(librarian, review_id)
    return redirect(url_for("social.moderate_reviews"))
