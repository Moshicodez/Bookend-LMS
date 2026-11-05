from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.loan_record import LoanRecord
from ..models.reservation import Reservation
from ..models.reservation_record import ReservationRecord
from ..models.book_record import BookRecord
from ..models.notification_record import NotificationRecord
from ..models.user import User
from ..models.user_record import UserRecord
from .book_repository import BookRepository


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
            db.select(ReservationRecord)
            .where(
                ReservationRecord.book_id == book_id,
                ReservationRecord.status == Reservation.READY,
            )
            .order_by(ReservationRecord.reservation_id)
            .limit(1)
        ).scalar_one_or_none()
        return self._to_domain(record) if record else None

    def find_ready_for_patron_book(self, patron_id, book_id):
        record = db.session.execute(
            db.select(ReservationRecord)
            .where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.book_id == book_id,
                ReservationRecord.status == Reservation.READY,
            )
            .order_by(ReservationRecord.reservation_id)
            .limit(1)
        ).scalar_one_or_none()
        return self._to_domain(record) if record else None

    def has_ready_for_other_patron(self, patron_id, book_id):
        return db.session.scalar(
            db.select(ReservationRecord.reservation_id)
            .where(
                ReservationRecord.book_id == book_id,
                ReservationRecord.patron_id != patron_id,
                ReservationRecord.status == Reservation.READY,
            )
            .limit(1)
        ) is not None

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

    def find_patron_cards(self, patron_id):
        active, reserved = BookRepository._stock_counts()
        waiting_positions = (
            db.select(
                ReservationRecord.reservation_id,
                db.func.row_number()
                .over(
                    partition_by=ReservationRecord.book_id,
                    order_by=ReservationRecord.reservation_id,
                )
                .label("queue_position"),
            )
            .where(ReservationRecord.status == Reservation.WAITING)
            .subquery()
        )
        rows = db.session.execute(
            db.select(
                ReservationRecord,
                BookRecord,
                waiting_positions.c.queue_position,
                db.func.coalesce(active.c.active_count, 0),
                db.func.coalesce(reserved.c.reserved_count, 0),
            )
            .join(BookRecord, BookRecord.book_id == ReservationRecord.book_id)
            .outerjoin(active, active.c.book_id == BookRecord.book_id)
            .outerjoin(reserved, reserved.c.book_id == BookRecord.book_id)
            .outerjoin(
                waiting_positions,
                waiting_positions.c.reservation_id
                == ReservationRecord.reservation_id,
            )
            .where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
            )
            .order_by(ReservationRecord.created_at.desc())
        )
        return [
            {
                "reservation": self._to_domain(reservation),
                "book": BookRepository._to_domain_book(
                    book,
                    on_loan,
                    reserved_count,
                ),
                "queue_position": queue_position,
            }
            for reservation, book, queue_position, on_loan, reserved_count in rows
        ]

    def find_for_management(self, status="", search=""):
        active, reserved = BookRepository._stock_counts()
        waiting_positions = (
            db.select(
                ReservationRecord.reservation_id,
                db.func.row_number()
                .over(
                    partition_by=ReservationRecord.book_id,
                    order_by=ReservationRecord.reservation_id,
                )
                .label("queue_position"),
            )
            .where(ReservationRecord.status == Reservation.WAITING)
            .subquery()
        )
        statement = (
            db.select(
                ReservationRecord,
                BookRecord,
                UserRecord,
                waiting_positions.c.queue_position,
                db.func.coalesce(active.c.active_count, 0),
                db.func.coalesce(reserved.c.reserved_count, 0),
            )
            .join(BookRecord, BookRecord.book_id == ReservationRecord.book_id)
            .join(UserRecord, UserRecord.user_id == ReservationRecord.patron_id)
            .outerjoin(active, active.c.book_id == BookRecord.book_id)
            .outerjoin(reserved, reserved.c.book_id == BookRecord.book_id)
            .outerjoin(
                waiting_positions,
                waiting_positions.c.reservation_id
                == ReservationRecord.reservation_id,
            )
            .where(ReservationRecord.status.in_(Reservation.OPEN_STATUSES))
        )
        if status in Reservation.OPEN_STATUSES:
            statement = statement.where(ReservationRecord.status == status)
        search = (search or "").strip()
        if search:
            safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{safe}%"
            statement = statement.where(
                db.or_(
                    BookRecord.title.ilike(pattern, escape="\\"),
                    BookRecord.author.ilike(pattern, escape="\\"),
                    UserRecord.username.ilike(pattern, escape="\\"),
                    UserRecord.email.ilike(pattern, escape="\\"),
                )
            )
        rows = db.session.execute(
            statement.order_by(
                ReservationRecord.created_at.desc(),
                ReservationRecord.reservation_id.desc(),
            )
        )
        return [
            {
                "reservation": self._to_domain(reservation),
                "book": BookRepository._to_domain_book(
                    book,
                    on_loan,
                    reserved_count,
                ),
                "patron": User.create(
                    patron.user_id,
                    patron.email,
                    patron.username,
                    patron.password_hash,
                    patron.role,
                    patron.active,
                ),
                "queue_position": queue_position,
            }
            for (
                reservation,
                book,
                patron,
                queue_position,
                on_loan,
                reserved_count,
            ) in rows
        ]

    def open_counts(self):
        counts = dict(
            db.session.execute(
                db.select(
                    ReservationRecord.status,
                    db.func.count(ReservationRecord.reservation_id),
                )
                .where(ReservationRecord.status.in_(Reservation.OPEN_STATUSES))
                .group_by(ReservationRecord.status)
            ).all()
        )
        return {
            Reservation.WAITING: counts.get(Reservation.WAITING, 0),
            Reservation.READY: counts.get(Reservation.READY, 0),
        }

    def count_open_for_patron(self, patron_id):
        return db.session.scalar(
            db.select(db.func.count(ReservationRecord.reservation_id)).where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
            )
        ) or 0

    def count_ready_for_patron(self, patron_id):
        return db.session.scalar(
            db.select(db.func.count(ReservationRecord.reservation_id)).where(
                ReservationRecord.patron_id == patron_id,
                ReservationRecord.status == Reservation.READY,
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
            active_count = db.session.scalar(
                db.select(db.func.count(LoanRecord.loan_id))
                .where(
                    LoanRecord.book_id == book_id,
                    LoanRecord.returned_at.is_(None),
                )
            ) or 0
            ready_count = db.session.scalar(
                db.select(db.func.count(ReservationRecord.reservation_id)).where(
                    ReservationRecord.book_id == book_id,
                    ReservationRecord.status == Reservation.READY,
                )
            ) or 0
            if book is None or not book.catalog:
                raise ValidationError("This book is no longer in the catalog.")
            if book.kind == "reference":
                raise ValidationError("Reference books can only be read in the library.")
            if (
                book.total_copies <= 0
                or active_count + ready_count < book.total_copies
            ):
                raise ValidationError(
                    "Reservations are only available when all copies are loaned or reserved."
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

    def promote_waiting(self, book_id, commit=True):
        try:
            book = db.session.get(BookRecord, book_id)
            if book is None or not book.catalog:
                return []
            active_count = db.session.scalar(
                db.select(db.func.count(LoanRecord.loan_id)).where(
                    LoanRecord.book_id == book_id,
                    LoanRecord.returned_at.is_(None),
                )
            ) or 0
            ready_count = db.session.scalar(
                db.select(db.func.count(ReservationRecord.reservation_id)).where(
                    ReservationRecord.book_id == book_id,
                    ReservationRecord.status == Reservation.READY,
                )
            ) or 0
            capacity = max(book.total_copies - active_count - ready_count, 0)
            waiting = db.session.execute(
                db.select(ReservationRecord)
                .where(
                    ReservationRecord.book_id == book_id,
                    ReservationRecord.status == Reservation.WAITING,
                )
                .order_by(ReservationRecord.reservation_id)
                .limit(capacity)
            ).scalars()
            promoted = []
            for reservation in waiting:
                reservation.status = Reservation.READY
                promoted.append(self._to_domain(reservation))
                db.session.add(
                    NotificationRecord(
                        user_id=reservation.patron_id,
                        category="loan",
                        title="Reserved book ready",
                        message=f"{book.title} is ready to borrow.",
                        link=f"/books/{book.book_id}",
                        dedupe_key=f"reservation:{reservation.reservation_id}:ready",
                    )
                )
            if commit:
                db.session.commit()
            return promoted
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The reservation queue could not be updated.") from error
        except SQLAlchemyError:
            db.session.rollback()
            raise

    @staticmethod
    def _to_domain(record):
        return Reservation(
            record.reservation_id,
            record.patron_id,
            record.book_id,
            record.status,
            record.created_at,
        )
