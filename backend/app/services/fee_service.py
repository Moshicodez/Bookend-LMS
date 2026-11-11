from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from ..config import Config
from ..exceptions import NotFoundError, ValidationError
from ..repositories.fee_repository import FeeRepository
from ..repositories.notification_repository import NotificationRepository
from ..services.notification_service import NotificationService
from ..utils.date_utils import today


class FeeService:
    STATUSES = {"outstanding", "paid", "all"}
    TYPES = {"all", "late", "loss"}
    SORTS = {"amount", "overdue", "name"}

    def __init__(self, repository=None, notification_service=None):
        self._fees = repository or FeeRepository()
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )

    def list_members_with_fees(
        self,
        librarian,
        status="outstanding",
        fee_type="all",
        search="",
        sort="amount",
        page=1,
    ):
        librarian.require("manage_fees")
        if status not in self.STATUSES:
            raise ValidationError("Choose a valid fee status filter.")
        if fee_type not in self.TYPES:
            raise ValidationError("Choose a valid fee type filter.")
        if sort not in self.SORTS:
            raise ValidationError("Choose a valid fee sort order.")
        try:
            page = int(page)
        except (TypeError, ValueError) as error:
            raise ValidationError("Choose a valid page number.") from error
        if page < 1 or page > 1_000_000:
            raise ValidationError("Choose a valid page number.")
        result = self._fees.list_members(
            status,
            fee_type,
            search,
            sort,
            page,
            today(),
        )
        result["summary"] = self._fees.summary(today())
        result.update(status=status, fee_type=fee_type, search=search, sort=sort)
        return result

    def outstanding_member_count(self):
        return self._fees.members_with_outstanding_count(today())

    def payment_preview(self, librarian, loan_id, fee_type):
        librarian.require("manage_fees")
        if fee_type not in {"late", "loss"}:
            raise ValidationError("Choose a valid fee type.")
        line = self._fees.fee_line(loan_id, fee_type, today())
        if line is None:
            raise NotFoundError("That fee could not be found.")
        member = self._fees.find_member(line["patron_id"])
        return {
            "member": member,
            "book_title": line["book_title"],
            "fee_type": fee_type,
            "amount": float(line["amount"]),
        }

    def member_outstanding_fees(self, librarian, patron_id):
        librarian.require("manage_fees")
        patron = self._fees.find_member(patron_id)
        if patron is None or patron.role != "patron":
            raise NotFoundError("Member not found.")
        lines = self._fees.lines_for_members(
            [patron_id],
            status="outstanding",
            fee_type="all",
            current_date=today(),
        )
        return patron, lines, round(sum(float(line["amount"]) for line in lines), 2)

    def confirm_payment(
        self,
        librarian,
        loan_id,
        fee_type,
        receipt_no=None,
        note=None,
    ):
        librarian.require("manage_fees")
        receipt_no, note = self._validate_payment_fields(receipt_no, note)
        try:
            payment, amount, member_name = self._confirm_payment(
                librarian,
                loan_id,
                fee_type,
                receipt_no,
                note,
            )
            self._fees.commit()
        except IntegrityError as error:
            self._fees.rollback()
            raise ValidationError("This fee was already confirmed.") from error
        except Exception:
            self._fees.rollback()
            raise
        return payment, amount, member_name

    def confirm_all_for_member(
        self,
        librarian,
        patron_id,
        receipt_no=None,
        note=None,
    ):
        librarian.require("manage_fees")
        receipt_no, note = self._validate_payment_fields(receipt_no, note)
        patron = self._fees.find_member(patron_id)
        if patron is None or patron.role != "patron":
            raise NotFoundError("Member not found.")
        lines = self._fees.lines_for_members(
            [patron_id],
            status="outstanding",
            fee_type="all",
            current_date=today(),
        )
        if not lines:
            raise ValidationError("This member has no outstanding fees.")
        try:
            total = 0.0
            for line in lines:
                _, amount, _ = self._confirm_payment(
                    librarian,
                    line["loan_id"],
                    line["fee_type"],
                    receipt_no,
                    note,
                )
                total += amount
            self._fees.commit()
        except IntegrityError as error:
            self._fees.rollback()
            raise ValidationError("A fee was already confirmed; no payments were recorded.") from error
        except Exception:
            self._fees.rollback()
            raise
        return len(lines), round(total, 2), patron.username

    def _confirm_payment(self, librarian, loan_id, fee_type, receipt_no, note):
        if fee_type not in {"late", "loss"}:
            raise ValidationError("Choose a valid fee type.")
        record = self._fees.find_loan_record(loan_id)
        if record is None:
            raise NotFoundError("Loan not found.")
        if self._fees.has_active_payment(loan_id, fee_type):
            raise ValidationError("This fee was already confirmed.")
        if fee_type == "late":
            if record.returned_at is None:
                raise ValidationError("Return the book first; late fees stop growing once it's back.")
            if record.lost:
                raise ValidationError("There is no late fee on a lost book.")
            amount = round(
                max(0, (record.returned_at - record.due_date).days)
                * Config.DAILY_LATE_FEE,
                2,
            )

        else:
            if not record.lost:
                raise ValidationError("This loan hasn't been marked as lost.")
            amount = round(Config.LOSS_FEE, 2)
        if amount <= 0:
            raise ValidationError("There is no fee due on this loan.")
        payment = self._fees.record_payment(
            loan_id,
            fee_type,
            amount,
            librarian.user_id,
            receipt_no,
            note,
            datetime.now(timezone.utc),
        )
        if payment is None:
            raise ValidationError("This fee was already confirmed.")
        line = self._fees.fee_line(loan_id, fee_type, today())
        member = self._fees.find_member(record.patron_id)
        book_title = line["book_title"] if line else "the book"
        self._notifications.notify(
            record.patron_id,
            "Fee payment confirmed",
            f"Your payment of ₱{amount:,.2f} for {book_title} was confirmed.",
            category="fee",
            link="/loans/",
            dedupe_key=f"fee-payment:{payment.payment_id}:confirmed",
            commit=False,
        )
        return payment, amount, member.username if member else "member"

    @staticmethod
    def _validate_payment_fields(receipt_no, note):
        receipt_no = (receipt_no or "").strip() or None
        note = (note or "").strip() or None
        if receipt_no is not None and len(receipt_no) > 40:
            raise ValidationError("Receipt / OR number must be 40 characters or fewer.")
        if note is not None and len(note) > 200:
            raise ValidationError("Note must be 200 characters or fewer.")
        return receipt_no, note
