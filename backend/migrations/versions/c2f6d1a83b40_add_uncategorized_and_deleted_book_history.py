"""Support deleted book history and virtual uncategorized genre."""

from alembic import op
import sqlalchemy as sa
from backend.app.constants import UNCATEGORIZED


revision = "c2f6d1a83b40"
down_revision = "9c4a0f1d2b7e"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "books" in inspector.get_table_names():
        op.execute(
            sa.text(
                """
                UPDATE books SET genre = ''
                WHERE genre IS NOT NULL
                  AND lower(trim(genre)) = :genre_name
                """
            ).bindparams(genre_name=UNCATEGORIZED.casefold()),
        )
    if "genres" in inspector.get_table_names():
        op.execute(
            sa.text(
                """
                DELETE FROM genres
                WHERE lower(trim(name)) = :genre_name
                """
            ).bindparams(genre_name=UNCATEGORIZED.casefold()),
        )

    if "books" in inspector.get_table_names():
        with op.batch_alter_table(
            "books",
            table_kwargs={"sqlite_autoincrement": True},
        ) as batch:
            batch.alter_column(
                "genre",
                existing_type=sa.String(length=100),
                nullable=True,
            )
    if "loans" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("loans")}
        with op.batch_alter_table(
            "loans",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch:
            if "book_title" not in columns:
                batch.add_column(
                    sa.Column("book_title", sa.String(length=250), nullable=True)
                )
            if "book_author" not in columns:
                batch.add_column(
                    sa.Column("book_author", sa.String(length=160), nullable=True)
                )
            batch.alter_column(
                "book_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
            foreign_keys = inspector.get_foreign_keys("loans")
            for key in foreign_keys:
                if key["constrained_columns"] == ["book_id"]:
                    batch.drop_constraint(
                        key["name"] or "fk_loans_book_id_books",
                        type_="foreignkey",
                    )
            batch.create_foreign_key(
                "fk_loans_book_id_books",
                "books",
                ["book_id"],
                ["book_id"],
                ondelete="SET NULL",
            )
        op.execute(
            sa.text(
                """
                UPDATE loans
                SET book_title = COALESCE(
                        (SELECT title FROM books WHERE books.book_id = loans.book_id),
                        ''
                    ),
                    book_author = COALESCE(
                        (SELECT author FROM books WHERE books.book_id = loans.book_id),
                        ''
                    )
                WHERE book_title IS NULL OR book_author IS NULL
                """
            )
        )
        with op.batch_alter_table("loans") as batch:
            batch.alter_column(
                "book_title",
                existing_type=sa.String(length=250),
                nullable=False,
                server_default="",
            )
            batch.alter_column(
                "book_author",
                existing_type=sa.String(length=160),
                nullable=False,
                server_default="",
            )
    if "genres" in inspector.get_table_names():
        with op.batch_alter_table("genres") as batch:
            batch.create_check_constraint(
                "reserved_virtual_genre",
                f"lower(trim(name)) != '{UNCATEGORIZED.casefold()}'",
            )

    if "basket_items" not in inspector.get_table_names():
        op.create_table(
            "basket_items",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["book_id"], ["books.book_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "book_id"),
        )


def downgrade():
    op.drop_table("basket_items")
    with op.batch_alter_table("genres") as batch:
        batch.drop_constraint("reserved_virtual_genre", type_="check")
