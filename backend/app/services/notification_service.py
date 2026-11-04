from datetime import date

from ..exceptions import ValidationError


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

    def notify_role(
        self,
        role,
        title,
        message,
        category="general",
        link=None,
        dedupe_key=None,
    ):
        return [
            self.notify(
                user_id,
                title,
                message,
                category,
                link,
                f"{dedupe_key}:user:{user_id}" if dedupe_key else None,
            )
            for user_id in self._notifications.users_with_role(role)
        ]

    def announce(self, librarian, title, message):
        librarian.require("manage_notifications")
        title = (title or "").strip()
        message = (message or "").strip()
        if not title or len(title) > 160:
            raise ValidationError("Announcement titles must be 1-160 characters.")
        if not message or len(message) > 500:
            raise ValidationError("Announcement messages must be 1-500 characters.")
        return self.notify_role(
            "patron",
            title,
            message,
            category="announcement",
            link="/notifications/",
        )

    def sync_due_date_reminders(self, patron_id):
        if self._loans is None:
            return 0
        active_loans = self._loans.find_patron_loans(patron_id)
        return self._sync_loan_reminders(active_loans, date.today())

    def sync_all_due_date_reminders(self):
        if self._loans is None:
            return 0
        return self._sync_loan_reminders(
            self._loans.find_active_loans(),
            date.today(),
        )

    def sync_overdue_notifications(self):
        if self._loans is None:
            return 0
        overdue_loans = self._loans.find_overdue(date.today())
        created = 0
        for loan in overdue_loans:
            notifications = self.notify_role(
                "librarian",
                "Book overdue",
                f"Loan #{loan.loan_id} is overdue and needs attention.",
                category="overdue",
                link=f"/loans/{loan.loan_id}",
                dedupe_key=f"loan:{loan.loan_id}:overdue:staff",
            )
            created += sum(notification is not None for notification in notifications)
        return created

    def _sync_loan_reminders(self, active_loans, current_date):
        created = 0
        for loan in active_loans:
            if loan.is_returned() or loan.lost:
                continue
            days_remaining = (loan.due_date - current_date).days
            if days_remaining < 0:
                stage = "overdue"
                title = "Book overdue"
                message = f"Your borrowed book was due on {loan.due_date:%b %d, %Y}."
            elif days_remaining == 0:
                stage = "due-today"
                title = "Book due today"
                message = f"Please return your book by the end of today, {loan.due_date:%b %d, %Y}."
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
            notification = self.notify(
                loan.patron_id,
                title,
                message,
                category="overdue" if stage == "overdue" else "due",
                link=f"/loans/{loan.loan_id}",
                dedupe_key=f"loan:{loan.loan_id}:{stage}",
            )
            created += notification is not None
        return created
