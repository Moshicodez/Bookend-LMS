from flask import Blueprint, redirect, render_template, request, url_for

from ..exceptions import ValidationError
from ..repositories.user_repository import UserRepository
from ..services.librarian_service import LibrarianService
from ..repositories.book_repository import BookRepository
from ..repositories.loan_repository import LoanRepository
from .auth import _signed_in_user


members_bp = Blueprint("members", __name__, url_prefix="/members")
user_repository = UserRepository()
book_repository = BookRepository()
loan_repository = LoanRepository()
librarian_service = LibrarianService(
    book_repository,
    loan_repository,
    user_repository,
)


@members_bp.route("/")
def index():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    librarian.require("manage_mem")
    search_term = request.args.get("q", "")
    members = librarian_service.find_members(librarian, search_term)
    return render_template(
        "members/members.html",
        members=members,
        search_term=search_term,
    )


@members_bp.route("/new", methods=["POST"])
def create():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    try:
        librarian_service.create_patron(
            librarian,
            request.form.get("email"),
            request.form.get("username"),
            request.form.get("password"),
            request.form.get("confirm_password"),
        )
    except ValidationError as error:
        return render_template(
            "members/members.html",
            members=librarian_service.find_members(
                librarian,
                request.form.get("q", ""),
            ),
            search_term=request.form.get("q", ""),
            error_message=str(error),
            form_data={
                "email": request.form.get("email", ""),
                "username": request.form.get("username", ""),
            },
        ), 400
    return redirect(url_for("members.index"))


@members_bp.route("/<int:user_id>")
def detail(user_id):
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    member, history = librarian_service.member_loan_history(
        librarian,
        user_id,
    )
    return render_template(
        "members/member_detail.html",
        member=member,
        history=history,
    )


@members_bp.route("/<int:user_id>/toggle", methods=["POST"])
def toggle(user_id):
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    librarian_service.manage_member(librarian, user_id)
    return redirect(url_for("members.index"))


@members_bp.route("/<int:user_id>/reset-password", methods=["POST"])
def reset_password(user_id):
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return redirect(url_for("auth.login"))
    temporary_password = librarian_service.reset_member_password(librarian, user_id)
    members = librarian_service.find_members(librarian, request.form.get("q", ""))
    return render_template(
        "members/members.html",
        members=members,
        search_term=request.form.get("q", ""),
        temporary_password=temporary_password,
    )
