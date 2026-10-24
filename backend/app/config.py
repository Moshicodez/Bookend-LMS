import os


COVER_COLORS = ("#a44235", "#476d57", "#536779", "#98713f", "#695676", "#9a5947")


class Config:
    SECRET_KEY = os.environ.get("BOOKEND_SECRET_KEY", "dev_only_change_me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "BOOKEND_DATABASE_URL",
        "sqlite:///bookend.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LOAN_DAYS = 14
    MAX_ACTIVE_LOANS = 5
    DAILY_LATE_FEE = 0.50
    LOSS_FEE = 25.00