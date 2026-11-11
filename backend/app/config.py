import os

from dotenv import load_dotenv


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def _database_url():
    database_url = os.environ.get("DATABASE_URL", "sqlite:///bookend.db")
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


COVER_COLORS = ("#a44235", "#476d57", "#536779", "#98713f", "#695676", "#9a5947")


class Config:
    SECRET_KEY = os.environ.get("BOOKEND_SECRET_KEY", "dev_only_change_me")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LOAN_DAYS = 14
    MAX_ACTIVE_LOANS = 5
    DAILY_LATE_FEE = 0.50
    LOSS_FEE = 2500.00