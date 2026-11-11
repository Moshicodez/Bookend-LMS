import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.reservation import Reservation
from backend.app.models.reservation_record import ReservationRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.notification_repository import NotificationRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.loan_service import LoanService
from backend.app.services.fee_service import FeeService


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
        self.librarian = UserRepository().create(
            "staff@example.com",
            "staff",
            generate_password_hash("StrongPass1!"),
            "librarian",
        )

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _sign_in(self):
        self._sign_in_as(self.user)

    def _sign_in_as(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role

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
        self.assertTrue(
            any(
                item.title == "New member registered"
                for item in NotificationRepository().for_user(
                    self.librarian.user_id
                )
            )
        )

    def test_notifications_can_be_read_and_bell_shows_count(self):
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
        self.assertIn(b"Notifications, 1 unread", inbox.data)

        response = self.client.post(
            f"/notifications/{notification.notification_id}/read",
            data={"csrf_token": self._csrf_token()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/loans/")
        self.assertEqual(NotificationRepository().unread_count(self.user.user_id), 0)

    def test_recent_endpoint_is_authenticated_limited_and_user_scoped(self):
        self._sign_in()
        other = UserRepository().create(
            "another@example.com",
            "another",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        repository = NotificationRepository()
        own_notifications = [
            repository.create(self.user.user_id, f"Update {index}", "Own message")
            for index in range(7)
        ]
        foreign = repository.create(other.user_id, "Private update", "Do not expose")

        response = self.client.get("/notifications/recent")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["notifications"]), 6)
        self.assertEqual(data["unread_count"], 7)
        self.assertTrue(data["notifications"][0]["created_at"].endswith("+00:00"))
        self.assertNotIn(foreign.notification_id, [item["id"] for item in data["notifications"]])
        self.assertEqual(data["notifications"][0]["id"], own_notifications[-1].notification_id)

    def test_recent_endpoint_returns_an_empty_state_without_fake_items(self):
        self._sign_in()

        response = self.client.get("/notifications/recent")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"notifications": [], "unread_count": 0})

    def test_recent_endpoint_rejects_guests_and_ajax_read_uses_csrf(self):
        self.assertEqual(self.client.get("/notifications/recent").status_code, 401)
        self._sign_in()
        notification = NotificationRepository().create(
            self.user.user_id,
            "A private update",
            "Only this patron can read it.",
        )
        other = UserRepository().create(
            "another@example.com",
            "another",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        foreign = NotificationRepository().create(
            other.user_id,
            "Another user's update",
            "Private.",
        )
        token = self._csrf_token()

        response = self.client.post(
            f"/notifications/{notification.notification_id}/read",
            headers={"Accept": "application/json", "X-CSRFToken": token},
        )
        forbidden_record = self.client.post(
            f"/notifications/{foreign.notification_id}/read",
            headers={"Accept": "application/json", "X-CSRFToken": token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["unread_count"], 0)
        self.assertEqual(forbidden_record.status_code, 404)

    def test_ajax_mark_all_read_updates_only_the_current_users_count(self):
        self._sign_in()
        repository = NotificationRepository()
        repository.create(self.user.user_id, "First", "Message")
        repository.create(self.user.user_id, "Second", "Message")
        other = UserRepository().create(
            "another@example.com",
            "another",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        foreign = repository.create(other.user_id, "Private", "Message")
        token = self._csrf_token()

        response = self.client.post(
            "/notifications/read-all",
            headers={"Accept": "application/json", "X-CSRFToken": token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["unread_count"], 0)
        self.assertIsNone(repository.find_for_user(other.user_id, foreign.notification_id).read_at)

    def test_librarian_recent_notifications_include_deduplicated_overdue_items(self):
        book = BookRepository().create(Book(None, "Overdue title", "Writer", "", ""))
        today = date.today()
        LoanRepository().create_loan(
            self.user.user_id,
            book.book_id,
            today - timedelta(days=20),
            today - timedelta(days=1),
        )
        self._sign_in_as(self.librarian)

        first = self.client.get("/notifications/recent")
        second = self.client.get("/notifications/recent")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        items = NotificationRepository().for_user(self.librarian.user_id)
        self.assertEqual(
            [item.title for item in items].count("Book overdue"),
            1,
        )
        self.assertIn("Overdue title", items[0].message)

    def test_reservation_and_fee_events_notify_librarians_and_patron(self):
        book = BookRepository().create(
            Book(None, "Circulation title", "Writer", "", "", total_copies=1)
        )
        borrower = UserRepository().create(
            "borrower@example.com",
            "borrower",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        loans = LoanRepository()
        loan_service = LoanService(BookRepository(), loans)
        loan_service.borrow_book(borrower, book.book_id)
        reservation = loan_service.reserve_book(self.user, book.book_id)

        librarian_updates = NotificationRepository().for_user(self.librarian.user_id)
        self.assertTrue(
            any(item.title == "New reservation placed" for item in librarian_updates)
        )
        self.assertEqual(reservation.patron_id, self.user.user_id)

        fee_book = BookRepository().create(Book(None, "Late title", "Writer", "", ""))
        today = date.today()
        fee_loan = loans.create_loan(
            self.user.user_id,
            fee_book.book_id,
            today - timedelta(days=20),
            today - timedelta(days=6),
        )
        fee_loan.mark_returned(today)
        loans.update_loan(fee_loan)
        FeeService().confirm_payment(self.librarian, fee_loan.loan_id, "late")

        patron_updates = NotificationRepository().for_user(self.user.user_id)
        librarian_updates = NotificationRepository().for_user(self.librarian.user_id)
        self.assertTrue(any(item.title == "Fee payment confirmed" for item in patron_updates))
        self.assertFalse(any(item.title == "Fee payment received" for item in librarian_updates))

    def test_inventory_threshold_notifies_on_low_and_zero_available(self):
        repository = BookRepository()
        loans = LoanRepository()
        service = LoanService(repository, loans)
        two_copies = repository.create(
            Book(None, "Low title", "Writer", "", "", total_copies=2)
        )
        service.borrow_book(self.user, two_copies.book_id)

        one_copy = repository.create(
            Book(None, "Out title", "Writer", "", "", total_copies=1)
        )
        service.borrow_book(self.user, one_copy.book_id)

        titles = [item.title for item in NotificationRepository().for_user(self.librarian.user_id)]
        self.assertIn("Book running low", titles)
        self.assertIn("Book out of stock", titles)

    def test_guest_patron_and_librarian_navigation_groups(self):
        guest_page = self.client.get("/")
        self.assertNotIn(b"data-notification-toggle", guest_page.data)
        self.assertIn(b'aria-label="Home"', guest_page.data)
        self.assertIn(b'aria-label="Books"', guest_page.data)
        self.assertNotIn(b'aria-label="Reservations"', guest_page.data)

        self._sign_in()
        patron_page = self.client.get("/")
        self.assertIn(b"data-notification-toggle", patron_page.data)
        self.assertIn(b'aria-label="Reservations"', patron_page.data)
        book = BookRepository().create(Book(None, "Ready title", "Writer", "", ""))
        db.session.add(
            ReservationRecord(
                patron_id=self.user.user_id,
                book_id=book.book_id,
                status=Reservation.READY,
            )
        )
        db.session.commit()
        patron_page = self.client.get("/")
        self.assertIn(b'aria-label="Reservations, 1 ready"', patron_page.data)

        self._sign_in_as(self.librarian)
        librarian_page = self.client.get("/")
        self.assertIn(b'aria-label="Manage Books"', librarian_page.data)
        self.assertIn(b'aria-label="Members"', librarian_page.data)
        self.assertIn(b'aria-label="Genres"', librarian_page.data)
        self.assertIn(b"data-notification-toggle", librarian_page.data)

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
