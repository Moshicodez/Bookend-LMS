from datetime import date

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.loan import Loan
from ..models.loan_record import LoanRecord
from ..models.reservation import Reservation
from ..models.reservation_record import ReservationRecord
from ..models.notification_record import NotificationRecord


class LoanRepository:
    def create_loan(
        self,
        patron_id,
        book_id,
        borrowed_at,
        due_date,
        reservation_id=None,
    ):
        try:
            book_record = db.session.get(BookRecord, book_id)
            active_loan_id = db.session.scalar(
                db.select(LoanRecord.loan_id)
                .where(
                    LoanRecord.book_id == book_id,
                    LoanRecord.returned_at.is_(None),
                )
                .limit(1)
            )
            if (
                book_record is None
                or not book_record.catalog
                or active_loan_id is not None
            ):
                title = book_record.title if book_record else "This book"
                raise ValidationError(f"{title} is no longer available to borrow.")
            ready_reservation = self._ready_reservation(book_id)
            if ready_reservation is not None and (
                ready_reservation.reservation_id != reservation_id
                or ready_reservation.patron_id != patron_id
            ):
                raise ValidationError("This book is being held for another patron.")
            if reservation_id is not None and ready_reservation is None:
                raise ValidationError("This reservation is no longer ready.")

            book_record.available = False
            record = LoanRecord(
                patron_id=patron_id,
                book_id=book_id,
                borrowed_at=borrowed_at,
                due_date=due_date,
            )
            db.session.add(record)
            if ready_reservation is not None:
                ready_reservation.status = Reservation.FULFILLED
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The loan could not be saved.") from error
        except (ValidationError, SQLAlchemyError):
            db.session.rollback()
            raise
        return self._to_domain_loan(record)

    def create_loans_atomic(self, patron_id, entries):
        records = []
        try:
            for entry in entries:
                book, borrowed_at, due_date = entry[:3]
                reservation_id = entry[3] if len(entry) > 3 else None
                book_record = db.session.get(BookRecord, book.book_id)
                if (
                    book_record is None
                    or not book_record.catalog
                    or not book_record.available
                ):
                    raise ValidationError(
                        f"{book.title} is no longer available to borrow."
                    )
                ready_reservation = self._ready_reservation(book.book_id)
                if ready_reservation is not None and (
                    ready_reservation.reservation_id != reservation_id
                    or ready_reservation.patron_id != patron_id
                ):
                    raise ValidationError(
                        f"{book.title} is being held for another patron."
                    )
                if reservation_id is not None and ready_reservation is None:
                    raise ValidationError(
                        f"The reservation for {book.title} is no longer ready."
                    )
                book_record.available = False
                records.append(
                    LoanRecord(
                        patron_id=patron_id,
                        book_id=book.book_id,
                        borrowed_at=borrowed_at,
                        due_date=due_date,
                    )
                )
                if ready_reservation is not None:
                    ready_reservation.status = Reservation.FULFILLED
            db.session.add_all(records)
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The loans could not be saved.") from error
        except (ValidationError, SQLAlchemyError):
            db.session.rollback()
            raise
        return [self._to_domain_loan(record) for record in records]

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

    def most_borrowed(self, limit=5):
        rows = db.session.execute(
            db.select(
                LoanRecord.book_id,
                db.func.count(LoanRecord.loan_id).label("loan_count"),
            )
            .group_by(LoanRecord.book_id)
            .order_by(db.desc("loan_count"), LoanRecord.book_id)
            .limit(limit)
        ).all()
        return [
            {"book_id": book_id, "loan_count": loan_count}
            for book_id, loan_count in rows
        ]

    def return_record(self, loan_id, returned_at):
        loan_id = self._valid_id(loan_id)
        if loan_id is None:
            raise NotFoundError("Loan not found.")
        loan = self.find_loan(loan_id)
        if loan is None:
            raise NotFoundError("Loan not found.")
        loan.mark_returned(returned_at)
        return self.complete_return(loan)

    def complete_return(self, loan):
        loan_id = self._valid_id(loan.loan_id)
        if loan_id is None:
            raise NotFoundError("Loan not found.")
        try:
            record = db.session.get(LoanRecord, loan_id)
            if record is None:
                raise NotFoundError("Loan not found.")
            if record.returned_at is not None:
                raise ValidationError("This loan has already been returned.")
            book = db.session.get(BookRecord, record.book_id)
            if book is None:
                raise NotFoundError("Book not found.")

            details = loan.to_record()
            record.returned_at = loan.returned_at
            record.fee_paid = details["fee_paid"]
            record.lost = details["lost"]
            record.loss_fee = details["loss_fee"]
            record.loss_paid = details["loss_paid"]
            book.available = not loan.lost
            if loan.lost:
                book.catalog = False
                db.session.execute(
                    db.update(ReservationRecord)
                    .where(
                        ReservationRecord.book_id == book.book_id,
                        ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
                    )
                    .values(status=Reservation.CANCELLED)
                )
            else:
                next_reservation = db.session.execute(
                    db.select(ReservationRecord)
                    .where(
                        ReservationRecord.book_id == book.book_id,
                        ReservationRecord.status == Reservation.WAITING,
                    )
                    .order_by(ReservationRecord.reservation_id)
                    .limit(1)
                ).scalar_one_or_none()
                if next_reservation is not None:
                    next_reservation.status = Reservation.READY
                    db.session.add(
                        NotificationRecord(
                            user_id=next_reservation.patron_id,
                            category="loan",
                            title="Reserved book ready",
                            message=(
                                "A book in your reservation queue is ready "
                                "to borrow."
                            ),
                            link=f"/books/{book.book_id}",
                            dedupe_key=(
                                f"reservation:{next_reservation.reservation_id}:ready"
                            ),
                        )
                    )
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The return could not be saved.") from error
        except (NotFoundError, ValidationError, SQLAlchemyError):
            db.session.rollback()
            raise
        return loan

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
    def _ready_reservation(book_id):
        return db.session.execute(
            db.select(ReservationRecord).where(
                ReservationRecord.book_id == book_id,
                ReservationRecord.status == Reservation.READY,
            )
        ).scalar_one_or_none()

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