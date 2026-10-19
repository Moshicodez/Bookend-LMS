from ..exceptions import NotFoundError, PermissionDenied
from .book_service import BookService
from .loan_service import LoanService


class LibrarianService:
    def __init__(self, book_repo, loan_repo, user_repo):
        self._books = BookService(book_repo)
        self._loans = LoanService(book_repo, loan_repo)
        self._user_repo = user_repo

    def add_book(self, librarian, title, author, genre, description, kind="standard"):
        return self._books.add_book(
            librarian, title, author, genre, description, kind
        )

    def edit_book(self, librarian, book_id, title, author, genre, description):
        return self._books.edit_book(
            librarian, book_id, title, author, genre, description
        )

    def archive_book(self, librarian, book_id):
        return self._books.archive_book(librarian, book_id)

    def update_return_status(self, librarian, book_id, lost=False):
        return self._loans.process_return(librarian, book_id, lost)

    def manage_member(self, librarian, user_id, active=None):
        librarian.require("manage_mem")

        member = self._user_repo.find_by_id(user_id)

        if member is None:
            raise NotFoundError("Member not found.")

        if not member.can_be_managed_by(librarian):
            raise PermissionDenied("That account can't be managed here.")

        turn_on = (not member.active) if active is None else bool(active)

        if turn_on:
            member.activate()
        else:
            member.deactivate()

        self._user_repo.set_active(member.user_id, member.active)
        return member