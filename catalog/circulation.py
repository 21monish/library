import datetime

from django.conf import settings
from django.utils import timezone

from .models import Loan, Penalty, Reservation
from .notifications import create_notification
from .permissions import is_library_staff


def _can_manage_circulation(user):
    return is_library_staff(user)


def checkout_copy(book_instance, borrower, issued_by=None):
    if not _can_manage_circulation(issued_by):
        raise PermissionError('Only the library in-charge can issue books.')
    role = getattr(getattr(borrower, 'profile', None), 'role', 'student')
    if role not in {'student', 'teacher'}:
        raise ValueError('Books can only be issued to active student or teacher accounts.')
    if not borrower.is_active:
        raise ValueError('Books cannot be issued to an inactive account.')
    if book_instance.status != 'a':
        raise ValueError('This copy is not available.')
    loan_limit = settings.LOAN_LIMIT_BY_ROLE.get(role, settings.LOAN_LIMIT_BY_ROLE['student'])
    if Loan.objects.filter(borrower=borrower, status='active').count() >= loan_limit:
        raise ValueError(f'This member has reached the active loan limit of {loan_limit}.')
    loan_days = settings.LOAN_DAYS_BY_ROLE.get(role, settings.LOAN_DAYS_BY_ROLE['student'])
    due_date = datetime.date.today() + datetime.timedelta(days=loan_days)
    book_instance.borrower = borrower
    book_instance.status = 'o'
    book_instance.due_back = due_date
    book_instance.save(update_fields=['borrower', 'status', 'due_back'])
    loan = Loan.objects.create(
        borrower=borrower,
        book_instance=book_instance,
        book_title=book_instance.book.title,
        due_date=due_date,
        issued_by=issued_by,
    )
    reservation = Reservation.objects.filter(
        book=book_instance.book, borrower=borrower, status='active'
    ).first()
    if reservation:
        reservation.resolve('fulfilled')
    return loan


def checkin_copy(book_instance, returned_by):
    if not _can_manage_circulation(returned_by):
        raise PermissionError('Only the library in-charge can return books.')
    if book_instance.status != 'o':
        raise ValueError('This copy is not currently on loan.')
    borrower = book_instance.borrower
    fine_amount = book_instance.fine_amount
    days_overdue = (
        (datetime.date.today() - book_instance.due_back).days
        if fine_amount and book_instance.due_back else 0
    )
    active_loan = Loan.objects.filter(
        book_instance=book_instance, borrower=borrower, status='active'
    ).first()
    if not active_loan and borrower and book_instance.due_back:
        active_loan = Loan.objects.create(
            borrower=borrower,
            book_instance=book_instance,
            book_title=book_instance.book.title,
            issued_at=timezone.make_aware(datetime.datetime.combine(
                book_instance.due_back - datetime.timedelta(
                    days=settings.LOAN_DAYS_BY_ROLE.get(
                        getattr(getattr(borrower, 'profile', None), 'role', 'student'),
                        settings.LOAN_DAYS_BY_ROLE['student'],
                    )
                ),
                datetime.time.min,
            )),
            due_date=book_instance.due_back,
        )
    penalty = None
    if fine_amount and borrower:
        penalty = Penalty.objects.create(
            borrower=borrower,
            book_instance=book_instance,
            book_title=book_instance.book.title,
            loan=active_loan,
            amount=fine_amount,
            days_overdue=days_overdue,
        )
    if active_loan:
        active_loan.status = 'returned'
        active_loan.returned_at = timezone.now()
        active_loan.returned_by = returned_by
        active_loan.save(update_fields=['status', 'returned_at', 'returned_by'])
    book_instance.borrower = None
    book_instance.status = 'a'
    book_instance.due_back = None
    book_instance.save(update_fields=['borrower', 'status', 'due_back'])
    waiting = Reservation.objects.filter(
        book=book_instance.book, status='active'
    ).select_related('borrower').order_by('created_at').first()
    if waiting:
        create_notification(
            user=waiting.borrower,
            notification_type='reservation',
            title='Reserved book is available',
            message=f"A copy of '{book_instance.book.title}' is available. Visit the library desk for issue.",
            link=book_instance.book.get_absolute_url(),
            dedupe_key=f'reservation:{waiting.pk}:available',
        )
    return {
        'loan': active_loan,
        'penalty': penalty,
        'fine_amount': fine_amount,
        'days_overdue': days_overdue,
        'borrower': borrower,
    }
