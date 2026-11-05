import json
import re
import unittest
from datetime import date, timedelta
from io import BytesIO

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.loan_record import LoanRecord
from backend.app.models.review_record import ReviewRecord
from backend.app.models.reservation_record import ReservationRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.genre_repository import GenreRepository
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

        dashboard_redirect = self.client.get("/dashboard")
        self.assertEqual(dashboard_redirect.status_code, 302)
        self.assertEqual(dashboard_redirect.location, "/librarian")

        response = self.client.get("/librarian")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Books", response.data)
        self.assertIn(b"Genres", response.data)
        self.assertIn(b"On loan", response.data)
        self.assertIn(b"Overdue", response.data)
        self.assertIn(b"Patrons", response.data)
        self.assertIn("₱26.00".encode(), response.data)
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
        dashboard = self.client.get("/librarian")
        self.assertIn(b"Archived books", dashboard.data)
        self.assertIn(b"The Old Library", dashboard.data)
        self.assertIn(date.today().strftime("%b %d, %Y").encode(), dashboard.data)

    def test_librarian_can_search_and_filter_reservations(self):
        db.session.add_all(
            [
                ReservationRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.history.book_id,
                    status="waiting",
                ),
                ReservationRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.mystery.book_id,
                    status="ready",
                ),
            ]
        )
        db.session.commit()
        self._sign_in(self.librarian)

        page = self.client.get("/librarian/reservations")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Reservations", page.data)
        self.assertIn(b"The Old Library", page.data)
        self.assertIn(b"Mystery at Noon", page.data)
        self.assertIn(b"reader", page.data)

        filtered = self.client.get(
            "/librarian/reservations?status=waiting&q=Old"
        )
        self.assertIn(b"The Old Library", filtered.data)
        self.assertNotIn(b"Mystery at Noon", filtered.data)

        dashboard = self.client.get("/librarian")
        self.assertIn(b"Reservations", dashboard.data)
        self.assertIn(b"1</strong> waiting", dashboard.data)
        self.assertIn(b"1</strong> ready", dashboard.data)

        self._sign_in(self.patron)
        self.assertEqual(self.client.get("/librarian/reservations").status_code, 403)

    def test_patron_cannot_access_librarian_dashboard_books_or_reviews(self):
        token = self._sign_in(self.patron)
        self.assertEqual(self.client.get("/librarian").status_code, 403)
        self.assertEqual(self.client.get("/books/manage").status_code, 403)
        self.assertEqual(self.client.get("/librarian/reviews").status_code, 403)
        self.assertEqual(
            self.client.get("/librarian/backup/export").status_code,
            403,
        )
        response = self.client.post(
            "/librarian/backup/import",
            data={"csrf_token": token},
        )
        self.assertEqual(response.status_code, 403)

    def test_librarian_can_export_and_restore_backup(self):
        token = self._sign_in(self.librarian)
        dashboard = self.client.get("/librarian")
        self.assertIn(b"Backup and restore", dashboard.data)
        self.assertIn(b"Download backup", dashboard.data)

        exported = self.client.get("/librarian/backup/export")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "application/json")
        backup = json.loads(exported.data)
        self.assertEqual(backup["format"], "bookend-lms-backup")
        self.assertEqual(
            set(backup["tables"]),
            {"books", "favorites", "genres", "loans", "notifications", "reservations", "reviews", "users"},
        )

        temporary_book = self.books.create(
            Book(None, "Temporary book", "C. Writer", "Test", "")
        )
        restored = self.client.post(
            "/librarian/backup/import",
            data={
                "csrf_token": token,
                "backup_file": (BytesIO(exported.data), "backup.json"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(restored.status_code, 302)
        self.assertIsNone(self.books.find_book(temporary_book.book_id))
        self.assertIsNotNone(self.books.find_book(self.history.book_id))

    def test_failed_backup_restore_preserves_current_data(self):
        token = self._sign_in(self.librarian)
        exported = self.client.get("/librarian/backup/export")
        backup = json.loads(exported.data)
        duplicate_user = dict(
            next(row for row in backup["tables"]["users"] if row["role"] == "patron")
        )
        duplicate_user["user_id"] = max(
            row["user_id"] for row in backup["tables"]["users"]
        ) + 1
        backup["tables"]["users"].append(duplicate_user)
        temporary_book = self.books.create(
            Book(None, "Keep this book", "D. Writer", "Test", "")
        )

        response = self.client.post(
            "/librarian/backup/import",
            data={
                "csrf_token": token,
                "backup_file": (BytesIO(json.dumps(backup).encode("utf-8")), "invalid.json"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"existing data was kept", response.data)
        self.assertIsNotNone(self.books.find_book(temporary_book.book_id))

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
        self.assertIn(b"Loan history", detail.data)

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

    def test_dashboard_counts_genres_with_no_books(self):
        GenreRepository().add("Fantasy")
        self._sign_in(self.librarian)

        response = self.client.get("/librarian")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b'<article class="admin-stat-card"><span>Genres</span><strong>3</strong></article>',
            response.data,
        )
        self.assertIn(b"Manage genres", response.data)


if __name__ == "__main__":
    unittest.main()
