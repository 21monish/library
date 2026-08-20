from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from catalog.models import BookInstance, Penalty
from catalog.notifications import deliver_pending_notifications, generate_library_notifications


class Command(BaseCommand):
    help = 'Report overdue circulation and outstanding penalty totals.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-email',
            action='store_true',
            help='Generate in-app notifications without attempting email delivery.',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        overdue_loans = BookInstance.objects.filter(
            status='o',
            due_back__lt=today,
        ).select_related('book', 'borrower')
        unpaid_penalties = Penalty.objects.filter(status='unpaid')

        active_fines = sum(instance.fine_amount for instance in overdue_loans)
        recorded_fines = unpaid_penalties.aggregate(total=Sum('amount'))['total'] or 0

        self.stdout.write(self.style.MIGRATE_HEADING('Shelfwise daily maintenance'))
        self.stdout.write(f'Date: {today:%d %b %Y}')
        self.stdout.write(f'Overdue active loans: {overdue_loans.count()}')
        self.stdout.write(f'Estimated active fines: INR {active_fines}')
        self.stdout.write(f'Unpaid recorded penalties: {unpaid_penalties.count()}')
        self.stdout.write(f'Outstanding recorded amount: INR {recorded_fines}')

        for instance in overdue_loans:
            borrower = instance.borrower.username if instance.borrower else 'Unknown'
            self.stdout.write(
                f'  - {instance.book.title} · {borrower} · '
                f'due {instance.due_back:%d %b %Y} · INR {instance.fine_amount}'
            )

        created = generate_library_notifications(today=today)
        delivery = (
            {'sent': 0, 'skipped': 0, 'failed': 0}
            if options['skip_email']
            else deliver_pending_notifications()
        )
        self.stdout.write(f'New in-app notifications: {created}')
        if options['skip_email']:
            self.stdout.write('Notification email delivery skipped.')
        else:
            self.stdout.write(
                f"Notification emails: {delivery['sent']} sent, "
                f"{delivery['skipped']} skipped, {delivery['failed']} failed"
            )
