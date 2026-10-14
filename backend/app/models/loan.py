from datetime import date

from config import Config
from models.fee import LateFee, LossFee
from utils.errors import ValidationError
from utils.validators import to_date


class Loan:
    def __init__(self, loan_id, patron_id, book_id, borrowed_at, due_date,
                 returned_at=None, fee_paid=False, lost=False,
                 loss_fee=0, loss_paid=False):
        self._loan_id = loan_id
        self._patron_id = patron_id
        self._book_id = book_id
        self._borrowed_at = to_date(borrowed_at)
        self._due_date = to_date(due_date)
        self._returned_at = to_date(returned_at)
        self._late_fee = LateFee(paid=fee_paid)
        self._loss_fee = LossFee(loss_fee or Config.LOSS_FEE, paid=loss_paid) if lost else None

    @property
    def loan_id(self):
        return self._loan_id

    @property
    def patron_id(self):
        return self._patron_id

    @property
    def book_id(self):
        return self._book_id

    @property
    def borrowed_at(self):
        return self._borrowed_at

    @property
    def due_date(self):
        return self._due_date

    @property
    def returned_at(self):
        return self._returned_at

    @property
    def lost(self):
        return self._loss_fee is not None

    @property
    def fees(self):
        return [fee for fee in (self._late_fee, self._loss_fee) if fee is not None]

    def is_returned(self):
        return self._returned_at is not None

    def is_overdue(self, current_date):
        reference = self._returned_at or to_date(current_date)
        return reference > self._due_date

    def calculate_late_fee(self, current_date):
        return self._late_fee.amount(self, current_date)

    def mark_returned(self, returned_at):
        if self.is_returned():
            raise ValidationError("This loan has already been returned.")
        self._returned_at = to_date(returned_at)

    def mark_lost(self, loss_fee=Config.LOSS_FEE):
        if self.is_returned():
            raise ValidationError("This loan has already been returned.")
        if self.lost:
            raise ValidationError("This loan is already marked as lost.")
        self._loss_fee = LossFee(loss_fee)

    def outstanding(self, current_date=None):
        today = to_date(current_date) or date.today()
        return round(sum(fee.outstanding(self, today) for fee in self.fees), 2)

    def fee_breakdown(self, current_date=None):
        today = to_date(current_date) or date.today()
        return [
            {
                "type": fee.label,
                "amount": fee.amount(self, today),
                "paid": fee.paid
            }
            for fee in self.fees
        ]

    def pay_late_fee(self, current_date=None):
        today = to_date(current_date) or date.today()

        if not self.is_returned():
            raise ValidationError("Return the book first; late fees stop growing once it's back.")

        amount = self._late_fee.amount(self, today)

        if amount <= 0:
            raise ValidationError("There is no late fee on this loan.")

        self._late_fee.pay()
        return amount

    def pay_loss_fee(self):
        if not self.lost:
            raise ValidationError("This loan hasn't been marked as lost.")

        self._loss_fee.pay()
        return self._loss_fee.amount(self, date.today())

    def to_record(self):
        today = date.today()

        return {
            "loan_id": self._loan_id,
            "patron_id": self._patron_id,
            "book_id": self._book_id,
            "borrowed_at": self._borrowed_at.isoformat(),
            "due_date": self._due_date.isoformat(),
            "returned_at": self._returned_at.isoformat() if self._returned_at else None,
            "late_fee": self._late_fee.amount(self, today),
            "fee_paid": self._late_fee.paid,
            "lost": self.lost,
            "loss_fee": self._loss_fee.amount(self, today) if self.lost else 0,
            "loss_paid": self._loss_fee.paid if self.lost else False
        }