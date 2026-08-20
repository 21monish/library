import csv
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from catalog.models import Book, BookInstance


class Command(BaseCommand):
    help = 'Export books, copies, and members to portable CSV files.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='backups/latest', help='Destination directory')

    def handle(self, *args, **options):
        destination = Path(options['output']).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        self._write(destination / 'books.csv', ['isbn', 'title', 'author_first_name', 'author_last_name', 'genres', 'summary', 'cover_url'], (
            [book.isbn, book.title, book.author.first_name if book.author else '', book.author.last_name if book.author else '', '|'.join(book.genre.values_list('name', flat=True)), book.summary, book.cover_url]
            for book in Book.objects.select_related('author').prefetch_related('genre').order_by('title')
        ))
        self._write(destination / 'copies.csv', ['id', 'accession_number', 'isbn', 'imprint', 'shelf_location', 'status', 'condition_notes'], (
            [copy.pk, copy.accession_number or '', copy.book.isbn, copy.imprint, copy.shelf_location, copy.status, copy.condition_notes]
            for copy in BookInstance.objects.select_related('book').order_by('accession_number')
        ))
        self._write(destination / 'members.csv', ['username', 'first_name', 'last_name', 'email', 'role', 'is_active'], (
            [user.username, user.first_name, user.last_name, user.email, getattr(user.profile, 'role', 'student'), user.is_active]
            for user in User.objects.select_related('profile').order_by('username')
        ))
        self.stdout.write(self.style.SUCCESS(f'Library data exported to {destination}'))

    @staticmethod
    def _write(path, headers, rows):
        with path.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
