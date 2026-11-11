import unittest
import io
import tempfile
from datetime import date, timedelta
from pathlib import Path

from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import NotFoundError, PermissionDenied, ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.notification_repository import NotificationRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.book_service import BookService
from backend.app.services.auth_service import AuthService
from backend.app.services.librarian_service import LibrarianService
from backend.app.services.loan_service import LoanService
from backend.app.repositories.notification_repository import NotificationRepository
from backend.app.services.notification_service import NotificationService


class BackendServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "service-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.books = BookRepository()
        self.loans = LoanRepository()
        self.users = UserRepository()
        self.book_service = BookService(self.books)
        self.loan_service = LoanService(self.books, self.loans)
        self.librarian_service = LibrarianService(self.books, self.loans, self.users)
        self.patron = self.users.create(
            "reader@example.com",
            "reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
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

    def test_librarian_can_create_search_edit_and_archive_books(self):
        book = self.book_service.add_book(
            self.librarian, "The Archive", "A. Author", "History", "A description"
        )
        matches = self.book_service.search_books("archive author")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].book_id, book.book_id)
        book_notifications = NotificationRepository().for_user(
            self.librarian.user_id
        )
        self.assertEqual(book_notifications[0].title, "Book added to the catalog")

        changed = self.book_service.edit_book(
            self.librarian, book.book_id, "Revised", "B. Writer", "Drama", ""
        )
        self.assertEqual(changed.title, "Revised")
        self.assertEqual(
            NotificationRepository().for_user(self.librarian.user_id)[0].title,
            "Book details updated",
        )
        self.book_service.archive_book(self.librarian, book.book_id)
        self.assertEqual(
            NotificationRepository().for_user(self.librarian.user_id)[0].title,
            "Book archived",
        )
        self.assertEqual(self.book_service.search_books(), [])

    def test_book_cover_upload_is_saved_and_replaced_safely(self):
        upload_directory = tempfile.TemporaryDirectory()
        self.addCleanup(upload_directory.cleanup)
        self.app.config["COVER_UPLOAD_FOLDER"] = upload_directory.name
        initial_cover = FileStorage(
            stream=io.BytesIO(b"\xff\xd8\xffjpeg-data"),
            filename="../../first-cover.JPG",
        )

        book = self.book_service.add_book(
            self.librarian,
            "Cover book",
            "Writer",
            "Drama",
            "",
            cover_file=initial_cover,
        )

        saved_path = Path(upload_directory.name) / book.cover
        self.assertTrue(saved_path.is_file())
        self.assertEqual(saved_path.read_bytes(), b"\xff\xd8\xffjpeg-data")
        self.assertEqual(Path(book.cover).name, book.cover)

        self.book_service.edit_book(
            self.librarian,
            book.book_id,
            "Cover book",
            "Writer",
            "Drama",
            "",
        )
        self.assertEqual(self.books.find_book(book.book_id).cover, book.cover)

        replacement = FileStorage(
            stream=io.BytesIO(b"\x89PNG\r\n\x1a\nimage-data"),
            filename="replacement.png",
        )
        edited = self.book_service.edit_book(
            self.librarian,
            book.book_id,
            "Cover book",
            "Writer",
            "Drama",
            "",
            replacement,
        )
        self.assertNotEqual(edited.cover, book.cover)
        self.assertFalse(saved_path.exists())
        self.assertTrue((Path(upload_directory.name) / edited.cover).is_file())

    def test_cover_upload_rejects_unsupported_type_bad_signature_and_oversize(self):
        from backend.app.services.cover_service import CoverService

        service = CoverService()
        with self.assertRaises(ValidationError):
            service.save(FileStorage(stream=io.BytesIO(b"bad"), filename="cover.gif"))
        with self.assertRaises(ValidationError):
            service.save(FileStorage(stream=io.BytesIO(b"not-a-jpeg"), filename="cover.jpg"))
        with self.assertRaises(ValidationError):
            service.save(
                FileStorage(
                    stream=io.BytesIO(b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024)),
                    filename="large.jpg",
                )
            )

    def test_librarian_can_restore_archived_book(self):
        book = self.books.create(Book(None, "Archived", "Writer", "", ""))
        self.book_service.archive_book(self.librarian, book.book_id)

        archived = self.book_service.archived_books(self.librarian)
        restored = self.book_service.restore_book(self.librarian, book.book_id)

        self.assertEqual([item.book_id for item in archived], [book.book_id])
        self.assertTrue(restored.catalog)
        self.assertEqual(self.book_service.archived_books(self.librarian), [])

    def test_archived_books_view_excludes_lost_books(self):
        archived = self.books.create(Book(None, "Archived", "Writer", "", ""))
        lost = self.books.create(Book(None, "Lost", "Writer", "", ""))
        self.book_service.archive_book(self.librarian, archived.book_id)
        lost.mark_lost()
        self.books.update_book(lost)

        listed = self.book_service.archived_books(self.librarian)

        self.assertEqual([book.book_id for book in listed], [archived.book_id])

    def test_patron_cannot_restore_archived_book(self):
        book = self.books.create(Book(None, "Archived", "Writer", "", ""))
        self.book_service.archive_book(self.librarian, book.book_id)

        with self.assertRaises(PermissionDenied):
            self.book_service.restore_book(self.patron, book.book_id)

    def test_patron_borrow_return_and_reference_restrictions(self):
        book = self.books.create(Book(None, "Available", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)

        self.assertEqual(loan.patron_id, self.patron.user_id)
        self.assertFalse(self.books.find_book(book.book_id).available)
        self.assertEqual(
            NotificationRepository().for_user(self.patron.user_id)[0].title,
            "Book borrowed",
        )
        with self.assertRaises(ValidationError):
            self.loan_service.borrow_book(self.patron, book.book_id)

        returned = self.loan_service.return_book(self.patron, book.book_id)
        self.assertTrue(returned.is_returned())
        self.assertTrue(self.books.find_book(book.book_id).available)
        self.assertEqual(
            NotificationRepository().for_user(self.patron.user_id)[0].title,
            "Book returned",
        )

        reference = self.book_service.add_book(
            self.librarian, "Reference", "Writer", "", "", "reference"
        )
        with self.assertRaises(ValidationError):
            self.loan_service.borrow_book(self.patron, reference.book_id)

    def test_reservation_queue_promotes_fifo_and_ready_patron_can_borrow(self):
        book = self.books.create(Book(None, "Popular book", "Writer", "", ""))
        borrower = self.users.create(
            "borrower@example.com",
            "borrower",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        next_patron = self.users.create(
            "next@example.com",
            "next",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        last_patron = self.users.create(
            "last@example.com",
            "last",
            generate_password_hash("StrongPass1!"),
            "patron",
        )

        self.loan_service.borrow_book(borrower, book.book_id)
        first_reservation = self.loan_service.reserve_book(
            next_patron, book.book_id
        )
        second_reservation = self.loan_service.reserve_book(
            last_patron, book.book_id
        )
        self.loan_service.return_book(borrower, book.book_id)

        self.assertEqual(first_reservation.status, "waiting")
        self.assertEqual(second_reservation.status, "waiting")
        first_status = self.loan_service.reservation_status(
            next_patron, book.book_id
        )
        self.assertTrue(first_status["ready_for_patron"])
        self.assertEqual(first_status["waiting_count"], 1)
        with self.assertRaisesRegex(ValidationError, "reserved for a patron"):
            self.book_service.archive_book(self.librarian, book.book_id)

        self.loan_service.borrow_book(next_patron, book.book_id)
        self.assertFalse(self.books.find_book(book.book_id).available)
        self.assertEqual(
            self.loan_service.reservation_status(
                last_patron, book.book_id
            )["own_reservation"].status,
            "waiting",
        )

        self.loan_service.return_book(next_patron, book.book_id)
        self.assertTrue(
            self.loan_service.reservation_status(
                last_patron, book.book_id
            )["ready_for_patron"]
        )

    def test_reservations_consume_the_patron_loan_limit(self):
        other_patron = self.users.create(
            "other-reader@example.com",
            "other-reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        active_books = [
            self.books.create(Book(None, f"Active {index}", "Writer", "", ""))
            for index in range(self.patron.loan_limit - 1)
        ]
        for book in active_books:
            self.loan_service.borrow_book(self.patron, book.book_id)

        first_waiting_book = self.books.create(
            Book(None, "Waiting one", "Writer", "", "")
        )
        second_waiting_book = self.books.create(
            Book(None, "Waiting two", "Writer", "", "")
        )
        self.loan_service.borrow_book(other_patron, first_waiting_book.book_id)
        self.loan_service.borrow_book(other_patron, second_waiting_book.book_id)
        self.loan_service.reserve_book(self.patron, first_waiting_book.book_id)

        with self.assertRaisesRegex(ValidationError, "borrow or reserve"):
            self.loan_service.reserve_book(self.patron, second_waiting_book.book_id)

    def test_due_date_notifications_are_staged_and_deduplicated(self):
        book = self.books.create(Book(None, "Due soon", "Writer", "", ""))
        today = date.today()
        loan = self.loans.create_loan(
            self.patron.user_id,
            book.book_id,
            today,
            today + timedelta(days=3),
        )
        service = NotificationService(NotificationRepository(), self.loans)

        service.sync_due_date_reminders(self.patron.user_id)
        service.sync_due_date_reminders(self.patron.user_id)
        due_soon = NotificationRepository().for_user(self.patron.user_id)
        self.assertEqual(len(due_soon), 1)
        self.assertEqual(due_soon[0].title, "Book due soon")

        loan.mark_returned(today)
        self.loans.update_loan(loan)
        service.sync_due_date_reminders(self.patron.user_id)
        self.assertEqual(len(NotificationRepository().for_user(self.patron.user_id)), 1)

    def test_patron_cannot_create_book_or_access_another_users_loan(self):
        with self.assertRaises(PermissionDenied):
            self.book_service.add_book(self.patron, "Book", "Writer", "", "")

        book = self.books.create(Book(None, "Available", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)
        other_patron = self.users.create(
            "other@example.com",
            "other",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        with self.assertRaises(NotFoundError):
            self.loan_service.view_payments(other_patron, loan.loan_id)

    def test_librarian_lost_return_closes_loan_and_removes_book_from_catalog(self):
        book = self.books.create(Book(None, "Lost book", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)
        waiting_patron = self.users.create(
            "waiting@example.com",
            "waiting",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self.loan_service.reserve_book(waiting_patron, book.book_id)

        updated_loan = self.librarian_service.update_return_status(
            self.librarian, book.book_id, lost=True
        )
        updated_book = self.books.find_book(book.book_id)

        self.assertEqual(updated_loan.loan_id, loan.loan_id)
        self.assertTrue(updated_loan.is_returned())
        self.assertTrue(updated_loan.lost)
        self.assertEqual(updated_loan.outstanding(), 2500.0)
        self.assertIsNone(self.loans.find_active_loan_by_book(book.book_id))
        self.assertFalse(updated_book.available)
        self.assertFalse(updated_book.catalog)
        self.assertEqual(
            self.loan_service.reservations_for(waiting_patron),
            [],
        )

    def test_librarian_can_toggle_patron_account(self):
        deactivated = self.librarian_service.manage_member(
            self.librarian, self.patron.user_id, active=False
        )
        self.assertFalse(deactivated.active)
        reactivated = self.librarian_service.manage_member(
            self.librarian, self.patron.user_id
        )
        self.assertTrue(reactivated.active)

    def test_librarian_can_reset_patron_password_with_strong_random_password(self):
        temporary_password = self.librarian_service.reset_member_password(
            self.librarian,
            self.patron.user_id,
        )

        self.assertEqual(len(temporary_password), 16)
        self.assertEqual(AuthService.pass_strength(temporary_password)[0], 5)
        saved_patron = self.users.find_by_id(self.patron.user_id)
        self.assertTrue(saved_patron.check_pass(temporary_password))
        self.assertNotEqual(saved_patron.password_hash, temporary_password)

    def test_patron_cannot_reset_member_password(self):
        with self.assertRaises(PermissionDenied):
            self.librarian_service.reset_member_password(
                self.patron,
                self.patron.user_id,
            )

    def test_librarian_can_search_and_create_patron(self):
        matches = self.librarian_service.find_members(self.librarian, "reader@")
        self.assertEqual([member.user_id for member in matches], [self.patron.user_id])

        created = self.librarian_service.create_patron(
            self.librarian,
            "new-reader@example.com",
            "new-reader",
            "StrongPass1!",
            "StrongPass1!",
        )

        self.assertTrue(created.is_patron())
        self.assertEqual(
            [member.username for member in self.librarian_service.find_members(self.librarian, "new-reader")],
            ["new-reader"],
        )

    def test_patron_cannot_create_a_patron_account(self):
        with self.assertRaises(PermissionDenied):
            self.librarian_service.create_patron(
                self.patron,
                "new-reader@example.com",
                "new-reader",
                "StrongPass1!",
                "StrongPass1!",
            )

    def test_librarian_can_view_member_loan_history_with_book_titles(self):
        book = self.books.create(Book(None, "History title", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)

        member, history = self.librarian_service.member_loan_history(
            self.librarian,
            self.patron.user_id,
        )

        self.assertEqual(member.user_id, self.patron.user_id)
        self.assertEqual(history[0]["loan"].loan_id, loan.loan_id)
        self.assertEqual(history[0]["book_title"], "History title")
        self.assertEqual(history[0]["outstanding"], 0)


if __name__ == "__main__":
    unittest.main()