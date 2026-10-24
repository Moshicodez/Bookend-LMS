import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.loan_record import LoanRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.user_repository import UserRepository


class BorrowBasketTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "basket-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.loans = LoanRepository()
        self.patron = UserRepository().create(
            "reader@example.com",
            "reader",
            generate_password_hash("StrongPass1!"),
            "patron",
        )
        self.first = self.books.create(
            Book(None, "Basket Book One", "A. Writer", "History", "")
        )
        self.second = self.books.create(
            Book(None, "Basket Book Two", "B. Writer", "Drama", "")
        )
        self.reference = self.books.create(
            Book.create(
                "reference",
                None,
                "Reading Room Atlas",
                "R. Librarian",
                "Reference",
                "",
            )
        )
        self.csrf_token = self._sign_in()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _sign_in(self):
        page = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"', page.data
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = self.patron.user_id
            session["username"] = self.patron.username
            session["role"] = self.patron.role
        return token

    def _post(self, path, data=None):
        return self.client.post(
            path,
            data={"csrf_token": self.csrf_token, **(data or {})},
        )

    def _set_basket(self, book_ids):
        with self.client.session_transaction() as session:
            session["basket_book_ids"] = list(book_ids)

    def test_basket_add_remove_duplicate_and_limit_validation(self):
        added = self._post(f"/basket/add/{self.first.book_id}")
        self.assertEqual(added.status_code, 302)
        duplicate = self._post(f"/basket/add/{self.first.book_id}")
        self.assertEqual(duplicate.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["basket_book_ids"], [self.first.book_id])

        basket = self.client.get("/basket")
        self.assertEqual(basket.status_code, 200)
        self.assertIn(b"Select all", basket.data)
        self.assertIn(b"Confirm borrowing", basket.data)
        self.assertIn(b"Due", basket.data)

        removed = self._post(
            "/basket/remove",
            {"book_ids": str(self.first.book_id)},
        )
        self.assertEqual(removed.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["basket_book_ids"], [])

        active_books = [
            self.books.create(Book(None, f"Current {index}", "Writer", "", ""))
            for index in range(self.patron.loan_limit)
        ]
        for book in active_books:
            self.loans.create_loan(
                self.patron.user_id,
                book.book_id,
                date.today(),
                date.today() + timedelta(days=14),
            )
        from backend.app.services.basket_service import BasketService

        with self.assertRaisesRegex(ValidationError, "remaining loan limit"):
            BasketService(self.books, self.loans).add(
                self.patron, [], self.first.book_id
            )

    def test_reference_book_cannot_be_added_to_basket(self):
        response = self._post(f"/basket/add/{self.reference.book_id}")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session.get("basket_book_ids", []), [])
        page = self.client.get("/books/")
        self.assertIn(b"not currently available to borrow", page.data)

    def test_checkout_creates_all_loans_and_receipt_then_clears_basket(self):
        self._set_basket([self.first.book_id, self.second.book_id])

        response = self._post("/basket/checkout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/basket/receipt")
        self.assertFalse(self.books.find_book(self.first.book_id).available)
        self.assertFalse(self.books.find_book(self.second.book_id).available)
        self.assertEqual(len(self.loans.find_patron_loans(self.patron.user_id)), 2)
        with self.client.session_transaction() as session:
            self.assertEqual(session["basket_book_ids"], [])
            self.assertEqual(len(session["last_receipt_loan_ids"]), 2)

        receipt = self.client.get("/basket/receipt")
        self.assertEqual(receipt.status_code, 200)
        self.assertIn(b"Your loan receipt", receipt.data)
        self.assertIn(b"Basket Book One", receipt.data)
        self.assertIn(b"Basket Book Two", receipt.data)
        self.assertIn(b"View my loans", receipt.data)

    def test_checkout_is_all_or_nothing_when_any_book_cannot_be_borrowed(self):
        self._set_basket([self.first.book_id, self.reference.book_id])

        response = self._post("/basket/checkout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            len(self.loans.find_patron_loans(self.patron.user_id)),
            0,
        )
        self.assertTrue(self.books.find_book(self.first.book_id).available)
        with self.client.session_transaction() as session:
            self.assertEqual(
                session["basket_book_ids"],
                [self.first.book_id, self.reference.book_id],
            )
        basket_page = self.client.get("/basket")
        self.assertIn(b"only be read in the library", basket_page.data)

    def test_loans_cards_profile_and_overdue_count(self):
        book = self.books.find_book(self.first.book_id)
        book.borrow()
        self.books.update_book(book)
        self.loans.create_loan(
            self.patron.user_id,
            self.first.book_id,
            date.today() - timedelta(days=15),
            date.today() - timedelta(days=1),
        )

        loans_page = self.client.get("/loans/")
        self.assertEqual(loans_page.status_code, 200)
        self.assertIn(b"Basket Book One", loans_page.data)
        self.assertIn(b"Overdue", loans_page.data)
        self.assertIn(b"Return book", loans_page.data)

        profile = self.client.get("/profile")
        self.assertEqual(profile.status_code, 200)
        self.assertIn(b"reader@example.com", profile.data)
        self.assertIn(b"Current loans", profile.data)
        self.assertIn(b">1</strong>", profile.data)
        self.assertIn(b"Change password", profile.data)

    def test_guest_checkout_and_profile_redirect_to_login(self):
        self.client.post("/logout", data={"csrf_token": self.csrf_token})
        self.assertEqual(
            self.client.get("/basket").location,
            "/login",
        )
        self.assertEqual(
            self.client.get("/profile").location,
            "/login",
        )


if __name__ == "__main__":
    unittest.main()
