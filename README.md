# Bookend-LMS

## Run the application

Install the dependencies and start the Flask app:

```powershell
pip install -r requirements.txt
python main.py
```

The app creates its SQLite database and `users` table automatically in Flask's
instance folder. Set `BOOKEND_DATABASE_URL` to use a different SQLAlchemy
database URL, and set `BOOKEND_SECRET_KEY` to a long, random value before
deploying.

Public signup creates patron accounts only. Librarian accounts must be added
directly to the `users` table by an administrator, with `role` set to
`librarian` and `password_hash` generated with Werkzeug's
`werkzeug.security.generate_password_hash` (never store a plain-text password).
