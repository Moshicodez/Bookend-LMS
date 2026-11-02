from datetime import date

class NotificationService:
    def __init__(self, notification_repository, loan_repository=None):
        self._notifications = notification_repository
        self._loans = loan_repository

    def notify(
        self,
        user_id,
        title,
        message,
        category="general",
        link=None,
        dedupe_key=None,
    ):
        return self._notifications.create(
            user_id,
            title,
            message,
            category=category,
            link=link,
            dedupe_key=dedupe_key,
        )

    def notify_role(self, role, title, message, category="general", link=None):
        return [
            self.notify(user_id, title, message, category, link)
            for user_id in self._notifications.users_with_role(role)
        ]

    def sync_due_date_reminders(self, patron_id):
        if self._loans is None:
            return
        active_loans = self._loans.find_patron_loans(patron_id)
        today = date.today()
        for loan in active_loans:
            if loan.is_returned():
                continue
            days_remaining = (loan.due_date - today).days
            if days_remaining <= 0:
                stage = "overdue"
                title = "Book overdue"
                message = f"Your borrowed book was due on {loan.due_date:%b %d, %Y}."
            elif days_remaining == 1:
                stage = "due-tomorrow"
                title = "Book due tomorrow"
                message = f"Please return your book by {loan.due_date:%b %d, %Y}."
            elif days_remaining <= 3:
                stage = "due-soon"
                title = "Book due soon"
                message = f"Your book is due on {loan.due_date:%b %d, %Y}."
            else:
                continue
            self.notify(
                patron_id,
                title,
                message,
                category="loan",
                link="/loans/",
                dedupe_key=f"loan:{loan.loan_id}:{stage}",
            )
