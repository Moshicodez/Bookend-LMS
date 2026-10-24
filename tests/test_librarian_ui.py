import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.loan_record import LoanRecord
from backend.app.models.review_record import ReviewRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository


class LibrarianUiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "librarian-ui-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.users = UserRepository()
        self.librarian = self._create_user("staff", "librarian")
        self.patron = self._create_user("reader", "patron")
        self.history = self.books.create(
            Book(None, "The Old Library", "A. Writer", "History", "")
        )
        self.mystery = self.books.create(
            Book(None, "Mystery at Noon", "B. Writer", "Mystery", "")
        )

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
        login = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', login.data
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
        return token

    def _post(self, path, token):
        return self.client.post(path, data={"csrf_token": token})

    def test_dashboard_statistics_recent_loans_and_most_borrowed(self):
        today = date.today()
        db.session.add_all(
            [
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.history.book_id,
                    borrowed_at=today - timedelta(days=14),
                    due_date=today - timedelta(days=4),
                    returned_at=today - timedelta(days=2),
                    fee_paid=True,
                ),
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.mystery.book_id,
                    borrowed_at=today - timedelta(days=30),
                    due_date=today - timedelta(days=16),
                    returned_at=today - timedelta(days=15),
                    lost=True,
                    loss_fee=25,
                    loss_paid=True,
                ),
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.history.book_id,
                    borrowed_at=today - timedelta(days=20),
                    due_date=today - timedelta(days=1),
                ),
            ]
        )
        db.session.commit()
        token = self._sign_in(self.librarian)

        response = self.client.get("/librarian")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Books", response.data)
        self.assertIn(b"Genres", response.data)
        self.assertIn(b"On loan", response.data)
        self.assertIn(b"Overdue", response.data)
        self.assertIn(b"Patrons", response.data)
        self.assertIn(b"$26.00", response.data)
        self.assertIn(b"The Old Library", response.data)
        self.assertIn(b"reader", response.data)
        self.assertIn(b"Most borrowed books", response.data)
        self.assertIn(b"Manage books", response.data)
        self.assertIn(b"Reviews", response.data)

        self.assertEqual(self.client.get("/loans/").status_code, 200)
        self.assertIn(b"Mark returned", self.client.get("/loans/").data)
        self.assertIn(b"Mark lost", self.client.get("/loans/").data)
        self.assertTrue(token)

    def test_book_management_table_edits_and_archives_books(self):
        token = self._sign_in(self.librarian)
        table = self.client.get("/books/manage")
        self.assertEqual(table.status_code, 200)
        self.assertIn(b"The Old Library", table.data)
        self.assertIn(b"History", table.data)
        self.assertIn(b"Edit", table.data)
        self.assertIn(b"Delete", table.data)

        deleted = self._post(
            f"/books/{self.history.book_id}/delete",
            token,
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(self.books.find_book(self.history.book_id).catalog)
        self.assertIn(b"Archived", self.client.get("/books/manage").data)

    def test_patron_cannot_access_librarian_dashboard_books_or_reviews(self):
        self._sign_in(self.patron)
        self.assertEqual(self.client.get("/librarian").status_code, 403)
        self.assertEqual(self.client.get("/books/manage").status_code, 403)
        self.assertEqual(self.client.get("/librarian/reviews").status_code, 403)

    def test_member_detail_and_review_moderation(self):
        db.session.add(
            ReviewRecord(
                user_id=self.patron.user_id,
                book_id=self.history.book_id,
                rating=5,
                comment="A lovely book.",
            )
        )
        db.session.commit()
        token = self._sign_in(self.librarian)

        members = self.client.get("/members/")
        self.assertIn(b"View", members.data)
        detail = self.client.get(f"/members/{self.patron.user_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"reader@example.com", detail.data)
        self.assertIn(b"Full loan history", detail.data)

        moderation = self.client.get("/librarian/reviews")
        self.assertEqual(moderation.status_code, 200)
        self.assertIn(b"A lovely book.", moderation.data)
        review = db.session.query(ReviewRecord).one()
        deleted = self._post(
            f"/librarian/reviews/{review.review_id}/delete",
            token,
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertEqual(db.session.query(ReviewRecord).count(), 0)

    def test_librarian_can_mark_loan_returned_or_lost(self):
        first = self.books.find_book(self.history.book_id)
        first.borrow()
        self.books.update_book(first)
        second = self.books.find_book(self.mystery.book_id)
        second.borrow()
        self.books.update_book(second)
        today = date.today()
        db.session.add_all(
            [
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.history.book_id,
                    borrowed_at=today - timedelta(days=2),
                    due_date=today + timedelta(days=12),
                ),
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.mystery.book_id,
                    borrowed_at=today - timedelta(days=2),
                    due_date=today + timedelta(days=12),
                ),
            ]
        )
        db.session.commit()
        token = self._sign_in(self.librarian)

        returned = self._post(
            f"/loans/manage/{self.history.book_id}/return",
            token,
        )
        self.assertEqual(returned.status_code, 302)
        self.assertTrue(self.books.find_book(self.history.book_id).available)

        lost = self._post(
            f"/loans/manage/{self.mystery.book_id}/lost",
            token,
        )
        self.assertEqual(lost.status_code, 302)
        self.assertFalse(self.books.find_book(self.mystery.book_id).catalog)


if __name__ == "__main__":
    unittest.main()
