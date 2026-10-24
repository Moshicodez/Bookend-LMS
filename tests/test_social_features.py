import re
import unittest

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.favorite_record import FavoriteRecord
from backend.app.models.review_record import ReviewRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository


class SocialFeatureRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "social-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.users = UserRepository()
        self.patron = self._create_user("reader")
        self.other_patron = self._create_user("other")
        self.book = BookRepository().create(
            Book(None, "A Book Worth Saving", "A. Writer", "History", "")
        )

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _create_user(self, username, role="patron"):
        return self.users.create(
            f"{username}@example.com",
            username,
            generate_password_hash("StrongPass1!"),
            role,
        )

    def _sign_in(self, user):
        response = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', response.data
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
        return token

    def _post(self, path, token, data=None):
        return self.client.post(
            path,
            data={"csrf_token": token, **(data or {})},
        )

    def test_favorite_toggle_and_saved_books_page(self):
        token = self._sign_in(self.patron)

        added = self._post(
            f"/books/{self.book.book_id}/favorite",
            token,
            {"next": "/favorites"},
        )
        self.assertEqual(added.status_code, 302)
        self.assertEqual(added.location, "/favorites")
        self.assertTrue(
            db.session.get(
                FavoriteRecord, (self.patron.user_id, self.book.book_id)
            )
        )
        page = self.client.get("/favorites")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"A Book Worth Saving", page.data)

        removed = self._post(
            f"/books/{self.book.book_id}/favorite",
            token,
            {"next": "/favorites"},
        )
        self.assertEqual(removed.status_code, 302)
        self.assertIn(b"Your saved shelf is empty", self.client.get("/favorites").data)

    def test_guests_are_redirected_from_favorites_and_favorite_actions(self):
        self.assertEqual(self.client.get("/favorites").location, "/login")
        login_page = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', login_page.data
        ).group(1).decode()
        response = self._post(f"/books/{self.book.book_id}/favorite", token)
        self.assertEqual(response.location, "/login")

    def test_review_create_edit_delete_and_average_rating(self):
        token = self._sign_in(self.patron)
        detail_url = f"/books/{self.book.book_id}"

        created = self._post(
            f"/books/{self.book.book_id}/reviews",
            token,
            {"rating": "4", "comment": "A thoughtful read."},
        )
        self.assertEqual(created.status_code, 302)
        review = db.session.query(ReviewRecord).one()
        self.assertEqual((review.rating, review.comment), (4, "A thoughtful read."))

        detail = self.client.get(detail_url)
        self.assertIn(b"4.0", detail.data)
        self.assertIn(b"(1 reviews)", detail.data)
        self.assertIn(b"A thoughtful read.", detail.data)
        catalog = self.client.get("/books/")
        self.assertIn(b"4.0", catalog.data)

        updated = self._post(
            f"/reviews/{review.review_id}/edit",
            token,
            {"rating": "5", "comment": "Updated review."},
        )
        self.assertEqual(updated.status_code, 302)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Updated review.")

        deleted = self._post(f"/reviews/{review.review_id}/delete", token)
        self.assertEqual(deleted.status_code, 302)
        self.assertEqual(db.session.query(ReviewRecord).count(), 0)
        self.assertIn(b"(0 reviews)", self.client.get(detail_url).data)

    def test_review_constraints_and_review_ownership(self):
        token = self._sign_in(self.patron)
        detail_url = f"/books/{self.book.book_id}"
        self._post(
            f"/books/{self.book.book_id}/reviews",
            token,
            {"rating": "3", "comment": "Original."},
        )
        review = db.session.query(ReviewRecord).one()

        duplicate = self._post(
            f"/books/{self.book.book_id}/reviews",
            token,
            {"rating": "5", "comment": "Duplicate."},
        )
        self.assertEqual(duplicate.status_code, 302)
        self.assertEqual(db.session.query(ReviewRecord).count(), 1)

        self._sign_in(self.other_patron)
        forbidden = self.client.post(
            f"/reviews/{review.review_id}/delete",
            data={"csrf_token": token},
        )
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(db.session.query(ReviewRecord).count(), 1)

    def test_librarian_cannot_save_or_write_patron_content(self):
        librarian = self._create_user("staff", "librarian")
        token = self._sign_in(librarian)

        self.assertEqual(
            self._post(f"/books/{self.book.book_id}/favorite", token).status_code,
            403,
        )
        self.assertEqual(
            self._post(
                f"/books/{self.book.book_id}/reviews",
                token,
                {"rating": "5", "comment": "Not a patron review."},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
