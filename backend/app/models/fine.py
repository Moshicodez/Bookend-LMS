from abc import ABC, abstractmethod

from config import Config
from utils.errors import ValidationError

class Fee(ABC):
    label = "Fee"

    def __init__(self, paid=False):
        self._paid = bool(paid)

    @property
    def paid(self):
        return self._paid

    def pay(self):
        if self._paid:
            raise ValidationError(f"This {self.label.lower()} has already been paid.")
        self._paid = True

    @abstractmethod
    def amount(self, loan, current_date):
        ...

    def outstanding(self, loan, current_date):
        return 0.0 if self._paid else self.amount(loan, current_date)





class LateFee(Fee):
    label = "Late fee"

    def __init__(self, daily_fee=Config.DAILY_LATE_FEE, paid=False):
        super().__init__(paid)
        self._daily_fee = daily_fee

    def amount(self, loan, current_date):
        if loan.lost:
            return 0.0

        reference = loan.returned_at or current_date
        days_late = max(0, (reference - loan.due_date).days)
        return round(days_late * self._daily_fee, 2)


class LossFee(Fee):
    label = "Loss fee"

    def __init__(self, fixed_amount=Config.LOSS_FEE, paid=False):
        super().__init__(paid)
        self._fixed_amount = fixed_amount

    def amount(self, loan, current_date):
        return self._fixed_amount