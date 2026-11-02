from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.loan_record import LoanRecord
from ..models.reservation import Reservation
from ..models.reservation_record import ReservationRecord
from ..models.book_record import BookRecord


class ReservationRepository:
    def find_for_patron_book(self, patron_id, book_id):
        record = db.session.execute(
            db.select(ReservationRecord)
            .where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.book_id == book_id,
                ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
            )
            .order_by(ReservationRecord.reservation_id.desc())
        ).scalars().first()
        return self._to_domain(record) if record else None

    def find_ready_for_book(self, book_id):
        record = db.session.execute(
            db.select(ReservationRecord).where(
                ReservationRecord.book_id == book_id,
                ReservationRecord.status == Reservation.READY,
            )
        ).scalar_one_or_none()
        return self._to_domain(record) if record else None

    def find_for_patron(self, patron_id):
        records = db.session.execute(
            db.select(ReservationRecord)
            .where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
            )
            .order_by(ReservationRecord.reservation_id)
        ).scalars()
        return [self._to_domain(record) for record in records]

    def count_open_for_patron(self, patron_id):
        return db.session.scalar(
            db.select(db.func.count(ReservationRecord.reservation_id)).where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
            )
        ) or 0

    def waiting_count(self, book_id):
        return db.session.scalar(
            db.select(db.func.count(ReservationRecord.reservation_id)).where(
                ReservationRecord.book_id == book_id,
                ReservationRecord.status == Reservation.WAITING,
            )
        ) or 0

    def create_waiting(self, patron_id, book_id):
        try:
            book = db.session.get(BookRecord, book_id)
            active_loan_id = db.session.scalar(
                db.select(LoanRecord.loan_id)
                .where(
                    LoanRecord.book_id == book_id,
                    LoanRecord.returned_at.is_(None),
                )
                .limit(1)
            )
            if book is None or not book.catalog:
                raise ValidationError("This book is no longer in the catalog.")
            if book.available or active_loan_id is None:
                raise ValidationError(
                    "Reservations are only available while a book is on loan."
                )
            if self.find_for_patron_book(patron_id, book_id):
                raise ValidationError("You already have a reservation for this book.")

            record = ReservationRecord(
                patron_id=patron_id,
                book_id=book_id,
                status=Reservation.WAITING,
            )
            db.session.add(record)
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The reservation could not be saved.") from error
        except (ValidationError, SQLAlchemyError):
            db.session.rollback()
            raise
        return self._to_domain(record)

    @staticmethod
    def _to_domain(record):
        return Reservation(
            record.reservation_id,
            record.patron_id,
            record.book_id,
            record.status,
            record.created_at,
        )
