from sqlalchemy.exc import IntegrityError

from ..data_structures import GenreTree
from ..exceptions import ValidationError
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.genre_record import GenreRecord


class GenreRepository:
    def list_genres(self):
        names = {}
        saved_names = db.session.execute(
            db.select(GenreRecord.name).order_by(db.func.lower(GenreRecord.name))
        ).scalars()
        book_names = db.session.execute(
            db.select(BookRecord.genre)
            .where(BookRecord.catalog.is_(True), BookRecord.genre != "")
            .distinct()
            .order_by(db.func.lower(BookRecord.genre))
        ).scalars()
        for name in (*saved_names, *book_names):
            cleaned_name = (name or "").strip()
            if cleaned_name:
                names.setdefault(cleaned_name.casefold(), cleaned_name)
        return GenreTree(names.values()).in_order()

    def list_for_management(self):
        counts = dict(
            db.session.execute(
                db.select(
                    db.func.lower(db.func.trim(BookRecord.genre)),
                    db.func.count(BookRecord.book_id),
                )
                .where(BookRecord.genre != "")
                .group_by(db.func.lower(db.func.trim(BookRecord.genre)))
            ).all()
        )
        return [
            {"name": name, "book_count": counts.get(name.casefold(), 0)}
            for name in self.list_genres()
        ]

    def books_use_genre(self, name):
        return db.session.scalar(
            db.select(db.func.count(BookRecord.book_id))
            .where(db.func.lower(db.func.trim(BookRecord.genre)) == name.casefold())
        ) or 0

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
        try:
            count = db.session.execute(
                db.update(BookRecord)
                .where(
                    db.func.lower(db.func.trim(BookRecord.genre)) == name.casefold()
                )
                .values(genre="")
            ).rowcount
            record = db.session.execute(
                db.select(GenreRecord).where(
                    db.func.lower(GenreRecord.name) == name.casefold()
                )
            ).scalars().first()
            if record is not None:
                db.session.delete(record)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return count
