import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app.exceptions import PermissionDenied, ValidationError
from backend.app.models.book import Book, NewReleaseBook, ReferenceBook
from backend.app.models.fine import LateFee, LossFee
from backend.app.models.librarian import Librarian
from backend.app.models.loan import Loan
from backend.app.models.patron import Patron
from backend.app.models.user import User


class BookModelTests(unittest.TestCase):
    def test_factory_creates_book_types_with_expected_loan_periods(self):
        standard = Book.create("standard", 1, "The Book", "A. Writer", "", "")
        new_release = Book.create("new_release", 2, "New", "B. Writer", "", "")
        reference = Book.create("reference", 3, "Guide", "C. Writer", "", "")

        self.assertIs(type(standard), Book)
        self.assertIsInstance(new_release, NewReleaseBook)
        self.assertIsInstance(reference, ReferenceBook)
        self.assertEqual(standard.loan_days, 14)
        self.assertEqual(new_release.loan_days, 7)
        self.assertFalse(reference.can_borrow())

    def test_book_validation_and_state_changes(self):
        with self.assertRaises(ValidationError):
            Book.create("unknown", None, "Book", "Author", "", "")
        with self.assertRaises(ValidationError):
            Book(None, "", "Author", "", "")

        book = Book(None, "Book", "Author", "", "")
        book.borrow()
        with self.assertRaises(ValidationError):
            book.archive()
        book.return_book()
        book.archive()
        self.assertFalse(book.can_borrow())

    def test_reference_book_cannot_be_borrowed(self):
        book = ReferenceBook(1, "Reference", "Author", "", "")
        with self.assertRaises(ValidationError):
            book.borrow()


class UserModelTests(unittest.TestCase):
    def test_factory_roles_permissions_and_account_management(self):
        password_hash = generate_password_hash("StrongPass1!")
        patron = User.create(1, "reader@example.com", "reader", password_hash, "patron")
        librarian = User.create(
            2, "staff@example.com", "staff", password_hash, "librarian"
        )

        self.assertIsInstance(patron, Patron)
        self.assertIsInstance(librarian, Librarian)
        self.assertTrue(patron.perms("borrow_book"))
        self.assertFalse(patron.perms("add_book"))
        with self.assertRaises(PermissionDenied):
            patron.require("add_book")
        self.assertTrue(patron.can_be_managed_by(librarian))
        self.assertFalse(librarian.can_be_managed_by(librarian))
        self.assertEqual(patron.loan_limit, 5)
        self.assertEqual(librarian.loan_limit, 0)

    def test_inactive_user_cannot_authenticate_or_use_permissions(self):
        user = Patron(1, "reader@example.com", "reader", "hash", active=False)

        self.assertFalse(user.check_pass("password"))
        self.assertFalse(user.perms("view_book"))

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValidationError):
            User.create(1, "x@example.com", "reader", "hash", "administrator")


class FeeAndLoanModelTests(unittest.TestCase):
    def setUp(self):
        self.due_date = date(2025, 1, 1)
        self.loan = Loan(1, 1, 1, self.due_date - timedelta(days=14), self.due_date)

    def test_late_fee_calculates_by_day_and_stops_at_return(self):
        today = self.due_date + timedelta(days=3)
        self.assertEqual(self.loan.calculate_late_fee(today), 1.5)
        self.loan.mark_returned(today)
        self.assertEqual(self.loan.calculate_late_fee(today + timedelta(days=9)), 1.5)

    def test_paying_fee_changes_outstanding_amount(self):
        returned = self.due_date + timedelta(days=2)
        self.loan.mark_returned(returned)

        self.assertEqual(self.loan.outstanding(), 1.0)
        self.assertEqual(self.loan.pay_late_fee(), 1.0)
        self.assertEqual(self.loan.outstanding(), 0.0)
        with self.assertRaises(ValidationError):
            self.loan.pay_late_fee()

    def test_lost_loan_closes_and_adds_loss_fee(self):
        self.loan.mark_lost(returned_at=self.due_date + timedelta(days=1))

        self.assertTrue(self.loan.lost)
        self.assertTrue(self.loan.is_returned())
        self.assertEqual(self.loan.outstanding(), 25.0)
        self.assertEqual(self.loan.pay_loss_fee(), 25.0)
        self.assertEqual(self.loan.outstanding(), 0.0)

    def test_fee_classes_report_amounts_and_paid_status(self):
        fee = LateFee(daily_fee=0.75)
        self.assertEqual(fee.amount(self.loan, self.due_date + timedelta(days=4)), 3.0)
        fee.pay()
        self.assertEqual(fee.outstanding(self.loan, self.due_date + timedelta(days=4)), 0)
        self.assertEqual(LossFee(10).amount(self.loan, date.today()), 10)


if __name__ == "__main__":
    unittest.main()