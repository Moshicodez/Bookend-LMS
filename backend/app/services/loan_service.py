from ..config import Config
from ..exceptions import NotFoundError, ValidationError
from ..utils.date_utils import add_days, today


class LoanService:
    def __init__(self, book_repo, loan_repo):
        self._book_repo = book_repo
        self._loan_repo = loan_repo

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

    def borrow_book(self, patron, book_id):
        patron.require("borrow_book")
        book = self._get_book(book_id)

        borrowed_at = today()
        loans = self._loan_repo.find_patron_loans(patron.user_id)

        active_loans = [loan for loan in loans if not loan.is_returned()]

        if len(active_loans) >= patron.loan_limit:
            raise ValidationError(f"You can only borrow {patron.loan_limit} books at a time.")

        if any(loan.outstanding(borrowed_at) > 0 for loan in loans):
            raise ValidationError("Please settle your outstanding fees before borrowing.")

        if self._loan_repo.find_active_loan(patron.user_id, book_id):
            raise ValidationError("You are already borrowing this book.")

        book.borrow()

        due_date = add_days(borrowed_at, book.loan_days)

        loan = self._loan_repo.create_loan(
            patron.user_id,
            book_id,
            borrowed_at,
            due_date
        )

        self._book_repo.update_book(book)
        return loan

    def return_book(self, patron, book_id):
        patron.require("return_book")
        book = self._get_book(book_id)

        loan = self._loan_repo.find_active_loan(patron.user_id, book_id)

        if loan is None:
            raise NotFoundError("You don't have an active loan for this book.")

        returned_at = today()

        loan.mark_returned(returned_at)
        self._loan_repo.return_record(loan.loan_id, returned_at)
        self._loan_repo.update_loan(loan)

        book.return_book()
        self._book_repo.update_book(book)

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
        book = self._get_book(book_id)

        loan = self._loan_repo.find_active_loan_by_book(book_id)

        if loan is None:
            raise NotFoundError("That book has no active loan.")

        if lost:
            loan.mark_lost(Config.LOSS_FEE)
            book.mark_lost()
        else:
            returned_at = today()
            loan.mark_returned(returned_at)
            self._loan_repo.return_record(loan.loan_id, returned_at)
            book.return_book()

        self._loan_repo.update_loan(loan)
        self._book_repo.update_book(book)

        return loan