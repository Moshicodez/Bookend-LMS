import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.notification_repository import NotificationRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.loan_service import LoanService


class NotificationRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "notification-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.user = UserRepository().create(
            "reader@example.com",
            "reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self.notifications = NotificationRepository()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _sign_in(self, user=None):
        user = user or self.user
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role

    def _csrf_token(self, path="/notifications/"):
        page = self.client.get(path)
        return re.search(
            rb'name="csrf_token" value="([^"]+)"', page.data
        ).group(1).decode()

    def _create_librarian(self):
        return UserRepository().create(
            "staff@example.com",
            "staff",
            generate_password_hash("StrongPass1!"),
            "librarian",
        )

    def test_auth_success_and_failure_are_announced(self):
        librarian = self._create_librarian()
        login_page = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', login_page.data
        ).group(1).decode()
        failed_login = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "reader",
                "password": "wrong-password",
            },
        )
        self.assertIn(b"Invalid username or password", failed_login.data)
        self.assertIn(b'class="global-flashes"', failed_login.data)

        registration_page = self.client.get("/register")
        registration_token = re.search(
            rb'name="csrf_token" value="([^"]+)"', registration_page.data
        ).group(1).decode()
        registered = self.client.post(
            "/register",
            data={
                "csrf_token": registration_token,
                "email": "new-reader@example.com",
                "username": "new-reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.assertIn(b"Account created. Please sign in.", registered.data)

        login_page = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', login_page.data
        ).group(1).decode()
        signed_in = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "new-reader",
                "password": "StrongPass1!",
            },
        )
        self.assertEqual(signed_in.status_code, 302)
        landing = self.client.get(signed_in.location)
        self.assertIn(b"You signed in successfully.", landing.data)
        registered_patron = UserRepository().find_username("new-reader")
        registration_notifications = self.notifications.for_user(librarian.user_id)
        self.assertEqual(registration_notifications[0].category, "member")
        self.assertEqual(
            registration_notifications[0].link,
            f"/members/{registered_patron.user_id}",
        )

    def test_notifications_render_in_nav_and_mark_as_read_navigates_to_link(self):
        self._sign_in()
        notification = self.notifications.create(
            self.user.user_id,
            "Book returned",
            "The book was returned.",
            category="loan",
            link="/loans/",
        )

        inbox = self.client.get("/notifications/")

        self.assertEqual(inbox.status_code, 200)
        self.assertIn(b"Book returned", inbox.data)
        self.assertIn(b"Notifications, 1 unread", inbox.data)
        self.assertIn(b"notification-dropdown-menu", inbox.data)

        response = self.client.post(
            f"/notifications/{notification.notification_id}/read",
            data={"csrf_token": self._csrf_token()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/loans/")
        self.assertEqual(self.notifications.unread_count(self.user.user_id), 0)

    def test_borrow_and_return_create_patron_notifications_and_stock_alert(self):
        librarian = self._create_librarian()
        self._sign_in()
        book = BookRepository().create(
            Book(None, "Last copy", "Writer", "", "", total_stock=1)
        )
        loan_service = LoanService(BookRepository(), LoanRepository())

        loan_service.borrow_book(self.user, book.book_id)
        patron_notifications = self.notifications.for_user(self.user.user_id)
        librarian_notifications = self.notifications.for_user(librarian.user_id)

        self.assertEqual(patron_notifications[0].title, "Book borrowed")
        self.assertEqual(patron_notifications[0].link, "/loans/")
        self.assertEqual(librarian_notifications[0].category, "inventory")
        self.assertEqual(librarian_notifications[0].link, f"/books/{book.book_id}")

        loan_service.return_book(self.user, book.book_id)
        patron_notifications = self.notifications.for_user(self.user.user_id)
        self.assertEqual(
            {notification.title for notification in patron_notifications},
            {"Book borrowed", "Book returned"},
        )

    def test_reservation_request_notifies_librarians_and_patron(self):
        librarian = self._create_librarian()
        book = BookRepository().create(
            Book(None, "Popular book", "Writer", "", "", total_stock=1)
        )
        borrower = UserRepository().create(
            "borrower@example.com",
            "borrower",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        LoanRepository().create_loan(
            borrower.user_id,
            book.book_id,
            date.today(),
            date.today() + timedelta(days=14),
        )

        reservation = LoanService(BookRepository(), LoanRepository()).reserve_book(
            self.user,
            book.book_id,
        )

        patron_notifications = self.notifications.for_user(self.user.user_id)
        staff_notifications = self.notifications.for_user(librarian.user_id)
        self.assertEqual(patron_notifications[0].title, "Reservation added")
        self.assertEqual(staff_notifications[0].title, "New reservation request")
        self.assertEqual(
            staff_notifications[0].dedupe_key,
            f"reservation:{reservation.reservation_id}:requested:user:{librarian.user_id}",
        )

    def test_due_reminders_are_persistent_and_deduplicated(self):
        self._sign_in()
        book = BookRepository().create(Book(None, "Due today", "Writer", "", ""))
        today = date.today()
        loan = LoanRepository().create_loan(
            self.user.user_id,
            book.book_id,
            today - timedelta(days=14),
            today,
        )

        response = self.client.get("/")
        self.client.get("/")

        self.assertEqual(response.status_code, 200)
        reminders = self.notifications.for_user(self.user.user_id)
        self.assertEqual([item.title for item in reminders], ["Book due today"])
        self.assertEqual(reminders[0].link, f"/loans/{loan.loan_id}")
        self.assertIn(
            f"/loans/{loan.loan_id}".encode(),
            self.client.get("/notifications/").data,
        )

        token = self._csrf_token("/")
        self.client.post("/logout", data={"csrf_token": token})
        self._sign_in()
        self.assertIn(b"Book due today", self.client.get("/notifications/").data)
        self.assertEqual(self.notifications.unread_count(self.user.user_id), 1)

    def test_notification_visibility_and_marking_are_scoped_to_owner(self):
        other_user = UserRepository().create(
            "other@example.com",
            "other",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        own = self.notifications.create(
            self.user.user_id, "Private update", "For reader only."
        )
        other = self.notifications.create(
            other_user.user_id, "Other update", "For the other reader."
        )
        self._sign_in()
        inbox = self.client.get("/notifications/")

        self.assertIn(b"Private update", inbox.data)
        self.assertNotIn(b"Other update", inbox.data)
        forbidden = self.client.post(
            f"/notifications/{other.notification_id}/read",
            data={"csrf_token": self._csrf_token()},
        )
        self.assertEqual(forbidden.status_code, 404)
        self.assertIsNone(
            self.notifications.find_for_user(
                other_user.user_id,
                own.notification_id,
            )
        )
        self.assertEqual(self.notifications.unread_count(other_user.user_id), 1)

    def test_mark_all_read_only_changes_the_signed_in_users_notifications(self):
        other_user = UserRepository().create(
            "other@example.com",
            "other",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self.notifications.create(self.user.user_id, "Mine", "First.")
        self.notifications.create(other_user.user_id, "Theirs", "Second.")
        self._sign_in()
        response = self.client.post(
            "/notifications/read-all",
            data={"csrf_token": self._csrf_token()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.notifications.unread_count(self.user.user_id), 0)
        self.assertEqual(self.notifications.unread_count(other_user.user_id), 1)

    def test_announcement_requires_librarian_and_reaches_active_patrons(self):
        librarian = self._create_librarian()
        other_user = UserRepository().create(
            "other@example.com",
            "other",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self._sign_in()
        unauthorized = self.client.get("/notifications/announcement")
        self.assertEqual(unauthorized.status_code, 403)

        self._sign_in(librarian)
        response = self.client.post(
            "/notifications/announcement",
            data={
                "csrf_token": self._csrf_token("/notifications/announcement"),
                "title": "Library hours",
                "message": "The library closes early on Friday.",
            },
        )

        self.assertEqual(response.status_code, 302)
        patron_notifications = self.notifications.for_user(self.user.user_id)
        other_notifications = self.notifications.for_user(other_user.user_id)
        self.assertEqual(patron_notifications[0].category, "announcement")
        self.assertEqual(patron_notifications[0].title, "Library hours")
        self.assertEqual(
            other_notifications[0].message,
            "The library closes early on Friday.",
        )

    def test_scheduled_sync_creates_overdue_alerts_once_for_patron_and_librarian(self):
        librarian = self._create_librarian()
        book = BookRepository().create(Book(None, "Past due", "Writer", "", ""))
        yesterday = date.today() - timedelta(days=1)
        LoanRepository().create_loan(
            self.user.user_id,
            book.book_id,
            yesterday - timedelta(days=14),
            yesterday,
        )

        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["sync-notifications"])
        second = runner.invoke(args=["sync-notifications"])

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertEqual(self.notifications.unread_count(self.user.user_id), 1)
        staff_notifications = self.notifications.for_user(librarian.user_id)
        self.assertEqual(len(staff_notifications), 1)
        self.assertEqual(staff_notifications[0].category, "overdue")
        self.assertEqual(
            first.output.strip(),
            "Created 2 notification(s): 1 patron reminder(s), 1 librarian alert(s).",
        )


if __name__ == "__main__":
    unittest.main()
