from config import Config
from models.user import User


class Patron(User):
    ROLE = "patron"
    PERMISSIONS = frozenset({
        "search_book",
        "view_book",
        "borrow_book",
        "return_book",
        "view_loans",
        "view_payments",
        "pay_late_fee",
        "pay_loss"
    })

    def home_endpoint(self):
        return "patron_dashboard"

    @property
    def loan_limit(self):
        return Config.MAX_ACTIVE_LOANS

    def can_be_managed_by(self, actor):
        return actor.perms("manage_mem")