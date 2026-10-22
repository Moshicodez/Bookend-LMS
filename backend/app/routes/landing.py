from datetime import date
from html import escape
from urllib.parse import quote

from flask import Blueprint, render_template, request

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


def _genre_carousel_items(genre_sections):
    items = []
    for index, genre in enumerate(genre_sections):
        books = genre["books"]
        cover_titles = [
            escape((book.title or genre["name"])[:22])
            for book in books[:3]
        ] or [escape(genre["name"])]
        while len(cover_titles) < 3:
            cover_titles.append(escape(genre["name"]))

        cover_groups = []
        cover_positions = (
            (95, 178, -12),
            (205, 145, 0),
            (315, 178, 12),
        )
        for cover_index, (x, y, angle) in enumerate(cover_positions):
            cover_color = COVER_COLORS[(index + cover_index) % len(COVER_COLORS)]
            cover_groups.append(
                f'<g transform="translate({x} {y}) rotate({angle} 85 135)">'
                f'<rect width="170" height="270" rx="8" fill="{cover_color}"/>'
                '<rect x="11" y="11" width="148" height="248" rx="3" '
                'fill="none" stroke="#fffefa" stroke-opacity=".6"/>'
                f'<text x="85" y="132" fill="#fffefa" font-family="Georgia,serif" '
                f'font-size="16" text-anchor="middle">{cover_titles[cover_index]}</text>'
                '</g>'
            )

        genre_name = escape(genre["name"])
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">'
            '<rect width="600" height="600" fill="#f6f4ee"/>'
            '<circle cx="300" cy="275" r="238" fill="#eeece3"/>'
            '<text x="300" y="74" fill="#435b43" font-family="Arial,sans-serif" '
            'font-size="14" letter-spacing="5" text-anchor="middle">BOOKEND LIBRARY</text>'
            f'{"".join(cover_groups)}'
            f'<text x="300" y="526" fill="#252a25" font-family="Georgia,serif" '
            f'font-size="34" text-anchor="middle">{genre_name}</text>'
            '<text x="300" y="557" fill="#777b70" font-family="Arial,sans-serif" '
            'font-size="13" letter-spacing="3" text-anchor="middle">BROWSE THE STACKS</text>'
            '</svg>'
        )
        items.append(
            {
                "src": f"data:image/svg+xml,{quote(svg, safe='')}",
                "alt": f"{genre['name']} book covers from the Bookend library",
                "title": genre["name"],
                "subtitle": f"{len(genre['all_books'])} books",
            }
        )
    return items


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
        genre_carousel_items=_genre_carousel_items(genre_sections),
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
