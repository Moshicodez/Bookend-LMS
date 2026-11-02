from ..extensions import db


class NotificationRecord(db.Model):
    __tablename__ = "notifications"

    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = db.Column(db.String(30), nullable=False, default="general")
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    dedupe_key = db.Column(db.String(160), nullable=True, unique=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        index=True,
    )
    read_at = db.Column(db.DateTime, nullable=True)
