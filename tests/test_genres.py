import re
import unittest

from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.book_record import BookRecord
from backend.app.models.genre_record import GenreRecord
from backend.app.models.notification_record import NotificationRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.genre_repository import GenreRepository
from backend.app.repositories.user_repository import UserRepository


class GenreManagementTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "genre-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.genres = GenreRepository()
        self.books = BookRepository()
        self.users = UserRepository()
        self.librarian = self.users.create(
            "staff@example.com",
            "staff",
            generate_password_hash("StrongPass1!"),
            "librarian",
        )

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _sign_in(self, user=None):
        user = user or self.librarian
        login = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', login.data
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
        return token

    def test_librarian_can_add_and_remove_unused_genres(self):
        token = self._sign_in()

        response = self.client.get("/librarian/genres/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage genres", response.data)
        self.assertGreaterEqual(response.data.count(b'name="csrf_token"'), 1)

        added = self.client.post(
            "/librarian/genres/add",
            data={"csrf_token": token, "name": "  Fantasy  "},
            follow_redirects=True,
        )
        self.assertEqual(added.status_code, 200)
        self.assertIn(b"Genre added.", added.data)
        self.assertIn("Fantasy", self.genres.list_genres())

        duplicate = self.client.post(
            "/librarian/genres/add",
            data={"csrf_token": token, "name": "fantasy"},
            follow_redirects=True,
        )
        self.assertIn(b"A genre with this name already exists.", duplicate.data)
        self.assertEqual(self.genres.list_genres().count("Fantasy"), 1)

        removed = self.client.post(
            "/librarian/genres/remove",
            data={
                "csrf_token": token,
                "name": "Fantasy",
                "confirm_action": "confirmed",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Genre removed:", removed.data)
        self.assertNotIn("Fantasy", self.genres.list_genres())

    def test_removing_a_genre_uncategorizes_books_and_notifies_librarians(self):
        book = self.books.create(
            Book(None, "The Harbor Archive", "A. Writer", "History", "")
        )
        token = self._sign_in()

        page = self.client.get("/librarian/genres/")
        self.assertIn(b">1</td>", page.data)
        self.assertIn(b'data-confirm-action="Remove genre"', page.data)

        response = self.client.post(
            "/librarian/genres/remove",
            data={
                "csrf_token": token,
                "name": "History",
                "confirm_action": "confirmed",
            },
            follow_redirects=True,
        )

        self.assertIn(b"Genre removed: History (1 books uncategorized).", response.data)
        self.assertNotIn("History", self.genres.list_genres())
        self.assertEqual(self.books.find_book(book.book_id).genre, "")
        notice = db.session.execute(
            db.select(NotificationRecord).where(
                NotificationRecord.title == "Genre removed"
            )
        ).scalar_one()
        self.assertIn("History (1 books uncategorized)", notice.message)

    def test_genre_management_post_requires_csrf(self):
        response = self.client.post(
            "/librarian/genres/add",
            data={"name": "Fantasy"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login"))

    def test_patron_cannot_open_genre_management(self):
        patron = self.users.create(
            "reader@example.com",
            "reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self._sign_in(patron)

        response = self.client.get("/librarian/genres/")

        self.assertEqual(response.status_code, 403)

    def test_virtual_uncategorized_filter_counts_and_role_visibility(self):
        blank = self.books.create(Book(None, "Blank genre", "Writer", "", ""))
        null_genre = self.books.create(Book(None, "Null genre", "Writer", "", ""))
        whitespace = self.books.create(Book(None, "Whitespace genre", "Writer", "", ""))
        archived = self.books.create(Book(None, "Archived blank", "Writer", "", ""))
        db.session.get(BookRecord, null_genre.book_id).genre = None
        db.session.get(BookRecord, whitespace.book_id).genre = " \t\n "
        archived_record = db.session.get(BookRecord, archived.book_id)
        archived_record.genre = None
        archived_record.catalog = False
        db.session.commit()
        self.genres.add("History")
        self.books.create(Book(None, "History book", "Writer", "History", ""))

        token = self._sign_in()
        catalog = self.client.get("/books/?genre=%20UnCaTeGoRiZeD%20")
        self.assertIn(b"Blank genre", catalog.data)
        self.assertIn(b"Null genre", catalog.data)
        self.assertIn(b"Whitespace genre", catalog.data)
        self.assertNotIn(b"Archived blank", catalog.data)
        self.assertIn(b"Uncategorized (3)", catalog.data)
        manage = self.client.get("/books/manage?genre=UNCATEGORIZED")
        self.assertIn(b"Blank genre", manage.data)
        self.assertIn(b"Null genre", manage.data)
        self.assertIn(b"Whitespace genre", manage.data)
        self.assertIn(b"Archived blank", manage.data)
        self.assertIn(b"Uncategorized", manage.data)
        self.assertIn(b">3</span>", manage.data)

        injection = self.client.get("/books/?genre=%27%20OR%201%3D1%20--")
        self.assertEqual(injection.status_code, 200)
        self.assertIn(b"No books found", injection.data)
        self.assertNotIn(b"Blank genre", injection.data)

        patron = self.users.create(
            "reader@example.com",
            "reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self._sign_in(patron)
        patron_page = self.client.get("/books/?genre=uncategorized")
        self.assertNotIn(b'href="/books/manage?genre=uncategorized"', patron_page.data)
        self.assertEqual(
            self.client.get("/books/manage?genre=uncategorized").status_code,
            403,
        )

    def test_reserved_virtual_genre_cannot_be_created(self):
        token = self._sign_in()
        response = self.client.post(
            "/librarian/genres/add",
            data={"csrf_token": token, "name": "  unCATEGORIZED  "},
            follow_redirects=True,
        )
        self.assertIn(b"reserved for books without a genre", response.data)
        self.assertNotIn("Uncategorized", self.genres.list_genres())
        db.session.add(GenreRecord(name=" unCATEGORIZED "))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


if __name__ == "__main__":
    unittest.main()
