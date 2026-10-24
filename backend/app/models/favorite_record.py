from ..extensions import db


class FavoriteRecord(db.Model):
    __tablename__ = "favorites"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.book_id", ondelete="CASCADE"),
        primary_key=True,
    )
