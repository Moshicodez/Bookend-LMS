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

Users can create patron accounts from the sign-in page. To enable librarian
registration, configure a private `BOOKEND_STAFF_CODE` environment variable.
