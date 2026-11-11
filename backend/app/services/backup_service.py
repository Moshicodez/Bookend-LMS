import json
import math
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.exc import SQLAlchemyError

from ..exceptions import ValidationError
from ..extensions import db
from ..models import (
    BookRecord,
    FavoriteRecord,
    FeePaymentRecord,
    GenreRecord,
    LoanRecord,
    NotificationRecord,
    ReservationRecord,
    ReviewRecord,
    UserRecord,
)


BACKUP_FORMAT = "bookend-lms-backup"
BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 20 * 1024 * 1024
BACKUP_RECORDS = (
    BookRecord,
    FavoriteRecord,
    FeePaymentRecord,
    GenreRecord,
    LoanRecord,
    NotificationRecord,
    ReservationRecord,
    ReviewRecord,
    UserRecord,
)
BACKUP_TABLE_NAMES = frozenset(record.__tablename__ for record in BACKUP_RECORDS)


class BackupService:
    @staticmethod
    def create_backup():
        tables = BackupService._tables()
        content = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now().astimezone().isoformat(),
            "tables": {
                table.name: [
                    {
                        column.name: row[column.name]
                        for column in table.columns
                    }
                    for row in db.session.execute(table.select()).mappings()
                ]
                for table in tables
            },
        }
        backup = json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            default=BackupService._serialize_value,
        ).encode("utf-8")
        if len(backup) > MAX_BACKUP_BYTES:
            raise ValidationError("The database backup exceeds the 20 MB limit.")
        return backup

    @staticmethod
    def restore_backup(stream):
        content = stream.read(MAX_BACKUP_BYTES + 1)
        if len(content) > MAX_BACKUP_BYTES:
            raise ValidationError("Backup files must be no larger than 20 MB.")

        try:
            backup = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("The backup file is not valid JSON.") from error

        if (
            not isinstance(backup, dict)
            or set(backup) != {"format", "version", "created_at", "tables"}
            or backup.get("format") != BACKUP_FORMAT
            or type(backup.get("version")) is not int
            or backup.get("version") != BACKUP_VERSION
            or not isinstance(backup.get("created_at"), str)
        ):
            raise ValidationError("This backup format or version is not supported.")

        tables = BackupService._tables()
        table_data = backup.get("tables")
        expected_names = {table.name for table in tables}
        legacy_names = expected_names - {"fee_payments"}
        if (
            not isinstance(table_data, dict)
            or set(table_data) not in (expected_names, legacy_names)
        ):
            raise ValidationError("The backup does not match this database schema.")

        rows_by_table = {
            table.name: BackupService._validated_rows(
                table,
                table_data.get(table.name, []),
            )
            for table in tables
        }

        try:
            for table in reversed(tables):
                db.session.execute(table.delete())
            for table in tables:
                rows = rows_by_table[table.name]
                if rows:
                    db.session.execute(table.insert(), rows)
            db.session.commit()
            db.session.expire_all()
        except SQLAlchemyError as error:
            db.session.rollback()
            raise ValidationError(
                "The backup could not be restored; the existing data was kept."
            ) from error

    @staticmethod
    def _tables():
        tables = db.metadata.sorted_tables
        if {table.name for table in tables} != BACKUP_TABLE_NAMES:
            raise RuntimeError("Backup table registry does not match the database schema.")
        return tables

    @staticmethod
    def _validated_rows(table, rows):
        if not isinstance(rows, list):
            raise ValidationError("The backup contains invalid table data.")

        expected_columns = {column.name for column in table.columns}
        validated = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != expected_columns:
                raise ValidationError("The backup contains invalid table data.")
            validated.append(
                {
                    column.name: BackupService._deserialize_value(
                        column,
                        row[column.name],
                    )
                    for column in table.columns
                }
            )
        return validated

    @staticmethod
    def _serialize_value(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(f"Unsupported backup value: {type(value).__name__}")

    @staticmethod
    def _deserialize_value(column, value):
        if value is None:
            if not column.nullable:
                raise ValidationError("The backup contains a missing required value.")
            return None
        try:
            if isinstance(column.type, DateTime):
                return datetime.fromisoformat(value)
            if isinstance(column.type, Date):
                return date.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("The backup contains an invalid date value.") from error
        if isinstance(column.type, Boolean):
            valid = isinstance(value, bool)
        elif isinstance(column.type, Integer):
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(column.type, Float):
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
        elif isinstance(column.type, String):
            valid = isinstance(value, str)
        else:
            valid = isinstance(value, (str, int, float, bool))
        if not valid:
            raise ValidationError("The backup contains invalid field values.")
        return value