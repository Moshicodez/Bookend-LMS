import secrets
import string
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from ..exceptions import NotFoundError, PermissionDenied
from ..repositories.genre_repository import GenreRepository
from ..repositories.fee_repository import FeeRepository
from ..repositories.reservation_repository import ReservationRepository
from ..utils.date_utils import today
from .auth_service import AuthService
from .book_service import BookService
from .loan_service import LoanService


ANALYTICS_RANGES = {
    "7d": 7,
    "30d": 30,
    "12m": 365,
}


def build_analytics_series(start_date, end_date, loan_rows, return_rows):
    """Fill missing dates without relying on database-specific date functions."""
    loans_by_date = {day: count for day, count in loan_rows}
    returns_by_date = {day: count for day, count in return_rows}
    series = []
    current = start_date
    while current <= end_date:
        series.append({
            "date": current.isoformat(),
            "loans": int(loans_by_date.get(current, 0)),
            "returns": int(returns_by_date.get(current, 0)),
        })
        current += timedelta(days=1)
    return series


class LibrarianService:
    def __init__(self, book_repo, loan_repo, user_repo):
        self._books = BookService(book_repo)
        self._loans = LoanService(book_repo, loan_repo)
        self._book_repo = book_repo
        self._loan_repo = loan_repo
        self._user_repo = user_repo
        self._genre_repo = GenreRepository()
        self._reservations = ReservationRepository()
        self._fee_repository = FeeRepository()

    def add_book(
        self,
        librarian,
        title,
        author,
        genre,
        description,
        kind="standard",
        total_copies=1,
    ):
        return self._books.add_book(
            librarian,
            title,
            author,
            genre,
            description,
            kind,
            total_copies=total_copies,
        )

    def edit_book(
        self,
        librarian,
        book_id,
        title,
        author,
        genre,
        description,
        kind=None,
        total_copies=None,
    ):
        return self._books.edit_book(
            librarian,
            book_id,
            title,
            author,
            genre,
            description,
            kind=kind,
            total_copies=total_copies,
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

        fees_collected = self._fee_repository.collected_total()
        reservation_counts = self._reservations.open_counts()
        recent_reservations = self._reservations.find_for_management()[:6]
        archived_books = list(self._book_repo.find_archived())
        return {
            "stats": {
                "books": len(books),
                "genres": len(self._genre_repo.list_genres()),
                "on_loan": sum(not loan.is_returned() for loan in loans),
                "overdue": len(overdue),
                "patrons": len(patrons),
                "fees_collected": round(fees_collected, 2),
                "reservations_waiting": reservation_counts["waiting"],
                "reservations_ready": reservation_counts["ready"],
                "archived_books": len(archived_books),
            },
            "recent_loans": recent_loans,
            "most_borrowed": most_borrowed,
            "recent_reservations": recent_reservations,
            "archived_books": archived_books[:5],
        }

    def dashboard_analytics(self, librarian, period="30d", current_date=None):
        librarian.require("manage_loans")
        librarian.require("manage_mem")
        if period not in ANALYTICS_RANGES:
            raise ValueError("Unsupported analytics range.")

        end_date = current_date or date.today()
        start_date = end_date - timedelta(days=ANALYTICS_RANGES[period] - 1)
        aggregates = self._loan_repo.analytics_counts(start_date, end_date)
        series = build_analytics_series(
            start_date,
            end_date,
            aggregates["loans"],
            aggregates["returns"],
        )
        return {
            "range": period,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "series": series,
            "genres": [
                {"genre": genre, "loans": int(count)}
                for genre, count in aggregates["genres"]
            ],
            "totals": {
                "loans": sum(point["loans"] for point in series),
                "returns": sum(point["returns"] for point in series),
            },
        }

    def reservation_management(self, librarian, status="", search=""):
        librarian.require("manage_loans")
        return self._reservations.find_for_management(status, search)

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
        member, history, _ = self.member_detail_data(librarian, user_id)
        return member, history

    def member_detail_data(self, librarian, user_id):
        librarian.require("manage_mem")
        member = self._user_repo.find_by_id(user_id)
        if member is None or not member.is_patron():
            raise NotFoundError("Patron not found.")

        history = []
        loans = self._loan_repo.find_patron_loans(member.user_id)
        for loan in loans:
            book = self._book_repo.find_book(loan.book_id)
            history.append({
                "loan": loan,
                "book": book,
                "book_title": book.title if book else f"Book #{loan.book_id}",
                "status": self._loan_status(loan),
                "fees": loan.fee_breakdown(),
                "outstanding": loan.outstanding(),
            })
        stats = {
            "active_loans": sum(not loan.is_returned() and not loan.lost for loan in loans),
            "overdue": sum(self._loan_status(loan) == "Overdue" for loan in loans),
            "fees_due": sum(loan.outstanding() for loan in loans),
            "reservations": self._reservations.count_open_for_patron(member.user_id),
        }
        return member, history, stats

    def member_rows(self, librarian, search_term="", status=""):
        librarian.require("manage_mem")
        if status not in {"active", "inactive"}:
            status = ""
        return self._user_repo.find_patron_summaries(search_term, status)

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