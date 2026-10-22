import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.loan_record import LoanRecord
from backend.app.models.user_record import UserRecord
from backend.app.repositories.book_repository import BookRepository


class LandingRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "landing-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_guest_landing_uses_empty_states_when_catalog_is_empty(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Find your", response.data)
        self.assertIn(b"Browse the stacks", response.data)
        self.assertIn(b"No books to show here just yet", response.data)
        self.assertIn(b"No books in this stack yet", response.data)
        self.assertIn(b"css/genre-carousel.css", response.data)

    def test_landing_shows_database_books_and_statistics(self):
        reader = UserRecord(
            email="reader@example.com",
            username="reader",
            password_hash=generate_password_hash("StrongPass1!"),
            role="patron",
        )
        staff = UserRecord(
            email="staff@example.com",
            username="staff",
            password_hash=generate_password_hash("StrongPass1!"),
            role="librarian",
        )
        db.session.add_all([reader, staff])
        db.session.commit()

        book = BookRepository().create(
            Book(None, "The Harbor Archive", "A. Writer", "History", "A story.")
        )
        borrowed = BookRepository().create(
            Book(None, "A Quiet Mystery", "B. Writer", "Mystery", "Another story.", available=False)
        )
        db.session.add(
            LoanRecord(
                patron_id=reader.user_id,
                book_id=borrowed.book_id,
                borrowed_at=date.today(),
                due_date=date.today() + timedelta(days=14),
            )
        )
        db.session.commit()

        response = self.client.get("/")
        html = response.data

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The Harbor Archive", html)
        self.assertIn(b"A Quiet Mystery", html)
        self.assertIn(b"2</span>\n      <span class=\"stat-label\">Books in the collection", html)
        self.assertIn(b"1</span>\n      <span class=\"stat-label\">Active patrons", html)
        self.assertIn(b"1</span>\n      <span class=\"stat-label\">Books borrowed", html)
        self.assertIn(b"Available", html)
        self.assertIn(b"Borrowed", html)
        self.assertEqual(book.genre, "History")

    def test_landing_search_filters_by_selected_type(self):
        BookRepository().create(
            Book(None, "The Harbor Archive", "A. Writer", "History", "")
        )
        BookRepository().create(
            Book(None, "The Quiet Room", "Harbor Lane", "Drama", "")
        )

        response = self.client.get("/?q=harbor&type=author")
        html = response.data
        result_start = html.index(b'search-results-section"')
        result_end = html.index(b'class="stats-strip"')
        results_html = html[result_start:result_end]

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Results for", results_html)
        self.assertIn(b"The Quiet Room", results_html)
        self.assertNotIn(b"The Harbor Archive", results_html)

    def test_signed_in_user_can_view_landing_page_and_dashboard_link(self):
        patron = UserRecord(
            email="reader@example.com",
            username="reader",
            password_hash=generate_password_hash("StrongPass1!"),
            role="patron",
        )
        db.session.add(patron)
        db.session.commit()
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = patron.user_id
            user_session["role"] = "patron"

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Hi, reader", response.data)
        self.assertIn(b'href="/patron">Dashboard</a>', response.data)
        self.assertIn(b"Log out", response.data)


if __name__ == "__main__":
    unittest.main()
