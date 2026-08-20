import datetime
import io
import uuid

import qrcode
from django.conf import settings
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Book, Author, BookInstance, Genre, Loan, Notification, Penalty, PenaltyTransaction, Reservation, ScanAudit
from .circulation import checkin_copy, checkout_copy
from .reporting import build_report, csv_response, pdf_response, report_period, xlsx_response
from .forms import AccountForm, AuthorForm, BookForm, BookInstanceForm, CopyIssueForm, GenreForm, ISBNImportForm, MemberForm
from .isbn import ISBNLookupError, lookup_isbn
from .permissions import (
    BORROWER_ROLES,
    can_manage_member,
    get_user_role,
    has_crud_permission,
    is_library_staff,
    is_superadmin,
)


def is_library_admin(user):
    """Return whether a user can manage loans and library records."""
    return is_library_staff(user)


def _require_crud_permission(user, action):
    if not is_library_admin(user) or not has_crud_permission(user, action):
        raise PermissionDenied


def _admin_report(request):
    if not has_crud_permission(request.user, 'view'):
        return None
    start, end = report_period(request.GET)
    return build_report(start, end)


@login_required
def reports(request):
    report = _admin_report(request)
    if report is None:
        raise PermissionDenied
    return render(request, 'catalog/reports.html', {'report': report})


@login_required
def export_report_csv(request):
    report = _admin_report(request)
    if report is None:
        raise PermissionDenied
    return csv_response(report)


@login_required
def export_report_xlsx(request):
    report = _admin_report(request)
    if report is None:
        raise PermissionDenied
    return xlsx_response(report)


@login_required
def export_report_pdf(request):
    report = _admin_report(request)
    if report is None:
        raise PermissionDenied
    return pdf_response(report)


@login_required
def book_create(request):
    _require_crud_permission(request.user, 'add')
    form = BookForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        book = form.save()
        messages.success(request, f"'{book.title}' was added to the catalog.")
        return redirect('book-detail', pk=book.pk)
    return render(request, 'catalog/book_form.html', {'form': form, 'mode': 'Add'})


@login_required
def book_update(request, pk):
    _require_crud_permission(request.user, 'change')
    book = get_object_or_404(Book, pk=pk)
    form = BookForm(request.POST or None, request.FILES or None, instance=book)
    if request.method == 'POST' and form.is_valid():
        book = form.save()
        messages.success(request, f"'{book.title}' was updated.")
        return redirect('book-detail', pk=book.pk)
    return render(request, 'catalog/book_form.html', {'form': form, 'book': book, 'mode': 'Edit'})


@login_required
def book_delete(request, pk):
    _require_crud_permission(request.user, 'delete')
    book = get_object_or_404(Book.objects.prefetch_related('bookinstance_set'), pk=pk)
    copy_count = book.bookinstance_set.count()
    if request.method == 'POST':
        title = book.title
        try:
            book.delete()
        except ProtectedError:
            messages.error(request, 'This book cannot be deleted because protected circulation records reference it.')
            return redirect('book-detail', pk=pk)
        messages.success(request, f"'{title}' and its catalog copies were deleted.")
        return redirect('books')
    return render(request, 'catalog/book_confirm_delete.html', {'book': book, 'copy_count': copy_count})


@login_required
def book_import_isbn(request):
    """Fetch book metadata by ISBN inside the custom Shelfwise workspace."""
    _require_crud_permission(request.user, 'add')
    looked_up = False
    form = ISBNImportForm(request.POST or None, initial={'isbn': request.GET.get('isbn', '')})
    action = request.POST.get('action') if request.method == 'POST' else None

    if action == 'lookup':
        raw_isbn = request.POST.get('isbn', '')
        try:
            metadata = lookup_isbn(raw_isbn)
        except ISBNLookupError as exc:
            form = ISBNImportForm(initial={'isbn': raw_isbn})
            form.add_error('isbn', str(exc))
        else:
            form = ISBNImportForm(initial=metadata)
            if Book.objects.filter(isbn=metadata['isbn']).exists():
                form.add_error('isbn', 'A book with this ISBN already exists.')
            else:
                looked_up = True
    elif action == 'create' and form.is_valid():
        author_name = form.cleaned_data['author'].strip() or 'Unknown'
        name_parts = author_name.rsplit(' ', 1)
        first_name, last_name = (
            (name_parts[0], name_parts[1]) if len(name_parts) == 2 else ('', name_parts[0])
        )
        with transaction.atomic():
            author, _ = Author.objects.get_or_create(
                first_name=first_name,
                last_name=last_name,
            )
            book = Book.objects.create(
                isbn=form.cleaned_data['isbn'],
                title=form.cleaned_data['title'],
                author=author,
                summary=form.cleaned_data['summary'] or 'No description available.',
                cover_url=form.cleaned_data['cover_url'],
            )
            for genre_name in form.cleaned_data['genres'].split(','):
                genre_name = genre_name.strip()[:200]
                if genre_name:
                    genre, _ = Genre.objects.get_or_create(name=genre_name)
                    book.genre.add(genre)
        messages.success(request, f"'{book.title}' was created from ISBN {book.isbn}.")
        return redirect('book-detail', pk=book.pk)
    elif request.method == 'POST':
        looked_up = True

    return render(request, 'catalog/book_import_isbn.html', {
        'form': form,
        'looked_up': looked_up,
    })


