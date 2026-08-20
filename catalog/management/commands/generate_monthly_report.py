import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from catalog.reporting import build_report, pdf_bytes


class Command(BaseCommand):
    help = 'Generate a PDF report for a completed calendar month.'

    def add_arguments(self, parser):
        parser.add_argument('--month', help='Month in YYYY-MM format; defaults to the previous month.')
        parser.add_argument('--output', help='Destination PDF path.')

    def handle(self, *args, **options):
        today = datetime.date.today()
        if options['month']:
            try:
                first = datetime.date.fromisoformat(f"{options['month']}-01")
            except ValueError as exc:
                raise ValueError('--month must use YYYY-MM format.') from exc
        else:
            first_this_month = today.replace(day=1)
            first = (first_this_month - datetime.timedelta(days=1)).replace(day=1)
        next_month = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        last = next_month - datetime.timedelta(days=1)
        output = Path(options['output'] or f'reports/shelfwise-{first:%Y-%m}.pdf').resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(pdf_bytes(build_report(first, last)))
        self.stdout.write(self.style.SUCCESS(f'Monthly report created: {output}'))
