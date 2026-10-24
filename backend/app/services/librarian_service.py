import secrets
import string

from werkzeug.security import generate_password_hash

from ..exceptions import NotFoundError, PermissionDenied
from ..utils.date_utils import today
from .auth_service import AuthService
from .book_service import BookService
from .loan_service import LoanService


class LibrarianService:
    def __init__(self, book_repo, loan_repo, user_repo):
        self._books = BookService(book_repo)
        self._loans = LoanService(book_repo, loan_repo)
        self._book_repo = book_repo
        self._loan_repo = loan_repo
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

    def archived_books(self, librarian):
        return self._books.archived_books(librarian)

    def restore_book(self, librarian, book_id):
        return self._books.restore_book(librarian, book_id)

    def dashboard_data(self, librarian):
        librarian.require("manage_loans")
        librarian.require("manage_mem")
        books = self._book_repo.find_all()
        loans = self._loan_repo.find_all()
        overdue = self._loan_repo.find_overdue()
        patrons = self._user_repo.find_patrons()
        book_by_id = {book.book_id: book for book in books}
        patrons_by_id = {patron.user_id: patron for patron in patrons}

        recent_loans = []
        for loan in loans[:8]:
            book = self._book_repo.find_book(loan.book_id)
            patron = patrons_by_id.get(loan.patron_id) or self._user_repo.find_by_id(
                loan.patron_id
            )
            recent_loans.append(
                {
                    "loan": loan,
                    "book_title": book.title if book else f"Book #{loan.book_id}",
                    "patron_name": patron.username if patron else "Unknown patron",
                    "status": self._loan_status(loan),
                }
            )

        most_borrowed = []
        for item in self._loan_repo.most_borrowed():
            book = book_by_id.get(item["book_id"]) or self._book_repo.find_book(
                item["book_id"]
            )
            if book is not None:
                most_borrowed.append(
                    {
                        "book": book,
                        "loan_count": item["loan_count"],
                    }
                )

        fees_collected = sum(
            fee["amount"]
            for loan in loans
            for fee in loan.fee_breakdown(today())
            if fee["paid"]
        )
        return {
            "stats": {
                "books": len(books),
                "genres": len(
                    {book.genre.casefold() for book in books if book.genre.strip()}
                ),
                "on_loan": sum(not loan.is_returned() for loan in loans),
                "overdue": len(overdue),
                "patrons": len(patrons),
                "fees_collected": round(fees_collected, 2),
            },
            "recent_loans": recent_loans,
            "most_borrowed": most_borrowed,
        }

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

    def find_members(self, librarian, search_term=""):
        librarian.require("manage_mem")
        return self._user_repo.find_patrons(search_term)

    def member_loan_history(self, librarian, user_id):
        librarian.require("manage_mem")
        member = self._user_repo.find_by_id(user_id)
        if member is None or not member.is_patron():
            raise NotFoundError("Patron not found.")

        history = []
        for loan in self._loan_repo.find_patron_loans(member.user_id):
            book = self._book_repo.find_book(loan.book_id)
            history.append({
                "loan": loan,
                "book": book,
                "book_title": book.title if book else f"Book #{loan.book_id}",
                "status": self._loan_status(loan),
                "fees": loan.fee_breakdown(),
                "outstanding": loan.outstanding(),
            })
        return member, history

    @staticmethod
    def _loan_status(loan):
        if loan.lost:
            return "Lost"
        if loan.is_returned():
            return "Returned"
        if loan.due_date < today():
            return "Overdue"
        return "On loan"

    def create_patron(self, librarian, email, username, password, confirm_password):
        librarian.require("manage_mem")
        return AuthService(self._user_repo).register(
            email,
            username,
            password,
            confirm_password,
        )

    def reset_member_password(self, librarian, user_id):
        librarian.require("manage_mem")
        member = self._user_repo.find_by_id(user_id)

        if member is None:
            raise NotFoundError("Member not found.")
        if not member.can_be_managed_by(librarian):
            raise PermissionDenied("That account can't be managed here.")

        character_groups = (
            string.ascii_lowercase,
            string.ascii_uppercase,
            string.digits,
            string.punctuation,
        )
        characters = [secrets.choice(group) for group in character_groups]
        alphabet = "".join(character_groups)
        characters.extend(secrets.choice(alphabet) for _ in range(12))
        secrets.SystemRandom().shuffle(characters)
        temporary_password = "".join(characters)

        self._user_repo.update_password_hash(
            member.user_id,
            generate_password_hash(temporary_password),
        )
        return temporary_password