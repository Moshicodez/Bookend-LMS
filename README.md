# Bookend-LMS

## Run the application

Install the dependencies and start the Flask app:

```powershell
pip install -r requirements.txt
python main.py
```

The app creates its SQLite database and its `users`, `books`, and `loans` tables
automatically in Flask's instance folder. Set `BOOKEND_DATABASE_URL` to use a
different SQLAlchemy database URL, and set `BOOKEND_SECRET_KEY` to a long,
random value before deploying.

Public signup creates patron accounts only. Librarian accounts must be added
directly to the `users` table by an administrator, with `role` set to
`librarian` and `password_hash` generated with Werkzeug's
`werkzeug.security.generate_password_hash` (never store a plain-text password).

## Backend

The backend lives in `backend/app`. `create_app()` registers the authentication,
dashboard, catalog, loans, and member blueprints and creates the SQLAlchemy
tables. Domain models are kept separate from their database records; repository
classes translate records to and from domain objects, and services enforce
permissions and library rules.

After signing in:

- `/books/` lists and searches the catalog; librarians can add, edit, and archive
  books.
- `/loans/` lists the current user's loans; patrons can borrow, return, and pay
  eligible fees.
- `/loans/overdue` lists overdue loans for librarians.
- `/members/` lets librarians activate or deactivate patron accounts.

Run the project tests from this directory with:

```powershell
python -m unittest discover -s tests -v
```
