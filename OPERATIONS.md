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

For a full disaster-recovery backup, also keep Supabase scheduled backups enabled and test restoring them periodically.

## Scheduled maintenance

Install the complete daily workflow using Windows Task Scheduler:

```powershell
.\install_automation.ps1 -DailyAt 08:00 -RunNow
```

It processes notifications, email, dated CSV backups, and monthly PDF reports.
See `AUTOMATION.md` for options, logs, manual runs, and removal.

## Production checklist

- Rotate every database/service key that has ever been pasted into chat or committed.
- Keep `.env` out of source control; use only the rotated server-side key.
- Run `manage.py check --deploy`, `manage.py migrate`, and `manage.py collectstatic --noinput` before deployment.
- Restrict Supabase database access, enforce SSL, and retain RLS/revokes on tables exposed through PostgREST.
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
