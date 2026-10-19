from ..extensions import db


class LoanRecord(db.Model):
    __tablename__ = "loans"

    loan_id = db.Column(db.Integer, primary_key=True)
    patron_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    book_id = db.Column(
        db.Integer,
        db.ForeignKey("books.book_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    borrowed_at = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.Date, nullable=True)
    fee_paid = db.Column(db.Boolean, nullable=False, default=False)
    lost = db.Column(db.Boolean, nullable=False, default=False)
    loss_fee = db.Column(db.Float, nullable=False, default=0)
    loss_paid = db.Column(db.Boolean, nullable=False, default=False)
