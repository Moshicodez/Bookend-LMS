from sqlalchemy.exc import IntegrityError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.genre_record import GenreRecord


class GenreRepository:
    def list_genres(self):
        names = {}
        saved_names = db.session.execute(
            db.select(GenreRecord.name).order_by(GenreRecord.name.collate("NOCASE"))
        ).scalars()
        book_names = db.session.execute(
            db.select(BookRecord.genre)
            .where(BookRecord.catalog.is_(True), BookRecord.genre != "")
            .distinct()
            .order_by(BookRecord.genre.collate("NOCASE"))
        ).scalars()
        for name in (*saved_names, *book_names):
            cleaned_name = (name or "").strip()
            if cleaned_name:
                names.setdefault(cleaned_name.casefold(), cleaned_name)
        return sorted(names.values(), key=str.casefold)

    def list_for_management(self):
        return [
            {
                "name": name,
                "in_use": self.books_use_genre(name),
            }
            for name in self.list_genres()
        ]

    def books_use_genre(self, name):
        return db.session.scalar(
            db.select(BookRecord.book_id)
            .where(db.func.lower(db.func.trim(BookRecord.genre)) == name.casefold())
            .limit(1)
        ) is not None

    def add(self, name):
        record = GenreRecord(name=name)
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError("A genre with this name already exists.") from error
        return record

    def remove(self, name):
        record = db.session.execute(
            db.select(GenreRecord).where(
                db.func.lower(GenreRecord.name) == name.casefold()
            )
        ).scalars().first()
        if record is None:
            return False
        db.session.delete(record)
        db.session.commit()
        return True
