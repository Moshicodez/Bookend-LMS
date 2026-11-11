from datetime import date

class NotificationService:
    def __init__(
        self,
        notification_repository,
        loan_repository=None,
        book_repository=None,
    ):
        self._notifications = notification_repository
        self._loans = loan_repository
        self._books = book_repository

    def notify(
        self,
        user_id,
        title,
        message,
        category="general",
        link=None,
        dedupe_key=None,
        commit=True,
    ):
        return self._notifications.create(
            user_id,
            title,
            message,
            category=category,
            link=link,
            dedupe_key=dedupe_key,
            commit=commit,
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
                dedupe_key=(
                    f"{dedupe_key}:user:{user_id}" if dedupe_key else None
                ),
            )
            for user_id in self._notifications.users_with_role(role)
        ]

    def sync_overdue_notifications(self):
        if self._loans is None:
            return
        for loan in self._loans.find_overdue():
            book = self._books.find_book(loan.book_id) if self._books else None
            title = book.title if book else "A borrowed book"
            self.notify_role(
                "librarian",
                "Book overdue",
                f"{title} (loan #{loan.loan_id}) is overdue.",
                category="loan",
                link="/loans/overdue",
                dedupe_key=f"loan:{loan.loan_id}:librarian-overdue",
            )

    def notify_inventory_transition(
        self,
        book,
        previous_available,
        dedupe_key,
    ):
        current_available = book.available_copies
        if current_available == 0 and (
            previous_available is None or previous_available > 0
        ):
            title = "Book out of stock"
            message = f"No copies of {book.title} are currently available."
            suffix = "out-of-stock"
        elif (
            current_available == 1
            and previous_available is not None
            and previous_available > 1
        ):
            title = "Book running low"
            message = f"Only one copy of {book.title} is currently available."
            suffix = "low-stock"
        else:
            return None

        return self.notify_role(
            "librarian",
            title,
            message,
            category="inventory",
            link="/books/",
            dedupe_key=f"{dedupe_key}:{suffix}",
        )

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
