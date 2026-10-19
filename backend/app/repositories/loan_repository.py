from datetime import date

from sqlalchemy.exc import IntegrityError

from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..models.loan import Loan
from ..models.loan_record import LoanRecord


class LoanRepository:
    def create_loan(self, patron_id, book_id, borrowed_at, due_date):
        record = LoanRecord(
            patron_id=patron_id,
            book_id=book_id,
            borrowed_at=borrowed_at,
            due_date=due_date,
        )
        db.session.add(record)
        self._commit()
        return self._to_domain_loan(record)

    def find_loan(self, loan_id):
        loan_id = self._valid_id(loan_id)
        if loan_id is None:
            return None
        record = db.session.get(LoanRecord, loan_id)
        return self._to_domain_loan(record) if record else None

    def find_patron_loans(self, patron_id):
        records = db.session.execute(
            db.select(LoanRecord)
            .where(LoanRecord.patron_id == patron_id)
            .order_by(LoanRecord.borrowed_at.desc(), LoanRecord.loan_id.desc())
        ).scalars()
        return [self._to_domain_loan(record) for record in records]

    def find_active_loan(self, patron_id, book_id):
        record = db.session.execute(
            db.select(LoanRecord).where(
                LoanRecord.patron_id == patron_id,
                LoanRecord.book_id == book_id,
                LoanRecord.returned_at.is_(None),
            )
        ).scalar_one_or_none()
        return self._to_domain_loan(record) if record else None

    def find_active_loan_by_book(self, book_id):
        record = db.session.execute(
            db.select(LoanRecord).where(
                LoanRecord.book_id == book_id,
                LoanRecord.returned_at.is_(None),
            )
        ).scalar_one_or_none()
        return self._to_domain_loan(record) if record else None

    def find_all(self):
        records = db.session.execute(
            db.select(LoanRecord).order_by(LoanRecord.borrowed_at.desc())
        ).scalars()
        return [self._to_domain_loan(record) for record in records]

    def find_overdue(self, current_date=None):
        current_date = current_date or date.today()
        records = db.session.execute(
            db.select(LoanRecord).where(
                LoanRecord.returned_at.is_(None),
                LoanRecord.due_date < current_date,
            ).order_by(LoanRecord.due_date)
        ).scalars()
        return [self._to_domain_loan(record) for record in records]

    def return_record(self, loan_id, returned_at):
        loan_id = self._valid_id(loan_id)
        if loan_id is None:
            raise NotFoundError("Loan not found.")
        record = db.session.get(LoanRecord, loan_id)
        if record is None:
            raise NotFoundError("Loan not found.")
        record.returned_at = returned_at
        self._commit()

    def update_loan(self, loan):
        loan_id = self._valid_id(loan.loan_id)
        if loan_id is None:
            raise NotFoundError("Loan not found.")
        record = db.session.get(LoanRecord, loan_id)
        if record is None:
            raise NotFoundError("Loan not found.")
        details = loan.to_record()
        record.returned_at = loan.returned_at
        record.fee_paid = details["fee_paid"]
        record.lost = details["lost"]
        record.loss_fee = details["loss_fee"]
        record.loss_paid = details["loss_paid"]
        self._commit()
        return loan

    @staticmethod
    def _valid_id(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_domain_loan(record):
        return Loan(
            record.loan_id,
            record.patron_id,
            record.book_id,
            record.borrowed_at,
            record.due_date,
            returned_at=record.returned_at,
            fee_paid=record.fee_paid,
            lost=record.lost,
            loss_fee=record.loss_fee,
            loss_paid=record.loss_paid,
        )

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The loan could not be saved.") from error