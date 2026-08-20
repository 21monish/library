# Shelfwise deployment on Render

The repository includes a Render Blueprint in `render.yaml`. It creates the Django
web service and a daily maintenance cron job while continuing to use Supabase as
the PostgreSQL database.

## 1. Rotate exposed Supabase credentials

Before deploying, reset the database password in Supabase and rotate every secret
or service-role key previously shared. Use the new session-pooler connection URI.
Do not commit credentials to this repository.

## 2. Push the project to a private GitHub repository

Commit the project, then push it to a repository that Render can access. Confirm
that `.env`, `.venv`, `db.sqlite3`, generated reports, and `staticfiles` are not
tracked.

## 3. Create the Render Blueprint

In Render, choose **New > Blueprint**, connect the repository, and apply
`render.yaml`. Enter these secret values when prompted for both the web service
and cron job:

- `DATABASE_URL`: the rotated Supabase session-pooler URI.
- `ALLOWED_HOSTS`: the Render hostname, for example `shelfwise-library.onrender.com`.
- `CSRF_TRUSTED_ORIGINS`: the full HTTPS origin, for example
  `https://shelfwise-library.onrender.com`.
- SMTP host, username, password, and sender address.
- `SUPABASE_URL` and a newly rotated `SUPABASE_SERVICE_KEY` for server-side image
  uploads. Keep `SUPABASE_STORAGE_BUCKET=library-assets`.

Render generates `SECRET_KEY`. Never copy the Supabase publishable or service-role
keys into Django settings; the server uses PostgreSQL through `DATABASE_URL`.
The Blueprint sets `DJANGO_DEBUG=false`; use that namespaced variable instead of
the generic system `DEBUG` variable.

## 4. Verify the deployment

After the first build succeeds, open the Render shell and run:

```bash
python manage.py check --deploy
python manage.py showmigrations
```

Then sign in and verify the dashboard, admin, reports, CSV/XLSX/PDF exports, QR
circulation, and notification pages. The build runs migrations and collects
versioned static assets automatically.

Create the image bucket once from a protected shell:

```bash
python manage.py setup_supabase_storage
```

The command creates a public `library-assets` bucket restricted to JPEG, PNG, and
WebP images up to 3 MB. Upload and mutation access stays server-side.

## 5. Custom domain

After adding a custom domain, add its hostname to `ALLOWED_HOSTS` and its full
HTTPS origin to `CSRF_TRUSTED_ORIGINS`, separated by commas when multiple values
are needed. Redeploy after changing environment variables.

## Operations

- Daily maintenance runs at 02:30 UTC (08:00 IST) and sends due/overdue emails.
- Download monthly PDFs from the Reports page, or generate one in a Render shell
  and download it before the shell ends; Render's filesystem is ephemeral.
- Keep Supabase backups enabled and review Render deploy/cron logs regularly.
