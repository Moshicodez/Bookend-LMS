from ..extensions import db


class GenreRecord(db.Model):
    __tablename__ = "genres"

    genre_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    __table_args__ = (
        db.Index("uq_genres_name_casefold", db.func.lower(name), unique=True),
    )
