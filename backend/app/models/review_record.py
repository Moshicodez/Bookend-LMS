from ..extensions import db


class ReviewRecord(db.Model):
    __tablename__ = "reviews"

    review_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.book_id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "book_id", name="one_review_per_user_book"),
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="valid_review_rating"),
    )
