import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import NotFoundError, PermissionDenied, ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.book_service import BookService
from backend.app.services.librarian_service import LibrarianService
from backend.app.services.loan_service import LoanService


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

        changed = self.book_service.edit_book(
            self.librarian, book.book_id, "Revised", "B. Writer", "Drama", ""
        )
        self.assertEqual(changed.title, "Revised")
        self.book_service.archive_book(self.librarian, book.book_id)
        self.assertEqual(self.book_service.search_books(), [])

    def test_patron_borrow_return_and_reference_restrictions(self):
        book = self.books.create(Book(None, "Available", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)

        self.assertEqual(loan.patron_id, self.patron.user_id)
        self.assertFalse(self.books.find_book(book.book_id).available)
        with self.assertRaises(ValidationError):
            self.loan_service.borrow_book(self.patron, book.book_id)

        returned = self.loan_service.return_book(self.patron, book.book_id)
        self.assertTrue(returned.is_returned())
        self.assertTrue(self.books.find_book(book.book_id).available)

        reference = self.book_service.add_book(
            self.librarian, "Reference", "Writer", "", "", "reference"
        )
        with self.assertRaises(ValidationError):
            self.loan_service.borrow_book(self.patron, reference.book_id)

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

    def test_paid_late_fee_is_persisted(self):
        book = self.books.create(Book(None, "Overdue", "Writer", "", ""))
        today = date.today()
        loan = self.loans.create_loan(
            self.patron.user_id,
            book.book_id,
            today - timedelta(days=20),
            today - timedelta(days=6),
        )
        loan.mark_returned(today)
        self.loans.update_loan(loan)

        self.assertEqual(self.loan_service.pay_late_fee(self.patron, loan.loan_id), 3.0)
        saved = self.loans.find_loan(loan.loan_id)
        self.assertEqual(saved.outstanding(today), 0.0)
        self.assertTrue(saved.fee_breakdown(today)[0]["paid"])

    def test_librarian_lost_return_closes_loan_and_removes_book_from_catalog(self):
        book = self.books.create(Book(None, "Lost book", "Writer", "", ""))
        loan = self.loan_service.borrow_book(self.patron, book.book_id)

        updated_loan = self.librarian_service.update_return_status(
            self.librarian, book.book_id, lost=True
        )
        updated_book = self.books.find_book(book.book_id)

        self.assertEqual(updated_loan.loan_id, loan.loan_id)
        self.assertTrue(updated_loan.is_returned())
        self.assertTrue(updated_loan.lost)
        self.assertEqual(updated_loan.outstanding(), 25.0)
        self.assertIsNone(self.loans.find_active_loan_by_book(book.book_id))
        self.assertFalse(updated_book.available)
        self.assertFalse(updated_book.catalog)

    def test_librarian_can_toggle_patron_account(self):
        deactivated = self.librarian_service.manage_member(
            self.librarian, self.patron.user_id, active=False
        )
        self.assertFalse(deactivated.active)
        reactivated = self.librarian_service.manage_member(
            self.librarian, self.patron.user_id
        )
        self.assertTrue(reactivated.active)


if __name__ == "__main__":
    unittest.main()