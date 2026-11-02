class Reservation:
    WAITING = "waiting"
    READY = "ready"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    OPEN_STATUSES = (WAITING, READY)

    def __init__(
        self,
        reservation_id,
        patron_id,
        book_id,
        status,
        created_at,
    ):
        self.reservation_id = reservation_id
        self.patron_id = patron_id
        self.book_id = book_id
        self.status = status
        self.created_at = created_at
