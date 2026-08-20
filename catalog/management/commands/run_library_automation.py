import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Run the complete Shelfwise automation cycle: maintenance alerts, '
        'email delivery, a dated CSV backup, and the previous-month PDF report.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-email',
            action='store_true',
            help='Create in-app alerts without attempting email delivery.',
        )
        parser.add_argument(
            '--skip-backup',
            action='store_true',
            help='Do not create the dated CSV export.',
        )
        parser.add_argument(
            '--skip-monthly-report',
            action='store_true',
            help='Do not generate a monthly PDF, even on the first day of a month.',
        )
        parser.add_argument(
            '--force-monthly-report',
            action='store_true',
            help='Generate the previous-month PDF even when today is not the first day.',
        )
        parser.add_argument(
            '--backup-root',
            default='backups',
            help='Root directory for dated CSV backups (default: backups).',
        )
        parser.add_argument(
            '--report-root',
            default='reports',
            help='Directory for monthly PDF reports (default: reports).',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        self.stdout.write(self.style.MIGRATE_HEADING('Shelfwise automation cycle'))
        self.stdout.write(f'Started for {today:%d %b %Y}')

        maintenance_options = {'stdout': self.stdout, 'stderr': self.stderr}
        if options['skip_email']:
            maintenance_options['skip_email'] = True
        call_command('library_maintenance', **maintenance_options)

        if not options['skip_backup']:
            backup_directory = Path(options['backup_root']).resolve() / today.isoformat()
            call_command(
                'export_library_data',
                output=str(backup_directory),
                stdout=self.stdout,
                stderr=self.stderr,
            )

        should_report = (
            not options['skip_monthly_report']
            and (today.day == 1 or options['force_monthly_report'])
        )
        if should_report:
            first_this_month = today.replace(day=1)
            previous_month_last = first_this_month - datetime.timedelta(days=1)
            month = previous_month_last.strftime('%Y-%m')
            report_path = Path(options['report_root']).resolve() / f'shelfwise-{month}.pdf'
            call_command(
                'generate_monthly_report',
                month=month,
                output=str(report_path),
                stdout=self.stdout,
                stderr=self.stderr,
            )
        elif not options['skip_monthly_report']:
            self.stdout.write('Monthly report not due; it runs automatically on day 1.')

        self.stdout.write(self.style.SUCCESS('Shelfwise automation completed successfully.'))
