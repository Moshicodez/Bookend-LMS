from ..extensions import db


class BasketRecord(db.Model):
    __tablename__ = "basket_items"

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
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )
