from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..exceptions import ValidationError
from ..repositories.genre_repository import GenreRepository
from ..services.genre_service import GenreService
from .auth import _signed_in_user


genres_bp = Blueprint("genres", __name__, url_prefix="/librarian/genres")
genre_service = GenreService(GenreRepository())


@genres_bp.route("/")
def index():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    return render_template(
        "genres/manage.html",
        genres=genre_service.manage_genres(librarian),
    )


@genres_bp.route("/add", methods=["POST"])
def add():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    try:
        genre_service.add_genre(librarian, request.form.get("name"))
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("Genre added.", "success")
    return redirect(url_for("genres.index"))


@genres_bp.route("/remove", methods=["POST"])
def remove():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    try:
        genre_service.remove_genre(librarian, request.form.get("name"))
    except ValidationError as error:
        flash(str(error), "error")
    else:
        flash("Genre removed.", "success")
    return redirect(url_for("genres.index"))
