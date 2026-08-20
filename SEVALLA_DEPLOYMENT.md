# Deploy Shelfwise completely on Sevalla

Shelfwise uses three Sevalla resources:

1. **Application Hosting** runs Django and Gunicorn from `21monish/library`.
2. **PostgreSQL Database Hosting** stores all application records and users.
3. **Application persistent storage** stores uploaded book covers and profile
   photos at `/app/media`.

No external database or file-storage provider is required.

## 1. Create the PostgreSQL database

In Sevalla, open **Databases > Create database** and use:

- Type: PostgreSQL 17
- Database name: `shelfwise`
- Database user: `shelfwise_app`
- Project: the same project as the application
- Location: exactly the same data center as the application
- Resource: the smallest suitable database size to begin with

Keep the generated password in Sevalla. Extensions are not required. Wait until
the database is ready before deploying the application.

## 2. Attach the private database connection

Open **Applications > library-f0ahg > Networking > Connected services**, click
**Add internal connection**, and choose the new PostgreSQL database. Select
**Add environment variables to the application** and rename the generated keys
to:

| Sevalla connection value | Application variable |
| --- | --- |
| Host | `DATABASE_HOST` |
| Port | `DATABASE_PORT` |
| Database name | `DATABASE_NAME` |
| User | `DATABASE_USER` |
| Password | `DATABASE_PASSWORD` |

Make all five variables available during both **Build** and **Runtime**. Do not
manually copy internal credentials and do not enable public database access.

## 3. Add application environment variables

Under **Applications > library-f0ahg > Environment variables**, add:

| Key | Value | Availability |
| --- | --- | --- |
| `DJANGO_DEBUG` | `false` | Build and runtime |
| `SECRET_KEY` | A new random value of at least 50 characters | Build and runtime |
| `ALLOWED_HOSTS` | `.sevalla.app` initially | Build and runtime |
| `CSRF_TRUSTED_ORIGINS` | `https://*.sevalla.app` initially | Build and runtime |
| `TIME_ZONE` | `Asia/Kolkata` | Build and runtime |
| `SECURE_SSL_REDIRECT` | `true` | Runtime |
| `DATABASE_SSL_REQUIRE` | `false` for the private internal connection | Build and runtime |
| `MEDIA_ROOT` | `/app/media` | Runtime |
| `ASSET_UPLOAD_MAX_BYTES` | `3145728` | Runtime |

Generate `SECRET_KEY` locally without saving it to the repository:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 4. Add persistent media storage

Open **Applications > library-f0ahg > Disks**, click **Create disk**, and use:

- Process: the web process
- Path: `/app/media`
- Size: 10 GB initially

The disk is required. Without it, user-uploaded images are erased when the
application restarts or redeploys. A process with persistent storage must run as
one instance, so leave horizontal scaling disabled and scale the web pod
vertically if more capacity is needed.

## 5. Configure the build and web process

Use the GitHub repository `21monish/library`, branch `main`, build path `.`, and
Nixpacks. Enable automatic deployment for `main`. The committed
`nixpacks.toml` runs:

```text
Build: python manage.py collectstatic --noinput
Start: python manage.py migrate --noinput && gunicorn library_management.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -
```

Do not define or hard-code `PORT`; Sevalla supplies it.

## 6. Configure health checks and deploy

Configure readiness and liveness checks on `/health/` with a 20-second initial
delay, 30-second interval, 5-second timeout, and failure threshold of 3. Click
**Deploy now** and verify that the log completes `collectstatic`, migrations,
and Gunicorn startup.

After Sevalla assigns the application domain, replace the wildcard environment
values with the exact host and redeploy:

```text
ALLOWED_HOSTS=actual-hostname.sevalla.app
CSRF_TRUSTED_ORIGINS=https://actual-hostname.sevalla.app
```

## 7. Initialize the production account

Open the application Web Terminal and run:

```bash
. /opt/venv/bin/activate
python manage.py check --deploy
python manage.py showmigrations
python manage.py createsuperuser --username superadmin --email admin@example.com
```

Choose a strong unique production password when prompted. The local SQLite
database and its users are not uploaded to Sevalla.

## 8. Add daily automation

Under **Processes**, create a cron process:

- Name: `shelfwise-daily-automation`
- Schedule: `0 8 * * *`
- Time zone: `Asia/Kolkata`
- Command:

```bash
python manage.py run_library_automation --skip-backup --skip-monthly-report --skip-email
```

Remove `--skip-email` after SMTP variables are configured. Sevalla cron storage
is ephemeral, so database recovery should use Sevalla's database backups rather
than CSV files created inside the cron container.

## 9. Verify the complete deployment

1. Open `/health/` and confirm `{"status":"ok"}`.
2. Sign in as the production superadmin.
3. Create one student, teacher, and library account.
4. Add a book and upload a cover.
5. Redeploy, then confirm the uploaded cover is still displayed.
6. Issue books and verify 15-day student and 30-day teacher due dates.
7. Return an overdue loan and verify its penalty.
8. Confirm the database appears under the application's connected services.
9. Keep external PostgreSQL networking disabled.

## Optional: external DATABASE_URL

`DATABASE_URL` remains supported for local maintenance tools or a temporary
external PostgreSQL connection. When using an external SSL connection, also set
`DATABASE_SSL_REQUIRE=true`. The normal Sevalla deployment should use the five
private `DATABASE_*` variables instead.
