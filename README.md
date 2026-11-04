# Bookend-LMS

## Run the application

Install the Python dependencies, build the ReactBits genre carousel, and start the Flask app:

```powershell
pip install -r requirements.txt
cd frontend/react
npm install
npm run build
cd ../..
python main.py
```

The landing-page genre carousel uses the ReactBits CircularCarousel component.
Its source and license are in `frontend/react`; rebuild its static assets with
`npm run build` from that directory after changing the component.

## Shared Database Setup

The app uses Flask-SQLAlchemy with PostgreSQL through psycopg. Neon is the
recommended provider because its PostgreSQL connection works directly with the
driver already used by this project.

1. Create a Neon PostgreSQL project on its free plan and copy its connection string.
2. Copy `.env.example` to `.env` and set `DATABASE_URL` to the Neon URL. Replace
   `BOOKEND_SECRET_KEY` with a random value. Keep `.env` private; it is ignored
   by Git. The app configures Neon `postgresql://` URLs to use psycopg.

```powershell
Copy-Item .env.example .env
pip install -r requirements.txt
flask --app main db upgrade
```

3. Seed books and genres from your local database, or from the committed starter
   catalog if there is no local database. Then start the app:

```powershell
flask --app main seed-catalog
python main.py
```

Both collaborators put the same Neon URL in their own ignored `.env` file. Do
not commit `.env`; migrations and seed data must never include passwords.

Whoever changes the models creates and reviews a migration, then commits and
pushes it:

```powershell
flask --app main db migrate -m "Describe the schema change"
git add backend/migrations
git commit -m "Add database migration"
git push
```

The other person pulls the changes and runs the migration before starting the
app:

```powershell
git pull
flask --app main db upgrade
```

Public signup creates patron accounts only. Email addresses are checked for
valid syntax; the app does not send email or verify mailbox ownership. Create a
librarian account with:

```powershell
flask --app main create-librarian
```

The command prompts for username, email, and password with confirmation.
Load the sample books from `frontend/static/data/genre-books.json` with:

```powershell
flask --app main seed-demo
```

The seed command skips books already in the database with the same title and
author. Librarians can create patron accounts, search members by username or email,
view patron loan history and fees, and reset a patron's password from the
Members page. Temporary passwords are shown once. The Catalog also provides
a librarian-only Archived books view with a Restore action. To reset any
account from the command line:

```powershell
flask --app main reset-user-password reader@example.com
```

The CLI prompts for a new password and confirmation. Signed-in users can also
change their password from the landing-page navigation.

## Database backups

Librarians can download or restore a database backup from the librarian
dashboard. Restore replaces all current database records, including accounts,
so use a backup from the same application version and test restores before
relying on them. Backup files include password hashes and should be stored
securely. The download contains database records only; cover image files in
`frontend/static/uploads` need a separate filesystem backup.

## Backend

The backend lives in `backend/app`. `create_app()` registers the authentication,
dashboard, catalog, loans, and member blueprints and creates the SQLAlchemy
tables. Domain models are kept separate from their database records; repository
classes translate records to and from domain objects, and services enforce
permissions and library rules.

The catalog uses a dynamically growing linked list for in-memory book
collections, avoiding fixed-capacity book containers, and an AVL tree for
case-insensitive, ordered genre navigation. Reservations are persisted in the
application database and promoted FIFO when a book is returned. Active
reservations count toward the same per-patron limit as active loans.
Signed-in users can review persisted in-app notifications from the bell icon.
Loan due-soon, due-tomorrow, due-today, and overdue reminders are generated
when a patron visits and by the `sync-notifications` command. Schedule
`flask --app main sync-notifications` to run daily in the host's task scheduler
to deliver reminders even when patrons do not sign in; the command is safe to
repeat and does not create duplicate reminders. Librarians also receive
deduplicated overdue and zero-stock alerts, and can send announcements from the
notification bell. These are in-app notifications, not email or push alerts.

After signing in:

- `/books/` lists and searches the catalog; librarians can add, edit, and archive
  books.
- `/loans/` lists the current user's loans; patrons can borrow, return, pay
  eligible fees, and view or check out ready reservations.
- `/loans/overdue` lists overdue loans for librarians.
- `/members/` lets librarians activate or deactivate patron accounts.

Run the project tests from this directory with:

```powershell
python -m unittest discover -s tests -v
```
