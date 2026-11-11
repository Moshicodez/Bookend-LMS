import unittest
from datetime import date, timedelta
from urllib.parse import urlencode

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.favorite_record import FavoriteRecord
from backend.app.models.loan_record import LoanRecord
from backend.app.models.notification_record import NotificationRecord
from backend.app.models.reservation_record import ReservationRecord
from backend.app.repositories.book_repository import BookRepository
from backend.app.repositories.user_repository import UserRepository


class BrowseUiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "browse-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.books = BookRepository()
        self.history = self.books.create(
            Book(None, "History of Libraries", "A. Writer", "History", "")
        )
        self.mystery = self.books.create(
            Book(None, "Mystery in the Stacks", "B. Writer", "Mystery", "")
        )
        self.history_companion = self.books.create(
            Book(None, "Another Library Story", "C. Writer", "History", "")
        )
        self.patron = self._create_user("reader", "patron")
        self.librarian = self._create_user("staff", "librarian")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _create_user(self, username, role):
        return UserRepository().create(
            f"{username}@example.com",
            username,
            generate_password_hash("StrongPass1!"),
            role,
        )

    def _sign_in(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = user.role

    def test_sidebar_navigation_is_role_aware(self):
        guest_page = self.client.get("/books/")
        guest_menu = guest_page.data.split(b'id="nav-drawer"', 1)[1].split(b"</aside>", 1)[0]
        self.assertIn(b"aria-hidden=\"true\" inert", guest_menu)
        self.assertIn(b">Genres</span>", guest_menu)
        self.assertIn(b"Sign in", guest_menu)
        self.assertIn(b"Create an account", guest_menu)
        self.assertNotIn(b"Dashboard", guest_menu)
        self.assertNotIn(b"Favorites", guest_menu)

        self._sign_in(self.patron)
        patron_page = self.client.get("/books/")
        patron_menu = patron_page.data.split(b'id="nav-drawer"', 1)[1].split(b"</aside>", 1)[0]
        self.assertIn(b"Favorites", patron_menu)
        self.assertIn(b"Borrow basket", patron_menu)
        self.assertNotIn(b"Notifications", patron_menu)
        self.assertNotIn(b"Manage books", patron_menu)
        self.assertNotIn(b"Members", patron_menu)
        self.assertIn(b"View all notifications", patron_page.data)
        self.assertIn(b"data-notification-toggle", patron_page.data)

        self._sign_in(self.librarian)
        librarian_page = self.client.get("/books/")
        librarian_menu = librarian_page.data.split(b'id="nav-drawer"', 1)[1].split(b"</aside>", 1)[0]
        for label in (
            b"Home",
            b"Dashboard",
            b"Books",
            b"Manage books",
            b"Manage genres",
            b"Reviews",
            b"Reservations",
            b"Manage loans",
            b"Manage fees",
            b"Overdue loans",
            b"Members",
            b"Archived",
        ):
            self.assertIn(label, librarian_menu)
        expected_order = (
            b"<span>Home</span>",
            b"<span>Dashboard</span>",
            b"<span>Books</span>",
            b"<span>Manage books</span>",
            b"<span>Manage genres</span>",
            b"<span>Reviews</span>",
            b"<span>Reservations</span>",
            b"<span>Manage loans</span>",
            b"<span>Manage fees</span>",
            b"<span>Overdue loans</span>",
            b"<span>Members</span>",
            b"<span>Archived</span>",
        )
        positions = [librarian_menu.index(label) for label in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn(b"Notifications", librarian_menu)
        self.assertIn(b"View all notifications", librarian_page.data)
        self.assertNotIn(b"Stock", librarian_menu)
        self.assertNotIn(b"Favorites", librarian_menu)

    def test_saved_count_is_neutral_and_unread_notifications_keep_alert_badge(self):
        db.session.add(FavoriteRecord(
            user_id=self.patron.user_id,
            book_id=self.history.book_id,
        ))
        db.session.add(NotificationRecord(
            user_id=self.patron.user_id,
            category="general",
            title="New library update",
            message="A new update is available.",
        ))
        db.session.add(ReservationRecord(
            patron_id=self.patron.user_id,
            book_id=self.history.book_id,
            status="ready",
        ))
        db.session.commit()
        self._sign_in(self.patron)

        response = self.client.get("/books/")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        header = page.split('<header class="landing-navbar"', 1)[1].split("</header>", 1)[0]
        saved_link = page.split('aria-label="Saved books"', 1)[1].split("</a>", 1)[0]
        self.assertNotIn("nav-count", saved_link)
        self.assertEqual(header.count('class="nav-count'), 1)
        self.assertIn('class="nav-count notification-count"', header)
        self.assertIn(
            '<span class="nav-count nav-count--muted">1</span>',
            page,
        )
        self.assertIn('class="nav-count nav-count--drawer-alert"', page)
        self.assertIn(
            '<span class="nav-count notification-count" aria-live="polite" >1</span>',
            page,
        )

    def test_guest_can_browse_catalog_detail_and_search_overlay(self):
        catalog = self.client.get("/books/")
        self.assertEqual(catalog.status_code, 200)
        self.assertIn(b"History of Libraries", catalog.data)
        self.assertIn(b"Books to borrow", catalog.data)
        self.assertIn(b'aria-label="Books"', catalog.data)
        self.assertIn(b'href="/books/"', catalog.data)
        self.assertIn(b'aria-current="page"', catalog.data)
        self.assertIn(b'class="book-grid catalog-book-grid"', catalog.data)
        self.assertIn(b"Search books or authors...", catalog.data)
        self.assertIn(b"History (2)", catalog.data)
        self.assertIn(b"Newest", catalog.data)
        self.assertIn(b"Most borrowed", catalog.data)
        self.assertIn(b"data-search-dialog", catalog.data)
        self.assertIn(b"Search by title, author, or genre", catalog.data)
        self.assertIn(b"Sign in to borrow", catalog.data)
        self.assertIn(b"About</a>", catalog.data)
        self.assertNotIn(b"Manage books", catalog.data)
        self.assertNotIn(b"Notifications", catalog.data)

        detail = self.client.get(f"/books/{self.history.book_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"History of Libraries", detail.data)
        self.assertIn(b"History", detail.data)
        self.assertIn(b"More in History", detail.data)
        self.assertIn(b'class="book-detail-layout"', detail.data)
        self.assertIn(b"About this book", detail.data)
        self.assertIn(b"Ratings &amp; reviews", detail.data)
        self.assertIn(b"Sign in to borrow", detail.data)

    def test_genre_filter_and_search_cover_title_author_and_genre(self):
        filtered = self.client.get("/books/?genre=history")
        self.assertIn(b"History of Libraries", filtered.data)
        self.assertNotIn(b"Mystery in the Stacks", filtered.data)

        by_title = self.client.get("/books/?q=Libraries")
        self.assertIn(b"History of Libraries", by_title.data)
        self.assertNotIn(b"Mystery in the Stacks", by_title.data)

        by_author = self.client.get("/books/?q=B.+Writer")
        self.assertIn(b"Mystery in the Stacks", by_author.data)

        by_genre = self.client.get("/books/?q=Mystery")
        self.assertIn(b"Mystery in the Stacks", by_genre.data)

    def test_catalog_matches_trimmed_encoded_genres_and_shows_unknown_empty_state(self):
        unusual = self.books.create(
            Book(
                None,
                "The Crossroads",
                "D. Writer",
                "  Sci-Fi + Mystery & More  ",
                "",
            )
        )
        query = urlencode({"genre": " sci-fi + mystery & more "})
        matching = self.client.get(f"/books/?{query}")

        self.assertEqual(matching.status_code, 200)
        self.assertIn(unusual.title.encode(), matching.data)
        self.assertIn(b"Books to borrow: Sci-Fi + Mystery &amp; More", matching.data)
        self.assertIn(b"Genre: <strong>Sci-Fi + Mystery &amp; More</strong>", matching.data)
        self.assertIn(b'aria-label="Clear genre filter"', matching.data)
        self.assertNotIn(self.history.title.encode(), matching.data)

        unknown = self.client.get("/books/?genre=Unlisted+Shelf")
        self.assertEqual(unknown.status_code, 200)
        self.assertIn(b"No books found in Unlisted Shelf.", unknown.data)
        self.assertIn(b'aria-label="Clear genre filter"', unknown.data)
        self.assertIn(
            b'href="/books/?q=&amp;sort=title">Clear genre filter</a>',
            unknown.data,
        )

    def test_genre_catalog_actions_are_role_appropriate(self):
        guest_page = self.client.get("/books/?genre=History")
        self.assertIn(b">Sign in to borrow</a>", guest_page.data)
        self.assertNotIn(b">Borrow</button>", guest_page.data)
        self.assertNotIn(b">Edit</a>", guest_page.data)

        self._sign_in(self.patron)
        patron_page = self.client.get("/books/?genre=History")
        self.assertIn(b">Borrow</button>", patron_page.data)
        self.assertNotIn(b">Edit</a>", patron_page.data)

        self._sign_in(self.librarian)
        librarian_page = self.client.get("/books/?genre=History")
        self.assertIn(b">Edit</a>", librarian_page.data)
        self.assertNotIn(b">Borrow</button>", librarian_page.data)

    def test_patron_navigation_counts_and_add_to_basket_action(self):
        self._sign_in(self.patron)
        db.session.add(
            FavoriteRecord(user_id=self.patron.user_id, book_id=self.history.book_id)
        )
        db.session.commit()
        with self.client.session_transaction() as session:
            session["basket_book_ids"] = [self.history.book_id]

        catalog = self.client.get("/books/")
        self.assertIn(b'aria-label="Saved books"', catalog.data)
        self.assertIn(b"Borrow basket, 1 books", catalog.data)
        self.assertIn(b">Borrow</button>", catalog.data)
        self.assertIn(b"My loans", catalog.data)
        self.assertIn(b"Books to borrow", catalog.data)
        self.assertIn(b'name="csrf_token"', catalog.data)

    def test_librarian_catalog_header_and_card_actions(self):
        self._sign_in(self.librarian)
        page = self.client.get("/books/")
        self.assertIn(b">Catalog</h1>", page.data)
        self.assertIn(b">Add a book</a>", page.data)
        self.assertIn(b">Archived books</a>", page.data)
        self.assertIn(b">Edit</a>", page.data)
        self.assertNotIn(b">Borrow</button>", page.data)
        self.assertIn(b">Manage books</span>", page.data)
        self.assertIn(b'aria-label="Open account menu for staff"', page.data)
        navigation = page.data.split(b'class="landing-navigation"', 1)[1].split(b"</nav>", 1)[0]
        self.assertNotIn(b"About", navigation)
        self.assertEqual(navigation.count(b'aria-label="Genres"'), 1)
        self.assertIn(b'data-notification-toggle', page.data)

    def test_catalog_most_borrowed_sort_orders_by_loan_count(self):
        today = date.today()
        db.session.add_all(
            [
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.mystery.book_id,
                    borrowed_at=today,
                    due_date=today + timedelta(days=14),
                ),
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.mystery.book_id,
                    borrowed_at=today,
                    due_date=today + timedelta(days=14),
                ),
                LoanRecord(
                    patron_id=self.patron.user_id,
                    book_id=self.history.book_id,
                    borrowed_at=today,
                    due_date=today + timedelta(days=14),
                ),
            ]
        )
        db.session.commit()
        page = self.client.get("/books/?sort=most_borrowed")
        self.assertLess(
            page.data.index(b"Mystery in the Stacks"),
            page.data.index(b"History of Libraries"),
        )

    def test_catalog_paginates_all_books_and_keeps_filters(self):
        for index in range(25):
            self.books.create(
                Book(
                    None,
                    f"History entry {index:02d}",
                    "Catalog Writer",
                    "History",
                    "",
                )
            )

        first_page = self.client.get("/books/?genre=History&sort=newest")
        self.assertIn(b"27 books found", first_page.data)
        self.assertIn(b"Page 1 of 2", first_page.data)
        self.assertEqual(first_page.data.count(b'class="catalog-book-card"'), 24)
        self.assertIn(b">Next</a>", first_page.data)

        second_page = self.client.get("/books/?genre=History&sort=newest&page=2")
        self.assertIn(b"Page 2 of 2", second_page.data)
        self.assertEqual(second_page.data.count(b'class="catalog-book-card"'), 3)
        self.assertIn(b">Previous</a>", second_page.data)
        self.assertIn(b"History of Libraries", second_page.data)

        available_page = self.client.get(
            "/books/?genre=History&sort=newest&available=1&page=2"
        )
        self.assertIn(
            b'id="catalog-available" name="available" type="checkbox" value="1" checked',
            available_page.data,
        )
        self.assertIn(b"genre=History", available_page.data)
        self.assertIn(b"available=1", available_page.data)

        landing = self.client.get("/")
        self.assertIn(b"History entry 24", landing.data)

    def test_patron_add_to_basket_and_guest_basket_redirect(self):
        self.assertEqual(self.client.get("/basket").location, "/login")
        self._sign_in(self.patron)
        page = self.client.get("/login")
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]

        response = self.client.post(
            f"/basket/add/{self.history.book_id}",
            data={
                "csrf_token": token,
                "next": f"/books/{self.history.book_id}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/books/{self.history.book_id}")
        self.assertIn(
            f"Borrow basket, 1 books".encode(),
            self.client.get("/books/").data,
        )

    def test_librarian_navigation_uses_shield_and_overdue_count(self):
        self._sign_in(self.librarian)
        page = self.client.get("/books/")
        self.assertIn(b'href="/librarian"', page.data)
        self.assertIn(b"Dashboard", page.data)
        self.assertNotIn(b"Saved books,", page.data)
        self.assertNotIn(b"Borrow basket,", page.data)


if __name__ == "__main__":
    unittest.main()
