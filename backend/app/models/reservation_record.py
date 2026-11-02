from ..extensions import db


class ReservationRecord(db.Model):
    __tablename__ = "reservations"

    reservation_id = db.Column(db.Integer, primary_key=True)
    patron_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.book_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default="waiting")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('waiting', 'ready', 'fulfilled', 'cancelled')",
            name="valid_reservation_status",
        ),
        db.Index("ix_reservations_book_queue", "book_id", "status", "reservation_id"),
        db.Index("ix_reservations_patron_status", "patron_id", "status"),
    )
