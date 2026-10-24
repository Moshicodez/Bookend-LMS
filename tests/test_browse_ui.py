import unittest

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.favorite_record import FavoriteRecord
from backend.app.models.loan_record import LoanRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository


class BrowseUiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "browse-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.history = self.books.create(
            Book(None, "History of Libraries", "A. Writer", "History", "")
        )
        self.mystery = self.books.create(
            Book(None, "Mystery in the Stacks", "B. Writer", "Mystery", "")
        )
        self.history_companion = self.books.create(
            Book(None, "Another Library Story", "C. Writer", "History", "")
        )
        self.patron = self._create_user("reader", "patron")
        self.librarian = self._create_user("staff", "librarian")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _create_user(self, username, role):
        return UserRepository().create(
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

    def test_guest_can_browse_catalog_detail_and_search_overlay(self):
        catalog = self.client.get("/books/")
        self.assertEqual(catalog.status_code, 200)
        self.assertIn(b"History of Libraries", catalog.data)
        self.assertIn(b"Books to borrow", catalog.data)
        self.assertIn(b"data-search-dialog", catalog.data)
        self.assertIn(b"Search by title, author, or genre", catalog.data)
        self.assertIn(b"Sign in to borrow", catalog.data)

        detail = self.client.get(f"/books/{self.history.book_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"History of Libraries", detail.data)
        self.assertIn(b"History", detail.data)
        self.assertIn(b"More in History", detail.data)

    def test_genre_filter_and_search_cover_title_author_and_genre(self):
        filtered = self.client.get("/books/?genre=history")
        self.assertIn(b"History of Libraries", filtered.data)
        self.assertNotIn(b"Mystery in the Stacks", filtered.data)

        by_title = self.client.get("/books/?q=Libraries")
        self.assertIn(b"History of Libraries", by_title.data)
        self.assertNotIn(b"Mystery in the Stacks", by_title.data)

        by_author = self.client.get("/books/?q=B.+Writer")
        self.assertIn(b"Mystery in the Stacks", by_author.data)

        by_genre = self.client.get("/books/?q=Mystery")
        self.assertIn(b"Mystery in the Stacks", by_genre.data)

    def test_patron_navigation_counts_and_add_to_basket_action(self):
        self._sign_in(self.patron)
        db.session.add(
            FavoriteRecord(user_id=self.patron.user_id, book_id=self.history.book_id)
        )
        db.session.commit()
        with self.client.session_transaction() as session:
            session["basket_book_ids"] = [self.history.book_id]

        catalog = self.client.get("/books/")
        self.assertIn(b"Saved books, 1 saved", catalog.data)
        self.assertIn(b"Borrow basket, 1 books", catalog.data)
        self.assertIn(b"Add to basket", catalog.data)
        self.assertIn(b"My loans", catalog.data)
        self.assertIn("\u2665".encode(), catalog.data)

    def test_patron_add_to_basket_and_guest_basket_redirect(self):
        self.assertEqual(self.client.get("/basket").location, "/login")
        self._sign_in(self.patron)
        page = self.client.get("/login")
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]

        response = self.client.post(
            f"/basket/add/{self.history.book_id}",
            data={
                "csrf_token": token,
                "next": f"/books/{self.history.book_id}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/books/{self.history.book_id}")
        self.assertIn(
            f"Borrow basket, 1 books".encode(),
            self.client.get("/books/").data,
        )

    def test_librarian_navigation_uses_shield_and_overdue_count(self):
        self._sign_in(self.librarian)
        page = self.client.get("/books/")
        self.assertIn(b"Librarian dashboard, 0 overdue loans", page.data)
        self.assertNotIn(b"Saved books,", page.data)
        self.assertNotIn(b"Borrow basket,", page.data)


if __name__ == "__main__":
    unittest.main()
