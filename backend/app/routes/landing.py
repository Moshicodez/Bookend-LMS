import base64
from datetime import date
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, current_app, render_template, request, url_for
from PIL import Image, ImageOps

from ..config import COVER_COLORS
from ..extensions import db
from ..models.loan_record import LoanRecord
from ..models.user_record import UserRecord
from ..repositories.book_repository import BookRepository
from ..repositories.genre_repository import GenreRepository
from ..repositories.review_repository import ReviewRepository


landing_bp = Blueprint("landing", __name__)

_FONT_DIRECTORY = Path(__file__).resolve().parents[3] / "frontend" / "static" / "fonts"
_CAROUSEL_FONTS = {
    weight: base64.b64encode(
        (_FONT_DIRECTORY / filename).read_bytes()
    ).decode("ascii")
    for weight, filename in (
        (500, "Poppins-Medium-Latin.woff2"),
        (600, "Poppins-SemiBold-Latin.woff2"),
    )
}

SEARCH_FIELDS = {
    "all": ("title", "author", "genre"),
    "title": ("title",),
    "author": ("author",),
    "genre": ("genre",),
}


@lru_cache(maxsize=256)
def _cached_cover_thumbnail(path, modified_ns):
    try:
        with Image.open(path) as image:
            thumbnail = ImageOps.fit(
                image.convert("RGB"),
                (170, 270),
                method=Image.Resampling.LANCZOS,
            )
            buffer = BytesIO()
            thumbnail.save(buffer, format="JPEG", quality=80, optimize=True)
    except (OSError, Image.DecompressionBombError):
        return None

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _cover_thumbnail_data_uri(filename):
    if not filename:
        return None

    cover_name = Path(filename)
    if (
        cover_name.name != filename
        or cover_name.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}
    ):
        return None

    upload_dir = (Path(current_app.static_folder) / "uploads").resolve()
    try:
        cover_path = (upload_dir / cover_name).resolve(strict=True)
        if cover_path.parent != upload_dir:
            return None
        modified_ns = cover_path.stat().st_mtime_ns
    except OSError:
        return None

    return _cached_cover_thumbnail(str(cover_path), modified_ns)


def _carousel_font_styles():
    return (
        '<style type="text/css">'
        '@font-face{font-family:Poppins;font-style:normal;font-weight:500;'
        f'src:url(data:font/woff2;base64,{_CAROUSEL_FONTS[500]}) format("woff2");'
        '}'
        '@font-face{font-family:Poppins;font-style:normal;font-weight:600;'
        f'src:url(data:font/woff2;base64,{_CAROUSEL_FONTS[600]}) format("woff2");'
        '}'
        '</style>'
    )


def _genre_carousel_items(genre_sections):
    items = []
    for index, genre in enumerate(genre_sections):
        books = genre["books"]
        cover_groups = []
        cover_positions = (
            (95, 178, -12),
            (205, 145, 0),
            (315, 178, 12),
        )
        for cover_index, (x, y, angle) in enumerate(cover_positions):
            cover_color = COVER_COLORS[(index + cover_index) % len(COVER_COLORS)]
            book = books[cover_index] if cover_index < len(books) else None
            cover_title = escape(
                ((book.title if book else None) or genre["name"])[:22]
            )
            book_id_attribute = (
                f' data-book-id="{book.book_id}"' if book is not None else ""
            )
            thumbnail_uri = (
                _cover_thumbnail_data_uri(book.cover)
                if book is not None
                else None
            )

            cover_content = (
                f'<rect width="170" height="270" rx="8" fill="{cover_color}"/>'
            )
            if thumbnail_uri:
                clip_id = f"cover-clip-{index}-{cover_index}"
                cover_content = (
                    f'<defs><clipPath id="{clip_id}">'
                    '<rect width="170" height="270" rx="8"/>'
                    '</clipPath></defs>'
                    f'<image x="0" y="0" width="170" height="270" '
                    f'preserveAspectRatio="xMidYMid slice" '
                    f'clip-path="url(#{clip_id})" href="{thumbnail_uri}"/>'
                    '<rect width="170" height="270" rx="8" fill="none" '
                    'stroke="#fffefa" stroke-width="2"/>'
                )
            else:
                cover_content += (
                    '<text x="85" y="132" fill="#fffefa" '
                    'font-family="Georgia, &quot;Times New Roman&quot;, serif" '
                    f'font-size="16" text-anchor="middle">{cover_title}</text>'
                )

            cover_groups.append(
                f'<g transform="translate({x} {y}) rotate({angle} 85 135)"'
                f'{book_id_attribute} aria-label="Book cover: {cover_title}">'
                f'{cover_content}'
                '<rect x="11" y="11" width="148" height="248" rx="3" '
                'fill="none" stroke="#fffefa" stroke-opacity=".6"/>'
                '</g>'
            )

        genre_label = genre["name"]
        if len(genre_label) > 27:
            genre_label = f"{genre_label[:26].rstrip()}…"
        genre_name = escape(genre_label)
        genre_font_size = min(30, max(18, 500 / len(genre_label)))
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">'
            f'{_carousel_font_styles()}'
            '<rect width="600" height="600" fill="#f6f4ee"/>'
            '<circle cx="300" cy="275" r="238" fill="#eeece3"/>'
            '<text x="300" y="74" fill="#435b43" '
            'font-family="Poppins, &quot;Segoe UI&quot;, Arial, sans-serif" '
            'font-size="14" font-weight="500" letter-spacing="5" text-anchor="middle">BOOKEND LIBRARY</text>'
            f'{"".join(cover_groups)}'
            f'<text x="300" y="526" fill="#252a25" '
            'font-family="Poppins, &quot;Segoe UI&quot;, Arial, sans-serif" '
            f'font-size="{genre_font_size:.1f}" font-weight="600" '
            f'text-anchor="middle">{genre_name}</text>'
            '<text x="300" y="557" fill="#777b70" '
            'font-family="Poppins, &quot;Segoe UI&quot;, Arial, sans-serif" '
            'font-size="13" font-weight="500" letter-spacing="3" text-anchor="middle">BROWSE THE STACKS</text>'
            '</svg>'
        )
        items.append(
            {
                "src": f"data:image/svg+xml,{quote(svg, safe='')}",
                "alt": f"{genre['name']} book covers from the Bookend library",
                "title": genre["name"],
                "subtitle": f"{len(genre['all_books'])} books",
                "href": url_for("books.catalog", genre=genre["name"]),
            }
        )
    return items


@landing_bp.route("/")
def index():
    books = BookRepository().find_all()
    ratings = ReviewRepository().summaries([book.book_id for book in books])
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

    genres = GenreRepository().list_genres()
    genre_sections = []
    for genre in genres:
        matching_books = [
            book
            for book in books
            if (book.genre or "").strip().casefold() == genre.casefold()
        ]
        genre_sections.append(
            {
                "name": genre,
                "books": sorted(
                    matching_books,
                    key=lambda book: book.book_id or 0,
                )[:3],
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
        ratings=ratings,
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
            "genres": len(genres),
        },
        search_term=search_term,
        search_type=search_type if search_type in SEARCH_FIELDS else "all",
        search_results=search_results,
        current_year=date.today().year,
    )
