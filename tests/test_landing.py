import unittest
from datetime import date, timedelta
from html import unescape
import json
import re

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
        for label in (
            b'aria-label="Search books"',
            b'aria-label="Sign in to view your profile"',
            b'aria-label="Sign in to view saved books"',
            b'aria-label="Sign in to use the borrow basket"',
            b'aria-label="Sign in to view your loans"',
        ):
            self.assertIn(label, response.data)
        self.assertNotIn(b"nav-icon-label", response.data)
        self.assertIn(b"No books to show here just yet", response.data)
        self.assertIn(b"No genres yet. Ask your librarian to add some.", response.data)
        self.assertIn(b"dist/genre-carousel.css", response.data)
        self.assertIn(b"dist/genre-carousel.js", response.data)
        self.assertIn(b"family=Anton&family=Poppins", response.data)
        self.assertNotIn(b'id="genre-carousel-root"', response.data)
        self.assertNotIn(b"data:image/svg+xml", response.data)
        self.assertNotIn(b'<option value="isbn"', response.data)
        self.assertNotIn(b'aria-live="polite"', response.data)
        for asset in ("css", "js"):
            response = self.client.get(f"/static/dist/genre-carousel.{asset}")
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_landing_shows_database_books_and_availability(self):
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
        self.assertIn(b"Available", html)
        self.assertIn(b"On loan", html)
        self.assertIn(b"WHY BOOKEND", html)
        self.assertIn(b"Browse the stacks", html)
        self.assertEqual(book.genre, "History")

    def test_landing_includes_unlisted_genres_and_correct_reference_status(self):
        BookRepository().create(Book(None, "Star Routes", "S. Author", "Sci-Fi", ""))
        BookRepository().create(Book(None, "Space Tales", "T. Author", "Adventure", ""))
        BookRepository().create(
            Book.create("reference", None, "Atlas", "A. Author", "History", "")
        )

        response = self.client.get("/")
        items_attribute = re.search(rb'data-items="([^"]+)"', response.data)
        carousel_items = json.loads(unescape(items_attribute.group(1).decode()))
        genres = [item["title"] for item in carousel_items]

        self.assertEqual(genres, ["Adventure", "History", "Sci-Fi"])
        self.assertIn(b"In-library use", response.data)
        self.assertIn(b'class="availability-badge is-borrowed">', response.data)

    def test_single_genre_uses_a_centered_link_without_carousel_controls(self):
        BookRepository().create(Book(None, "The Harbor Archive", "A. Writer", "History", ""))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="genre-single-card"', response.data)
        self.assertIn(b'href="/books/?genre=History"', response.data)
        self.assertNotIn(b'id="genre-carousel-root"', response.data)
        self.assertNotIn(b"circular-carousel__controls", response.data)

    def test_multiple_genres_render_carousel_items_with_catalog_links(self):
        BookRepository().create(Book(None, "The Harbor Archive", "A. Writer", "History", ""))
        BookRepository().create(Book(None, "A Quiet Mystery", "B. Writer", "Mystery", ""))

        response = self.client.get("/")
        items_attribute = re.search(rb'data-items="([^"]+)"', response.data)
        carousel_items = json.loads(unescape(items_attribute.group(1).decode()))

        self.assertEqual(len(carousel_items), 2)
        self.assertEqual(
            [item["href"] for item in carousel_items],
            ["/books/?genre=History", "/books/?genre=Mystery"],
        )
        self.assertIn(b'id="genre-carousel-root"', response.data)

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
        result_end = html.index(b'class="landing-section genre-section"')
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
