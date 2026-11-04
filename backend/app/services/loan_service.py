from ..config import Config
from ..exceptions import NotFoundError, ValidationError
from ..models.reservation import Reservation
from ..repositories.notification_repository import NotificationRepository
from ..repositories.reservation_repository import ReservationRepository
from ..repositories.user_repository import UserRepository
from .notification_service import NotificationService
from ..utils.date_utils import add_days, today, to_date


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

    def _notify_stock_exhaustion(self, book, loan_id):
        if book.available_stock != 0:
            return
        self._notifications.notify_role(
            "librarian",
            "Book out of stock",
            f"No copies of {book.title} are currently available to borrow.",
            category="inventory",
            link=f"/books/{book.book_id}",
            dedupe_key=f"loan:{loan_id}:stock-zero",
        )

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
        ready_reservation = self._reservations.find_ready_for_book(book_id)
        if ready_reservation and ready_reservation.patron_id != patron.user_id:
            raise ValidationError("This book is being held for another patron.")
        if ready_reservation is not None and existing_reservation is None:
            raise ValidationError("This book is being held for another patron.")
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

        book.borrow()
        due_date = add_days(borrowed_at, book.loan_days)
        return book, borrowed_at, due_date, reservation

    def borrow_book(self, patron, book_id):
        loans = self._loan_repo.find_patron_loans(patron.user_id)
        book, borrowed_at, due_date, reservation = self._prepare_borrow(
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
        self._notify_stock_exhaustion(book, loan.loan_id)
        self._notifications.notify(
            patron.user_id,
            "Book borrowed",
            f"{book.title} is due on {loan.due_date:%b %d, %Y}.",
            category="borrow",
            link="/loans/",
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
        pending_count = 0
        for book_id in book_ids:
            entry = self._prepare_borrow(
                patron,
                book_id,
                loans,
                pending_count=pending_count,
            )
            book, borrowed_at, due_date, reservation = entry
            entries.append(
                (
                    book,
                    borrowed_at,
                    due_date,
                    reservation.reservation_id if reservation else None,
                )
            )
            if reservation is None:
                pending_count += 1
        loans = self._loan_repo.create_loans_atomic(patron.user_id, entries)
        for loan in loans:
            book = self._book_repo.find_book(loan.book_id)
            if book is not None:
                self._notify_stock_exhaustion(book, loan.loan_id)
            self._notifications.notify(
                patron.user_id,
                "Book borrowed",
                f"{book.title if book else 'Your book'} is due on {loan.due_date:%b %d, %Y}.",
                category="borrow",
                link="/loans/",
            )
        return loans

    def issue_for_patron(
        self,
        librarian,
        patron_id,
        book_id,
        borrowed_at,
        due_date,
    ):
        librarian.require("manage_loans")
        try:
            patron_id = int(patron_id)
            book_id = int(book_id)
            borrowed_at = to_date(borrowed_at)
            due_date = to_date(due_date)
        except (TypeError, ValueError) as error:
            raise ValidationError("Choose a valid patron, book, and loan date.") from error

        patron = UserRepository().find_by_id(patron_id)
        if patron is None or not patron.is_patron() or not patron.active:
            raise ValidationError("Choose an active patron account.")
        if borrowed_at is None or due_date is None or due_date <= borrowed_at:
            raise ValidationError("The due date must be after the borrowing date.")
        if borrowed_at > today():
            raise ValidationError("The borrowing date cannot be in the future.")

        book = self._get_book(book_id)
        if not book.catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if book.kind == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if not book.can_borrow():
            raise ValidationError(
                "This book is currently unavailable because there are no copies in stock."
            )

        loans = self._loan_repo.find_patron_loans(patron.user_id)
        active_loans = [loan for loan in loans if not loan.is_returned()]
        reservation_count = self._reservations.count_open_for_patron(patron.user_id)
        if len(active_loans) + reservation_count >= patron.loan_limit:
            raise ValidationError(
                f"This patron has reached the {patron.loan_limit}-book loan limit."
            )
        if any(loan.outstanding(borrowed_at) > 0 for loan in loans):
            raise ValidationError("This patron has outstanding fees.")
        if self._loan_repo.find_active_loan(patron.user_id, book_id):
            raise ValidationError("This patron is already borrowing this book.")

        existing_reservation = self._reservations.find_for_patron_book(
            patron.user_id, book_id
        )
        if existing_reservation and existing_reservation.status != Reservation.READY:
            raise ValidationError("This patron already has a reservation for the book.")
        ready_reservation = self._reservations.find_ready_for_book(book_id)
        if ready_reservation and (
            existing_reservation is None
            or ready_reservation.patron_id != patron.user_id
        ):
            raise ValidationError("This book is being held for another patron.")

        book.borrow()
        loan = self._loan_repo.create_loan(
            patron.user_id,
            book.book_id,
            borrowed_at,
            due_date,
            reservation_id=(
                existing_reservation.reservation_id
                if existing_reservation is not None
                and existing_reservation.status == Reservation.READY
                else None
            ),
        )
        self._notify_stock_exhaustion(book, loan.loan_id)
        self._notifications.notify(
            patron.user_id,
            "Book borrowed",
            f"{book.title} is due on {loan.due_date:%b %d, %Y}.",
            category="borrow",
            link="/loans/",
        )
        return loan

    def reserve_book(self, patron, book_id):
        patron.require("borrow_book")
        book = self._get_book(book_id)
        if not book.catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if book.kind == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if book.available:
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
            category="reservation",
            link=f"/books/{book.book_id}",
        )
        self._notifications.notify_role(
            "librarian",
            "New reservation request",
            f"{patron.username} joined the queue for {book.title}.",
            category="reservation",
            link=f"/books/{book.book_id}",
            dedupe_key=f"reservation:{reservation.reservation_id}:requested",
        )
        return reservation

    def reservation_status(self, patron, book_id):
        own_reservation = (
            self._reservations.find_for_patron_book(patron.user_id, book_id)
            if patron is not None and patron.is_patron()
            else None
        )
        ready_reservation = self._reservations.find_ready_for_book(book_id)
        return {
            "own_reservation": own_reservation,
            "held_for_other": (
                ready_reservation is not None
                and (patron is None or ready_reservation.patron_id != patron.user_id)
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
        return [
            {
                "reservation": reservation,
                "book": self._book_repo.find_book(reservation.book_id),
            }
            for reservation in self.reservations_for(patron)
        ]

    def active_reservation_count(self, patron_id):
        return self._reservations.count_open_for_patron(patron_id)

    def loan_cards(self, patron):
        patron.require("view_loans")
        current_date = today()
        cards = []
        for loan in self._loan_repo.find_patron_loans(patron.user_id):
            book = self._book_repo.find_book(loan.book_id)
            status = self._loan_status(loan, current_date)
            cards.append(
                {
                    "loan": loan,
                    "book": book,
                    "status": status,
                    "outstanding": loan.outstanding(current_date),
                    "fees": loan.fee_breakdown(current_date),
                    "days_overdue": self._days_overdue(loan, current_date),
                }
            )
        return cards

    @staticmethod
    def _days_overdue(loan, current_date):
        if loan.lost or loan.is_returned() or loan.due_date >= current_date:
            return 0
        return (current_date - loan.due_date).days

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
        member_id="",
        book_id="",
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
            book = self._book_repo.find_book(loan.book_id)
            patron = users.find_by_id(loan.patron_id)
            patron_name = patron.username if patron else f"#{loan.patron_id}"
            loan_status = self._loan_status(loan, today())
            if status and loan_status.lower().replace(" ", "-") != status:
                continue
            if member_id and str(loan.patron_id) != str(member_id):
                continue
            if book_id and str(loan.book_id) != str(book_id):
                continue
            haystack = (
                f"{book.title if book else ''} {patron_name} "
                f"#{loan.loan_id} #{loan.book_id}"
            ).casefold()
            if term and term not in haystack:
                continue
            cards.append(
                {
                    "loan": loan,
                    "book": book,
                    "patron_name": patron_name,
                    "status": loan_status,
                    "outstanding": loan.outstanding(today()),
                    "days_overdue": self._days_overdue(loan, today()),
                }
            )
        return cards

    def management_summary(self, librarian):
        librarian.require("manage_loans")
        current_date = today()
        loans = self._loan_repo.find_all()
        statuses = [self._loan_status(loan, current_date) for loan in loans]
        return {
            "total": len(loans),
            "active": sum(not loan.is_returned() and not loan.lost for loan in loans),
            "returned": sum(loan.is_returned() and not loan.lost for loan in loans),
            "overdue": statuses.count("Overdue"),
        }

    def loan_detail_card(self, user, loan_id):
        loan = self._loan_repo.find_loan(loan_id)
        if loan is None:
            raise NotFoundError("Loan not found.")
        if user.is_librarian():
            user.require("manage_loans")
        elif not user.is_patron() or loan.patron_id != user.user_id:
            raise NotFoundError("Loan not found.")
        patron = UserRepository().find_by_id(loan.patron_id)
        current_date = today()
        return {
            "loan": loan,
            "book": self._book_repo.find_book(loan.book_id),
            "patron_name": patron.username if patron else f"#{loan.patron_id}",
            "status": self._loan_status(loan, current_date),
            "outstanding": loan.outstanding(current_date),
            "days_overdue": self._days_overdue(loan, current_date),
        }

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
            category="return",
            link="/loans/",
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

    def pay_late_fee(self, patron, loan_id):
        patron.require("pay_late_fee")
        loan = self._get_own_loan(patron, loan_id)

        amount = loan.pay_late_fee(today())
        self._loan_repo.update_loan(loan)

        return amount

    def pay_loss_fee(self, patron, loan_id):
        patron.require("pay_loss")
        loan = self._get_own_loan(patron, loan_id)

        amount = loan.pay_loss_fee()
        self._loan_repo.update_loan(loan)

        return amount

    def process_return(self, librarian, book_id, lost=False):
        librarian.require("update_return_status")
        loan = self._loan_repo.find_active_loan_by_book(book_id)
        if loan is None:
            raise NotFoundError("That book has no active loan.")
        return self.process_return_loan(librarian, loan.loan_id, lost=lost)

    def process_return_loan(self, librarian, loan_id, lost=False):
        librarian.require("update_return_status")
        loan = self._loan_repo.find_loan(loan_id)
        if loan is None:
            raise NotFoundError("Loan not found.")
        if loan.is_returned():
            raise ValidationError("This loan has already been returned.")
        book = self._get_book(loan.book_id)
        if lost:
            loan.mark_lost(Config.LOSS_FEE)
            book.mark_lost()
        else:
            returned_at = today()
            loan.mark_returned(returned_at)
            book.return_book()

        self._loan_repo.complete_return(loan)
        if lost:
            self._notify_stock_exhaustion(book, loan.loan_id)
        self._notifications.notify(
            loan.patron_id,
            "Loan closed",
            (
                f"{book.title} was marked as lost."
                if lost
                else f"{book.title} was returned."
            ),
            category="lost" if lost else "return",
            link="/loans/",
        )

        return loan