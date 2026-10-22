from datetime import date

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models.loan_record import LoanRecord
from ..models.user_record import UserRecord
from ..repositories.book_repository import BookRepository


landing_bp = Blueprint("landing", __name__)

GENRES = (
    "History",
    "Kids",
    "Mystery",
    "Crime",
    "Horror",
    "Thriller",
    "Romance",
    "Drama",
)
SEARCH_FIELDS = {
    "all": ("title", "author", "genre"),
    "title": ("title",),
    "author": ("author",),
    "genre": ("genre",),
    "isbn": ("isbn",),
}
COVER_COLORS = ("#a44235", "#476d57", "#536779", "#98713f", "#695676", "#9a5947")


@landing_bp.route("/")
def index():
    books = BookRepository().find_all()
    loan_counts = dict(
        db.session.execute(
            db.select(LoanRecord.book_id, db.func.count(LoanRecord.loan_id))
            .group_by(LoanRecord.book_id)
        ).all()
    )
    trending_books = sorted(
        books,
        key=lambda book: (loan_counts.get(book.book_id, 0), book.book_id or 0),
        reverse=True,
    )[:10]
    new_arrivals = sorted(
        books,
        key=lambda book: (
            book.kind == "new_release",
            book.book_id or 0,
        ),
        reverse=True,
    )[:10]
    available_books = [book for book in books if book.can_borrow()][:10]

    genre_sections = [
        {
            "name": "Featured",
            "books": (trending_books or books)[:3],
            "all_books": trending_books or books,
        }
    ]
    for genre in GENRES:
        matching_books = [
            book for book in books if (book.genre or "").casefold() == genre.casefold()
        ]
        genre_sections.append(
            {
                "name": genre,
                "books": matching_books[:3],
                "all_books": matching_books,
            }
        )

    active_patron_count = db.session.scalar(
        db.select(db.func.count(UserRecord.user_id)).where(
            UserRecord.role == "patron",
            UserRecord.active.is_(True),
        )
    ) or 0
    borrowed_count = db.session.scalar(
        db.select(db.func.count(LoanRecord.loan_id)).where(
            LoanRecord.returned_at.is_(None),
        )
    ) or 0
    genre_count = len({book.genre.strip().casefold() for book in books if book.genre.strip()})

    search_term = request.args.get("q", "").strip()
    search_type = request.args.get("type", "all")
    search_fields = SEARCH_FIELDS.get(search_type, SEARCH_FIELDS["all"])
    search_results = []
    if search_term:
        normalized_term = search_term.casefold()
        search_results = [
            book
            for book in books
            if any(
                normalized_term in str(getattr(book, field, "") or "").casefold()
                for field in search_fields
            )
        ]

    return render_template(
        "landing.html",
        books=books,
        trending_books=trending_books,
        new_arrivals=new_arrivals,
        available_books=available_books,
        genre_sections=genre_sections,
        cover_colors=COVER_COLORS,
        stats={
            "books": len(books),
            "patrons": active_patron_count,
            "borrowed": borrowed_count,
            "genres": genre_count,
        },
        search_term=search_term,
        search_type=search_type if search_type in SEARCH_FIELDS else "all",
        search_results=search_results,
        current_year=date.today().year,
    )
