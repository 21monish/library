from django.core.management.base import BaseCommand

from catalog.notifications import (
    deliver_pending_notifications,
    generate_library_notifications,
)


class Command(BaseCommand):
    help = 'Generate idempotent library alerts and deliver pending notification emails.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-email',
            action='store_true',
            help='Generate in-app alerts but leave email delivery pending.',
        )

    def handle(self, *args, **options):
        created = generate_library_notifications()
        self.stdout.write(f'Created {created} new in-app notification(s).')
        if options['skip_email']:
            self.stdout.write('Email delivery skipped by request.')
            return
        result = deliver_pending_notifications()
        self.stdout.write(self.style.SUCCESS(
            f"Email delivery: {result['sent']} sent, {result['skipped']} skipped, "
            f"{result['failed']} failed."
        ))
