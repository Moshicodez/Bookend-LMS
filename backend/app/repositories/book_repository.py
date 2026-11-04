from sqlalchemy.exc import IntegrityError

from ..data_structures import BookLinkedList, GenreTree
from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..models.book import Book
from ..models.book_record import BookRecord
from ..models.loan_record import LoanRecord


class BookRepository:
    @staticmethod
    def _active_loan_count_expression():
        return (
            db.select(db.func.count(LoanRecord.loan_id))
            .where(
                LoanRecord.book_id == BookRecord.book_id,
                LoanRecord.returned_at.is_(None),
                LoanRecord.lost.is_(False),
            )
            .scalar_subquery()
        )

    @staticmethod
    def _active_counts(book_ids):
        if not book_ids:
            return {}
        rows = db.session.execute(
            db.select(LoanRecord.book_id, db.func.count(LoanRecord.loan_id))
            .where(
                LoanRecord.book_id.in_(book_ids),
                LoanRecord.returned_at.is_(None),
                LoanRecord.lost.is_(False),
            )
            .group_by(LoanRecord.book_id)
        )
        return {book_id: count for book_id, count in rows}

    def list_genres(self):
        names = db.session.execute(
            db.select(BookRecord.genre)
            .where(BookRecord.catalog.is_(True), BookRecord.genre != "")
            .distinct()
        ).scalars()
        return GenreTree(names).in_order()

    def genre_counts(self):
        rows = db.session.execute(
            db.select(
                db.func.lower(BookRecord.genre),
                db.func.count(BookRecord.book_id),
            )
            .where(BookRecord.catalog.is_(True), BookRecord.genre != "")
            .group_by(db.func.lower(BookRecord.genre))
        )
        return {genre: count for genre, count in rows}

    @staticmethod
    def _book_collection(records):
        records = list(records)
        borrowed_counts = BookRepository._active_counts(
            [record.book_id for record in records]
        )
        return BookLinkedList(
            BookRepository._to_domain_book(
                record, borrowed_counts.get(record.book_id, 0)
            )
            for record in records
        )

    def find_more_in_genre(self, genre, exclude_book_id, limit=4):
        if not genre:
            return []
        records = db.session.execute(
            db.select(BookRecord)
            .where(
                BookRecord.catalog.is_(True),
                db.func.lower(BookRecord.genre) == genre.casefold(),
                BookRecord.book_id != exclude_book_id,
            )
            .order_by(BookRecord.title, BookRecord.book_id)
            .limit(limit)
        ).scalars()
        return self._book_collection(records)

    def search(self, term="", genre="", status="", sort="title", page=1, per_page=12):
        stmt = db.select(BookRecord)
        active_loan_count = self._active_loan_count_expression()
        has_stock = BookRecord.total_stock > active_loan_count
        if status == "available":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                has_stock,
                BookRecord.kind != "reference",
            )
        elif status == "on_loan":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                BookRecord.total_stock <= active_loan_count,
                active_loan_count > 0,
            )
        elif status == "unavailable":
            stmt = stmt.where(
                BookRecord.catalog.is_(True),
                BookRecord.kind != "reference",
                BookRecord.total_stock <= active_loan_count,
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
        if genre:
            stmt = stmt.where(db.func.lower(BookRecord.genre) == genre.casefold())

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
        ).scalars()
        return list(self._book_collection(rows)), total

    def create(self, book):
        record = BookRecord(
            kind=book.kind,
            title=book.title,
            author=book.author,
            genre=book.genre,
            description=book.description,
            cover=book.cover,
            total_stock=book.total_stock,
            available=book.total_stock > book.borrowed_stock,
            catalog=book.catalog,
        )
        db.session.add(record)
        self._commit()
        return self._to_domain_book(record)

    def find_book(self, book_id):
        book_id = self._valid_id(book_id)
        if book_id is None:
            return None
        record = db.session.get(BookRecord, book_id)
        return self._to_domain_book(
            record, self._active_counts([book_id]).get(book_id, 0)
        ) if record else None

    def find_by_title_author(self, title, author):
        record = db.session.execute(
            db.select(BookRecord).where(
                db.func.lower(BookRecord.title) == (title or "").strip().lower(),
                db.func.lower(BookRecord.author) == (author or "").strip().lower(),
            )
        ).scalars().first()
        return self._to_domain_book(record) if record else None

    def find_all(self, include_archived=False):
        statement = db.select(BookRecord).order_by(
            BookRecord.title.collate("NOCASE"),
            BookRecord.book_id,
        )
        if not include_archived:
            statement = statement.where(BookRecord.catalog.is_(True))
        records = db.session.execute(statement).scalars()
        return self._book_collection(records)

    def find_archived(self):
        records = db.session.execute(
            db.select(BookRecord)
            .where(
                BookRecord.catalog.is_(False),
                BookRecord.total_stock > 0,
            )
            .order_by(BookRecord.title, BookRecord.book_id)
        ).scalars()
        return self._book_collection(records)

    def update_book(self, book):
        book_id = self._valid_id(book.book_id)
        if book_id is None:
            raise NotFoundError("Book not found.")
        record = db.session.get(BookRecord, book_id)
        if record is None:
            raise NotFoundError("Book not found.")
        try:
            active_count = (
                db.select(db.func.count(LoanRecord.loan_id))
                .where(
                    LoanRecord.book_id == BookRecord.book_id,
                    LoanRecord.returned_at.is_(None),
                    LoanRecord.lost.is_(False),
                )
                .scalar_subquery()
            )
            result = db.session.execute(
                db.update(BookRecord)
                .where(
                    BookRecord.book_id == book_id,
                    book.total_stock >= active_count,
                )
                .values(
                    kind=book.kind,
                    title=book.title,
                    author=book.author,
                    genre=book.genre,
                    description=book.description,
                    cover=book.cover,
                    total_stock=book.total_stock,
                    available=book.total_stock > active_count,
                    catalog=book.catalog,
                )
            )
            if result.rowcount != 1:
                borrowed_count = self._active_counts([book_id]).get(book_id, 0)
                if book.total_stock < borrowed_count:
                    raise ValidationError(
                        f"Total stock cannot be lower than the {borrowed_count} copies currently on loan."
                    )
                raise NotFoundError("Book not found.")
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The book could not be saved.") from error
        except ValidationError:
            db.session.rollback()
            raise
        except NotFoundError:
            db.session.rollback()
            raise
        return book

    @staticmethod
    def _valid_id(book_id):
        try:
            return int(book_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_domain_book(record, borrowed_stock=0):
        return Book.create(
            record.kind,
            record.book_id,
            record.title,
            record.author,
            record.genre,
            record.description,
            available=record.available and record.total_stock > borrowed_stock,
            catalog=record.catalog,
            cover=record.cover,
            total_stock=record.total_stock,
            borrowed_stock=borrowed_stock,
        )

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The book could not be saved.") from error