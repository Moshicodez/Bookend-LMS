from .user import User


class Librarian(User):
    ROLE = "librarian"
    PERMISSIONS = frozenset({
        "search_book",
        "view_book",
        "add_book",
        "edit_book",
        "archive_book",
        "update_return_status",
        "manage_mem",
        "manage_loans",
        "manage_reviews",
    })

    def home_endpoint(self):
        return "librarian_dashboard"

    @property
    def loan_limit(self):
        return 0

    def can_be_managed_by(self, actor):
        return False