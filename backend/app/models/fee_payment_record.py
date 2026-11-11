from ..extensions import db


class FeePaymentRecord(db.Model):
    __tablename__ = "fee_payments"

    payment_id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(
        db.Integer,
        db.ForeignKey("loans.loan_id", ondelete="RESTRICT"),
        nullable=False,
    )
    fee_type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    confirmed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    receipt_no = db.Column(db.String(40), nullable=True)
    note = db.Column(db.String(200), nullable=True)
    voided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    voided_by = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    void_reason = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        db.CheckConstraint("fee_type IN ('late', 'loss')", name="valid_fee_type"),
        db.Index(
            "ix_fee_payments_loan_id_fee_type",
            "loan_id",
            "fee_type",
        ),
        db.Index(
            "uq_fee_payments_active_loan_type",
            "loan_id",
            "fee_type",
            unique=True,
            sqlite_where=db.text("voided_at IS NULL"),
            postgresql_where=db.text("voided_at IS NULL"),
        ),
    )
