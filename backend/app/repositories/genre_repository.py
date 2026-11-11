from sqlalchemy.exc import IntegrityError

from ..data_structures import GenreTree
from ..exceptions import ValidationError
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.genre_record import GenreRecord
from ..constants import UNCATEGORIZED


class GenreRepository:
    @staticmethod
    def _trimmed_genre():
        return db.func.trim(BookRecord.genre, " \t\n\r\f\v")

    def list_genres(self):
        names = {}
        saved_names = db.session.execute(
            db.select(GenreRecord.name).order_by(db.func.lower(GenreRecord.name))
        ).scalars()
        book_names = db.session.execute(
            db.select(BookRecord.genre)
            .where(
                BookRecord.catalog.is_(True),
                BookRecord.genre.is_not(None),
                self._trimmed_genre() != "",
            )
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
                    db.func.lower(self._trimmed_genre()),
                    db.func.count(BookRecord.book_id),
                )
                .where(
                    BookRecord.genre.is_not(None),
                    self._trimmed_genre() != "",
                )
                .group_by(db.func.lower(self._trimmed_genre()))
            ).all()
        )
        genres = [
            {"name": name, "book_count": counts.get(name.casefold(), 0)}
            for name in self.list_genres()
        ]
        genres.append(
            {
                "name": UNCATEGORIZED,
                "book_count": db.session.scalar(
                    db.select(db.func.count(BookRecord.book_id)).where(
                        db.or_(
                            BookRecord.genre.is_(None),
                            self._trimmed_genre() == "",
                        )
                    )
                ) or 0,
                "system": True,
            }
        )
        return genres

    def books_use_genre(self, name):
        return db.session.scalar(
            db.select(db.func.count(BookRecord.book_id))
            .where(db.func.lower(self._trimmed_genre()) == name.casefold())
        ) or 0

    def add(self, name):
        record = GenreRecord(name=name)
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError(
                "A genre with this name already exists or is reserved."
            ) from error
        return record

    def remove(self, name):
        try:
            count = db.session.execute(
                db.update(BookRecord)
                .where(
                    db.func.lower(self._trimmed_genre()) == name.casefold()
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
