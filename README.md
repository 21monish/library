# Shelfwise Library Management

Shelfwise is a user-friendly Django library management application for students,
teachers, library staff, and superadmins. It provides catalog management,
role-based CRUD access, circulation, reservations, overdue penalties, reporting,
notifications, QR workflows, and operational automation without relying on the
default Django admin interface.

## Main features

- Four roles: Student, Teacher, Library In-charge, and Superadmin
- Configurable View, Add, Change, and Delete permissions for library accounts
- Student 15-day and teacher 30-day borrowing policies
- Staff-only issue, renewal, return, and penalty-resolution workflows
- Book covers and profile-image uploads on Django/Sevalla persistent storage
- Bootstrap interface and responsive DataTables
- CSV/XLSX/PDF reports, QR cards and labels, audit history, and backups
- Daily Windows automation for alerts, backups, and monthly PDF reports
- SQLite for local development and Sevalla PostgreSQL for deployment

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\start.ps1
```

Open <http://127.0.0.1:8000/>. Create an administrator when needed:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

The startup script validates Django, checks migration drift, applies migrations,
and launches the development server. Use `start.cmd` if direct PowerShell script
execution is blocked.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test
```

## Automation

Run one automation cycle:

```powershell
.\automation.ps1 -SkipEmail
```

Install the daily Windows task:

```powershell
.\install_automation.ps1 -DailyAt 08:00 -SkipEmail -RunNow
```

See [AUTOMATION.md](AUTOMATION.md), [OPERATIONS.md](OPERATIONS.md), and
[SEVALLA_DEPLOYMENT.md](SEVALLA_DEPLOYMENT.md) for complete operational and
deployment guidance.

## Security

Keep `.env`, database files, passwords, generated backups, reports, uploaded
media, and runtime logs out of source control. Rotate any credential that has
been shared outside a protected secret manager before deployment.