@login_required
def member_list(request):
    _require_crud_permission(request.user, 'view')
    member_queryset = User.objects.select_related('profile')
    if not is_superadmin(request.user):
        member_queryset = member_queryset.filter(profile__role__in=BORROWER_ROLES)
    members = list(member_queryset.annotate(
        loan_count=Count('loans', distinct=True),
        active_loan_count=Count('loans', filter=Q(loans__status='active'), distinct=True),
    ).order_by('username'))
    penalty_totals = dict(
        Penalty.objects.filter(status='unpaid').values_list('borrower_id')
        .annotate(total=Sum('amount'))
    )
    for member in members:
        member.unpaid_penalty_total = penalty_totals.get(member.pk, 0)
    return render(request, 'catalog/member_list.html', {'members': members})


@login_required
def member_create(request):
    _require_crud_permission(request.user, 'add')
    form = MemberForm(request.POST or None, request.FILES or None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        member = form.save()
        messages.success(request, f"Member '{member.username}' was created.")
        return redirect('member-detail', pk=member.pk)
    return render(request, 'catalog/member_form.html', {'form': form, 'mode': 'Add'})


@login_required
def member_detail(request, pk):
    _require_crud_permission(request.user, 'view')
    member = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    if not can_manage_member(request.user, member):
        raise PermissionDenied
    context = {
        'member': member,
        'loans': member.loans.select_related('book_instance').order_by('-issued_at')[:20],
        'penalties': member.penalties.order_by('-assessed_at')[:20],
        'active_loans': member.loans.filter(status='active').count(),
        'unpaid_total': member.penalties.filter(status='unpaid').aggregate(total=Sum('amount'))['total'] or 0,
    }
    return render(request, 'catalog/member_detail.html', context)


@login_required
def member_update(request, pk):
    _require_crud_permission(request.user, 'change')
    member = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    if not can_manage_member(request.user, member):
        raise PermissionDenied
    form = MemberForm(request.POST or None, request.FILES or None, instance=member, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        member = form.save()
        messages.success(request, f"Member '{member.username}' was updated.")
        return redirect('member-detail', pk=member.pk)
    return render(request, 'catalog/member_form.html', {'form': form, 'member': member, 'mode': 'Edit'})


@login_required
def member_delete(request, pk):
    _require_crud_permission(request.user, 'delete')
    member = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    if not can_manage_member(request.user, member):
        raise PermissionDenied
    if member == request.user or is_superadmin(member):
        messages.error(request, 'Your own account and super-admin accounts cannot be deleted here.')
        return redirect('member-detail', pk=member.pk)
    active_loans = member.loans.filter(status='active').count()
    loan_count = member.loans.count()
    penalty_count = member.penalties.count()
    if request.method == 'POST':
        if active_loans:
            messages.error(request, 'Return all active loans before deleting this member.')
            return redirect('member-detail', pk=member.pk)
        try:
            member.delete()
        except ProtectedError:
            messages.error(request, 'This member has protected loan or penalty history and cannot be deleted. Deactivate the account instead.')
            return redirect('member-detail', pk=pk)
        messages.success(request, 'Member account was deleted.')
        return redirect('members')
    return render(request, 'catalog/member_confirm_delete.html', {'member': member, 'active_loans': active_loans, 'loan_count': loan_count, 'penalty_count': penalty_count})


@login_required
def copy_list(request):
    _require_crud_permission(request.user, 'view')
    copies = BookInstance.objects.select_related('book', 'book__author', 'borrower').order_by('book__title', 'accession_number', 'id')
    return render(request, 'catalog/copy_list.html', {'copies': copies})


@login_required
def copy_create(request):
    _require_crud_permission(request.user, 'add')
    form = BookInstanceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        copy = form.save()
        messages.success(request, f"Copy of '{copy.book.title}' was registered.")
        return redirect('copy-detail', pk=copy.pk)
    return render(request, 'catalog/copy_form.html', {'form': form, 'mode': 'Add'})


@login_required
def copy_detail(request, pk):
    _require_crud_permission(request.user, 'view')
    copy = get_object_or_404(BookInstance.objects.select_related('book', 'book__author', 'borrower'), pk=pk)
    return render(request, 'catalog/copy_detail.html', {
        'copy': copy,
        'loans': copy.loans.select_related('borrower').order_by('-issued_at')[:20],
        'audits': copy.scan_audits.select_related('actor', 'target_user').order_by('-created_at')[:20],
        'issue_form': CopyIssueForm(),
    })


@login_required
def copy_update(request, pk):
    _require_crud_permission(request.user, 'change')
    copy = get_object_or_404(BookInstance.objects.select_related('book'), pk=pk)
    form = BookInstanceForm(request.POST or None, instance=copy)
    if request.method == 'POST' and form.is_valid():
        copy = form.save()
        messages.success(request, 'Physical copy information was updated.')
        return redirect('copy-detail', pk=copy.pk)
    return render(request, 'catalog/copy_form.html', {'form': form, 'copy': copy, 'mode': 'Edit'})


@login_required
@require_POST
def copy_issue(request, pk):
    _require_crud_permission(request.user, 'change')
    form = CopyIssueForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Select an active member account.')
        return redirect('copy-detail', pk=pk)
    with transaction.atomic():
        copy = get_object_or_404(BookInstance.objects.select_for_update(of=('self',)).select_related('book'), pk=pk)
        try:
            loan = checkout_copy(copy, form.cleaned_data['borrower'], issued_by=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('copy-detail', pk=pk)
        ScanAudit.objects.create(actor=request.user, action='issue', raw_code=f'MANUAL:COPY:{copy.pk}', book_instance=copy, target_user=loan.borrower, success=True, message=f'Manually issued {copy.book.title} to {loan.borrower.username}.')
    messages.success(request, f"Issued to {loan.borrower.username}; due {loan.due_date:%d %b %Y}.")
    return redirect('copy-detail', pk=pk)


@login_required
@require_POST
def copy_checkin(request, pk):
    _require_crud_permission(request.user, 'change')
    with transaction.atomic():
        copy = get_object_or_404(BookInstance.objects.select_for_update(of=('self',)).select_related('book', 'borrower'), pk=pk)
        try:
            result = checkin_copy(copy, request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('copy-detail', pk=pk)
        ScanAudit.objects.create(actor=request.user, action='return', raw_code=f'MANUAL:COPY:{copy.pk}', book_instance=copy, target_user=result['loan'].borrower, success=True, message=f'Manually returned {copy.book.title}.')
    message = f"'{copy.book.title}' was returned."
    if result['fine_amount']:
        message += f" INR {result['fine_amount']} penalty recorded."
    messages.success(request, message)
    return redirect('copy-detail', pk=pk)


@login_required
def copy_delete(request, pk):
    _require_crud_permission(request.user, 'delete')
    copy = get_object_or_404(BookInstance.objects.select_related('book', 'borrower'), pk=pk)
    active_loan = copy.loans.filter(status='active').exists() or copy.status == 'o'
    history_count = copy.loans.count()
    if request.method == 'POST':
        if active_loan:
            messages.error(request, 'Return the copy before deleting it.')
            return redirect('copy-detail', pk=pk)
        title = copy.book.title
        copy.delete()
        messages.success(request, f"Physical copy of '{title}' was deleted. Loan history was retained.")
        return redirect('copies')
    return render(request, 'catalog/copy_confirm_delete.html', {'copy': copy, 'active_loan': active_loan, 'history_count': history_count})


def _taxonomy_crud(request, model, form_class, template, redirect_name, pk=None):
    _require_crud_permission(request.user, 'change' if pk else 'add')
    instance = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        messages.success(request, f"'{item}' was saved.")
        return redirect(redirect_name)
    return render(request, template, {'form': form, 'item': instance, 'mode': 'Edit' if instance else 'Add'})


@login_required
def taxonomy_list(request):
    _require_crud_permission(request.user, 'view')
    authors = Author.objects.annotate(book_count=Count('book')).order_by('last_name', 'first_name')
    genres = Genre.objects.annotate(book_count=Count('book')).order_by('name')
    return render(request, 'catalog/taxonomy_list.html', {'authors': authors, 'genres': genres})


@login_required
def author_create(request): return _taxonomy_crud(request, Author, AuthorForm, 'catalog/taxonomy_form.html', 'taxonomy')
@login_required
def author_update(request, pk): return _taxonomy_crud(request, Author, AuthorForm, 'catalog/taxonomy_form.html', 'taxonomy', pk)
@login_required
def genre_create(request): return _taxonomy_crud(request, Genre, GenreForm, 'catalog/taxonomy_form.html', 'taxonomy')
@login_required
def genre_update(request, pk): return _taxonomy_crud(request, Genre, GenreForm, 'catalog/taxonomy_form.html', 'taxonomy', pk)


@login_required
@require_POST
def taxonomy_delete(request, kind, pk):
    _require_crud_permission(request.user, 'delete')
    model = Author if kind == 'author' else Genre if kind == 'genre' else None
    if model is None: return HttpResponse(status=404)
    item = get_object_or_404(model, pk=pk)
    if (kind == 'author' and item.book_set.exists()) or (kind == 'genre' and item.book_set.exists()):
        messages.error(request, 'This record is used by books and cannot be deleted.')
    else:
        item.delete(); messages.success(request, 'Catalog classification was deleted.')
    return redirect('taxonomy')


@login_required
@require_POST
def fulfill_reservation(request, pk):
    _require_crud_permission(request.user, 'change')
    reservation = get_object_or_404(Reservation, pk=pk, status='active')
    reservation.resolve('fulfilled')
    messages.success(request, 'Reservation marked fulfilled.')
    return redirect('reservations')


@login_required
def penalty_receipt(request, pk):
    penalty = get_object_or_404(
        Penalty.objects.select_related('borrower').prefetch_related('transactions__recorded_by'),
        pk=pk,
    )
    if penalty.borrower != request.user:
        _require_crud_permission(request.user, 'view')
    if penalty.status == 'unpaid':
        messages.error(request, 'A receipt is available after payment or waiver.')
        return redirect('penalties')
    return render(request, 'catalog/penalty_receipt.html', {'penalty': penalty})


@login_required
def audit_dashboard(request):
    _require_crud_permission(request.user, 'view')
    base = ScanAudit.objects.all()
    audits = base.select_related('actor', 'target_user', 'book_instance__book').order_by('-created_at')[:500]
    return render(request, 'catalog/audit_dashboard.html', {'audits': audits, 'success_count': base.filter(success=True).count(), 'error_count': base.filter(success=False).count()})

def index(request):
    """Render a role-focused home page backed by live circulation data."""
    today = timezone.localdate()
    num_books = Book.objects.count()
    num_instances = BookInstance.objects.count()
    num_instances_available = BookInstance.objects.filter(status__exact='a').count()
    num_instances_issued = BookInstance.objects.filter(status__exact='o').count()
    num_instances_overdue = sum(
        instance.is_overdue
        for instance in BookInstance.objects.filter(status='o').only('due_back')
    )
    num_authors = Author.objects.count()
    all_on_loan = BookInstance.objects.filter(status__exact='o')
    active_fines = sum(inst.fine_amount for inst in all_on_loan)
    recorded_fines = Penalty.objects.filter(status='unpaid').aggregate(
        total=Sum('amount')
    )['total'] or 0
    total_fines = active_fines + recorded_fines

    context = {
        'num_books': num_books,
        'num_instances': num_instances,
        'num_instances_available': num_instances_available,
        'num_instances_issued': num_instances_issued,
        'num_instances_overdue': num_instances_overdue,
        'num_authors': num_authors,
        'total_fines': total_fines,
    }

    if request.user.is_authenticated:
        role = get_user_role(request.user)
        user_loans = BookInstance.objects.filter(borrower=request.user, status__exact='o')
        active_user_fines = sum(inst.fine_amount for inst in user_loans)
        recorded_user_fines = Penalty.objects.filter(
            borrower=request.user,
            status='unpaid',
        ).aggregate(total=Sum('amount'))['total'] or 0
        context['user_fines'] = active_user_fines + recorded_user_fines

        if role in BORROWER_ROLES:
            active_loans = list(
                Loan.objects.filter(borrower=request.user, status='active')
                .select_related('book_instance__book', 'book_instance__book__author')
                .order_by('due_date')
            )
            context.update({
                'member_active_loans': active_loans,
                'member_overdue_count': sum(loan.is_overdue for loan in active_loans),
                'member_due_soon_count': sum(
                    today <= loan.due_date <= today + datetime.timedelta(days=3)
                    for loan in active_loans
                ),
                'member_reservation_count': Reservation.objects.filter(
                    borrower=request.user,
                    status='active',
                ).count(),
                'member_notifications': request.user.notifications.filter(
                    is_read=False,
                )[:3],
                'member_loan_days': settings.LOAN_DAYS_BY_ROLE[role],
                'member_loan_limit': settings.LOAN_LIMIT_BY_ROLE[role],
                'next_due_loan': active_loans[0] if active_loans else None,
            })
        elif is_library_admin(request.user) and has_crud_permission(request.user, 'view'):
            context.update({
                'issued_today': Loan.objects.filter(issued_at__date=today).count(),
                'returned_today': Loan.objects.filter(returned_at__date=today).count(),
                'active_reservation_count': Reservation.objects.filter(status='active').count(),
                'unpaid_penalty_count': Penalty.objects.filter(status='unpaid').count(),
                'recent_loans': Loan.objects.select_related(
                    'borrower',
                    'book_instance',
                ).order_by('-issued_at')[:5],
            })

    return render(request, 'index.html', context=context)


@login_required
def library_card(request):
    """Display a borrower's scannable Shelfwise membership card."""
    role = get_user_role(request.user)
    if role not in BORROWER_ROLES:
        raise PermissionDenied
    context = {
        'member_role': role,
        'loan_days': settings.LOAN_DAYS_BY_ROLE[role],
        'loan_limit': settings.LOAN_LIMIT_BY_ROLE[role],
        'active_loan_count': request.user.loans.filter(status='active').count(),
        'active_reservation_count': request.user.reservations.filter(status='active').count(),
        'unpaid_total': request.user.penalties.filter(status='unpaid').aggregate(
            total=Sum('amount'),
        )['total'] or 0,
    }
    return render(request, 'catalog/library_card.html', context)


@login_required
def account_settings(request):
    """Allow users to maintain contact details without changing their role."""
    form = AccountForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your account details were updated.')
        return redirect('account-settings')
    role = get_user_role(request.user)
    return render(request, 'catalog/account_settings.html', {
        'form': form,
        'active_loan_count': request.user.loans.filter(status='active').count(),
        'unread_count': request.user.notifications.filter(is_read=False).count(),
        'account_loan_days': settings.LOAN_DAYS_BY_ROLE.get(role),
        'account_loan_limit': settings.LOAN_LIMIT_BY_ROLE.get(role),
    })


class BookListView(generic.ListView):
    model = Book
    paginate_by = 10

    def get_queryset(self):
        queryset = Book.objects.select_related('author').prefetch_related('genre').annotate(
            available_copies=Count(
                'bookinstance',
                filter=Q(bookinstance__status='a'),
                distinct=True,
            ),
            total_copies=Count('bookinstance', distinct=True),
        )
        query = self.request.GET.get('q', '').strip()
        genre = self.request.GET.get('genre', '').strip()
        availability = self.request.GET.get('availability', '').strip()
        sort = self.request.GET.get('sort', 'title').strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(isbn__icontains=query)
                | Q(author__first_name__icontains=query)
                | Q(author__last_name__icontains=query)
                | Q(genre__name__icontains=query)
            ).distinct()
        if genre.isdigit():
            queryset = queryset.filter(genre__pk=int(genre))
        if availability == 'available':
            queryset = queryset.filter(available_copies__gt=0)
        elif availability == 'unavailable':
            queryset = queryset.filter(available_copies=0)

        ordering = {
            'title': ('title', 'pk'),
            'author': ('author__last_name', 'author__first_name', 'title'),
            'newest': ('-pk',),
            'availability': ('-available_copies', 'title'),
        }
        return queryset.order_by(*ordering.get(sort, ordering['title']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['genres'] = Genre.objects.annotate(
            book_count=Count('book', distinct=True),
        ).filter(book_count__gt=0).order_by('name')
        context['selected_genre'] = self.request.GET.get('genre', '')
        context['availability_filter'] = self.request.GET.get('availability', '')
        selected_sort = self.request.GET.get('sort', 'title')
        context['selected_sort'] = selected_sort if selected_sort in {
            'title', 'author', 'newest', 'availability'
        } else 'title'
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['querystring'] = query_params.urlencode()
        context['active_filter_count'] = sum(bool(value) for value in (
            context['q'], context['selected_genre'], context['availability_filter'],
        ))
        return context


class BookDetailView(generic.DetailView):
    model = Book

    def get_queryset(self):
        return Book.objects.select_related('author').prefetch_related(
            'genre', 'bookinstance_set'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        copies = list(self.object.bookinstance_set.all())
        context['copies'] = copies
        context['available_count'] = sum(copy.status == 'a' for copy in copies)
        context['reservation_count'] = self.object.reservations.filter(
            status='active'
        ).count()
        context['user_has_reservation'] = False
        if self.request.user.is_authenticated:
            context['user_has_reservation'] = self.object.reservations.filter(
                borrower=self.request.user,
                status='active',
            ).exists()
        return context


class LoanedBooksByUserListView(LoginRequiredMixin, generic.ListView):
    """Generic class-based view listing books on loan to current user."""
    model = BookInstance
    template_name = 'catalog/bookinstance_list_borrowed_user.html'

    def get_queryset(self):
        return (
            BookInstance.objects.select_related('book', 'book__author')
            .filter(borrower=self.request.user)
            .filter(status__exact='o')
            .order_by('due_back')
        )


class LoanedBooksAllListView(UserPassesTestMixin, generic.ListView):
    """Generic class-based view listing all books on loan. Only visible to Super Admin or Admin."""
    model = BookInstance
    template_name = 'catalog/bookinstance_list_borrowed_all.html'

    def test_func(self):
        return has_crud_permission(self.request.user, 'view')

    def get_queryset(self):
        return (
            BookInstance.objects.select_related('book', 'borrower')
            .filter(status__exact='o')
            .order_by('due_back')
        )


class PenaltyListView(LoginRequiredMixin, generic.ListView):
    model = Penalty
    template_name = 'catalog/penalty_list.html'

    def get_queryset(self):
        queryset = Penalty.objects.select_related('borrower', 'book_instance')
        if is_library_admin(self.request.user) and not has_crud_permission(self.request.user, 'view'):
            raise PermissionDenied
        if not is_library_admin(self.request.user):
            queryset = queryset.filter(borrower=self.request.user)
        status = self.request.GET.get('status', '').strip()
        if status in {'unpaid', 'paid', 'waived'}:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-assessed_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible_penalties = Penalty.objects.all()
        if not is_library_admin(self.request.user):
            visible_penalties = visible_penalties.filter(borrower=self.request.user)
        context['is_library_admin'] = (
            is_library_admin(self.request.user)
            and has_crud_permission(self.request.user, 'view')
        )
        context['status_filter'] = self.request.GET.get('status', '')
        context['outstanding_total'] = visible_penalties.filter(
            status='unpaid'
        ).aggregate(total=Sum('amount'))['total'] or 0
        return context


class LoanHistoryListView(LoginRequiredMixin, generic.ListView):
    model = Loan
    template_name = 'catalog/loan_history.html'

    def get_queryset(self):
        queryset = Loan.objects.select_related('borrower', 'book_instance')
        if is_library_admin(self.request.user) and not has_crud_permission(self.request.user, 'view'):
            raise PermissionDenied
        if not is_library_admin(self.request.user):
            queryset = queryset.filter(borrower=self.request.user)
        status = self.request.GET.get('status', '').strip()
        if status in {'active', 'returned', 'lost'}:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-issued_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_library_admin'] = (
            is_library_admin(self.request.user)
            and has_crud_permission(self.request.user, 'view')
        )
        context['status_filter'] = self.request.GET.get('status', '')
        return context


class ReservationListView(LoginRequiredMixin, generic.ListView):
    model = Reservation
    template_name = 'catalog/reservation_list.html'

    def get_queryset(self):
        queryset = Reservation.objects.select_related('book', 'borrower')
        if is_library_admin(self.request.user) and not has_crud_permission(self.request.user, 'view'):
            raise PermissionDenied
        if not is_library_admin(self.request.user):
            queryset = queryset.filter(borrower=self.request.user)
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_library_admin'] = (
            is_library_admin(self.request.user)
            and has_crud_permission(self.request.user, 'view')
        )
        return context


class NotificationListView(LoginRequiredMixin, generic.ListView):
    model = Notification
    template_name = 'catalog/notification_list.html'

    def get_queryset(self):
        queryset = self.request.user.notifications.all()
        status = self.request.GET.get('status', '').strip()
        if status == 'unread':
            queryset = queryset.filter(is_read=False)
        elif status == 'read':
            queryset = queryset.filter(is_read=True)
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', '')
        return context


@login_required
@require_POST
def borrow_book_copy(request, pk):
    """Legacy self-checkout endpoint retained only to reject unauthorized issue attempts."""
    return HttpResponse('Only the library in-charge can issue books.', status=403)


@login_required
@require_POST
def return_book_copy(request, pk):
    """View function for returning a specific copy of a book (Super Admin/Admin only)."""
    # Check permissions
    if not is_library_admin(request.user):
        messages.error(request, "You do not have permission to mark books as returned.")
        return redirect('index')
    _require_crud_permission(request.user, 'change')

    with transaction.atomic():
        book_instance = get_object_or_404(
            BookInstance.objects.select_for_update(of=('self',)).select_related('book'),
            pk=pk,
        )

        if book_instance.status != 'o':
            messages.error(request, "This copy is not currently on loan.")
            return redirect('all-borrowed')

        result = checkin_copy(book_instance, request.user)
        fine_amount = result['fine_amount']
        days_overdue = result['days_overdue']

    if fine_amount:
        messages.success(
            request,
            f"'{book_instance.book.title}' was returned. An INR {fine_amount} "
            f"penalty was recorded for {days_overdue} overdue days.",
        )
    else:
        messages.success(
            request,
            f"'{book_instance.book.title}' was returned and is now available.",
        )
    return redirect('all-borrowed')


@login_required
@require_POST
def resolve_penalty(request, pk, resolution):
    """Mark an outstanding penalty as paid or waived (library admins only)."""
    if not is_library_admin(request.user):
        messages.error(request, 'You do not have permission to resolve penalties.')
        return redirect('penalties')
    _require_crud_permission(request.user, 'change')
    if resolution not in {'paid', 'waived'}:
        messages.error(request, 'Unknown penalty resolution.')
        return redirect('penalties')

    with transaction.atomic():
        penalty = get_object_or_404(Penalty.objects.select_for_update(), pk=pk)
        if penalty.status != 'unpaid':
            messages.error(request, 'This penalty has already been resolved.')
            return redirect('penalties')
        penalty.resolve(resolution)
        method = request.POST.get('method', '').strip()
        allowed_methods = {value for value, _ in PenaltyTransaction.METHOD_CHOICES}
        if resolution == 'waived':
            method = 'waiver'
        elif method not in allowed_methods or method == 'waiver':
            method = 'cash'
        PenaltyTransaction.objects.create(
            penalty=penalty,
            resolution=resolution,
            amount=penalty.amount if resolution == 'paid' else 0,
            method=method,
            reference=request.POST.get('reference', '').strip()[:100],
            notes=request.POST.get('notes', '').strip(),
            recorded_by=request.user,
        )

    messages.success(
        request,
        f"Penalty for {penalty.borrower.username} marked {resolution}.",
    )
    return redirect('penalties')


@login_required
@require_POST
def renew_loan(request, pk):
    if not is_library_admin(request.user):
        messages.error(request, 'Only the library in-charge can renew a loan.')
        return redirect('loan-history')
    _require_crud_permission(request.user, 'change')
    with transaction.atomic():
        loan = get_object_or_404(
            Loan.objects.select_for_update(of=('self',)).select_related('book_instance__book'),
            pk=pk,
            status='active',
        )
        if loan.is_overdue:
            messages.error(request, 'Overdue loans cannot be renewed.')
            return redirect('loan-history')
        if loan.renewal_count >= settings.MAX_RENEWALS:
            messages.error(request, 'This loan has already used its renewal.')
            return redirect('loan-history')
        if Reservation.objects.filter(
            book=loan.book_instance.book,
            status='active',
        ).exclude(borrower=loan.borrower).exists():
            messages.error(request, 'This book is reserved by another member.')
            return redirect('loan-history')

        borrower_role = getattr(loan.borrower.profile, 'role', 'student')
        renewal_days = settings.LOAN_DAYS_BY_ROLE.get(
            borrower_role,
            settings.LOAN_DAYS_BY_ROLE['student'],
        )
        loan.due_date += datetime.timedelta(days=renewal_days)
        loan.renewal_count += 1
        loan.save(update_fields=['due_date', 'renewal_count'])
        loan.book_instance.due_back = loan.due_date
        loan.book_instance.save(update_fields=['due_back'])

    messages.success(request, f"'{loan.book_title}' renewed until {loan.due_date}.")
    return redirect('loan-history')


@login_required
@require_POST
def create_reservation(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if book.bookinstance_set.filter(status='a').exists():
        messages.error(request, 'A copy is available. Ask the library in-charge to issue it.')
        return redirect('book-detail', pk=book.pk)
    if BookInstance.objects.filter(
        book=book,
        borrower=request.user,
        status='o',
    ).exists():
        messages.error(request, 'You already have this book on loan.')
        return redirect('book-detail', pk=book.pk)

    reservation, created = Reservation.objects.get_or_create(
        book=book,
        borrower=request.user,
        status='active',
    )
    if created:
        messages.success(request, f"'{book.title}' was added to your reservations.")
    else:
        messages.error(request, 'You already have an active reservation for this book.')
    return redirect('book-detail', pk=book.pk)


@login_required
@require_POST
def cancel_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, status='active')
    if reservation.borrower != request.user:
        if not is_library_admin(request.user):
            messages.error(request, 'You do not have permission to cancel this reservation.')
            return redirect('reservations')
        _require_crud_permission(request.user, 'change')
    reservation.resolve('cancelled')
    messages.success(request, f"Reservation for '{reservation.book.title}' cancelled.")
    return redirect('reservations')


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_read()
    return redirect('notifications')


@login_required
@require_POST
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications')


def _qr_png(payload):
    image = qrcode.make(payload)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return HttpResponse(output.getvalue(), content_type='image/png')


def _copy_uuid_from_code(raw_code):
    value = raw_code.strip()
    if value.upper().startswith('SHELFWISE:COPY:'):
        value = value.split(':', 2)[2]
    return uuid.UUID(value)


def _member_from_code(raw_code):
    value = raw_code.strip()
    if value.upper().startswith('SHELFWISE:MEMBER:'):
        return User.objects.get(pk=int(value.split(':', 2)[2]), is_active=True)
    return User.objects.get(username=value, is_active=True)


@login_required
def copy_qr_code(request, pk):
    _require_crud_permission(request.user, 'view')
    book_instance = get_object_or_404(BookInstance, pk=pk)
    return _qr_png(f'SHELFWISE:COPY:{book_instance.pk}')


@login_required
def member_qr_code(request, pk):
    member = get_object_or_404(User, pk=pk, is_active=True)
    if member != request.user:
        _require_crud_permission(request.user, 'view')
    return _qr_png(f'SHELFWISE:MEMBER:{member.pk}')


@login_required
def scanner(request):
    if not is_library_admin(request.user):
        messages.error(request, 'Only library administrators can use circulation scanning.')
        return redirect('index')
    _require_crud_permission(request.user, 'change')
    return render(request, 'catalog/scanner.html')


@login_required
@require_POST
def process_scan(request):
    _require_crud_permission(request.user, 'change')
    action = request.POST.get('action', '').strip()
    copy_code = request.POST.get('copy_code', '').strip()
    member_code = request.POST.get('member_code', '').strip()
    audit_values = {
        'actor': request.user,
        'action': action if action in {'issue', 'return'} else 'error',
        'raw_code': f'copy={copy_code}; member={member_code}'[:300],
    }
    try:
        copy_id = _copy_uuid_from_code(copy_code)
        with transaction.atomic():
            book_instance = get_object_or_404(
                BookInstance.objects.select_for_update(of=('self',)).select_related('book', 'borrower'),
                pk=copy_id,
            )
            audit_values['book_instance'] = book_instance
            if action == 'issue':
                member = _member_from_code(member_code)
                audit_values['target_user'] = member
                loan = checkout_copy(book_instance, member, issued_by=request.user)
                message = (
                    f"Issued '{book_instance.book.title}' to {member.username}; "
                    f'due {loan.due_date:%d %b %Y}.'
                )
            elif action == 'return':
                member = book_instance.borrower
                audit_values['target_user'] = member
                result = checkin_copy(book_instance, request.user)
                message = f"Returned '{book_instance.book.title}'."
                if result['fine_amount']:
                    message += f" Penalty: INR {result['fine_amount']}."
            else:
                raise ValueError('Select Issue or Return before processing the scan.')
            ScanAudit.objects.create(**audit_values, success=True, message=message)
    except (ValueError, User.DoesNotExist, Http404) as exc:
        error_message = str(exc) or 'No matching active copy or member was found.'
        ScanAudit.objects.create(**audit_values, success=False, message=error_message[:300])
        messages.error(request, error_message)
    else:
        messages.success(request, message)
    return redirect('scanner')


@login_required
def print_qr_labels(request):
    _require_crud_permission(request.user, 'view')
    context = {
        'copies': BookInstance.objects.select_related('book').order_by('book__title', 'imprint'),
        'members': User.objects.filter(
            is_active=True, profile__role__in=BORROWER_ROLES
        ).order_by('username'),
    }
    return render(request, 'catalog/qr_labels.html', context)
