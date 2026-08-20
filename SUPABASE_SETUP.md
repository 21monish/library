# Supabase database setup

This project uses Supabase as a hosted PostgreSQL database through Django's
standard ORM. SQLite remains the default when `DATABASE_URL` is not set.

## Configure the connection

1. In Supabase, open **Project Settings > Database** and copy a PostgreSQL
   connection URI. Prefer the session pooler for a persistent Django server.
2. Set `DATABASE_URL` in the environment. Do not commit the real URI.

PowerShell example:

```powershell
$env:DATABASE_URL='postgresql://postgres.PROJECT_REF:PASSWORD@HOST:5432/postgres'
```

If the password contains characters such as `@`, `:`, `/`, or `#`, URL-encode
the password before placing it in the URI.

## Install and initialize

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Running `migrate` creates the Django tables in Supabase. It does not copy the
records currently stored in `db.sqlite3`.

## Copy existing SQLite data (optional)

Export while `DATABASE_URL` is not set:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --output data.json
```

Then set `DATABASE_URL`, migrate, and import:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py loaddata data.json
```

Delete `data.json` after confirming the import because it may contain user and
application data.
