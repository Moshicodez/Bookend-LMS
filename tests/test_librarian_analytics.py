import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.loan_record import LoanRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository


class LibrarianAnalyticsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "librarian-analytics-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.users = UserRepository()
        self.books = BookRepository()
        self.librarian = self._create_user("analytics-staff", "librarian")
        self.patron = self._create_user("analytics-reader", "patron")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _create_user(self, username, role):
        return self.users.create(
            f"{username}@example.com",
            username,
            generate_password_hash("StrongPass1!"),
            role,
        )

    def _sign_in(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role

    def test_analytics_endpoint_returns_grouped_counts_and_no_store_headers(self):
        today = date.today()
        fiction = self.books.create(Book(None, "Story", "Writer", "Fiction", ""))
        uncategorized = self.books.create(Book(None, "Untitled", "Writer", "", ""))
        db.session.add_all([
            LoanRecord(
                patron_id=self.patron.user_id,
                book_id=fiction.book_id,
                borrowed_at=today - timedelta(days=1),
                due_date=today + timedelta(days=13),
                returned_at=today,
            ),
            LoanRecord(
                patron_id=self.patron.user_id,
                book_id=uncategorized.book_id,
                borrowed_at=today,
                due_date=today + timedelta(days=14),
            ),
            LoanRecord(
                patron_id=self.patron.user_id,
                book_id=fiction.book_id,
                borrowed_at=today - timedelta(days=8),
                due_date=today + timedelta(days=6),
                returned_at=today,
            ),
        ])
        db.session.commit()
        self._sign_in(self.librarian)

        response = self.client.get("/librarian/analytics?range=7d")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        data = response.get_json()
        self.assertEqual(data["range"], "7d")
        self.assertEqual(data["start"], (today - timedelta(days=6)).isoformat())
        self.assertEqual(data["end"], today.isoformat())
        self.assertEqual(data["totals"], {"loans": 2, "returns": 2})
        self.assertEqual(len(data["series"]), 7)
        self.assertEqual(data["series"][-1]["date"], today.isoformat())
        self.assertEqual(data["series"][-1]["loans"], 1)
        self.assertEqual(data["series"][-1]["returns"], 2)
        self.assertEqual(
            data["genres"],
            [
                {"genre": "Fiction", "loans": 1},
                {"genre": "Uncategorized", "loans": 1},
            ],
        )

    def test_endpoint_returns_empty_series_for_range_without_activity(self):
        self._sign_in(self.librarian)

        response = self.client.get("/librarian/analytics?range=12m")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["series"]), 365)
        self.assertEqual(data["totals"], {"loans": 0, "returns": 0})
        self.assertEqual(data["genres"], [])
        self.assertTrue(all(point["loans"] == point["returns"] == 0 for point in data["series"]))

    def test_endpoint_supports_twelve_week_range(self):
        self._sign_in(self.librarian)

        response = self.client.get("/librarian/analytics?range=12w")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["range"], "12w")
        self.assertEqual(len(data["series"]), 84)
        self.assertEqual(
            data["start"],
            (date.today() - timedelta(days=83)).isoformat(),
        )
        self.assertEqual(data["end"], date.today().isoformat())

    def test_endpoint_requires_librarian_and_returns_no_store_errors(self):
        unauthorized = self.client.get("/librarian/analytics")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.headers["Cache-Control"], "no-store")
        self.assertIn("error", unauthorized.get_json())

        self._sign_in(self.patron)
        forbidden = self.client.get("/librarian/analytics")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.headers["Cache-Control"], "no-store")
        self.assertIn("error", forbidden.get_json())

    def test_endpoint_rejects_unknown_range_as_json_without_caching(self):
        self._sign_in(self.librarian)

        response = self.client.get("/librarian/analytics?range=all")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"error": "Unsupported analytics range."})


if __name__ == "__main__":
    unittest.main()
