from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..exceptions import NotFoundError, PermissionDenied, ValidationError
from ..services.fee_service import FeeService
from .auth import _signed_in_user


fees_bp = Blueprint("fees", __name__, url_prefix="/librarian/fees")
fee_service = FeeService()


def _librarian():
    librarian = _signed_in_user("librarian")
    if librarian is None:
        return None, redirect(url_for("auth.login"))
    return librarian, None


def _safe_fee_return():
    destination = request.form.get("next", "")
    parsed = urlsplit(destination)
    if (
        parsed.scheme == ""
        and parsed.netloc == ""
        and parsed.path == url_for("fees.index")
        and not destination.startswith("//")
        and "\\" not in destination
    ):
        return destination
    return url_for("fees.index")


def _fee_error_redirect(error):
    flash(str(error), "error")
    return redirect(_safe_fee_return())


@fees_bp.route("/")
def index():
    librarian, response = _librarian()
    if response:
        return response
    try:
        result = fee_service.list_members_with_fees(
            librarian,
            status=request.args.get("status", "outstanding"),
            fee_type=request.args.get("type", "all"),
            search=request.args.get("q", ""),
            sort=request.args.get("sort", "amount"),
            page=request.args.get("page", 1),
        )
    except (ValidationError, NotFoundError, PermissionDenied) as error:
        flash(str(error), "error")
        destination = (
            url_for("dashboard.librarian_dashboard")
            if isinstance(error, PermissionDenied)
            else url_for("fees.index")
        )
        return redirect(destination)
    return render_template("fees/index.html", **result)


@fees_bp.route("/confirm", methods=["POST"])
def confirm():
    librarian, response = _librarian()
    if response:
        return response
    next_url = _safe_fee_return()
    try:
        loan_id = int(request.form.get("loan_id", ""))
        fee_type = request.form.get("fee_type", "")
        preview = fee_service.payment_preview(librarian, loan_id, fee_type)
        if request.form.get("received_full") != "on":
            return render_template(
                "fees/confirm.html",
                action=url_for("fees.confirm"),
                next_url=next_url,
                preview=preview,
                csrf_token_value=request.form.get("csrf_token", ""),
                confirm_all=False,
            )
        _, amount, member_name = fee_service.confirm_payment(
            librarian,
            loan_id,
            fee_type,
            request.form.get("receipt_no"),
            request.form.get("note"),
        )
    except (ValueError, ValidationError, NotFoundError, PermissionDenied) as error:
        return _fee_error_redirect(error)
    flash(
        f"Payment of ₱{amount:,.2f} confirmed for {member_name}.",
        "success",
    )
    return redirect(next_url)


@fees_bp.route("/confirm-all/<int:member_id>", methods=["POST"])
def confirm_all(member_id):
    librarian, response = _librarian()
    if response:
        return response
    next_url = _safe_fee_return()
    try:
        if request.form.get("received_full") != "on":
            member, lines, total = fee_service.member_outstanding_fees(
                librarian,
                member_id,
            )
            return render_template(
                "fees/confirm.html",
                action=url_for("fees.confirm_all", member_id=member_id),
                next_url=next_url,
                preview={
                    "member": member,
                    "book_title": f"{len(lines)} outstanding fees",
                    "fee_type": "all",
                    "amount": total,
                },
                csrf_token_value=request.form.get("csrf_token", ""),
                confirm_all=True,
            )
        count, total, member_name = fee_service.confirm_all_for_member(
            librarian,
            member_id,
            request.form.get("receipt_no"),
            request.form.get("note"),
        )
    except (ValidationError, NotFoundError, PermissionDenied) as error:
        return _fee_error_redirect(error)
    flash(
        f"Confirmed {count} payments totaling ₱{total:,.2f} for {member_name}.",
        "success",
    )
    return redirect(next_url)
