from datetime import date, datetime, timedelta


def to_date(value):
    if value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def today():
    return date.today()


def add_days(start_date, days):
    return start_date + timedelta(days=days)


def days_between(end_date, start_date):
    return (end_date - start_date).days


def format_date(value):
    value = to_date(value)
    return value.isoformat() if value else None