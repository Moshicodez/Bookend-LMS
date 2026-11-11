import re
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.book_record import BookRecord
from backend.app.models.basket_record import BasketRecord
from backend.app.models.favorite_record import FavoriteRecord
from backend.app.models.fee_payment_record import FeePaymentRecord
from backend.app.models.loan_record import LoanRecord
from backend.app.models.notification_record import NotificationRecord
from backend.app.models.reservation_record import ReservationRecord
from backend.app.models.review_record import ReviewRecord
from backend.app.models.user_record import UserRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.fee_repository import FeeRepository
from backend.app.repositories.user_repository import UserRepository


class BookDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "book-deletion-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "COVER_UPLOAD_FOLDER": self.temp_dir.name,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.librarian = self._create_user("staff", "librarian")
        self.patron = self._create_user("reader", "patron")
        self.token = self._sign_in(self.librarian)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.temp_dir.cleanup()

    def _create_user(self, username, role):
        return UserRepository().create(
            f"{username}@example.com",
            username,
            generate_password_hash("StrongPass1!"),
            role,
        )

    def _sign_in(self, user):
        page = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', page.data
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
        return token

    def _post(self, path, data=None, token=None, follow_redirects=True):
        payload = dict(data or {})
        payload.setdefault("confirm_action", "confirmed")
        payload["csrf_token"] = token or self.token
        return self.client.post(path, data=payload, follow_redirects=follow_redirects)

    def _book(self, title="Book", cover=None):
        return self.books.create(Book(None, title, "Writer", "", "", cover=cover))

    @staticmethod
    def _archive(book_id):
        record = db.session.get(BookRecord, book_id)
        record.catalog = False
        record.archived_at = datetime.now()
        db.session.commit()

    def test_delete_requires_archived_and_removes_associated_records_and_cover(self):
        cover = "book-cover.png"
        cover_path = Path(self.temp_dir.name) / cover
        cover_path.write_bytes(b"cover")
        book = self._book("Saved title", cover)
        db.session.add_all(
            [
                FavoriteRecord(user_id=self.patron.user_id, book_id=book.book_id),
                BasketRecord(user_id=self.patron.user_id, book_id=book.book_id),
                ReviewRecord(
                    user_id=self.patron.user_id,
                    book_id=book.book_id,
                    rating=5,
                    comment="Saved review",
                ),
            ]
        )
        db.session.commit()

        rejected = self._post(f"/books/{book.book_id}/delete")
        self.assertIn(b"Archive the book first.", rejected.data)
        self.assertIsNotNone(self.books.find_book(book.book_id))
        self.assertTrue(cover_path.exists())

        self._archive(book.book_id)
        deleted = self._post(f"/books/{book.book_id}/delete")
        self.assertIn(b"Book permanently deleted: Saved title", deleted.data)
        self.assertIsNone(self.books.find_book(book.book_id))
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count(FavoriteRecord.book_id)).where(
                    FavoriteRecord.book_id == book.book_id
                )
            ),
            0,
        )
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count(BasketRecord.book_id)).where(
                    BasketRecord.book_id == book.book_id
                )
            ),
            0,
        )
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count(ReviewRecord.review_id)).where(
                    ReviewRecord.book_id == book.book_id
                )
            ),
            0,
        )
        self.assertFalse(cover_path.exists())
        notice = db.session.execute(
            db.select(NotificationRecord).where(
                NotificationRecord.title == "Book permanently deleted"
            )
        ).scalar_one()
        self.assertIsNone(notice.link)
        self.assertEqual(
            db.session.scalar(
                db.select(db.func.count(NotificationRecord.notification_id)).where(
                    NotificationRecord.dedupe_key.like(
                        f"book:{book.book_id}:permanently-deleted:%"
                    )
                )
            ),
            1,
        )

    def test_deleted_book_preserves_loan_snapshot_and_fee_history(self):
        book = self._book("Snapshot title")
        record = LoanRecord(
            patron_id=self.patron.user_id,
            book_id=book.book_id,
            book_title=book.title,
            book_author=book.author,
            borrowed_at=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=16),
            returned_at=date.today() - timedelta(days=15),
            lost=True,
            loss_fee=2500,
            loss_paid=True,
        )
        db.session.add(record)
        db.session.flush()
        db.session.add(
            FeePaymentRecord(
                loan_id=record.loan_id,
                fee_type="loss",
                amount=2500,
                confirmed_at=datetime.now(),
            )
        )
        db.session.commit()
        self._archive(book.book_id)

        response = self._post(f"/books/{book.book_id}/delete")

        self.assertEqual(response.status_code, 200)
        migrated_loan = db.session.get(LoanRecord, record.loan_id)
        self.assertIsNone(migrated_loan.book_id)
        self.assertEqual(migrated_loan.book_title, "Snapshot title")
        self.assertEqual(migrated_loan.book_author, "Writer")
        fee = FeeRepository().lines_for_members([self.patron.user_id])[0]
        self.assertEqual(fee["book_title"], "Snapshot title")
        self.assertTrue(fee["deleted_book"])

    def test_archiving_keeps_the_book_and_loan_history(self):
        book = self._book("History stays")
        loan = LoanRecord(
            patron_id=self.patron.user_id,
            book_id=book.book_id,
            book_title=book.title,
            book_author=book.author,
            borrowed_at=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=16),
            returned_at=date.today() - timedelta(days=15),
        )
        db.session.add(loan)
        db.session.commit()

        response = self._post(f"/books/{book.book_id}/archive")

        self.assertIn(b"Book archived: History stays.", response.data)
        self.assertIsNotNone(self.books.find_book(book.book_id))
        self.assertFalse(self.books.find_book(book.book_id).catalog)
        self.assertEqual(db.session.get(LoanRecord, loan.loan_id).book_id, book.book_id)

    def test_active_loan_and_open_reservations_block_delete(self):
        for status in ("loan", "waiting", "ready"):
            book = self._book(f"Blocked {status}")
            self._archive(book.book_id)
            if status == "loan":
                db.session.add(
                    LoanRecord(
                        patron_id=self.patron.user_id,
                        book_id=book.book_id,
                        book_title=book.title,
                        book_author=book.author,
                        borrowed_at=date.today(),
                        due_date=date.today() + timedelta(days=14),
                    )
                )
            else:
                db.session.add(
                    ReservationRecord(
                        patron_id=self.patron.user_id,
                        book_id=book.book_id,
                        status=status,
                    )
                )
            db.session.commit()

            response = self._post(f"/books/{book.book_id}/delete")

            self.assertIn(b"Return the book or cancel the reservations first.", response.data)
            self.assertIsNotNone(self.books.find_book(book.book_id))
            db.session.execute(
                db.delete(LoanRecord).where(LoanRecord.book_id == book.book_id)
            )
            db.session.execute(
                db.delete(ReservationRecord).where(
                    ReservationRecord.book_id == book.book_id
                )
            )
            db.session.commit()

    def test_bulk_delete_is_atomic_and_routes_are_protected(self):
        first = self._book("Delete candidate")
        blocked = self._book("Reserved candidate")
        self._archive(first.book_id)
        self._archive(blocked.book_id)
        db.session.add(
            ReservationRecord(
                patron_id=self.patron.user_id,
                book_id=blocked.book_id,
                status="waiting",
            )
        )
        db.session.commit()

        response = self._post(
            "/books/delete-selected",
            {
                "ids[]": [str(first.book_id), str(blocked.book_id)],
                "confirm_text": "DELETE",
            },
        )

        self.assertIn(b"Reserved candidate", response.data)
        self.assertIsNotNone(self.books.find_book(first.book_id))
        self.assertIsNotNone(self.books.find_book(blocked.book_id))

        self._sign_in(self.patron)
        self.assertEqual(
            self._post(f"/books/{first.book_id}/delete").status_code,
            403,
        )
        missing_csrf = self.client.post(f"/books/{first.book_id}/delete", data={})
        self.assertEqual(missing_csrf.status_code, 302)
        self.assertIsNotNone(self.books.find_book(first.book_id))

    def test_bulk_delete_requires_exact_confirmation_phrase(self):
        book = self._book("Phrase protected")
        self._archive(book.book_id)

        rejected = self._post(
            "/books/delete-selected",
            {"ids[]": [str(book.book_id)], "confirm_text": "delete"},
        )
        self.assertIn(b"Type DELETE to confirm", rejected.data)
        self.assertIsNotNone(self.books.find_book(book.book_id))

        deleted = self._post(
            "/books/delete-selected",
            {"ids[]": [str(book.book_id)], "confirm_text": "DELETE"},
        )
        self.assertIn(b"1 book permanently deleted.", deleted.data)
        self.assertIsNone(self.books.find_book(book.book_id))

    def test_unconfirmed_delete_shows_standalone_confirmation_page(self):
        book = self._book("No script confirmation")
        self._archive(book.book_id)

        response = self.client.post(
            f"/books/{book.book_id}/delete",
            data={
                "csrf_token": self.token,
                "_confirm_title": f"Delete {book.title} permanently?",
                "_confirm_message": "Book details will be removed.",
                "_confirm_note": "This cannot be undone.",
                "_confirm_action": "Delete permanently",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Delete No script confirmation permanently?", response.data)
        self.assertIn(b'name="confirm_action" value="confirmed"', response.data)
        self.assertIsNotNone(self.books.find_book(book.book_id))


if __name__ == "__main__":
    unittest.main()
