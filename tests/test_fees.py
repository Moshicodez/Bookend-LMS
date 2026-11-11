import re
import unittest
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.exceptions import ValidationError
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.fee_payment_record import FeePaymentRecord
from backend.app.models.loan_record import LoanRecord
from backend.app.models.notification_record import NotificationRecord
from backend.app.models.user_record import UserRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.backup_service import BackupService
from backend.app.services.fee_service import FeeService
from backend.app.services.loan_service import LoanService
from backend.app.repositories.loan_repository import LoanRepository
from backend.app.repositories.fee_repository import FeeRepository
from backend.app.services.librarian_service import LibrarianService


class ManageFeesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "manage-fees-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.users = UserRepository()
        self.books = BookRepository()
        self.librarian = self._create_user("staff", "librarian")
        self.patron = self._create_user("reader", "patron")
        self.book = self.books.create(Book(None, "Known Title", "Writer", "History", ""))
        self.token = self._sign_in(self.librarian)

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
        login = self.client.get("/login")
        token = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login.data,
        ).group(1).decode()
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role
        return token

    def _loan(
        self,
        patron=None,
        book=None,
        *,
        due_days_ago=5,
        returned=True,
        lost=False,
        fee_paid=False,
        loss_paid=False,
    ):
        today = date.today()
        record = LoanRecord(
            patron_id=(patron or self.patron).user_id,
            book_id=(book or self.book).book_id,
            borrowed_at=today - timedelta(days=30),
            due_date=today - timedelta(days=due_days_ago),
            returned_at=today - timedelta(days=1) if returned else None,
            lost=lost,
            loss_fee=2500.0 if lost else 0.0,
            fee_paid=fee_paid,
            loss_paid=loss_paid,
        )
        db.session.add(record)
        db.session.commit()
        return record

    def _confirm_form(self, loan, fee_type, **overrides):
        data = {
            "csrf_token": self.token,
            "loan_id": str(loan.loan_id),
            "fee_type": fee_type,
            "next": "/librarian/fees/?status=all",
            "received_full": "on",
        }
        data.update(overrides)
        return self.client.post("/librarian/fees/confirm", data=data)

    def test_authentication_and_librarian_routes_are_protected(self):
        anonymous = self.app.test_client()
        response = anonymous.get("/librarian/fees/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

        patron_token = self._sign_in(self.patron)
        self.assertEqual(self.client.get("/librarian/fees/").status_code, 403)
        for path, data in (
            ("/librarian/fees/confirm", {"loan_id": 1, "fee_type": "late"}),
            ("/librarian/fees/confirm-all/1", {}),
        ):
            payload = {"csrf_token": patron_token, **data}
            self.assertEqual(self.client.post(path, data=payload).status_code, 403)

    def test_page_lists_outstanding_fees_and_supports_filters_and_literal_search(self):
        symbols = self.books.create(
            Book(None, "Guide %_ to SQL", "Writer", "Reference", "")
        )
        late = self._loan()
        self._loan(book=symbols, lost=True, returned=True)
        unreturned = self._loan(
            patron=self._create_user("another"),
            due_days_ago=3,
            returned=False,
        )

        response = self.client.get("/librarian/fees/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage fees", response.data)
        self.assertIn(b"Known Title", response.data)
        self.assertIn(b"Accruing", response.data)
        self.assertIn("₱2,500.00".encode(), response.data)
        self.assertNotIn(b"Paid history only", response.data)
        self.assertIn(b"Confirm payment received", response.data)
        self.assertIn(b"Return the book first", response.data)
        self.assertEqual(response.data.count(b'class="pagination-nav"'), 0)

        literal = self.client.get("/librarian/fees/?status=outstanding&q=%25_")
        self.assertEqual(literal.status_code, 200)
        self.assertIn(b"Guide %_ to SQL", literal.data)
        self.assertNotIn(b"Known Title", literal.data)
        wildcard = self.client.get("/librarian/fees/?status=outstanding&q=%25")
        self.assertIn(b"Guide %_ to SQL", wildcard.data)
        self.assertNotIn(b"Known Title", wildcard.data)

        for query in (
            "?status=all%27%20OR%201%3D1",
            "?type=late%27%20OR%201%3D1",
            "?sort=amount%20DESC",
            "?page=1%20OR%201%3D1",
        ):
            self.assertEqual(
                self.client.get(f"/librarian/fees/{query}").status_code,
                302,
            )
        self.assertEqual(late.fee_paid, False)
        self.assertEqual(unreturned.returned_at, None)

    def test_paid_members_are_only_in_paid_or_all_status(self):
        loan = self._loan(fee_paid=True)
        db.session.add(
            FeePaymentRecord(
                loan_id=loan.loan_id,
                fee_type="late",
                amount=2.5,
                confirmed_by=self.librarian.user_id,
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        db.session.commit()

        outstanding = self.client.get("/librarian/fees/?status=outstanding")
        self.assertNotIn(b"reader", outstanding.data)
        paid = self.client.get("/librarian/fees/?status=paid")
        self.assertIn(b"reader", paid.data)
        self.assertIn(b"Confirmed by staff", paid.data)
        self.assertIn("₱2.50".encode(), paid.data)

    def test_fee_type_sort_and_pagination_use_one_navigation(self):
        names = [f"member-{index:02d}" for index in range(21)]
        for username in reversed(names):
            member = self._create_user(username)
            self._loan(patron=member, lost=True)

        service = FeeService()
        result = service.list_members_with_fees(
            self.librarian,
            status="outstanding",
            fee_type="loss",
            sort="name",
            page=1,
        )
        self.assertEqual(result["total"], 21)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(
            [member["username"] for member in result["members"]],
            names[:20],
        )
        second = service.list_members_with_fees(
            self.librarian,
            status="outstanding",
            fee_type="loss",
            sort="name",
            page=2,
        )
        self.assertEqual(
            [member["username"] for member in second["members"]],
            names[20:],
        )

        page = self.client.get("/librarian/fees/?sort=name&type=loss")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data.count(b'class="pagination-nav"'), 1)

        late_only = self.client.get("/librarian/fees/?type=late")
        self.assertNotIn(b"member-00", late_only.data)

    def test_late_fee_on_unreturned_loan_cannot_be_confirmed_and_csrf_redirects(self):
        loan = self._loan(returned=False)
        response = self._confirm_form(loan, "late")
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.location)
        self.assertIn(b"Return the book first", page.data)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count(FeePaymentRecord.payment_id))),
            0,
        )

        missing_token = self.client.post(
            "/librarian/fees/confirm",
            data={"loan_id": loan.loan_id, "fee_type": "late"},
        )
        self.assertEqual(missing_token.status_code, 302)
        self.assertIn("/login", missing_token.location)

    def test_loss_payment_uses_fixed_server_amount_and_is_idempotent(self):
        loan = self._loan(lost=True)
        response = self._confirm_form(
            loan,
            "loss",
            amount="1.00",
            receipt_no="OR-123",
            note="At desk",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/librarian/fees/?status=all")
        payment = db.session.scalar(db.select(FeePaymentRecord))
        self.assertEqual(payment.amount, 2500.0)
        self.assertEqual(payment.confirmed_by, self.librarian.user_id)
        self.assertEqual(payment.receipt_no, "OR-123")
        self.assertTrue(db.session.get(LoanRecord, loan.loan_id).loss_paid)
        notifications = db.session.scalars(
            db.select(NotificationRecord).where(
                NotificationRecord.user_id == self.patron.user_id,
                NotificationRecord.category == "fee",
            )
        ).all()
        self.assertEqual(len(notifications), 1)
        self.assertIn("₱2,500.00", notifications[0].message)

        duplicate = self._confirm_form(
            loan,
            "loss",
            next="https://attacker.example/",
        )
        self.assertEqual(duplicate.status_code, 302)
        self.assertEqual(duplicate.location, "/librarian/fees/")
        self.assertEqual(
            db.session.scalar(db.select(db.func.count(FeePaymentRecord.payment_id))),
            1,
        )
        self.assertEqual(len(notifications), 1)

        db.session.add(
            FeePaymentRecord(
                loan_id=loan.loan_id,
                fee_type="loss",
                amount=2500.0,
                confirmed_by=self.librarian.user_id,
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_confirm_all_rolls_back_every_payment_on_midway_failure(self):
        first = self._loan(lost=True)
        second_book = self.books.create(Book(None, "Another lost book", "Writer", "", ""))
        self._loan(book=second_book, lost=True)
        service = FeeService()
        original = service._confirm_payment
        calls = 0

        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValidationError("forced failure")
            return original(*args)

        with patch("backend.app.routes.fees.fee_service", service), patch.object(
            service,
            "_confirm_payment",
            side_effect=fail_second,
        ):
            response = self.client.post(
                f"/librarian/fees/confirm-all/{self.patron.user_id}",
                data={
                    "csrf_token": self.token,
                    "next": "/librarian/fees/",
                    "received_full": "on",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count(FeePaymentRecord.payment_id))),
            0,
        )
        self.assertFalse(db.session.get(LoanRecord, first.loan_id).loss_paid)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count(NotificationRecord.notification_id))),
            0,
        )

    def test_paid_balance_no_longer_blocks_borrowing(self):
        overdue = self._loan()
        book_to_borrow = self.books.create(Book(None, "Borrow after payment", "Writer", "", ""))
        service = LoanService(self.books, LoanRepository())
        with self.assertRaises(ValidationError):
            service.borrow_book(self.patron, book_to_borrow.book_id)

        self._confirm_form(overdue, "late")
        new_loan = service.borrow_book(self.patron, book_to_borrow.book_id)
        self.assertIsNotNone(new_loan.loan_id)

    def test_backup_round_trips_fee_payment_records(self):
        loan = self._loan(lost=True)
        db.session.add(
            FeePaymentRecord(
                loan_id=loan.loan_id,
                fee_type="loss",
                amount=2500.0,
                confirmed_by=self.librarian.user_id,
                confirmed_at=datetime.now(timezone.utc),
                receipt_no="OR-1",
            )
        )
        db.session.commit()
        backup = BackupService.create_backup()
        db.session.execute(db.delete(FeePaymentRecord))
        db.session.commit()

        BackupService.restore_backup(BytesIO(backup))
        restored = db.session.scalar(db.select(FeePaymentRecord))
        self.assertEqual(restored.amount, 2500.0)
        self.assertEqual(restored.receipt_no, "OR-1")

    def test_collected_totals_use_nonvoided_ledger_rows(self):
        loan = self._loan(lost=True)
        db.session.add_all(
            [
                FeePaymentRecord(
                    loan_id=loan.loan_id,
                    fee_type="loss",
                    amount=99.0,
                    confirmed_by=self.librarian.user_id,
                    confirmed_at=datetime.now(timezone.utc),
                    voided_at=datetime.now(timezone.utc),
                    voided_by=self.librarian.user_id,
                    void_reason="Duplicate receipt",
                ),
                FeePaymentRecord(
                    loan_id=loan.loan_id,
                    fee_type="loss",
                    amount=2500.0,
                    confirmed_by=self.librarian.user_id,
                    confirmed_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.session.commit()

        self.assertEqual(FeeRepository().collected_total(), 2500.0)
        summary = FeeRepository().summary()
        self.assertEqual(summary["collected_month"], 2500.0)
        dashboard = LibrarianService(
            BookRepository(),
            LoanRepository(),
            UserRepository(),
        ).dashboard_data(self.librarian)
        self.assertEqual(dashboard["stats"]["fees_collected"], 2500.0)


if __name__ == "__main__":
    unittest.main()
