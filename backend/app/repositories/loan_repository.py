from datetime import date

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..constants import UNCATEGORIZED
from ..models.book_record import BookRecord
from ..models.loan import Loan
from ..models.loan_record import LoanRecord
from ..models.reservation import Reservation
from ..models.reservation_record import ReservationRecord
from .reservation_repository import ReservationRepository


class LoanRepository:
    def __init__(self):
        self._reservations = ReservationRepository()

    def create_loan(
        self,
        patron_id,
        book_id,
        borrowed_at,
        due_date,
        reservation_id=None,
    ):
        try:
            book_record = self._reserve_copy(
                patron_id,
                book_id,
                reservation_id,
            )
            if book_record is None:
                book_record = db.session.get(BookRecord, book_id)
                title = book_record.title if book_record else "This book"
                raise ValidationError(f"{title} is no longer available to borrow.")

            record = LoanRecord(
                patron_id=patron_id,
                book_id=book_id,
                book_title=book_record.title,
                book_author=book_record.author,
                borrowed_at=borrowed_at,
                due_date=due_date,
            )
            db.session.add(record)
            if reservation_id is not None:
                ready_reservation = db.session.get(
                    ReservationRecord,
                    reservation_id,
                )
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
                book_record = self._reserve_copy(
                    patron_id,
                    book.book_id,
                    reservation_id,
                )
                if book_record is None:
                    raise ValidationError(
                        f"{book.title} is no longer available to borrow."
                    )
                record = LoanRecord(
                    patron_id=patron_id,
                    book_id=book.book_id,
                    book_title=book_record.title,
                    book_author=book_record.author,
                    borrowed_at=borrowed_at,
                    due_date=due_date,
                )
                db.session.add(record)
                if reservation_id is not None:
                    ready_reservation = db.session.get(
                        ReservationRecord,
                        reservation_id,
                    )
                    ready_reservation.status = Reservation.FULFILLED
                db.session.flush()
                records.append(record)
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

    def active_book_ids(self, patron_id):
        return set(
            db.session.execute(
                db.select(LoanRecord.book_id)
                .where(
                    LoanRecord.patron_id == patron_id,
                    LoanRecord.returned_at.is_(None),
                )
                .distinct()
            ).scalars()
        )

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
            db.select(LoanRecord)
            .where(
                LoanRecord.book_id == book_id,
                LoanRecord.returned_at.is_(None),
            )
            .order_by(LoanRecord.loan_id)
            .limit(1)
        ).scalar_one_or_none()
        return self._to_domain_loan(record) if record else None

    def find_active_loans_by_book(self, book_id):
        records = db.session.execute(
            db.select(LoanRecord)
            .where(
                LoanRecord.book_id == book_id,
                LoanRecord.returned_at.is_(None),
            )
            .order_by(LoanRecord.loan_id)
        ).scalars()
        return [self._to_domain_loan(record) for record in records]

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
                db.func.max(LoanRecord.book_title).label("book_title"),
                db.func.max(LoanRecord.book_author).label("book_author"),
                db.func.count(LoanRecord.loan_id).label("loan_count"),
            )
            .group_by(
                LoanRecord.book_id,
                LoanRecord.book_title,
                LoanRecord.book_author,
            )
            .order_by(db.desc("loan_count"), LoanRecord.book_id)
            .limit(limit)
        ).all()
        return [
            {
                "book_id": book_id,
                "book_title": book_title,
                "book_author": book_author,
                "loan_count": loan_count,
            }
            for book_id, book_title, book_author, loan_count in rows
        ]

    def analytics_counts(self, start_date, end_date):
        borrowed_rows = db.session.execute(
            db.select(
                LoanRecord.borrowed_at,
                db.func.count(LoanRecord.loan_id).label("loan_count"),
            )
            .where(
                LoanRecord.borrowed_at >= start_date,
                LoanRecord.borrowed_at <= end_date,
            )
            .group_by(LoanRecord.borrowed_at)
            .order_by(LoanRecord.borrowed_at)
        ).all()
        returned_rows = db.session.execute(
            db.select(
                LoanRecord.returned_at,
                db.func.count(LoanRecord.loan_id).label("return_count"),
            )
            .where(
                LoanRecord.returned_at.is_not(None),
                LoanRecord.returned_at >= start_date,
                LoanRecord.returned_at <= end_date,
            )
            .group_by(LoanRecord.returned_at)
            .order_by(LoanRecord.returned_at)
        ).all()
        genre_rows = db.session.execute(
            db.select(
                db.func.coalesce(
                    db.func.nullif(
                        db.func.trim(BookRecord.genre, " \t\n\r\f\v"),
                        "",
                    ),
                    UNCATEGORIZED,
                ).label("genre"),
                db.func.count(LoanRecord.loan_id).label("loan_count"),
            )
            .join(BookRecord, BookRecord.book_id == LoanRecord.book_id)
            .where(
                LoanRecord.borrowed_at >= start_date,
                LoanRecord.borrowed_at <= end_date,
            )
            .group_by(
                db.func.coalesce(
                    db.func.nullif(
                        db.func.trim(BookRecord.genre, " \t\n\r\f\v"),
                        "",
                    ),
                    UNCATEGORIZED,
                )
            )
            .order_by(db.desc("loan_count"), "genre")
        ).all()
        return {
            "loans": borrowed_rows,
            "returns": returned_rows,
            "genres": genre_rows,
        }

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
            if loan.lost:
                book.total_copies = max(0, book.total_copies - 1)
                if book.total_copies == 0:
                    book.catalog = False
                    db.session.execute(
                        db.update(ReservationRecord)
                        .where(
                            ReservationRecord.book_id == book.book_id,
                            ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
                        )
                        .values(status=Reservation.CANCELLED)
                    )
            active_count = db.session.scalar(
                db.select(db.func.count(LoanRecord.loan_id)).where(
                    LoanRecord.book_id == book.book_id,
                    LoanRecord.returned_at.is_(None),
                )
            ) or 0
            book.available = book.total_copies > active_count
            if not loan.lost:
                db.session.flush()
                self._reservations.promote_waiting(book.book_id, commit=False)
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
    def _reserve_copy(patron_id, book_id, reservation_id):
        book = db.session.get(BookRecord, book_id)
        if book is None or not book.catalog:
            return None

        reservation_credit = 0
        if reservation_id is not None:
            reservation = db.session.get(ReservationRecord, reservation_id)
            if (
                reservation is None
                or reservation.book_id != book_id
                or reservation.patron_id != patron_id
                or reservation.status != Reservation.READY
            ):
                raise ValidationError("This reservation is no longer ready.")
            reservation_credit = 1

        active_count = (
            db.select(db.func.count(LoanRecord.loan_id))
            .where(
                LoanRecord.book_id == BookRecord.book_id,
                LoanRecord.returned_at.is_(None),
            )
            .correlate(BookRecord)
            .scalar_subquery()
        )
        reserved_count = (
            db.select(db.func.count(ReservationRecord.reservation_id))
            .where(
                ReservationRecord.book_id == BookRecord.book_id,
                ReservationRecord.status == Reservation.READY,
            )
            .correlate(BookRecord)
            .scalar_subquery()
        )
        borrowable = (
            BookRecord.total_copies
            - active_count
            - reserved_count
            + reservation_credit
        )
        result = db.session.execute(
            db.update(BookRecord)
            .where(
                BookRecord.book_id == book_id,
                BookRecord.catalog.is_(True),
                borrowable > 0,
            )
            .values(available=BookRecord.total_copies > active_count + 1)
        )
        return book if result.rowcount == 1 else None

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
            book_title=record.book_title,
            book_author=record.book_author,
        )

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The loan could not be saved.") from error