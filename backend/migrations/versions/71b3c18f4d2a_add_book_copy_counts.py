"""Add inventory counts to catalog books."""

from alembic import op
import sqlalchemy as sa


revision = "71b3c18f4d2a"
down_revision = "66d9be0a3eb0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "books",
        sa.Column("total_copies", sa.Integer(), server_default="1", nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE books
            SET total_copies = CASE
                WHEN available = 1 THEN 1
                WHEN EXISTS (
                    SELECT 1 FROM loans
                    WHERE loans.book_id = books.book_id
                      AND loans.returned_at IS NULL
                ) THEN 1
                WHEN EXISTS (
                    SELECT 1 FROM loans
                    WHERE loans.book_id = books.book_id
                      AND loans.lost = 1
                ) THEN 0
                ELSE 1
            END
            """
        )
    )
    with op.batch_alter_table("books") as batch_op:
        batch_op.create_check_constraint(
            "nonnegative_book_copies",
            "total_copies >= 0",
        )


def downgrade():
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_constraint("nonnegative_book_copies", type_="check")
    op.drop_column("books", "total_copies")
