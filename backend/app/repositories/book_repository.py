from sqlalchemy.exc import IntegrityError

from ..data_structures import BookLinkedList, GenreTree
from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..models.book import Book
from ..models.book_record import BookRecord
from ..models.favorite_record import FavoriteRecord
from ..models.loan_record import LoanRecord
from ..models.review_record import ReviewRecord
from ..models.reservation import Reservation
from ..models.reservation_record import ReservationRecord


class BookRepository:
    @staticmethod
    def _trimmed_genre():
        return db.func.trim(BookRecord.genre, " \t\n\r\f\v")

    def list_genres(self):
        saved_names = db.session.execute(
            db.select(BookRecord.genre)
            .where(
                BookRecord.catalog.is_(True),
                BookRecord.genre.is_not(None),
                self._trimmed_genre() != "",
            )
        ).scalars()
        names = {}
        for name in saved_names:
            cleaned_name = (name or "").strip()
            if cleaned_name:
                names.setdefault(cleaned_name.casefold(), cleaned_name)
        return GenreTree(names.values()).in_order()

    def genre_counts(self):
        rows = db.session.execute(
            db.select(
                db.func.lower(self._trimmed_genre()),
                db.func.count(BookRecord.book_id),
            )
            .where(
                BookRecord.catalog.is_(True),
                BookRecord.genre.is_not(None),
                self._trimmed_genre() != "",
            )
            .group_by(db.func.lower(self._trimmed_genre()))
        ).all()
        return {name: count for name, count in rows}

    def uncategorized_count(self, catalog_only=True):
        statement = db.select(db.func.count(BookRecord.book_id)).where(
            db.or_(
                BookRecord.genre.is_(None),
                self._trimmed_genre() == "",
            )
        )
        if catalog_only:
            statement = statement.where(BookRecord.catalog.is_(True))
        return db.session.scalar(statement) or 0

    def archived_count(self):
        return db.session.scalar(
            db.select(db.func.count(BookRecord.book_id)).where(
                BookRecord.catalog.is_(False),
                db.or_(
                    BookRecord.total_copies > 0,
                    BookRecord.archived_at.is_not(None),
                ),
            )
        ) or 0

    @staticmethod
    def _stock_counts():
        active = (
            db.select(
                LoanRecord.book_id,
                db.func.count(LoanRecord.loan_id).label("active_count"),
            )
            .where(LoanRecord.returned_at.is_(None))
            .group_by(LoanRecord.book_id)
            .subquery()
        )
        reserved = (
            db.select(
                ReservationRecord.book_id,
                db.func.count(ReservationRecord.reservation_id).label(
                    "reserved_count"
                ),
            )
            .where(ReservationRecord.status == Reservation.READY)
            .group_by(ReservationRecord.book_id)
            .subquery()
        )
        return active, reserved

    @classmethod
    def _book_select(cls):
        active, reserved = cls._stock_counts()
        active_count = db.func.coalesce(active.c.active_count, 0)
        reserved_count = db.func.coalesce(reserved.c.reserved_count, 0)
        statement = (
            db.select(BookRecord, active_count, reserved_count)
            .outerjoin(active, active.c.book_id == BookRecord.book_id)
            .outerjoin(reserved, reserved.c.book_id == BookRecord.book_id)
        )
        return statement, active_count, reserved_count

    @staticmethod
    def _active_count_expression():
        return (
            db.select(db.func.count(LoanRecord.loan_id))
            .where(
                LoanRecord.book_id == BookRecord.book_id,
                LoanRecord.returned_at.is_(None),
            )
            .correlate(BookRecord)
            .scalar_subquery()
        )

    @staticmethod
    def _reserved_count_expression():
        return (
            db.select(db.func.count(ReservationRecord.reservation_id))
            .where(
                ReservationRecord.book_id == BookRecord.book_id,
                ReservationRecord.status == Reservation.READY,
            )
            .correlate(BookRecord)
            .scalar_subquery()
        )

    def find_more_in_genre(self, genre, exclude_book_id, limit=4):
        if not genre:
            return []
        statement, _, _ = self._book_select()
        records = db.session.execute(
            statement
            .where(
                BookRecord.catalog.is_(True),
                db.func.lower(BookRecord.genre) == genre.casefold(),
                BookRecord.book_id != exclude_book_id,
            )
            .order_by(BookRecord.title, BookRecord.book_id)
            .limit(limit)
        ).all()
        return [
            self._to_domain_book(record, on_loan, reserved)
            for record, on_loan, reserved in records
        ]

    def search(self, term="", genre="", status="", sort="title", page=1, per_page=12):
        stmt, on_loan_count, reserved_count = self._book_select()
        borrowable_count = (
            BookRecord.total_copies - on_loan_count - reserved_count
        )
        if status == "available":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                borrowable_count > 0,
                BookRecord.kind != "reference",
            )
        elif status == "on_loan":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                on_loan_count > 0,
            )
        elif status == "out_of_stock":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                BookRecord.total_copies == 0,
            )
        elif status == "archived":
            stmt = stmt.where(BookRecord.catalog.is_(False))
        elif status != "all":
            stmt = stmt.where(BookRecord.catalog.is_(True))

        for word in (term or "").split():
            safe = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{safe}%"
            stmt = stmt.where(
                db.or_(
                    BookRecord.title.ilike(pattern, escape="\\"),
                    BookRecord.author.ilike(pattern, escape="\\"),
                    BookRecord.genre.ilike(pattern, escape="\\"),
                )
            )
        normalized_genre = (genre or "").strip().casefold()
        if normalized_genre:
            from ..constants import UNCATEGORIZED_SLUG

            if normalized_genre == UNCATEGORIZED_SLUG:
                stmt = stmt.where(
                    db.or_(
                        BookRecord.genre.is_(None),
                        self._trimmed_genre() == "",
                    )
                )
            else:
                stmt = stmt.where(
                    db.func.lower(self._trimmed_genre())
                    == normalized_genre
                )

        order = {
            "title": BookRecord.title.collate("NOCASE"),
            "author": BookRecord.author.collate("NOCASE"),
            "newest": BookRecord.book_id.desc(),
        }.get(sort)
        if sort == "most_borrowed":
            borrow_counts = (
                db.select(
                    LoanRecord.book_id,
                    db.func.count(LoanRecord.loan_id).label("borrow_count"),
                )
                .group_by(LoanRecord.book_id)
                .subquery()
            )
            stmt = stmt.outerjoin(
                borrow_counts,
                borrow_counts.c.book_id == BookRecord.book_id,
            )
            order = db.func.coalesce(borrow_counts.c.borrow_count, 0).desc()
        elif order is None:
            order = BookRecord.title.collate("NOCASE")

        total = db.session.scalar(
            db.select(db.func.count()).select_from(stmt.subquery())
        ) or 0
        tie_breakers = (
            (BookRecord.title.collate("NOCASE"), BookRecord.book_id)
            if sort == "most_borrowed"
            else (BookRecord.book_id,)
        )
        rows = db.session.execute(
            stmt.order_by(order, *tie_breakers)
            .limit(per_page)
            .offset((max(page, 1) - 1) * per_page)
        ).all()
        return [
            self._to_domain_book(record, on_loan, reserved)
            for record, on_loan, reserved in rows
        ], total

    def create(self, book):
        record = BookRecord(
            kind=book.kind,
            title=book.title,
            author=book.author,
            genre=book.genre,
            description=book.description,
            cover=book.cover,
            available=book.available,
            catalog=book.catalog,
            total_copies=book.total_copies,
        )
        db.session.add(record)
        self._commit()
        return self._to_domain_book(record, 0, 0)

    def find_book(self, book_id):
        book_id = self._valid_id(book_id)
        if book_id is None:
            return None
        statement, _, _ = self._book_select()
        row = db.session.execute(
            statement.where(BookRecord.book_id == book_id)
        ).first()
        return self._to_domain_book(*row) if row else None

    def find_by_title_author(self, title, author):
        statement, _, _ = self._book_select()
        record = db.session.execute(
            statement.where(
                db.func.lower(BookRecord.title) == (title or "").strip().lower(),
                db.func.lower(BookRecord.author) == (author or "").strip().lower(),
            )
        ).first()
        return self._to_domain_book(*record) if record else None

    def find_all(self, include_archived=False):
        statement, _, _ = self._book_select()
        statement = statement.order_by(
            BookRecord.title.collate("NOCASE"),
            BookRecord.book_id,
        )
        if not include_archived:
            statement = statement.where(BookRecord.catalog.is_(True))
        rows = db.session.execute(statement).all()
        return BookLinkedList(
            self._to_domain_book(record, on_loan, reserved)
            for record, on_loan, reserved in rows
        )

    def find_archived(self):
        statement, on_loan_count, _ = self._book_select()
        records = db.session.execute(
            statement.where(
                BookRecord.catalog.is_(False),
                db.or_(
                    BookRecord.total_copies > 0,
                    BookRecord.archived_at.is_not(None),
                ),
                on_loan_count == 0,
            )
            .order_by(
                BookRecord.archived_at.desc().nullslast(),
                BookRecord.book_id.desc(),
            )
        ).all()
        return BookLinkedList(
            self._to_domain_book(record, on_loan, reserved)
            for record, on_loan, reserved in records
        )

    def delete_archived(self, book_ids):
        from ..models.basket_record import BasketRecord
        from ..models.reservation_record import ReservationRecord

        records = list(
            db.session.execute(
                db.select(BookRecord)
                .where(BookRecord.book_id.in_(book_ids))
                .order_by(BookRecord.book_id)
            ).scalars()
        )
        found_ids = {record.book_id for record in records}
        if found_ids != set(book_ids):
            missing_id = next(iter(set(book_ids) - found_ids))
            raise NotFoundError(f"Book #{missing_id} not found.")
        by_id = {record.book_id: record for record in records}
        for book_id in book_ids:
            record = by_id[book_id]
            if record.catalog:
                raise ValidationError(
                    f"{record.title}: Archive the book first."
                )
            active_loan = db.session.scalar(
                db.select(LoanRecord.loan_id)
                .where(
                    LoanRecord.book_id == book_id,
                    LoanRecord.returned_at.is_(None),
                )
                .limit(1)
            )
            open_reservation = db.session.scalar(
                db.select(ReservationRecord.reservation_id)
                .where(
                    ReservationRecord.book_id == book_id,
                    ReservationRecord.status.in_(Reservation.OPEN_STATUSES),
                )
                .limit(1)
            )
            if active_loan:
                raise ValidationError(
                    f"{record.title}: Return the book or cancel the reservations first."
                )
            if open_reservation:
                raise ValidationError(
                    f"{record.title}: Return the book or cancel the reservations first."
                )

        covers = {}
        for record in records:
            book_id = record.book_id
            covers[book_id] = record.cover
            db.session.execute(
                db.delete(FavoriteRecord).where(FavoriteRecord.book_id == book_id)
            )
            db.session.execute(
                db.delete(ReviewRecord).where(ReviewRecord.book_id == book_id)
            )
            db.session.execute(
                db.delete(BasketRecord).where(BasketRecord.book_id == book_id)
            )
            db.session.execute(
                db.delete(ReservationRecord).where(
                    ReservationRecord.book_id == book_id
                )
            )
            db.session.delete(record)
        db.session.flush()
        return [
            {"book_id": book_id, "title": by_id[book_id].title,
             "cover": covers[book_id]}
            for book_id in book_ids
        ]

    @staticmethod
    def cover_is_used(filename):
        if not filename:
            return False
        return db.session.scalar(
            db.select(BookRecord.book_id)
            .where(BookRecord.cover == filename)
            .limit(1)
        ) is not None

    def update_book(self, book):
        book_id = self._valid_id(book.book_id)
        if book_id is None:
            raise NotFoundError("Book not found.")
        record = db.session.get(BookRecord, book_id)
        if record is None:
            raise NotFoundError("Book not found.")
        record.kind = book.kind
        record.title = book.title
        record.author = book.author
        record.genre = book.genre
        record.description = book.description
        record.cover = book.cover
        record.available = book.available
        record.catalog = book.catalog
        record.archived_at = book.archived_at
        if book.total_copies != record.total_copies:
            result = db.session.execute(
                db.update(BookRecord)
                .where(
                    BookRecord.book_id == book_id,
                    book.total_copies
                    >= self._active_count_expression()
                    + self._reserved_count_expression(),
                )
                .values(total_copies=book.total_copies)
            )
            if result.rowcount != 1:
                db.session.rollback()
                raise ValidationError(
                    "Copies on loan or reserved cannot be removed from stock."
                )
            record.total_copies = book.total_copies
        self._commit()
        return book

    @staticmethod
    def _valid_id(book_id):
        try:
            return int(book_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_domain_book(record, on_loan=0, reserved=0):
        total_copies = record.total_copies
        return Book.create(
            record.kind,
            record.book_id,
            record.title,
            record.author,
            record.genre,
            record.description,
            available=total_copies > on_loan,
            catalog=record.catalog,
            cover=record.cover,
            archived_at=record.archived_at,
            total_copies=total_copies,
            available_copies=max(total_copies - on_loan - reserved, 0),
            on_loan_copies=on_loan,
            reserved_copies=reserved,
        )

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The book could not be saved.") from error