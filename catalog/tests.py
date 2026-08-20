import datetime
import base64
import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.conf import settings
from django.core.management import call_command
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .management.commands.seed_demo import DEMO_BOOKS
from .models import Author, Book, BookInstance, Genre, Loan, Notification, Penalty, Reservation, ScanAudit
from .notifications import deliver_pending_notifications, generate_library_notifications
from .circulation import checkout_copy
from .permissions import LIBRARY_GROUP_NAME


class CatalogTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(first_name='Octavia', last_name='Butler')
        cls.genre = Genre.objects.create(name='Science Fiction')
        cls.book = Book.objects.create(
            title='Kindred',
            author=cls.author,
            summary='A landmark speculative novel.',
            isbn='9780807083697',
        )
        cls.book.genre.add(cls.genre)
        cls.copy = BookInstance.objects.create(
            book=cls.book,
            imprint='Beacon Press',
            status='a',
        )
        cls.member = User.objects.create_user('member', password='safe-test-password')
        cls.teacher = User.objects.create_user('teacher', password='safe-test-password')
        cls.teacher.profile.role = 'teacher'
        cls.teacher.profile.save(update_fields=['role'])
        cls.admin_user = User.objects.create_user('librarian', password='safe-test-password')
        cls.admin_user.profile.role = 'library'
        cls.admin_user.profile.can_view = True
        cls.admin_user.profile.can_add = True
        cls.admin_user.profile.can_change = True
        cls.admin_user.profile.can_delete = True
        cls.admin_user.profile.save(update_fields=[
            'role', 'can_view', 'can_add', 'can_change', 'can_delete',
        ])

    def test_public_pages_render(self):
        for url in (reverse('index'), reverse('books'), self.book.get_absolute_url()):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_application_uses_one_custom_login_page(self):
        login_response = self.client.get(reverse('login'))
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, 'One login for members, librarians, and administrators.')
        self.assertContains(login_response, reverse('password_reset'))

    def test_member_dashboard_prioritizes_personal_account(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('index'))
        self.assertContains(response, 'My library dashboard')
        self.assertContains(response, 'My account')
        self.assertContains(response, '15 days')
        self.assertContains(response, reverse('library-card'))

    def test_staff_dashboard_prioritizes_circulation(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('index'))
        self.assertContains(response, 'Circulation dashboard')
        self.assertContains(response, 'Today at the desk')
        self.assertNotContains(response, 'My library card')

    def test_borrower_can_open_own_library_card(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('library-card'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SW-')
        self.assertContains(response, reverse('member-qr', args=[self.member.pk]))

        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse('library-card')).status_code, 403)

    def test_member_can_update_personal_account_without_changing_role(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('account-settings'), {
            'first_name': 'Asha',
            'last_name': 'Reader',
            'email': 'asha.reader@example.com',
        })
        self.assertRedirects(response, reverse('account-settings'))
        self.member.refresh_from_db()
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.get_full_name(), 'Asha Reader')
        self.assertEqual(self.member.email, 'asha.reader@example.com')
        self.assertEqual(self.member.profile.role, 'student')

    def test_account_requires_a_unique_email_address(self):
        self.teacher.email = 'teacher@example.com'
        self.teacher.save(update_fields=['email'])
        self.client.force_login(self.member)
        response = self.client.post(reverse('account-settings'), {
            'first_name': 'Member',
            'last_name': 'Reader',
            'email': 'TEACHER@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This email address is already used by another account.')

    def test_custom_password_change_flow_updates_password(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('password_change'), {
            'old_password': 'safe-test-password',
            'new_password1': 'Better-member-password-2026',
            'new_password2': 'Better-member-password-2026',
        })
        self.assertRedirects(response, reverse('password_change_done'))
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password('Better-member-password-2026'))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_sends_email_for_registered_member(self):
        self.member.email = 'member@example.com'
        self.member.save(update_fields=['email'])
        response = self.client.post(reverse('password_reset'), {'email': self.member.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reset your Shelfwise password', mail.outbox[0].subject)

    def test_health_check_and_legacy_service_worker_render(self):
        health = self.client.get(reverse('health-check'))
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {'status': 'ok'})
        self.assertEqual(health['Cache-Control'], 'no-store')

        worker = self.client.get(reverse('legacy-service-worker'))
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker['Content-Type'], 'application/javascript')
        self.assertContains(worker, 'unregister')

    def test_django_admin_routes_are_not_exposed(self):
        self.assertEqual(self.client.get('/admin/').status_code, 404)
        self.assertEqual(self.client.get('/admin/login/').status_code, 404)

    def test_catalog_searches_title_author_isbn_and_genre(self):
        for query in ('Kindred', 'Butler', '9780807083697', 'Science Fiction'):
            with self.subTest(query=query):
                response = self.client.get(reverse('books'), {'q': query})
                self.assertContains(response, 'Kindred')

    def test_catalog_displays_live_copy_availability(self):
        response = self.client.get(reverse('books'))
        self.assertContains(response, '1 available')

    def test_catalog_filters_by_genre_and_availability(self):
        other_genre = Genre.objects.create(name='History')
        other_book = Book.objects.create(
            title='A Short History of Libraries',
            author=self.author,
            summary='A reference title.',
            isbn='9780000000002',
        )
        other_book.genre.add(other_genre)

        response = self.client.get(reverse('books'), {
            'genre': self.genre.pk,
            'availability': 'available',
        })
        self.assertContains(response, 'Kindred')
        self.assertNotContains(response, other_book.title)

        self.copy.status = 'o'
        self.copy.borrower = self.member
        self.copy.save(update_fields=['status', 'borrower'])
        response = self.client.get(reverse('books'), {'availability': 'unavailable'})
        self.assertContains(response, 'Kindred')

    def test_catalog_pagination_preserves_active_filters(self):
        for index in range(11):
            book = Book.objects.create(
                title=f'Unavailable title {index:02d}',
                author=self.author,
                summary='Catalog filter pagination test.',
                isbn=f'9000000000{index:03d}',
            )
            book.genre.add(self.genre)

        response = self.client.get(reverse('books'), {
            'genre': self.genre.pk,
            'availability': 'unavailable',
            'sort': 'newest',
        })
        self.assertContains(response, 'page=2')
        self.assertContains(response, f'genre={self.genre.pk}')
        self.assertContains(response, 'availability=unavailable')
        self.assertContains(response, 'sort=newest')

    def test_librarian_can_edit_book_with_local_generated_cover(self):
        self.book.cover_url = '/static/catalog/book-covers/foundation-ai.webp'
        self.book.save(update_fields=['cover_url'])
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('book-update', args=[self.book.pk]), {
            'title': self.book.title,
            'author': self.author.pk,
            'summary': self.book.summary,
            'isbn': self.book.isbn,
            'genre': [self.genre.pk],
            'cover_url': self.book.cover_url,
        })
        self.assertRedirects(response, self.book.get_absolute_url())

    def test_uploaded_cover_uses_django_media_storage_and_is_served(self):
        png_bytes = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
            'AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        )
        upload = SimpleUploadedFile('cover.png', png_bytes, content_type='image/png')
        self.client.force_login(self.admin_user)

        media_root = settings.BASE_DIR / '.test-media'
        shutil.rmtree(media_root, ignore_errors=True)
        media_root.mkdir(exist_ok=True)
        try:
            with self.settings(MEDIA_ROOT=media_root):
                response = self.client.post(reverse('book-create'), {
                    'title': 'Parable of the Sower',
                    'author': self.author.pk,
                    'summary': 'A test catalog record with a stored cover.',
                    'isbn': '9780446675505',
                    'genre': [self.genre.pk],
                    'cover_url': '',
                    'asset_upload': upload,
                })
                book = Book.objects.get(isbn='9780446675505')

                self.assertRedirects(response, book.get_absolute_url())
                self.assertTrue(book.cover_url.startswith('/media/book-covers/'))
                self.assertTrue((media_root / book.cover_url.removeprefix('/media/')).is_file())
                media_response = self.client.get(book.cover_url)
                self.assertEqual(media_response.status_code, 200)
                self.assertEqual(b''.join(media_response.streaming_content), png_bytes)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)

    def test_borrow_requires_authentication_and_post(self):
        url = reverse('borrow-copy', args=[self.copy.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_member_cannot_self_issue_available_copy(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('borrow-copy', args=[self.copy.pk]))
        self.assertEqual(response.status_code, 403)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, 'a')
        self.assertIsNone(self.copy.borrower)
        self.assertFalse(Loan.objects.filter(book_instance=self.copy).exists())

    def test_library_incharge_issues_student_for_fifteen_days(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('copy-issue', args=[self.copy.pk]), {'borrower': self.member.pk})
        self.assertRedirects(response, reverse('copy-detail', args=[self.copy.pk]))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.borrower, self.member)
        self.assertEqual(self.copy.due_back, datetime.date.today() + datetime.timedelta(days=15))

    def test_library_incharge_issues_teacher_for_thirty_days(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('copy-issue', args=[self.copy.pk]), {'borrower': self.teacher.pk})
        self.assertRedirects(response, reverse('copy-detail', args=[self.copy.pk]))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.borrower, self.teacher)
        self.assertEqual(self.copy.due_back, datetime.date.today() + datetime.timedelta(days=30))

    def test_checkout_service_rejects_non_librarian_issuer(self):
        with self.assertRaises(PermissionError):
            checkout_copy(self.copy, self.member, issued_by=self.teacher)

    def test_staff_flag_does_not_override_student_role(self):
        self.member.is_staff = True
        self.member.save(update_fields=['is_staff'])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('members')).status_code, 403)
        with self.assertRaises(PermissionError):
            checkout_copy(self.copy, self.teacher, issued_by=self.member)

    def test_library_role_cannot_manage_superadmin_account(self):
        superadmin = User.objects.create_superuser(
            'root-account', 'root@example.com', 'safe-test-password'
        )
        self.client.force_login(self.admin_user)
        self.assertEqual(
            self.client.get(reverse('member-update', args=[superadmin.pk])).status_code,
            403,
        )

    def test_library_role_cannot_assign_privileged_role(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('member-create'), {
            'username': 'attempted-admin',
            'password': 'Stronger-test-password-21',
            'role': 'superadmin',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='attempted-admin').exists())

    def test_superadmin_can_create_library_account_with_synced_access(self):
        superadmin = User.objects.create_superuser(
            'root-account', 'root@example.com', 'safe-test-password'
        )
        self.client.force_login(superadmin)
        response = self.client.post(reverse('member-create'), {
            'username': 'desk-librarian',
            'email': 'desk-librarian@example.com',
            'password': 'Stronger-test-password-21',
            'role': 'library',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        librarian = User.objects.get(username='desk-librarian')
        self.assertTrue(librarian.is_staff)
        self.assertFalse(librarian.is_superuser)
        self.assertTrue(librarian.groups.filter(name=LIBRARY_GROUP_NAME).exists())
        self.assertTrue(librarian.profile.can_view)
        self.assertTrue(librarian.profile.can_add)
        self.assertTrue(librarian.profile.can_change)
        self.assertTrue(librarian.profile.can_delete)

    def test_superadmin_can_restrict_library_crud_permissions(self):
        superadmin = User.objects.create_superuser(
            'access-root', 'access-root@example.com', 'safe-test-password'
        )
        self.client.force_login(superadmin)
        response = self.client.post(reverse('member-create'), {
            'username': 'catalog-assistant',
            'email': 'catalog-assistant@example.com',
            'password': 'Strong-catalog-password-2026',
            'role': 'library',
            'is_active': 'on',
            'permissions_configured': 'on',
            'can_view': 'on',
            'can_add': 'on',
        })
        assistant = User.objects.get(username='catalog-assistant')
        self.assertRedirects(response, reverse('member-detail', args=[assistant.pk]))
        assistant.profile.refresh_from_db()
        self.assertTrue(assistant.profile.can_view)
        self.assertTrue(assistant.profile.can_add)
        self.assertFalse(assistant.profile.can_change)
        self.assertFalse(assistant.profile.can_delete)

        self.client.force_login(assistant)
        self.assertEqual(self.client.get(reverse('members')).status_code, 200)
        self.assertEqual(self.client.get(reverse('book-create')).status_code, 200)
        self.assertEqual(self.client.get(reverse('book-update', args=[self.book.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('book-delete', args=[self.book.pk])).status_code, 403)

    def test_superadmin_member_actions_are_prominent_and_self_delete_is_protected(self):
        superadmin = User.objects.create_superuser(
            'visible-actions-root', 'visible-actions@example.com', 'safe-test-password'
        )
        self.client.force_login(superadmin)
        response = self.client.get(reverse('members'))
        self.assertContains(response, 'Add user')
        self.assertContains(response, 'member-action-edit')
        self.assertContains(response, 'member-action-delete')
        self.assertContains(response, 'member-action-disabled')
        self.assertContains(response, 'protected from deletion')

    def test_locked_copy_query_only_locks_book_instance_table(self):
        """Nullable related rows must not be included in PostgreSQL FOR UPDATE."""
        from django.db import connection, transaction

        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL-specific row-lock SQL assertion')
        with transaction.atomic():
            queryset = (
                BookInstance.objects.select_for_update(of=('self',))
                .select_related('book', 'borrower')
                .filter(pk=self.copy.pk)
            )
            sql = str(queryset.query)
            self.assertIn('FOR UPDATE OF', sql)
            self.assertIn('catalog_bookinstance', sql.split('FOR UPDATE OF', 1)[1])

    def test_unavailable_copy_cannot_be_borrowed_again(self):
        self.copy.status = 'o'
        self.copy.borrower = self.admin_user
        self.copy.due_back = datetime.date.today() + datetime.timedelta(days=5)
        self.copy.save()
        self.client.force_login(self.member)
        self.client.post(reverse('borrow-copy', args=[self.copy.pk]))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.borrower, self.admin_user)

    def test_only_library_admin_can_return_copy(self):
        self.copy.status = 'o'
        self.copy.borrower = self.member
        self.copy.due_back = datetime.date.today()
        self.copy.save()
        url = reverse('return-copy', args=[self.copy.pk])

        self.client.force_login(self.member)
        self.client.post(url)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, 'o')

        self.client.force_login(self.admin_user)
        self.client.post(url)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, 'a')
        self.assertIsNone(self.copy.borrower)
        self.assertIsNone(self.copy.due_back)

    def test_overdue_return_creates_persistent_penalty(self):
        self.copy.status = 'o'
        self.copy.borrower = self.member
        self.copy.due_back = datetime.date.today() - datetime.timedelta(days=4)
        self.copy.save()
        self.client.force_login(self.admin_user)

        self.client.post(reverse('return-copy', args=[self.copy.pk]))

        penalty = Penalty.objects.get(borrower=self.member)
        self.assertEqual(penalty.amount, 40)
        self.assertEqual(penalty.days_overdue, 4)
        self.assertEqual(penalty.status, 'unpaid')
        self.assertEqual(penalty.loan.status, 'returned')

    def test_admin_can_resolve_penalty_but_member_cannot(self):
        penalty = Penalty.objects.create(
            borrower=self.member,
            book_instance=self.copy,
            book_title=self.book.title,
            amount=30,
            days_overdue=3,
        )
        url = reverse('resolve-penalty', args=[penalty.pk, 'paid'])

        self.client.force_login(self.member)
        self.client.post(url)
        penalty.refresh_from_db()
        self.assertEqual(penalty.status, 'unpaid')

        self.client.force_login(self.admin_user)
        self.client.post(url)
        penalty.refresh_from_db()
        self.assertEqual(penalty.status, 'paid')
        self.assertIsNotNone(penalty.resolved_at)

    def test_member_can_find_receipt_for_resolved_penalty(self):
        penalty = Penalty.objects.create(
            borrower=self.member,
            book_instance=self.copy,
            book_title=self.book.title,
            amount=30,
            days_overdue=3,
            status='paid',
        )
        self.client.force_login(self.member)
        response = self.client.get(reverse('penalties'))
        receipt_url = reverse('penalty-receipt', args=[penalty.pk])
        self.assertContains(response, receipt_url)
        self.assertEqual(self.client.get(receipt_url).status_code, 200)

    def test_member_active_loans_page_links_to_history(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('my-borrowed'))
        self.assertContains(response, reverse('loan-history'))

    def test_fine_amount_is_ten_rupees_per_overdue_day(self):
        self.copy.status = 'o'
        self.copy.due_back = datetime.date.today() - datetime.timedelta(days=3)
        self.assertEqual(self.copy.fine_amount, 30)

    def test_demo_seed_is_repeatable(self):
        call_command('seed_demo', verbosity=0)
        call_command('seed_demo', verbosity=0)
        demo_isbns = [item['isbn'] for item in DEMO_BOOKS]
        self.assertEqual(Book.objects.filter(isbn__in=demo_isbns).count(), len(DEMO_BOOKS))
        self.assertEqual(
            BookInstance.objects.filter(book__isbn__in=demo_isbns).count(),
            len(DEMO_BOOKS) * 2,
        )
        self.assertEqual(
            BookInstance.objects.filter(book__isbn__in=demo_isbns, status='o').count(),
            4,
        )
        self.assertEqual(Penalty.objects.filter(book_instance__book__isbn__in=demo_isbns).count(), 2)
        self.assertEqual(Loan.objects.filter(book_instance__book__isbn__in=demo_isbns).count(), 6)
        self.assertEqual(Reservation.objects.filter(book__isbn__in=demo_isbns).count(), 1)
        generated_covers = Book.objects.filter(
            isbn__in=demo_isbns,
            cover_url__startswith='/static/catalog/book-covers/',
        )
        self.assertEqual(generated_covers.count(), 4)
        for cover_url in generated_covers.values_list('cover_url', flat=True):
            asset = (
                settings.BASE_DIR / 'catalog' / 'static' / 'catalog'
                / cover_url.removeprefix('/static/catalog/')
            )
            self.assertTrue(asset.is_file(), cover_url)

    def test_member_can_reserve_unavailable_book_and_cancel(self):
        self.copy.status = 'o'
        self.copy.borrower = self.admin_user
        self.copy.due_back = datetime.date.today() + datetime.timedelta(days=5)
        self.copy.save()
        self.client.force_login(self.member)

        self.client.post(reverse('reserve-book', args=[self.book.pk]))
        reservation = Reservation.objects.get(book=self.book, borrower=self.member)
        self.assertEqual(reservation.status, 'active')

        self.client.post(reverse('cancel-reservation', args=[reservation.pk]))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, 'cancelled')

    def test_active_loan_can_be_renewed_once(self):
        self.client.force_login(self.admin_user)
        self.client.post(reverse('copy-issue', args=[self.copy.pk]), {'borrower': self.member.pk})
        loan = Loan.objects.get(book_instance=self.copy, status='active')
        original_due_date = loan.due_date

        self.client.post(reverse('renew-loan', args=[loan.pk]))
        loan.refresh_from_db()
        self.copy.refresh_from_db()
        self.assertEqual(loan.renewal_count, 1)
        self.assertEqual(loan.due_date, original_due_date + datetime.timedelta(days=15))
        self.assertEqual(self.copy.due_back, loan.due_date)

        self.client.post(reverse('renew-loan', args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.renewal_count, 1)

    def test_member_cannot_renew_own_loan(self):
        checkout_copy(self.copy, self.member, issued_by=self.admin_user)
        loan = Loan.objects.get(book_instance=self.copy, status='active')
        self.client.force_login(self.member)
        self.client.post(reverse('renew-loan', args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.renewal_count, 0)

    def test_history_and_reservation_pages_require_login(self):
        for url in (reverse('loan-history'), reverse('reservations')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
                self.client.force_login(self.member)
                self.assertEqual(self.client.get(url).status_code, 200)
                self.client.logout()

    def test_maintenance_command_reports_totals(self):
        output = StringIO()
        call_command('library_maintenance', stdout=output)
        report = output.getvalue()
        self.assertIn('Shelfwise daily maintenance', report)
        self.assertIn('Overdue active loans:', report)
        self.assertIn('Outstanding recorded amount:', report)

    def test_notification_generation_is_idempotent(self):
        due_date = datetime.date.today() + datetime.timedelta(days=3)
        self.copy.status = 'o'
        self.copy.borrower = self.member
        self.copy.due_back = due_date
        self.copy.save()
        Loan.objects.create(
            borrower=self.member,
            book_instance=self.copy,
            book_title=self.book.title,
            due_date=due_date,
        )

        self.assertEqual(generate_library_notifications(), 1)
        self.assertEqual(generate_library_notifications(), 0)
        notification = Notification.objects.get(user=self.member)
        self.assertEqual(notification.notification_type, 'due_soon')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_pending_notification_email_is_delivered(self):
        self.member.email = 'member@example.com'
        self.member.save(update_fields=['email'])
        notification = Notification.objects.create(
            user=self.member,
            notification_type='due_today',
            title='Book due today',
            message='Return your book.',
            link='/history/',
            dedupe_key='test-email-delivery',
        )

        result = deliver_pending_notifications()
        notification.refresh_from_db()
        self.assertEqual(result['sent'], 1)
        self.assertEqual(notification.email_status, 'sent')
        self.assertEqual(len(mail.outbox), 1)

    def test_complete_automation_creates_backup_and_monthly_report(self):
        output = StringIO()
        today = datetime.date.today()
        previous_month = (today.replace(day=1) - datetime.timedelta(days=1)).strftime('%Y-%m')
        root = Path(settings.BASE_DIR) / '.runtime' / 'automation-test'
        self.assertTrue(root.resolve().is_relative_to(Path(settings.BASE_DIR).resolve()))
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            call_command(
                'run_library_automation',
                skip_email=True,
                force_monthly_report=True,
                backup_root=str(root / 'backups'),
                report_root=str(root / 'reports'),
                stdout=output,
            )
            dated_backup = root / 'backups' / today.isoformat()
            self.assertTrue((dated_backup / 'books.csv').exists())
            self.assertTrue((dated_backup / 'copies.csv').exists())
            self.assertTrue((dated_backup / 'members.csv').exists())
            self.assertTrue((root / 'reports' / f'shelfwise-{previous_month}.pdf').exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertIn('Shelfwise automation completed successfully.', output.getvalue())

    def test_return_notifies_first_waiting_member(self):
        self.copy.status = 'o'
        self.copy.borrower = self.admin_user
        self.copy.due_back = datetime.date.today()
        self.copy.save()
        Loan.objects.create(
            borrower=self.admin_user,
            book_instance=self.copy,
            book_title=self.book.title,
            due_date=self.copy.due_back,
        )
        Reservation.objects.create(book=self.book, borrower=self.member)
        self.client.force_login(self.admin_user)

        self.client.post(reverse('return-copy', args=[self.copy.pk]))

        notification = Notification.objects.get(user=self.member)
        self.assertEqual(notification.notification_type, 'reservation')

    def test_member_can_mark_notifications_read(self):
        notification = Notification.objects.create(
            user=self.member,
            notification_type='due_today',
            title='Book due today',
            message='Return your book.',
            link='/history/',
            dedupe_key='test-read-action',
        )
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('notifications')).status_code, 200)
        self.client.post(reverse('mark-notification-read', args=[notification.pk]))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_admin_can_generate_copy_and_member_qr_codes(self):
        self.client.force_login(self.admin_user)
        copy_response = self.client.get(reverse('copy-qr', args=[self.copy.pk]))
        member_response = self.client.get(reverse('member-qr', args=[self.member.pk]))
        self.assertEqual(copy_response.status_code, 200)
        self.assertEqual(copy_response['Content-Type'], 'image/png')
        self.assertTrue(copy_response.content.startswith(b'\x89PNG'))
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response['Content-Type'], 'image/png')

    def test_qr_scanner_issues_and_returns_copy_with_audit(self):
        self.client.force_login(self.admin_user)
        issue_response = self.client.post(reverse('process-scan'), {
            'action': 'issue',
            'copy_code': f'SHELFWISE:COPY:{self.copy.pk}',
            'member_code': f'SHELFWISE:MEMBER:{self.member.pk}',
        })
        self.assertRedirects(issue_response, reverse('scanner'))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, 'o')
        loan = Loan.objects.get(book_instance=self.copy, status='active')
        self.assertEqual(loan.borrower, self.member)
        self.assertEqual(loan.issued_by, self.admin_user)

        return_response = self.client.post(reverse('process-scan'), {
            'action': 'return',
            'copy_code': str(self.copy.pk),
        })
        self.assertRedirects(return_response, reverse('scanner'))
        self.copy.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.copy.status, 'a')
        self.assertEqual(loan.status, 'returned')
        self.assertEqual(ScanAudit.objects.filter(success=True).count(), 2)

    def test_non_admin_cannot_use_scanner(self):
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse('scanner')), reverse('index'))
        self.assertEqual(self.client.get(reverse('copy-qr', args=[self.copy.pk])).status_code, 403)

    def test_invalid_scan_is_audited(self):
        self.client.force_login(self.admin_user)
        self.client.post(reverse('process-scan'), {
            'action': 'issue',
            'copy_code': 'not-a-valid-code',
            'member_code': self.member.username,
        })
        audit = ScanAudit.objects.get()
        self.assertFalse(audit.success)
        self.assertEqual(audit.action, 'issue')

    def test_reports_are_admin_only_and_render_analytics(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('reports')).status_code, 403)
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reports & analytics')
        self.assertContains(response, 'Most borrowed books')

    def test_report_exports_generate_valid_files(self):
        Loan.objects.create(
            borrower=self.member,
            book_instance=self.copy,
            book_title=self.book.title,
            due_date=datetime.date.today() + datetime.timedelta(days=15),
        )
        self.client.force_login(self.admin_user)
        csv_response = self.client.get(reverse('report-csv'))
        xlsx_response = self.client.get(reverse('report-xlsx'))
        pdf_response = self.client.get(reverse('report-pdf'))
        self.assertEqual(csv_response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(b'Kindred', csv_response.content)
        self.assertTrue(xlsx_response.content.startswith(b'PK'))
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))

    def test_monthly_report_command_writes_pdf(self):
        output = Path.cwd() / '.test-monthly-report.pdf'
        try:
            call_command(
                'generate_monthly_report',
                month=datetime.date.today().strftime('%Y-%m'),
                output=str(output),
            )
            self.assertTrue(output.read_bytes().startswith(b'%PDF'))
        finally:
            output.unlink(missing_ok=True)

    @patch('catalog.views.lookup_isbn')
    def test_library_staff_can_lookup_and_create_book_by_isbn(self, mocked_lookup):
        mocked_lookup.return_value = {
            'isbn': '9780061120084',
            'title': 'To Kill a Mockingbird',
            'author': 'Harper Lee',
            'summary': 'First published: 1960.',
            'genres': 'Fiction, Classics',
            'cover_url': 'https://covers.openlibrary.org/b/id/123-L.jpg',
        }
        self.client.force_login(self.admin_user)
        url = reverse('book-import-isbn')

        lookup_response = self.client.post(url, {'isbn': '978-0-06-112008-4', 'action': 'lookup'})
        self.assertEqual(lookup_response.status_code, 200)
        self.assertContains(lookup_response, 'To Kill a Mockingbird')

        create_response = self.client.post(url, {
            **mocked_lookup.return_value,
            'action': 'create',
        })
        book = Book.objects.get(isbn='9780061120084')
        self.assertRedirects(create_response, reverse('book-detail', args=[book.pk]))
        self.assertEqual(str(book.author), 'Lee, Harper')
        self.assertEqual(set(book.genre.values_list('name', flat=True)), {'Fiction', 'Classics'})

    def test_isbn_import_rejects_duplicate_book(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('book-import-isbn'), {
            'isbn': self.book.isbn,
            'title': 'Duplicate',
            'author': 'Another Author',
            'summary': 'Duplicate record',
            'genres': 'Fiction',
            'cover_url': '',
            'action': 'create',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A book with this ISBN already exists.')
        self.assertEqual(Book.objects.filter(isbn=self.book.isbn).count(), 1)

    def test_library_admin_can_create_edit_and_delete_book(self):
        self.client.force_login(self.admin_user)
        create_response = self.client.post(reverse('book-create'), {
            'title': 'Parable of the Sower',
            'author': self.author.pk,
            'summary': 'A speculative fiction novel.',
            'isbn': '9780446675505',
            'genre': [self.genre.pk],
            'cover_url': '',
        })
        created = Book.objects.get(isbn='9780446675505')
        self.assertRedirects(create_response, created.get_absolute_url())

        update_response = self.client.post(reverse('book-update', args=[created.pk]), {
            'title': 'Parable of the Sower — Updated',
            'author': self.author.pk,
            'summary': created.summary,
            'isbn': created.isbn,
            'genre': [self.genre.pk],
            'cover_url': '',
        })
        created.refresh_from_db()
        self.assertRedirects(update_response, created.get_absolute_url())
        self.assertIn('Updated', created.title)

        delete_response = self.client.post(reverse('book-delete', args=[created.pk]))
        self.assertRedirects(delete_response, reverse('books'))
        self.assertFalse(Book.objects.filter(pk=created.pk).exists())

    def test_member_cannot_access_book_crud(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('book-create'))
        self.assertContains(response, 'Access restricted', status_code=403)
        self.assertEqual(self.client.get(reverse('book-import-isbn')).status_code, 403)
        self.assertEqual(self.client.get(reverse('book-update', args=[self.book.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('book-delete', args=[self.book.pk])).status_code, 403)

    def test_admin_can_create_update_and_view_member(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('member-create'), {
            'username': 'newreader',
            'first_name': 'New',
            'last_name': 'Reader',
            'email': 'reader@example.com',
            'is_active': 'on',
            'role': 'student',
            'password': 'Strong-reader-pass-2026',
        })
        created = User.objects.get(username='newreader')
        self.assertRedirects(response, reverse('member-detail', args=[created.pk]))
        self.assertTrue(created.check_password('Strong-reader-pass-2026'))
        self.assertEqual(created.profile.role, 'student')

        response = self.client.post(reverse('member-update', args=[created.pk]), {
            'username': 'newreader',
            'first_name': 'Updated',
            'last_name': 'Reader',
            'email': 'updated@example.com',
            'is_active': 'on',
            'role': 'teacher',
            'password': '',
        })
        created.refresh_from_db()
        created.profile.refresh_from_db()
        self.assertRedirects(response, reverse('member-detail', args=[created.pk]))
        self.assertEqual(created.first_name, 'Updated')
        self.assertEqual(created.profile.role, 'teacher')
        self.assertContains(self.client.get(reverse('members')), 'updated@example.com')

    def test_member_management_is_admin_only_and_protects_active_borrowers(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('members')).status_code, 403)
        self.client.force_login(self.admin_user)
        checkout_copy(self.copy, self.member, issued_by=self.admin_user)
        response = self.client.post(reverse('member-delete', args=[self.member.pk]))
        self.assertRedirects(response, reverse('member-detail', args=[self.member.pk]))
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_admin_can_manage_physical_copy_and_manual_circulation(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('copy-create'), {
            'book': self.book.pk,
            'accession_number': 'ACC-TEST-001',
            'imprint': 'Test edition',
            'shelf_location': 'A-01-02',
            'status': 'a',
            'condition_notes': 'Good condition',
        })
        copy = BookInstance.objects.get(accession_number='ACC-TEST-001')
        self.assertRedirects(response, reverse('copy-detail', args=[copy.pk]))

        issue = self.client.post(reverse('copy-issue', args=[copy.pk]), {'borrower': self.member.pk})
        self.assertRedirects(issue, reverse('copy-detail', args=[copy.pk]))
        copy.refresh_from_db()
        self.assertEqual(copy.status, 'o')
        self.assertTrue(ScanAudit.objects.filter(book_instance=copy, action='issue', success=True).exists())

        checkin = self.client.post(reverse('copy-checkin', args=[copy.pk]))
        self.assertRedirects(checkin, reverse('copy-detail', args=[copy.pk]))
        copy.refresh_from_db()
        self.assertEqual(copy.status, 'a')
        self.assertTrue(ScanAudit.objects.filter(book_instance=copy, action='return', success=True).exists())

        delete = self.client.post(reverse('copy-delete', args=[copy.pk]))
        self.assertRedirects(delete, reverse('copies'))
        self.assertFalse(BookInstance.objects.filter(pk=copy.pk).exists())

    def test_member_cannot_access_inventory_management(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('copies')).status_code, 403)
        self.assertEqual(self.client.get(reverse('copy-create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('copy-detail', args=[self.copy.pk])).status_code, 403)
