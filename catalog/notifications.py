from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.utils import timezone

from .models import BookInstance, Loan, Notification, Penalty, Reservation


def create_notification(*, user, notification_type, title, message, link, dedupe_key):
    notification, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            'user': user,
            'notification_type': notification_type,
            'title': title,
            'message': message,
            'link': link,
        },
    )
    return notification, created


def generate_library_notifications(today=None):
    today = today or timezone.localdate()
    created_count = 0

    active_loans = Loan.objects.filter(status='active').select_related(
        'borrower', 'book_instance'
    )
    for loan in active_loans:
        days_until_due = (loan.due_date - today).days
        if days_until_due == 3:
            notification_type = 'due_soon'
            title = 'Book due in 3 days'
            message = f"'{loan.book_title}' is due on {loan.due_date:%d %b %Y}."
        elif days_until_due == 0:
            notification_type = 'due_today'
            title = 'Book due today'
            message = f"'{loan.book_title}' is due today. Please return or renew it."
        elif days_until_due < 0:
            overdue_days = abs(days_until_due)
            notification_type = 'overdue'
            title = f'Book overdue by {overdue_days} day' + ('s' if overdue_days != 1 else '')
            message = (
                f"'{loan.book_title}' is overdue. The estimated fine is "
                f"INR {overdue_days * 10}."
            )
        else:
            continue

        _, created = create_notification(
            user=loan.borrower,
            notification_type=notification_type,
            title=title,
            message=message,
            link='/history/',
            dedupe_key=f'loan:{loan.pk}:{notification_type}:{today.isoformat()}',
        )
        created_count += int(created)

    available_reservations = Reservation.objects.filter(
        status='active',
        book__bookinstance__status='a',
    ).select_related('book', 'borrower').distinct()
    for reservation in available_reservations:
        _, created = create_notification(
            user=reservation.borrower,
            notification_type='reservation',
            title='Reserved book is available',
            message=f"A copy of '{reservation.book.title}' is now available to borrow.",
            link=reservation.book.get_absolute_url(),
            dedupe_key=f'reservation:{reservation.pk}:available',
        )
        created_count += int(created)

    overdue_count = active_loans.filter(due_date__lt=today).count()
    if overdue_count:
        active_fines = sum(
            instance.fine_amount
            for instance in BookInstance.objects.filter(status='o', due_back__lt=today)
        )
        recorded_fines = Penalty.objects.filter(status='unpaid').aggregate(
            total=Sum('amount')
        )['total'] or 0
        admins = User.objects.filter(
            Q(is_superuser=True)
            | Q(profile__role__in=('superadmin', 'library'))
        ).distinct()
        for admin_user in admins:
            _, created = create_notification(
                user=admin_user,
                notification_type='admin_digest',
                title='Daily overdue summary',
                message=(
                    f'{overdue_count} active loans are overdue. Estimated active fines: '
                    f'INR {active_fines}; recorded unpaid penalties: INR {recorded_fines}.'
                ),
                link='/borrowed/',
                dedupe_key=f'admin-digest:{admin_user.pk}:{today.isoformat()}',
            )
            created_count += int(created)

    return created_count


def deliver_pending_notifications():
    sent = skipped = failed = 0
    pending = Notification.objects.filter(email_status='pending').select_related('user')
    for notification in pending:
        if not notification.user.email:
            notification.email_status = 'skipped'
            notification.email_error = 'User has no email address.'
            notification.save(update_fields=['email_status', 'email_error'])
            skipped += 1
            continue
        try:
            send_mail(
                subject=f'Shelfwise: {notification.title}',
                message=f'{notification.message}\n\nOpen Shelfwise: {notification.link}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                fail_silently=False,
            )
        except Exception as exc:
            notification.email_status = 'failed'
            notification.email_error = str(exc)[:1000]
            notification.save(update_fields=['email_status', 'email_error'])
            failed += 1
        else:
            notification.email_status = 'sent'
            notification.email_error = ''
            notification.save(update_fields=['email_status', 'email_error'])
            sent += 1
    return {'sent': sent, 'skipped': skipped, 'failed': failed}
