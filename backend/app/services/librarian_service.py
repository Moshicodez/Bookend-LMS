from datetime import date

from config import Config
from models.book import Book
from utils.errors import NotFoundError, ValidationError, PermissionDenied


class LibrarianService:
    def __init__(self, book_repo, loan_repo, user_repo):
        self._book_repo = book_repo
        self._loan_repo = loan_repo
        self._user_repo = user_repo

    def _get_book(self, book_id):
        book = self._book_repo.find_book(book_id)
        if book is None:
            raise NotFoundError("Book not found.")
        return book

    def add_book(self, librarian, title, author, genre, description, kind="standard"):
        librarian.require("add_book")

        book = Book.create(kind, None, title, author, genre, description)
        return self._book_repo.create(book)

    def edit_book(self, librarian, book_id, title, author, genre, description):
        librarian.require("edit_book")
        book = self._get_book(book_id)

        book.update_details(title, author, genre, description)
        self._book_repo.update_book(book)

        return book

    def archive_book(self, librarian, book_id):
        librarian.require("archive_book")
        book = self._get_book(book_id)

        book.archive()
        self._book_repo.update_book(book)

        return book

    def update_return_status(self, librarian, book_id, lost=False):
        librarian.require("update_return_status")
        book = self._get_book(book_id)

        loan = self._loan_repo.find_active_loan_by_book(book_id)

        if loan is None:
            raise NotFoundError("That book has no active loan.")

        if lost:
            loan.mark_lost(Config.LOSS_FEE)
            book.mark_lost()
        else:
            loan.mark_returned(date.today())
            self._loan_repo.return_record(loan.loan_id, loan.returned_at)
            book.return_book()

        self._loan_repo.update_loan(loan)
        self._book_repo.update_book(book)

        return loan

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