import os
import sqlite3

from ..extensions import db
from ..models import BookRecord, GenreRecord


class CatalogSeedService:
    def seed_from_sqlite(self, source_path):
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"Catalog source database not found: {source_path}")

        source_uri = f"file:{os.path.abspath(source_path).replace(os.sep, '/')}?mode=ro"
        source = sqlite3.connect(source_uri, uri=True)
        source.row_factory = sqlite3.Row
        row_counts = {}
        try:
            for model in (GenreRecord, BookRecord):
                table = model.__table__
                primary_key = next(iter(table.primary_key.columns)).name
                try:
                    rows = source.execute(
                        f'SELECT * FROM "{table.name}" ORDER BY "{primary_key}"'
                    ).fetchall()
                except sqlite3.OperationalError as error:
                    raise ValueError(
                        f"Catalog source is missing the {table.name} table."
                    ) from error

                for row in rows:
                    db.session.merge(model(**dict(row)))
                row_counts[table.name] = len(rows)

            db.session.commit()
            if db.engine.dialect.name == "postgresql":
                for table in (GenreRecord.__table__, BookRecord.__table__):
                    primary_key = next(iter(table.primary_key.columns)).name
                    db.session.execute(
                        db.text(
                            "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                            f"COALESCE(MAX({primary_key}), 1), MAX({primary_key}) IS NOT NULL) "
                            f"FROM {table.name}"
                        ),
                        {
                            "table_name": table.name,
                            "column_name": primary_key,
                        },
                    )
                db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        finally:
            source.close()

        return row_counts
