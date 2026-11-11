from ..extensions import db
from ..constants import UNCATEGORIZED


class GenreRecord(db.Model):
    __tablename__ = "genres"

    genre_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    __table_args__ = (
        db.Index("uq_genres_name_casefold", db.func.lower(name), unique=True),
        db.CheckConstraint(
            db.func.lower(db.func.trim(name)) != UNCATEGORIZED.casefold(),
            name="reserved_virtual_genre",
        ),
    )
