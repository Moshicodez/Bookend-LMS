"""Add the fee payment ledger."""

from alembic import op
import sqlalchemy as sa


revision = "9c4a0f1d2b7e"
down_revision = "71b3c18f4d2a"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("fee_payments"):
        op.create_table(
            "fee_payments",
            sa.Column("payment_id", sa.Integer(), primary_key=True),
            sa.Column(
                "loan_id",
                sa.Integer(),
                sa.ForeignKey("loans.loan_id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("fee_type", sa.String(length=10), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column(
                "confirmed_by",
                sa.Integer(),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("receipt_no", sa.String(length=40), nullable=True),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "voided_by",
                sa.Integer(),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("void_reason", sa.String(length=200), nullable=True),
            sa.CheckConstraint("fee_type IN ('late', 'loss')", name="valid_fee_type"),
        )
        op.create_index(
            "ix_fee_payments_loan_id_fee_type",
            "fee_payments",
            ["loan_id", "fee_type"],
        )
        op.create_index(
            "uq_fee_payments_active_loan_type",
            "fee_payments",
            ["loan_id", "fee_type"],
            unique=True,
            postgresql_where=sa.text("voided_at IS NULL"),
            sqlite_where=sa.text("voided_at IS NULL"),
        )

    if bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT loans.loan_id, 'late',
                    ROUND(MAX(0, julianday(COALESCE(returned_at, CURRENT_DATE))
                        - julianday(due_date)) * 0.5, 2),
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans
                WHERE fee_paid = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments
                    WHERE fee_payments.loan_id = loans.loan_id
                      AND fee_payments.fee_type = 'late'
                      AND fee_payments.voided_at IS NULL
                  )
                """
            )
        )
        op.execute(
            sa.text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT loans.loan_id, 'loss',
                    CASE WHEN loss_fee > 0 THEN loss_fee ELSE 2500.0 END,
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans
                WHERE loss_paid = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments
                    WHERE fee_payments.loan_id = loans.loan_id
                      AND fee_payments.fee_type = 'loss'
                      AND fee_payments.voided_at IS NULL
                  )
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT l.loan_id, 'late',
                    ROUND(GREATEST(0, COALESCE(l.returned_at, CURRENT_DATE) - l.due_date) * 0.5, 2),
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans l
                WHERE l.fee_paid = TRUE
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments p
                    WHERE p.loan_id = l.loan_id AND p.fee_type = 'late'
                      AND p.voided_at IS NULL
                  )
                """
            )
        )
        op.execute(
            sa.text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT l.loan_id, 'loss',
                    CASE WHEN l.loss_fee > 0 THEN l.loss_fee ELSE 2500.0 END,
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans l
                WHERE l.loss_paid = TRUE
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments p
                    WHERE p.loan_id = l.loan_id AND p.fee_type = 'loss'
                      AND p.voided_at IS NULL
                  )
                """
            )
        )


def downgrade():
    op.drop_index("uq_fee_payments_active_loan_type", table_name="fee_payments")
    op.drop_index("ix_fee_payments_loan_id_fee_type", table_name="fee_payments")
    op.drop_table("fee_payments")
