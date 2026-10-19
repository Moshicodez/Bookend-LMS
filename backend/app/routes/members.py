from flask import Blueprint, redirect, render_template, url_for

from ..repositories.user_repository import UserRepository
from ..services.librarian_service import LibrarianService
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from .auth import _signed_in_user


members_bp = Blueprint("members", __name__, url_prefix="/members")
user_repository = UserRepository()
librarian_service = LibrarianService(
    BookRepository(),
    LoanRepository(),
    user_repository,
)


@members_bp.route("/")
def index():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    librarian.require("manage_mem")
    members = [
        user for user in user_repository.find_all()
        if user.is_patron()
    ]
    return render_template("members/members.html", members=members)


@members_bp.route("/<int:user_id>/toggle", methods=["POST"])
def toggle(user_id):
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    librarian_service.manage_member(librarian, user_id)
    return redirect(url_for("members.index"))
