from ..extensions import db


class BookRecord(db.Model):
    __tablename__ = "books"

    book_id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False, default="standard")
    title = db.Column(db.String(250), nullable=False)
    author = db.Column(db.String(160), nullable=False)
    genre = db.Column(db.String(100), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    cover = db.Column(db.String(255), nullable=True)
    available = db.Column(db.Boolean, nullable=False, default=True)
    catalog = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.CheckConstraint(
            "kind IN ('standard', 'new_release', 'reference')",
            name="valid_book_kind",
        ),
    )
