# Shelfwise operations

## Daily startup

```powershell
.\start.ps1
```

Use `start.cmd` if the Windows execution policy blocks direct `.ps1` files.
Both launchers load `.env` without printing secret values.

Open `http://127.0.0.1:8000/`. The startup script applies pending migrations before starting Django.

## Backup and restore

Create a timestamped or named export outside source control:

```powershell
.\.venv\Scripts\python.exe manage.py export_library_data --output backups\2026-08-12
```

Validate a restore without changing the database, then import it:

```powershell
.\.venv\Scripts\python.exe manage.py import_library_data backups\2026-08-12 --dry-run
.\.venv\Scripts\python.exe manage.py import_library_data backups\2026-08-12
```

For full disaster recovery, keep Sevalla's automatic database and persistent
disk backups enabled and test the database restore process periodically.

## Scheduled maintenance

Install the complete daily workflow using Windows Task Scheduler:

```powershell
.\install_automation.ps1 -DailyAt 08:00 -RunNow
```

It processes notifications, email, dated CSV backups, and monthly PDF reports.
See `AUTOMATION.md` for options, logs, manual runs, and removal.

## Production checklist

- Rotate every database password that has ever been pasted into chat or committed.
- Keep `.env` and all production credentials out of source control.
- Run `manage.py check --deploy`, `manage.py migrate`, and `manage.py collectstatic --noinput` before deployment.
- Attach the Sevalla PostgreSQL database through a private internal connection
  and keep external database access disabled unless it is temporarily needed.
- Mount `/app/media` as persistent storage and verify an uploaded image after
  every infrastructure change.
- Test CSV exports and a database restore at least monthly.
# Local startup

Run the complete startup sequence from PowerShell:

```powershell
.\start.ps1
```

Useful options:

```powershell
.\start.ps1 -SkipInstall             # start without reinstalling packages
.\start.ps1 -RunTests                # run tests before starting
.\start.ps1 -SeedDemo                # safely load repeatable demo data
.\start.ps1 -CheckOnly               # checks and migrations only
.\start.ps1 -BindAddress 127.0.0.1:8001
```

The startup script validates configuration and migration drift before serving.
Use `/health/` for database-aware uptime monitoring.
