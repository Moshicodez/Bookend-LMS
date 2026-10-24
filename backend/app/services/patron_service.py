from .loan_service import LoanService
from ..utils.date_utils import today


class PatronService:
    def __init__(self, book_repo, loan_repo):
        self._loans = LoanService(book_repo, loan_repo)

    def view_loans(self, patron):
        return self._loans.view_loans(patron)

    def profile_summary(self, patron):
        loans = self._loans.view_loans(patron)
        current_loans = [loan for loan in loans if not loan.is_returned()]
        overdue_count = sum(loan.due_date < today() for loan in current_loans)
        return {
            "current_loans": len(current_loans),
            "overdue_count": overdue_count,
        }

    def borrow(self, patron, book_id):
        return self._loans.borrow_book(patron, book_id)

    def return_book(self, patron, book_id):
        return self._loans.return_book(patron, book_id)

    def view_payments(self, patron, loan_id=None):
        return self._loans.view_payments(patron, loan_id)

    def pay_late_fee(self, patron, loan_id):
        return self._loans.pay_late_fee(patron, loan_id)

    def pay_loss(self, patron, loan_id):
        return self._loans.pay_loss_fee(patron, loan_id)
