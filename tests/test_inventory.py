import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.loan_service import LoanService


class InventoryLoanTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "inventory-test",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.books = BookRepository()
        self.loans = LoanRepository()
        self.users = UserRepository()
        self.loan_service = LoanService(self.books, self.loans)
        self.patron = self._create_patron("reader")
        self.other_patron = self._create_patron("other-reader")
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

    def _create_patron(self, username):
        return self.users.create(
            f"{username}@example.com",
            username,
            generate_password_hash("StrongPass1!"),
            "patron",
        )

    def _create_book(self, stock=1, kind="standard"):
        return self.books.create(
            Book(
                None,
                "Inventory title",
                "A. Writer",
                "Fiction",
                "",
                total_stock=stock,
            )
            if kind == "standard"
            else Book.create(
                kind,
                None,
                "Inventory title",
                "A. Writer",
                "Fiction",
                "",
                total_stock=stock,
            )
        )

    def test_multiple_copies_are_counted_and_return_frees_one_copy(self):
        book = self._create_book(stock=2)

        self.loan_service.borrow_book(self.patron, book.book_id)
        self.loan_service.borrow_book(self.other_patron, book.book_id)

        exhausted = self.books.find_book(book.book_id)
        self.assertEqual(exhausted.total_stock, 2)
        self.assertEqual(exhausted.borrowed_stock, 2)
        self.assertEqual(exhausted.available_stock, 0)
        self.assertFalse(exhausted.available)
        third_patron = self._create_patron("third")
        with self.assertRaisesRegex(ValidationError, "no copies in stock"):
            self.loan_service.borrow_book(third_patron, book.book_id)

        self.loan_service.return_book(self.patron, book.book_id)
        available = self.books.find_book(book.book_id)
        self.assertEqual(available.borrowed_stock, 1)
        self.assertEqual(available.available_stock, 1)
        self.assertTrue(available.available)

        self.loan_service.borrow_book(third_patron, book.book_id)
        self.assertEqual(self.books.find_book(book.book_id).borrowed_stock, 2)

    def test_reference_and_archived_books_cannot_be_borrowed(self):
        reference = self._create_book(stock=2, kind="reference")
        with self.assertRaisesRegex(ValidationError, "Reference books"):
            self.loan_service.borrow_book(self.patron, reference.book_id)

        archived = self._create_book(stock=2)
        archived.archive()
        self.books.update_book(archived)
        with self.assertRaisesRegex(ValidationError, "no longer in the catalog"):
            self.loan_service.borrow_book(self.patron, archived.book_id)

    def test_stock_cannot_be_reduced_below_active_loans_but_can_be_increased(self):
        book = self._create_book(stock=2)
        self.loan_service.borrow_book(self.patron, book.book_id)
        current = self.books.find_book(book.book_id)

        with self.assertRaisesRegex(ValidationError, "cannot be lower"):
            current.set_total_stock(0)

        current.set_total_stock(3)
        self.books.update_book(current)
        updated = self.books.find_book(book.book_id)
        self.assertEqual(updated.total_stock, 3)
        self.assertEqual(updated.borrowed_stock, 1)
        self.assertEqual(updated.available_stock, 2)

    def test_lost_copy_reduces_stock_without_hiding_remaining_copies(self):
        book = self._create_book(stock=2)
        loan = self.loan_service.borrow_book(self.patron, book.book_id)

        self.loan_service.process_return_loan(self.librarian, loan.loan_id, lost=True)

        remaining = self.books.find_book(book.book_id)
        self.assertEqual(remaining.total_stock, 1)
        self.assertEqual(remaining.available_stock, 1)
        self.assertTrue(remaining.catalog)
        self.assertTrue(remaining.available)
        self.loan_service.borrow_book(self.other_patron, book.book_id)

    def test_overdue_status_days_filters_summary_and_return_are_consistent(self):
        book = self._create_book()
        yesterday = date.today() - timedelta(days=1)
        loan = self.loans.create_loan(
            self.patron.user_id,
            book.book_id,
            yesterday - timedelta(days=14),
            yesterday,
        )

        card = self.loan_service.loan_detail_card(self.librarian, loan.loan_id)
        self.assertEqual(card["status"], "Overdue")
        self.assertEqual(card["days_overdue"], 1)

        filtered = self.loan_service.management_cards(
            self.librarian,
            search="inventory",
            status="overdue",
            member_id=self.patron.user_id,
            book_id=book.book_id,
        )
        self.assertEqual([item["loan"].loan_id for item in filtered], [loan.loan_id])
        self.assertEqual(filtered[0]["days_overdue"], 1)
        self.assertEqual(
            self.loan_service.management_summary(self.librarian)["overdue"], 1
        )

        self.loan_service.process_return_loan(self.librarian, loan.loan_id)
        returned = self.loan_service.loan_detail_card(self.patron, loan.loan_id)
        self.assertEqual(returned["status"], "Returned")
        self.assertEqual(self.books.find_book(book.book_id).available_stock, 1)

    def test_librarian_can_issue_a_loan_with_valid_dates(self):
        book = self._create_book(stock=2)
        borrowed_at = date.today() - timedelta(days=2)
        due_date = date.today() + timedelta(days=12)

        loan = self.loan_service.issue_for_patron(
            self.librarian,
            self.patron.user_id,
            book.book_id,
            borrowed_at.isoformat(),
            due_date.isoformat(),
        )

        self.assertEqual(loan.patron_id, self.patron.user_id)
        self.assertEqual(loan.borrowed_at, borrowed_at)
        self.assertEqual(loan.due_date, due_date)
        self.assertEqual(self.books.find_book(book.book_id).borrowed_stock, 1)

        with self.assertRaisesRegex(ValidationError, "due date must be after"):
            self.loan_service.issue_for_patron(
                self.librarian,
                self.other_patron.user_id,
                book.book_id,
                date.today().isoformat(),
                date.today().isoformat(),
            )


if __name__ == "__main__":
    unittest.main()
