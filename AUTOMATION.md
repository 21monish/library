# Shelfwise automation

## One-command startup

Local SQLite with existing data:

```powershell
.\start.ps1
```

If Windows blocks PowerShell scripts, use the included launcher instead:

```bat
start.cmd
```

`start.ps1` automatically loads a local `.env` file when present. Explicit
command-line parameters and existing process environment variables take priority.

Skip the dependency check on later runs:

```powershell
.\start.ps1 -SkipInstall
```

Run one complete automation cycle during startup:

```powershell
.\start.ps1 -SkipInstall -RunAutomation
```

Supabase with repeatable demo data:

```powershell
$env:DATABASE_URL='YOUR_SUPABASE_SESSION_POOLER_URI'
.\start.ps1 -SeedDemo
```

The script installs dependencies, validates Django, applies migrations, optionally
loads demo data, and starts the development server. It stops immediately if any
required step fails.

## Complete automation cycle

Run every operational job once:

```powershell
.\automation.ps1
```

This workflow is safe to repeat. It:

- creates idempotent due-soon, due-today, overdue, reservation, and staff alerts;
- delivers pending notification email when SMTP is configured;
- exports books, physical copies, and users to `backups\YYYY-MM-DD`;
- creates the previous month's PDF report on the first day of each month;
- records output in `.runtime\automation.log`;
- uses a process lock so overlapping runs are rejected.

For a local in-app-only run, skip email delivery:

```powershell
.\automation.ps1 -SkipEmail
```

The cross-platform Django equivalent is:

```powershell
.\.venv\Scripts\python.exe manage.py run_library_automation
```

## Daily maintenance details

```powershell
.\.venv\Scripts\python.exe manage.py library_maintenance
```

The command reports active overdue loans, their estimated fines, unpaid persistent
penalties, and the total outstanding amount. It also generates idempotent due-date,
overdue, reservation, and administrator notifications and delivers pending email.
Set `DATABASE_URL` first when the report should run against Supabase.

To run only the notification workflow manually:

```powershell
.\.venv\Scripts\python.exe manage.py send_library_notifications
```

Use `--skip-email` to generate only in-app alerts.

SMTP delivery is controlled with `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and
`DEFAULT_FROM_EMAIL`. Local development uses Django's console email backend.

## Windows Task Scheduler

Install the included daily task at 8:00 AM and run its first cycle immediately:

```powershell
.\install_automation.ps1 -DailyAt 08:00 -RunNow
```

Choose another 24-hour time with `-DailyAt HH:mm`. To install an in-app-only
task, add `-SkipEmail`. The task runs as the current Windows user, starts when
available if its scheduled time was missed, and rejects overlapping instances.

Remove it with:

```powershell
.\install_automation.ps1 -Uninstall
```

The scheduled action references `automation.ps1`; it does not place database or
email secrets in Task Scheduler. Store production credentials in the ignored
`.env` file or protected system environment variables.
