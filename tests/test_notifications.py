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

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _sign_in(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.user_id
            session["username"] = self.user.username
            session["role"] = self.user.role

    def _csrf_token(self):
        page = self.client.get("/notifications/")
        return re.search(
            rb'name="csrf_token" value="([^"]+)"', page.data
        ).group(1).decode()

    def test_auth_success_and_failure_are_announced(self):
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

    def test_notifications_can_be_read_without_nav_bell(self):
        self._sign_in()
        notification = NotificationRepository().create(
            self.user.user_id,
            "Book returned",
            "The book was returned.",
            category="loan",
            link="/loans/",
        )

        inbox = self.client.get("/notifications/")

        self.assertEqual(inbox.status_code, 200)
        self.assertIn(b"Book returned", inbox.data)
        self.assertNotIn(b"Notifications, 1 unread", inbox.data)

        response = self.client.post(
            f"/notifications/{notification.notification_id}/read",
            data={"csrf_token": self._csrf_token()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/loans/")
        self.assertEqual(NotificationRepository().unread_count(self.user.user_id), 0)

    def test_due_reminder_is_created_when_patron_visits(self):
        self._sign_in()
        book = BookRepository().create(Book(None, "Due today", "Writer", "", ""))
        today = date.today()
        LoanRepository().create_loan(
            self.user.user_id,
            book.book_id,
            today - timedelta(days=14),
            today,
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        reminders = NotificationRepository().for_user(self.user.user_id)
        self.assertEqual([item.title for item in reminders], ["Book overdue"])


if __name__ == "__main__":
    unittest.main()
