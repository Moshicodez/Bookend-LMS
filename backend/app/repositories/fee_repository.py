from datetime import date, datetime

from sqlalchemy import case, cast, func, literal, select, union_all, update
from sqlalchemy.orm import aliased

from ..config import Config
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.fee_payment_record import FeePaymentRecord
from ..models.loan_record import LoanRecord
from ..models.user_record import UserRecord
from ..utils.search import escape_like


class FeeRepository:
    PAGE_SIZE = 20

    def summary(self, current_date=None):
        current_date = current_date or date.today()
        lines = self._fee_lines(current_date).subquery()
        unpaid = lines.c.paid.is_(False)
        next_month = (
            date(current_date.year + 1, 1, 1)
            if current_date.month == 12
            else date(current_date.year, current_date.month + 1, 1)
        )
        collected = db.session.scalar(
            select(func.coalesce(func.sum(FeePaymentRecord.amount), 0.0)).where(
                FeePaymentRecord.voided_at.is_(None),
                FeePaymentRecord.confirmed_at >= datetime(
                    current_date.year, current_date.month, 1
                ),
                FeePaymentRecord.confirmed_at < datetime(
                    next_month.year,
                    next_month.month,
                    next_month.day,
                ),
            )
        ) or 0
        totals = db.session.execute(
            select(
                func.coalesce(func.sum(case((unpaid, lines.c.amount), else_=0)), 0),
                func.count(func.distinct(case((unpaid, lines.c.patron_id)))),
                func.coalesce(
                    func.sum(case((unpaid & (lines.c.fee_type == "late"), lines.c.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((unpaid & (lines.c.fee_type == "loss"), lines.c.amount), else_=0)),
                    0,
                ),
            )
        ).one()
        return {
            "outstanding": round(float(totals[0]), 2),
            "members": int(totals[1]),
            "late": round(float(totals[2]), 2),
            "loss": round(float(totals[3]), 2),
            "collected_month": round(float(collected), 2),
        }

    def list_members(self, status, fee_type, search, sort, page, current_date=None):
        current_date = current_date or date.today()
        lines = self._fee_lines(current_date).subquery()
        query = select(
            lines.c.patron_id,
            func.coalesce(func.sum(case((lines.c.paid.is_(False), lines.c.amount), else_=0)), 0).label("amount_owed"),
            func.max(case((lines.c.paid.is_(False), lines.c.days_overdue))).label("days_overdue"),
        )
        if status == "outstanding":
            query = query.where(lines.c.paid.is_(False), lines.c.amount > 0)
        elif status == "paid":
            query = query.where(lines.c.paid.is_(True))
        if fee_type in {"late", "loss"}:
            query = query.where(lines.c.fee_type == fee_type)
        if search:
            term = f"%{escape_like(search.strip())}%"
            query = query.where(self._search_filter(lines, term))
        grouped = query.group_by(lines.c.patron_id).subquery()
        total = db.session.scalar(select(func.count()).select_from(grouped)) or 0
        sort_column = {
            "amount": grouped.c.amount_owed.desc(),
            "overdue": grouped.c.days_overdue.desc().nullslast(),
            "name": UserRecord.username.asc(),
        }[sort]
        offset = (page - 1) * self.PAGE_SIZE
        users = list(
            db.session.execute(
                select(
                    UserRecord.user_id,
                    UserRecord.username,
                    UserRecord.email,
                    grouped.c.amount_owed,
                    grouped.c.days_overdue,
                )
                .join(grouped, grouped.c.patron_id == UserRecord.user_id)
                .order_by(sort_column, UserRecord.username.asc())
                .offset(offset)
                .limit(self.PAGE_SIZE)
            ).mappings()
        )
        member_ids = [row["user_id"] for row in users]
        fee_lines = self.lines_for_members(
            member_ids,
            status,
            fee_type,
            current_date,
            search,
        )
        grouped_lines = {}
        for line in fee_lines:
            grouped_lines.setdefault(line["patron_id"], []).append(line)
        return {
            "members": [
                {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"],
                    "amount_owed": round(float(row["amount_owed"]), 2),
                    "days_overdue": row["days_overdue"] or 0,
                    "fees": grouped_lines.get(row["user_id"], []),
                }
                for row in users
            ],
            "total": total,
            "page": page,
            "pages": max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE),
        }

    def members_with_outstanding_count(self, current_date=None):
        lines = self._fee_lines(current_date or date.today()).subquery()
        return db.session.scalar(
            select(func.count(func.distinct(lines.c.patron_id))).where(
                lines.c.paid.is_(False),
                lines.c.amount > 0,
            )
        ) or 0

    def collected_total(self):
        return float(
            db.session.scalar(
                select(func.coalesce(func.sum(FeePaymentRecord.amount), 0.0)).where(
                    FeePaymentRecord.voided_at.is_(None)
                )
            )
            or 0
        )

    def lines_for_members(
        self,
        member_ids,
        status="all",
        fee_type="all",
        current_date=None,
        search="",
    ):
        if not member_ids:
            return []
        lines = self._fee_lines(current_date or date.today()).subquery()
        query = select(lines).where(lines.c.patron_id.in_(member_ids))
        if status == "outstanding":
            query = query.where(lines.c.paid.is_(False), lines.c.amount > 0)
        elif status == "paid":
            query = query.where(lines.c.paid.is_(True))
        if fee_type in {"late", "loss"}:
            query = query.where(lines.c.fee_type == fee_type)
        if search:
            query = query.where(
                self._search_filter(
                    lines,
                    f"%{escape_like(search.strip())}%",
                )
            )
        return list(
            db.session.execute(
                query.order_by(lines.c.due_date, lines.c.loan_id)
            ).mappings()
        )

    def fee_line(self, loan_id, fee_type, current_date=None):
        lines = self._fee_lines(current_date or date.today()).subquery()
        return db.session.execute(
            select(lines).where(
                lines.c.loan_id == loan_id,
                lines.c.fee_type == fee_type,
            )
        ).mappings().one_or_none()

    @staticmethod
    def find_loan_record(loan_id):
        return db.session.get(LoanRecord, loan_id)

    @staticmethod
    def find_member(member_id):
        return db.session.get(UserRecord, member_id)

    @staticmethod
    def has_active_payment(loan_id, fee_type):
        return db.session.scalar(
            select(FeePaymentRecord.payment_id).where(
                FeePaymentRecord.loan_id == loan_id,
                FeePaymentRecord.fee_type == fee_type,
                FeePaymentRecord.voided_at.is_(None),
            )
        ) is not None

    @staticmethod
    def record_payment(
        loan_id,
        fee_type,
        amount,
        librarian_id,
        receipt_no,
        note,
        confirmed_at,
    ):
        flag = (
            LoanRecord.fee_paid
            if fee_type == "late"
            else LoanRecord.loss_paid
        )
        conditions = [flag.is_(False)]
        if fee_type == "late":
            conditions.extend(
                [LoanRecord.returned_at.is_not(None), LoanRecord.lost.is_(False)]
            )
        else:
            conditions.append(LoanRecord.lost.is_(True))
        updated = db.session.execute(
            update(LoanRecord)
            .where(LoanRecord.loan_id == loan_id, *conditions)
            .values({flag.key: True})
        )
        if updated.rowcount != 1:
            return None
        payment = FeePaymentRecord(
            loan_id=loan_id,
            fee_type=fee_type,
            amount=amount,
            confirmed_by=librarian_id,
            confirmed_at=confirmed_at,
            receipt_no=receipt_no,
            note=note,
        )
        db.session.add(payment)
        db.session.flush()
        return payment

    @staticmethod
    def commit():
        db.session.commit()

    @staticmethod
    def rollback():
        db.session.rollback()

    def payment_details_for_loans(self, loan_ids):
        if not loan_ids:
            return {}
        payment = aliased(FeePaymentRecord)
        rows = db.session.execute(
            select(
                payment.loan_id,
                payment.fee_type,
                payment.amount,
                payment.confirmed_by,
                payment.confirmed_at,
                payment.receipt_no,
                UserRecord.username.label("confirmer"),
            )
            .outerjoin(UserRecord, UserRecord.user_id == payment.confirmed_by)
            .where(
                payment.loan_id.in_(loan_ids),
                payment.voided_at.is_(None),
            )
        ).mappings()
        return {(row["loan_id"], row["fee_type"]): row for row in rows}

    @staticmethod
    def _fee_lines(current_date):
        payment = aliased(FeePaymentRecord)
        patron = aliased(UserRecord)
        confirmer = aliased(UserRecord)
        late_days = FeeRepository._days_between(
            func.coalesce(LoanRecord.returned_at, current_date),
            LoanRecord.due_date,
        )
        positive_late_days = case((late_days > 0, late_days), else_=0)
        late_amount = case(
            (LoanRecord.lost.is_(True), 0.0),
            else_=func.round(
                positive_late_days * Config.DAILY_LATE_FEE,
                2,
            ),
        )
        late_query = (
            select(
                LoanRecord.patron_id.label("patron_id"),
                LoanRecord.loan_id.label("loan_id"),
                LoanRecord.book_id.label("book_id"),
                func.coalesce(BookRecord.title, LoanRecord.book_title).label("book_title"),
                LoanRecord.book_id.is_(None).label("deleted_book"),
                literal("late").label("fee_type"),
                case(
                    (payment.payment_id.is_not(None), payment.amount),
                    else_=late_amount,
                ).label("amount"),
                payment.payment_id.is_not(None).label("paid"),
                LoanRecord.due_date.label("due_date"),
                positive_late_days.label("days_overdue"),
                LoanRecord.returned_at.label("returned_at"),
                payment.payment_id.label("payment_id"),
                payment.confirmed_at.label("confirmed_at"),
                payment.confirmed_by.label("confirmed_by"),
                payment.receipt_no.label("receipt_no"),
                payment.note.label("note"),
                confirmer.username.label("confirmer"),
            )
            .outerjoin(BookRecord, BookRecord.book_id == LoanRecord.book_id)
            .join(patron, patron.user_id == LoanRecord.patron_id)
            .outerjoin(
                payment,
                (payment.loan_id == LoanRecord.loan_id)
                & (payment.fee_type == "late")
                & payment.voided_at.is_(None),
            )
            .where((late_amount > 0) | payment.payment_id.is_not(None))
        )
        late_query = late_query.outerjoin(
            confirmer,
            confirmer.user_id == payment.confirmed_by,
        )

        loss_payment = aliased(FeePaymentRecord)
        loss_confirmer = aliased(UserRecord)
        loss_amount = literal(Config.LOSS_FEE)
        loss_query = (
            select(
                LoanRecord.patron_id.label("patron_id"),
                LoanRecord.loan_id.label("loan_id"),
                LoanRecord.book_id.label("book_id"),
                func.coalesce(BookRecord.title, LoanRecord.book_title).label("book_title"),
                LoanRecord.book_id.is_(None).label("deleted_book"),
                literal("loss").label("fee_type"),
                case(
                    (loss_payment.payment_id.is_not(None), loss_payment.amount),
                    else_=loss_amount,
                ).label("amount"),
                loss_payment.payment_id.is_not(None).label("paid"),
                LoanRecord.due_date.label("due_date"),
                literal(0).label("days_overdue"),
                LoanRecord.returned_at.label("returned_at"),
                loss_payment.payment_id.label("payment_id"),
                loss_payment.confirmed_at.label("confirmed_at"),
                loss_payment.confirmed_by.label("confirmed_by"),
                loss_payment.receipt_no.label("receipt_no"),
                loss_payment.note.label("note"),
                loss_confirmer.username.label("confirmer"),
            )
            .outerjoin(BookRecord, BookRecord.book_id == LoanRecord.book_id)
            .join(patron, patron.user_id == LoanRecord.patron_id)
            .outerjoin(
                loss_payment,
                (loss_payment.loan_id == LoanRecord.loan_id)
                & (loss_payment.fee_type == "loss")
                & loss_payment.voided_at.is_(None),
            )
            .outerjoin(
                loss_confirmer,
                loss_confirmer.user_id == loss_payment.confirmed_by,
            )
            .where(
                (LoanRecord.lost.is_(True) & (loss_amount > 0))
                | loss_payment.payment_id.is_not(None)
            )
        )
        return union_all(late_query, loss_query)

    @staticmethod
    def _days_between(later, earlier):
        if db.engine.dialect.name == "sqlite":
            return cast(func.julianday(later) - func.julianday(earlier), db.Integer)
        return cast(later - earlier, db.Integer)

    @staticmethod
    def _search_filter(lines, term):
        matching_member = (
            select(UserRecord.user_id)
            .where(
                UserRecord.user_id == lines.c.patron_id,
                UserRecord.username.ilike(term, escape="\\")
                | UserRecord.email.ilike(term, escape="\\"),
            )
            .exists()
        )
        return matching_member | lines.c.book_title.ilike(term, escape="\\")
