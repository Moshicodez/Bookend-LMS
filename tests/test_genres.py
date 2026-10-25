import re
import unittest

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
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
            data={"csrf_token": token, "name": "Fantasy"},
            follow_redirects=True,
        )
        self.assertIn(b"Genre removed.", removed.data)
        self.assertNotIn("Fantasy", self.genres.list_genres())

    def test_removing_a_genre_in_use_is_blocked(self):
        self.books.create(Book(None, "The Harbor Archive", "A. Writer", "History", ""))
        token = self._sign_in()

        page = self.client.get("/librarian/genres/")
        self.assertIn(b"Reassign or clear books in this genre first", page.data)

        response = self.client.post(
            "/librarian/genres/remove",
            data={"csrf_token": token, "name": "History"},
            follow_redirects=True,
        )

        self.assertIn(
            b"Reassign or clear books in this genre before removing it.",
            response.data,
        )
        self.assertIn("History", self.genres.list_genres())

    def test_genre_management_post_requires_csrf(self):
        response = self.client.post(
            "/librarian/genres/add",
            data={"name": "Fantasy"},
        )

        self.assertEqual(response.status_code, 400)

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


if __name__ == "__main__":
    unittest.main()
