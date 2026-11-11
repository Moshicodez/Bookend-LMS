from ..config import Config
from ..exceptions import NotFoundError, ValidationError
from ..models.reservation import Reservation
from ..repositories.notification_repository import NotificationRepository
from ..repositories.reservation_repository import ReservationRepository
from ..repositories.user_repository import UserRepository
from .notification_service import NotificationService
from ..utils.date_utils import add_days, today


class LoanService:
    def __init__(
        self,
        book_repo,
        loan_repo,
        reservation_repo=None,
        notification_service=None,
    ):
        self._book_repo = book_repo
        self._loan_repo = loan_repo
        self._reservations = reservation_repo or ReservationRepository()
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )

    def _get_book(self, book_id):
        book = self._book_repo.find_book(book_id)

        if book is None:
            raise NotFoundError("Book not found.")

        return book

    def _get_own_loan(self, patron, loan_id):
        loan = self._loan_repo.find_loan(loan_id)

        if loan is None or loan.patron_id != patron.user_id:
            raise NotFoundError("Loan not found.")

        return loan

    def view_loans(self, patron):
        patron.require("view_loans")
        return self._loan_repo.find_patron_loans(patron.user_id)

    def _prepare_borrow(
        self,
        patron,
        book_id,
        loans,
        pending_count=0,
        reservation=None,
    ):
        patron.require("borrow_book")
        book = self._get_book(book_id)
        borrowed_at = today()
        active_loans = [loan for loan in loans if not loan.is_returned()]
        existing_reservation = self._reservations.find_for_patron_book(
            patron.user_id, book_id
        )
        if existing_reservation and existing_reservation.status != Reservation.READY:
            raise ValidationError("You already have a reservation in the queue.")
        if existing_reservation and existing_reservation.status == Reservation.READY:
            reservation = existing_reservation

        reservation_count = self._reservations.count_open_for_patron(
            patron.user_id
        )

        additional_book = 0 if reservation is not None else 1
        if (
            len(active_loans)
            + reservation_count
            + pending_count
            + additional_book
            > patron.loan_limit
        ):
            raise ValidationError(f"You can only borrow {patron.loan_limit} books at a time.")

        if any(loan.outstanding(borrowed_at) > 0 for loan in loans):
            raise ValidationError("Please settle your outstanding fees before borrowing.")

        if self._loan_repo.find_active_loan(patron.user_id, book_id):
            raise ValidationError("You are already borrowing this book.")

        previous_available = book.available_copies
        book.borrow(reserved=reservation is not None)
        due_date = add_days(borrowed_at, book.loan_days)
        return book, borrowed_at, due_date, reservation, previous_available

    def borrow_book(self, patron, book_id):
        loans = self._loan_repo.find_patron_loans(patron.user_id)
        book, borrowed_at, due_date, reservation, previous_available = self._prepare_borrow(
            patron, book_id, loans
        )
        loan = self._loan_repo.create_loan(
            patron.user_id,
            book.book_id,
            borrowed_at,
            due_date,
            reservation_id=(
                reservation.reservation_id if reservation is not None else None
            ),
        )
        self._notifications.notify(
            patron.user_id,
            "Book borrowed",
            f"{book.title} is due on {loan.due_date:%b %d, %Y}.",
            category="loan",
            link="/loans/",
            dedupe_key=f"loan:{loan.loan_id}:borrowed",
        )
        self._notifications.notify_inventory_transition(
            book,
            previous_available,
            f"book:{book.book_id}:loan:{loan.loan_id}",
        )
        return loan

    def borrow_books(self, patron, book_ids):
        patron.require("borrow_book")
        if not book_ids:
            raise ValidationError("Your borrow basket is empty.")
        if len(set(book_ids)) != len(book_ids):
            raise ValidationError("Your borrow basket contains duplicate books.")

        loans = self._loan_repo.find_patron_loans(patron.user_id)
        entries = []
        previous_availability = []
        pending_count = 0
        for book_id in book_ids:
            entry = self._prepare_borrow(
                patron,
                book_id,
                loans,
                pending_count=pending_count,
            )
            book, borrowed_at, due_date, reservation, previous_available = entry
            entries.append(
                (
                    book,
                    borrowed_at,
                    due_date,
                    reservation.reservation_id if reservation else None,
                )
            )
            previous_availability.append(previous_available)
            if reservation is None:
                pending_count += 1
        loans = self._loan_repo.create_loans_atomic(patron.user_id, entries)
        for loan, previous_available in zip(loans, previous_availability):
            book = self._book_repo.find_book(loan.book_id)
            self._notifications.notify(
                patron.user_id,
                "Book borrowed",
                f"{book.title if book else 'Your book'} is due on {loan.due_date:%b %d, %Y}.",
                category="loan",
                link="/loans/",
                dedupe_key=f"loan:{loan.loan_id}:borrowed",
            )
            if book is not None:
                self._notifications.notify_inventory_transition(
                    book,
                    previous_available,
                    f"book:{book.book_id}:loan:{loan.loan_id}",
                )
        return loans

    def reserve_book(self, patron, book_id):
        patron.require("borrow_book")
        book = self._get_book(book_id)
        if not book.catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if book.kind == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if book.available_copies > 0:
            raise ValidationError("This book is available to borrow now.")
        if self._loan_repo.find_active_loan(patron.user_id, book_id):
            raise ValidationError("You are already borrowing this book.")
        if self._reservations.find_for_patron_book(patron.user_id, book_id):
            raise ValidationError("You already have a reservation for this book.")

        loans = self._loan_repo.find_patron_loans(patron.user_id)
        if any(loan.outstanding(today()) > 0 for loan in loans):
            raise ValidationError("Please settle your outstanding fees before reserving.")
        active_count = sum(not loan.is_returned() for loan in loans)
        reservation_count = self._reservations.count_open_for_patron(
            patron.user_id
        )
        if active_count + reservation_count >= patron.loan_limit:
            raise ValidationError(
                f"You can only borrow or reserve {patron.loan_limit} books at a time."
            )
        reservation = self._reservations.create_waiting(patron.user_id, book_id)
        self._notifications.notify(
            patron.user_id,
            "Reservation added",
            f"You joined the queue for {book.title}.",
            category="loan",
            link=f"/books/{book.book_id}",
            dedupe_key=f"reservation:{reservation.reservation_id}:placed",
        )
        self._notifications.notify_role(
            "librarian",
            "New reservation placed",
            f"{patron.username} reserved {book.title}.",
            category="reservation",
            link="/librarian/reservations?status=waiting",
            dedupe_key=f"reservation:{reservation.reservation_id}:placed",
        )
        return reservation

    def reservation_status(self, patron, book_id):
        own_reservation = (
            self._reservations.find_for_patron_book(patron.user_id, book_id)
            if patron is not None and patron.is_patron()
            else None
        )
        ready_reservation = (
            self._reservations.find_ready_for_patron_book(
                patron.user_id,
                book_id,
            )
            if patron is not None and patron.is_patron()
            else None
        )
        return {
            "own_reservation": own_reservation,
            "held_for_other": (
                self._reservations.has_ready_for_other_patron(
                    patron.user_id if patron is not None else -1,
                    book_id,
                )
            ),
            "ready_for_patron": (
                ready_reservation is not None
                and patron is not None
                and ready_reservation.patron_id == patron.user_id
            ),
            "waiting_count": self._reservations.waiting_count(book_id),
        }

    def reservations_for(self, patron):
        patron.require("view_loans")
        return self._reservations.find_for_patron(patron.user_id)

    def reservation_cards(self, patron):
        patron.require("view_loans")
        return self._reservations.find_patron_cards(patron.user_id)

    def active_reservation_count(self, patron_id):
        return self._reservations.count_open_for_patron(patron_id)

    def loan_cards(self, patron):
        patron.require("view_loans")
        current_date = today()
        loans = self._loan_repo.find_patron_loans(patron.user_id)
        from ..repositories.fee_repository import FeeRepository

        payment_details = FeeRepository().payment_details_for_loans(
            [loan.loan_id for loan in loans]
        )
        cards = []
        for loan in loans:
            book = self._book_repo.find_book(loan.book_id)
            status = self._loan_status(loan, current_date)
            cards.append(
                {
                    "loan": loan,
                    "book": book,
                    "status": status,
                    "outstanding": loan.outstanding(current_date),
                    "fees": loan.fee_breakdown(current_date),
                    "days_left": max(0, (loan.due_date - current_date).days),
                    "days_overdue": max(0, (current_date - loan.due_date).days),
                    "fee_confirmations": {
                        fee_type: payment_details.get((loan.loan_id, fee_type))
                        for fee_type in ("late", "loss")
                    },
                }
            )
        return cards

    @staticmethod
    def _loan_status(loan, current_date):
        if loan.lost:
            return "Lost"
        if loan.is_returned():
            return "Returned"
        if loan.due_date < current_date:
            return "Overdue"
        return "On loan"

    def management_cards(
        self,
        librarian,
        overdue_only=False,
        search="",
        status="",
        member_id=None,
        book_id=None,
    ):
        librarian.require("manage_loans")
        loans = (
            self._loan_repo.find_overdue()
            if overdue_only
            else self._loan_repo.find_all()
        )
        users = UserRepository()
        term = (search or "").strip().casefold()
        cards = []
        for loan in loans:
            if member_id is not None and loan.patron_id != member_id:
                continue
            if book_id is not None and loan.book_id != book_id:
                continue
            book = self._book_repo.find_book(loan.book_id)
            patron = users.find_by_id(loan.patron_id)
            patron_name = patron.username if patron else f"#{loan.patron_id}"
            loan_status = self._loan_status(loan, today())
            if status and loan_status.lower().replace(" ", "-") != status:
                continue
            display_title = book.title if book else loan.book_title
            haystack = f"{display_title} {patron_name}".casefold()
            if term and term not in haystack:
                continue
            cards.append(
                {
                    "loan": loan,
                    "book": book,
                    "patron_name": patron_name,
                    "status": loan_status,
                    "outstanding": loan.outstanding(today()),
                    "days_overdue": max(0, (today() - loan.due_date).days),
                }
            )
        return cards

    def issue_for_patron(
        self,
        librarian,
        patron_id,
        book_id,
        borrowed_at=None,
        due_date=None,
    ):
        librarian.require("manage_loans")
        patron = UserRepository().find_by_id(patron_id)
        if patron is None:
            raise NotFoundError("Patron not found.")
        if not patron.is_patron():
            raise ValidationError("Only patrons can be issued loans.")

        book = self._get_book(book_id)
        if not book.catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if book.kind == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if book.available_copies <= 0:
            raise ValidationError("No copies in stock.")

        borrowed_date = today() if borrowed_at is None else getattr(__import__("datetime"), "date").fromisoformat(str(borrowed_at)) if isinstance(borrowed_at, str) else borrowed_at
        due_date_value = add_days(borrowed_date, book.loan_days) if due_date is None else (
            getattr(__import__("datetime"), "date").fromisoformat(str(due_date))
            if isinstance(due_date, str)
            else due_date
        )
        if due_date_value <= borrowed_date:
            raise ValidationError("due date must be after the borrowed date")

        return self._loan_repo.create_loan(
            patron.user_id,
            book.book_id,
            borrowed_date,
            due_date_value,
        )

    def process_return_loan(self, librarian, loan_id, lost=False):
        return self.process_return(librarian, loan_id, lost=lost)

    def loan_detail_card(self, actor, loan_id):
        loan = self._loan_repo.find_loan(loan_id)
        if loan is None:
            raise NotFoundError("Loan not found.")
        if actor.is_patron() and loan.patron_id != actor.user_id:
            raise NotFoundError("Loan not found.")
        actor.require("manage_loans") if actor.is_librarian() else actor.require("view_loans")
        book = self._book_repo.find_book(loan.book_id)
        current_date = today()
        return {
            "loan": loan,
            "book": book,
            "status": self._loan_status(loan, current_date),
            "days_overdue": max(0, (current_date - loan.due_date).days),
            "outstanding": loan.outstanding(current_date),
        }

    def management_summary(self, librarian):
        librarian.require("manage_loans")
        summary = {"overdue": 0, "on_loan": 0, "returned": 0}
        for loan in self._loan_repo.find_all():
            if loan.is_returned():
                summary["returned"] += 1
            elif loan.due_date < today():
                summary["overdue"] += 1
            else:
                summary["on_loan"] += 1
        return summary

    def return_book(self, patron, book_id):
        patron.require("return_book")
        book = self._get_book(book_id)

        loan = self._loan_repo.find_active_loan(patron.user_id, book_id)

        if loan is None:
            raise NotFoundError("You don't have an active loan for this book.")

        returned_at = today()

        loan.mark_returned(returned_at)
        book.return_book()
        self._loan_repo.complete_return(loan)
        self._notifications.notify(
            patron.user_id,
            "Book returned",
            f"{book.title} was successfully returned.",
            category="loan",
            link="/loans/",
            dedupe_key=f"loan:{loan.loan_id}:returned",
        )

        return loan

    def view_payments(self, patron, loan_id=None):
        patron.require("view_payments")
        current_date = today()

        if loan_id is not None:
            loans = [self._get_own_loan(patron, loan_id)]
        else:
            loans = self._loan_repo.find_patron_loans(patron.user_id)

        report = []

        for loan in loans:
            breakdown = loan.fee_breakdown(current_date)

            if loan_id is None and not any(item["amount"] > 0 for item in breakdown):
                continue

            report.append({
                "loan_id": loan.loan_id,
                "book_id": loan.book_id,
                "fees": breakdown,
                "outstanding": loan.outstanding(current_date)
            })

        return report

    def process_return(self, librarian, loan_id, lost=False):
        librarian.require("update_return_status")
        loan = self._loan_repo.find_loan(loan_id)
        if loan is None or loan.is_returned():
            raise NotFoundError("That loan is already closed.")
        book = self._get_book(loan.book_id)

        if lost:
            loan.mark_lost(Config.LOSS_FEE)
            book.mark_lost()
        else:
            returned_at = today()
            loan.mark_returned(returned_at)
            book.return_book()

        self._loan_repo.complete_return(loan)
        self._notifications.notify(
            loan.patron_id,
            "Loan closed",
            (
                f"{book.title} was marked as lost."
                if lost
                else f"{book.title} was returned."
            ),
            category="loan",
            link="/loans/",
            dedupe_key=f"loan:{loan.loan_id}:closed",
        )

        return loan