import re
import random
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.reservation_record import ReservationRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.reservation_repository import ReservationRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.book_service import BookService
from backend.app.services.loan_service import LoanService


class StockManagementTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "stock-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.loans = LoanRepository()
        self.reservations = ReservationRepository()
        self.users = UserRepository()
        self.book_service = BookService(self.books, self.reservations)
        self.loan_service = LoanService(
            self.books,
            self.loans,
            self.reservations,
        )
        self.librarian = self._create_user("staff", "librarian")
        self.patrons = [
            self._create_user(f"reader{index}", "patron")
            for index in range(1, 5)
        ]

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

    def test_multiple_copies_are_borrowed_and_availability_is_derived(self):
        book = self.books.create(
            Book(None, "Shared Shelf", "A. Writer", "History", "", total_copies=3)
        )
        self.assertEqual(book.available_copies, 3)

        self.loan_service.borrow_book(self.patrons[0], book.book_id)
        self.loan_service.borrow_book(self.patrons[1], book.book_id)
        self.assertEqual(self.books.find_book(book.book_id).available_copies, 1)

        self.loan_service.borrow_book(self.patrons[2], book.book_id)
        unavailable = self.books.find_book(book.book_id)
        self.assertEqual(unavailable.available_copies, 0)
        self.assertEqual(unavailable.on_loan_copies, 3)
        self.assertEqual(unavailable.availability_status, "On loan")
        self.assertEqual(self.books.search(status="available")[0], [])
        self.assertEqual(
            self.books.search(status="on_loan")[0][0].book_id,
            book.book_id,
        )

        with self.assertRaises(ValidationError):
            self.loan_service.borrow_book(self.patrons[3], book.book_id)

        self.loan_service.return_book(self.patrons[0], book.book_id)
        self.assertEqual(self.books.find_book(book.book_id).available_copies, 1)

    def test_return_promotes_reservation_and_reserved_copy_can_be_borrowed(self):
        book = self.books.create(
            Book(None, "Popular Shelf", "B. Writer", "Drama", "", total_copies=2)
        )
        self.loan_service.borrow_book(self.patrons[0], book.book_id)
        self.loan_service.borrow_book(self.patrons[1], book.book_id)
        reservation = self.loan_service.reserve_book(self.patrons[2], book.book_id)
        self.assertEqual(reservation.status, "waiting")

        self.loan_service.return_book(self.patrons[0], book.book_id)

        ready = self.reservations.find_for_patron_book(
            self.patrons[2].user_id,
            book.book_id,
        )
        self.assertEqual(ready.status, "ready")
        self.loan_service.reserve_book(self.patrons[3], book.book_id)
        self.loan_service.return_book(self.patrons[1], book.book_id)
        held = self.books.find_book(book.book_id)
        self.assertEqual(held.available_copies, 0)
        self.assertEqual(held.reserved_copies, 2)

        loan = self.loan_service.borrow_book(self.patrons[2], book.book_id)
        second_loan = self.loan_service.borrow_book(self.patrons[3], book.book_id)

        self.assertEqual(loan.patron_id, self.patrons[2].user_id)
        self.assertEqual(second_loan.patron_id, self.patrons[3].user_id)
        fulfilled = db.session.execute(
            db.select(ReservationRecord).where(
                ReservationRecord.patron_id == self.patrons[2].user_id,
                ReservationRecord.book_id == book.book_id,
            )
        ).scalar_one()
        self.assertEqual(fulfilled.status, "fulfilled")
        stocked = self.books.find_book(book.book_id)
        self.assertEqual(stocked.on_loan_copies, 2)
        self.assertEqual(stocked.reserved_copies, 0)

    def test_stock_edits_cannot_remove_allocated_copies_and_promote_waiters(self):
        book = self.books.create(
            Book(None, "Restocked Shelf", "C. Writer", "Poetry", "", total_copies=1)
        )
        self.loan_service.borrow_book(self.patrons[0], book.book_id)
        self.loan_service.reserve_book(self.patrons[1], book.book_id)

        with self.assertRaisesRegex(ValidationError, "on loan or reserved"):
            self.book_service.edit_book(
                self.librarian,
                book.book_id,
                book.title,
                book.author,
                book.genre,
                book.description,
                total_copies=0,
            )

        self.book_service.edit_book(
            self.librarian,
            book.book_id,
            book.title,
            book.author,
            book.genre,
            book.description,
            total_copies=2,
        )

        self.assertEqual(self.books.find_book(book.book_id).total_copies, 2)
        self.assertEqual(
            self.reservations.find_for_patron_book(
                self.patrons[1].user_id,
                book.book_id,
            ).status,
            "ready",
        )
        with self.assertRaisesRegex(ValidationError, "on loan or reserved"):
            self.book_service.edit_book(
                self.librarian,
                book.book_id,
                book.title,
                book.author,
                book.genre,
                book.description,
                total_copies=1,
            )

    def test_stock_counts_require_nonnegative_whole_numbers(self):
        for value in ("-1", "1.5", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.book_service.add_book(
                    self.librarian,
                    "Invalid stock",
                    f"Writer {value}",
                    "History",
                    "",
                    total_copies=value,
                )

    def test_marking_one_copy_lost_preserves_other_copies(self):
        book = self.books.create(
            Book(None, "Two-Copy Shelf", "D. Writer", "Mystery", "", total_copies=2)
        )
        first = self.loan_service.borrow_book(self.patrons[0], book.book_id)
        second = self.loan_service.borrow_book(self.patrons[1], book.book_id)

        self.loan_service.process_return(self.librarian, first.loan_id, lost=True)

        remaining = self.books.find_book(book.book_id)
        self.assertTrue(remaining.catalog)
        self.assertEqual(remaining.total_copies, 1)
        self.assertEqual(remaining.on_loan_copies, 1)
        self.loan_service.process_return(self.librarian, second.loan_id, lost=True)
        self.assertFalse(self.books.find_book(book.book_id).catalog)
        self.assertEqual(self.books.find_book(book.book_id).total_copies, 0)

    def test_randomized_inventory_lifecycle_preserves_stock_invariant(self):
        rng = random.Random(6206)
        patrons = self.patrons + [
            self._create_user(f"random-reader{index}", "patron")
            for index in range(5, 9)
        ]
        books = [
            self.books.create(
                Book(
                    None,
                    f"Random Shelf {index}",
                    f"Writer {index}",
                    "Fiction",
                    "",
                    total_copies=rng.randint(2, 4),
                )
            )
            for index in range(4)
        ]
        coverage_book = self.books.create(
            Book(None, "Coverage Shelf", "Random Writer", "Fiction", "", total_copies=3)
        )
        books.append(coverage_book)
        expected_actions = {"borrow", "return", "lost", "reserve", "archive", "restore"}
        exercised_actions = set()

        def assert_invariant():
            for original in books:
                book = self.books.find_book(original.book_id)
                self.assertEqual(
                    book.total_copies,
                    book.on_loan_copies
                    + book.reserved_copies
                    + book.available_copies,
                    f"Inventory invariant failed for {book.title}",
                )

        def perform(action, book, subject=None):
            if action == "borrow":
                self.loan_service.borrow_book(subject, book.book_id)
            elif action == "return":
                self.loan_service.return_book(subject, book.book_id)
            elif action == "lost":
                self.loan_service.process_return(
                    self.librarian,
                    subject.loan_id,
                    lost=True,
                )
            elif action == "reserve":
                self.loan_service.reserve_book(subject, book.book_id)
            elif action == "archive":
                self.book_service.archive_book(self.librarian, book.book_id)
            else:
                self.book_service.restore_book(self.librarian, book.book_id)
            exercised_actions.add(action)
            assert_invariant()

        borrowers = rng.sample(patrons, 4)
        for patron in borrowers[:3]:
            perform("borrow", coverage_book, patron)
        perform("reserve", coverage_book, borrowers[3])
        perform("return", coverage_book, borrowers[0])
        perform("borrow", coverage_book, borrowers[3])
        lost_loan = self.loans.find_active_loan(
            borrowers[1].user_id,
            coverage_book.book_id,
        )
        perform("lost", coverage_book, lost_loan)
        perform("return", coverage_book, borrowers[2])
        perform("return", coverage_book, borrowers[3])
        perform("archive", coverage_book)
        perform("restore", coverage_book)

        for step in range(150):
            candidates = []
            for original in books:
                book = self.books.find_book(original.book_id)
                active_loans = self.loans.find_active_loans_by_book(book.book_id)
                if book.catalog:
                    for patron in patrons:
                        patron_loans = self.loans.find_patron_loans(
                            patron.user_id
                        )
                        can_transact = (
                            not any(
                                loan.outstanding(date.today()) > 0
                                for loan in patron_loans
                            )
                            and sum(
                                not loan.is_returned() for loan in patron_loans
                            )
                            + self.reservations.count_open_for_patron(
                                patron.user_id
                            )
                            < patron.loan_limit
                        )
                        if (
                            can_transact
                            and book.available_copies > 0
                            and self.loans.find_active_loan(
                                patron.user_id, book.book_id
                            )
                            is None
                            and self.reservations.find_for_patron_book(
                                patron.user_id, book.book_id
                            )
                            is None
                        ):
                            candidates.append(("borrow", book, patron))
                        if (
                            can_transact
                            and book.total_copies > 0
                            and book.available_copies == 0
                            and self.loans.find_active_loan(
                                patron.user_id, book.book_id
                            )
                            is None
                            and self.reservations.find_for_patron_book(
                                patron.user_id, book.book_id
                            )
                            is None
                        ):
                            candidates.append(("reserve", book, patron))
                    if (
                        not active_loans
                        and book.reserved_copies == 0
                        and self.reservations.waiting_count(book.book_id) == 0
                    ):
                        candidates.append(("archive", book, None))
                elif book.total_copies > 0:
                    candidates.append(("restore", book, None))

                for loan in active_loans:
                    patron = next(
                        patron
                        for patron in patrons
                        if patron.user_id == loan.patron_id
                    )
                    candidates.append(("return", book, patron))
                    candidates.append(("lost", book, loan))

            if not candidates:
                break

            action, book, subject = rng.choice(candidates)
            perform(action, book, subject)
            if step >= 59 and expected_actions.issubset(exercised_actions):
                break

        self.assertEqual(exercised_actions, expected_actions)

    def test_stale_competing_loan_cannot_exceed_stock(self):
        book = self.books.create(
            Book(None, "Single Copy Shelf", "E. Writer", "Fiction", "", total_copies=1)
        )
        stale = self.books.find_book(book.book_id)
        today = date.today()

        self.loans.create_loan(
            self.patrons[0].user_id,
            book.book_id,
            today,
            today + timedelta(days=14),
        )
        with self.assertRaises(ValidationError):
            self.loans.create_loan(
                self.patrons[1].user_id,
                stale.book_id,
                today,
                today + timedelta(days=14),
            )
        self.assertEqual(len(self.loans.find_active_loans_by_book(book.book_id)), 1)

    def test_librarian_add_and_edit_forms_expose_copy_count(self):
        login = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login.data,
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = self.librarian.user_id
            session["username"] = self.librarian.username
            session["role"] = self.librarian.role

        add_page = self.client.get("/books/new")
        self.assertIn(b'name="total_copies"', add_page.data)
        created = self.client.post(
            "/books/new",
            data={
                "csrf_token": token,
                "title": "Stock Form",
                "author": "F. Writer",
                "genre": "History",
                "description": "",
                "kind": "standard",
                "total_copies": "4",
            },
        )
        self.assertEqual(created.status_code, 302)
        book = self.books.find_by_title_author("Stock Form", "F. Writer")
        self.assertEqual(book.total_copies, 4)

        edit_page = self.client.get(f"/books/{book.book_id}/edit")
        self.assertIn(b'name="total_copies"', edit_page.data)
        updated = self.client.post(
            f"/books/{book.book_id}/edit",
            data={
                "csrf_token": token,
                "title": book.title,
                "author": book.author,
                "genre": book.genre,
                "description": book.description,
                "kind": book.kind,
                "total_copies": "5",
            },
        )
        self.assertEqual(updated.status_code, 302)
        self.assertEqual(self.books.find_book(book.book_id).total_copies, 5)


if __name__ == "__main__":
    unittest.main()
