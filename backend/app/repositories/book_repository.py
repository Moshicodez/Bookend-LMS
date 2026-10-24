from sqlalchemy.exc import IntegrityError

from ..exceptions import NotFoundError, ValidationError
from ..extensions import db
from ..models.book import Book
from ..models.book_record import BookRecord


class BookRepository:
    def list_genres(self):
        return list(
            db.session.execute(
                db.select(BookRecord.genre)
                .where(BookRecord.catalog.is_(True), BookRecord.genre != "")
                .distinct()
                .order_by(BookRecord.genre.collate("NOCASE"))
            ).scalars()
        )

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
        )
        db.session.add(record)
        self._commit()
        return self._to_domain_book(record)

    def find_book(self, book_id):
        book_id = self._valid_id(book_id)
        if book_id is None:
            return None
        record = db.session.get(BookRecord, book_id)
        return self._to_domain_book(record) if record else None

    def find_by_title_author(self, title, author):
        record = db.session.execute(
            db.select(BookRecord).where(
                db.func.lower(BookRecord.title) == (title or "").strip().lower(),
                db.func.lower(BookRecord.author) == (author or "").strip().lower(),
            )
        ).scalars().first()
        return self._to_domain_book(record) if record else None

    def find_all(self, include_archived=False):
        statement = db.select(BookRecord).order_by(BookRecord.title, BookRecord.book_id)
        if not include_archived:
            statement = statement.where(BookRecord.catalog.is_(True))
        records = db.session.execute(statement).scalars()
        return [self._to_domain_book(record) for record in records]

    def find_archived(self):
        records = db.session.execute(
            db.select(BookRecord)
            .where(BookRecord.catalog.is_(False), BookRecord.available.is_(True))
            .order_by(BookRecord.title, BookRecord.book_id)
        ).scalars()
        return [self._to_domain_book(record) for record in records]

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
        self._commit()
        return book

    @staticmethod
    def _valid_id(book_id):
        try:
            return int(book_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_domain_book(record):
        return Book.create(
            record.kind,
            record.book_id,
            record.title,
            record.author,
            record.genre,
            record.description,
            available=record.available,
            catalog=record.catalog,
            cover=record.cover,
        )

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("The book could not be saved.") from error