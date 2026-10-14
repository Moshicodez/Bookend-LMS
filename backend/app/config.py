import os

SECRET_KEY = os.environ.get("BOOKEND_SECRET_KEY", "dev_only_change_me")
DATABASE = "bookend.db"
STAFF_CODE = "B0ok3nd Nvr Ends!"

LOAN_DAYS = 14
MAX_ACTIVE_LOANS = 5
DAILY_LATE_FEE = 0.50
LOSS_FEE = 25.00