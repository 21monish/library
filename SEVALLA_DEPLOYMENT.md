# Deploy Shelfwise on Sevalla

Shelfwise includes `nixpacks.toml` and `runtime.txt` for Sevalla Application
Hosting. The container installs `requirements.txt`, collects production static
assets, applies database migrations, and starts Gunicorn on Sevalla's `$PORT`.

## 1. Application source and build

In the `library-f0ahg` application, use:

- Repository: `21monish/library`
- Branch: `main`
- Build environment: Nixpacks
- Build path: `.`
- Automatic deployment: enabled for `main`

The committed Nixpacks configuration supplies the build and start commands. If
you enter a custom web start command in Sevalla, use exactly:

```bash
python manage.py migrate --noinput && gunicorn library_management.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -
```

## 2. Required environment variables

Add these under **Environment variables**. Mark the first six variables as both
build-time and runtime variables because Django loads them while collecting
static assets. Do not commit their real values.

| Key | Value |
| --- | --- |
| `DJANGO_DEBUG` | `false` |
| `SECRET_KEY` | A new long random production secret |
| `DATABASE_URL` | Rotated Supabase session-pooler PostgreSQL URI |
| `ALLOWED_HOSTS` | `.sevalla.app` for initial deployment; use the exact host afterward |
| `CSRF_TRUSTED_ORIGINS` | `https://*.sevalla.app` initially; use the exact HTTPS origin afterward |
| `TIME_ZONE` | `Asia/Kolkata` |
| `SECURE_SSL_REDIRECT` | `true` |
| `SUPABASE_URL` | The Supabase project URL |
| `SUPABASE_SERVICE_KEY` | A newly rotated server-side service key |
| `SUPABASE_STORAGE_BUCKET` | `library-assets` |

The Supabase password and service-role credentials previously shared outside a
secret manager must be rotated before use. If the database password contains
special characters, percent-encode it inside `DATABASE_URL`.

Sevalla applies commas and double quotes specially in environment variables.
The initial values above avoid commas; do not surround values with quotes.

## 3. Web process and health checks

The web process must expose the port supplied by `$PORT`. Configure both probes:

- Readiness path: `/health/`
- Liveness path: `/health/`
- Port: the web process port
- Initial delay: 20 seconds
- Period: 30 seconds
- Timeout: 5 seconds
- Failure threshold: 3

After the first successful deployment, open **Domains**, copy the assigned
`sevalla.app` hostname, and replace the wildcard `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` values with that exact hostname and HTTPS origin.

## 4. Daily automation cron job

Under **Processes**, create a Cron job:

- Name: `shelfwise-daily-automation`
- Start command: `python manage.py run_library_automation --skip-backup --skip-monthly-report`
- Schedule: `0 8 * * *`
- Custom time zone: `Asia/Kolkata`

Sevalla cron containers have no persistent storage, so CSV backups and generated
PDF files are skipped there. Keep Supabase scheduled backups enabled. If SMTP is
not configured, append `--skip-email` so notifications remain pending rather
than being treated as delivered by a console backend.

## 5. Optional SMTP variables

For real email reminders, add:

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=your SMTP host
EMAIL_PORT=587
EMAIL_HOST_USER=your SMTP username
EMAIL_HOST_PASSWORD=your SMTP password
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=your verified sender address
```

## 6. Deployment verification

Deploy `main`, then confirm:

1. The build log completes `collectstatic`.
2. The runtime log completes all migrations and starts Gunicorn.
3. `/health/` returns `{"status":"ok"}`.
4. Login, catalog, member permissions, issue/return, penalties, and reports load.
5. In the Web terminal, activate Nixpacks Python with `. /opt/venv/bin/activate`
   before running `python manage.py check --deploy` or other Django commands.
