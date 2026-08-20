import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Author, Book, BookInstance, Genre, Loan, Penalty, Reservation


DEMO_BOOKS = [
    {
        'title': 'The Midnight Library',
        'isbn': '9780525559498',
        'summary': 'A moving exploration of regret, hope, and the many paths a life might take.',
        'author': ('Matt', 'Haig'),
        'genres': ('Contemporary Fiction', 'Fantasy'),
        'imprints': ('Viking First Edition', 'Canongate Reader Edition'),
    },
    {
        'title': 'Atomic Habits',
        'isbn': '9780735211292',
        'summary': 'A practical guide to building good habits and breaking unhelpful ones through small changes.',
        'author': ('James', 'Clear'),
        'genres': ('Self Development', 'Non-Fiction'),
        'imprints': ('Avery Hardcover', 'Penguin International'),
    },
    {
        'title': 'The Alchemist',
        'isbn': '9780062315007',
        'summary': 'A young shepherd follows a recurring dream and discovers the meaning of a personal legend.',
        'author': ('Paulo', 'Coelho'),
        'genres': ('Fiction', 'Adventure'),
        'imprints': ('HarperOne Anniversary Edition', 'HarperCollins Paperback'),
    },
    {
        'title': 'Sapiens',
        'isbn': '9780062316097',
        'summary': 'A broad history of humankind, from early species to modern technological societies.',
        'author': ('Yuval Noah', 'Harari'),
        'genres': ('History', 'Non-Fiction'),
        'imprints': ('Harper First Edition', 'Vintage International'),
        'cover_url': '/static/catalog/book-covers/sapiens-ai.webp',
    },
    {
        'title': 'To Kill a Mockingbird',
        'isbn': '9780061120084',
        'summary': 'A coming-of-age story about justice, empathy, and prejudice in the American South.',
        'author': ('Harper', 'Lee'),
        'genres': ('Classic', 'Fiction'),
        'imprints': ('Harper Perennial Modern Classics', 'Arrow Classroom Edition'),
    },
    {
        'title': 'The Psychology of Money',
        'isbn': '9780857197689',
        'summary': 'Short lessons about wealth, greed, happiness, and the behavior behind financial decisions.',
        'author': ('Morgan', 'Housel'),
        'genres': ('Finance', 'Non-Fiction'),
        'imprints': ('Harriman House Hardcover', 'Jaico Indian Edition'),
    },
    {
        'title': '1984',
        'isbn': '9780451524935',
        'summary': 'A dystopian classic about surveillance, truth, power, and individual freedom.',
        'author': ('George', 'Orwell'),
        'genres': ('Classic', 'Dystopian'),
        'imprints': ('Signet Classics', 'Penguin Modern Classics'),
        'cover_url': '/static/catalog/book-covers/1984-ai.webp',
    },
    {
        'title': 'The Hobbit',
        'isbn': '9780261102217',
        'summary': 'Bilbo Baggins leaves his quiet home for an unexpected journey across Middle-earth.',
        'author': ('J. R. R.', 'Tolkien'),
        'genres': ('Fantasy', 'Adventure'),
        'imprints': ('Mariner Books', 'HarperCollins Illustrated Edition'),
        'cover_url': '/static/catalog/book-covers/the-hobbit-ai.webp',
    },
    {
        'title': 'Foundation',
        'isbn': '9780553293357',
        'summary': 'A mathematician develops a science of history to preserve civilization through a coming dark age.',
        'author': ('Isaac', 'Asimov'),
        'genres': ('Science Fiction', 'Classic'),
        'imprints': ('Bantam Spectra', 'Del Rey Anniversary Edition'),
        'cover_url': '/static/catalog/book-covers/foundation-ai.webp',
    },
    {
        'title': 'Dune', 'isbn': '9780441172719',
        'summary': 'Politics, ecology, and destiny collide on the desert world of Arrakis.',
        'author': ('Frank', 'Herbert'), 'genres': ('Science Fiction', 'Adventure'),
        'imprints': ('Ace Trade Edition', 'Hodder Anniversary Edition'),
    },
    {
        'title': 'Pride and Prejudice', 'isbn': '9780141439518',
        'summary': 'Elizabeth Bennet navigates family expectations, first impressions, and an unexpected love.',
        'author': ('Jane', 'Austen'), 'genres': ('Classic', 'Romance'),
        'imprints': ('Penguin Classics', 'Oxford World Classics'),
    },
    {
        'title': 'The Great Gatsby', 'isbn': '9780743273565',
        'summary': 'A portrait of ambition, reinvention, and disillusionment in the Jazz Age.',
        'author': ('F. Scott', 'Fitzgerald'), 'genres': ('Classic', 'Fiction'),
        'imprints': ('Scribner Paperback', 'Penguin Modern Classics'),
    },
    {
        'title': 'Brave New World', 'isbn': '9780060850524',
        'summary': 'A technologically ordered society confronts freedom, identity, and human connection.',
        'author': ('Aldous', 'Huxley'), 'genres': ('Classic', 'Dystopian'),
        'imprints': ('Harper Perennial', 'Vintage Classics'),
    },
    {
        'title': 'The Book Thief', 'isbn': '9780375842207',
        'summary': 'A young reader finds courage and connection through stolen books during wartime Germany.',
        'author': ('Markus', 'Zusak'), 'genres': ('Historical Fiction', 'Young Adult'),
        'imprints': ('Knopf Young Readers', 'Black Swan Edition'),
    },
    {
        'title': 'Educated', 'isbn': '9780399590504',
        'summary': 'A memoir about learning, family, and the difficult journey toward an independent life.',
        'author': ('Tara', 'Westover'), 'genres': ('Memoir', 'Non-Fiction'),
        'imprints': ('Random House Hardcover', 'Windmill Paperback'),
    },
    {
        'title': 'Thinking, Fast and Slow', 'isbn': '9780374533557',
        'summary': 'An exploration of the intuitive and deliberate systems that shape human decisions.',
        'author': ('Daniel', 'Kahneman'), 'genres': ('Psychology', 'Non-Fiction'),
        'imprints': ('Farrar Straus Giroux', 'Penguin Psychology Edition'),
    },
    {
        'title': 'Deep Work', 'isbn': '9781455586691',
        'summary': 'Principles for sustained concentration and meaningful work in a distracted world.',
        'author': ('Cal', 'Newport'), 'genres': ('Productivity', 'Self Development'),
        'imprints': ('Grand Central Publishing', 'Piatkus Paperback'),
    },
    {
        'title': 'Clean Code', 'isbn': '9780132350884',
        'summary': 'Practical principles for writing software that remains readable and maintainable.',
        'author': ('Robert C.', 'Martin'), 'genres': ('Technology', 'Programming'),
        'imprints': ('Prentice Hall', 'Pearson India Edition'),
    },
    {
        'title': 'The Pragmatic Programmer', 'isbn': '9780135957059',
        'summary': 'A field guide to thoughtful software development and sustainable engineering habits.',
        'author': ('David', 'Thomas'), 'genres': ('Technology', 'Programming'),
        'imprints': ('Addison-Wesley Anniversary', 'Pearson International'),
    },
    {
        'title': 'Introduction to Algorithms', 'isbn': '9780262046305',
        'summary': 'A comprehensive reference for algorithms, data structures, and computational analysis.',
        'author': ('Thomas H.', 'Cormen'), 'genres': ('Computer Science', 'Education'),
        'imprints': ('MIT Press Fourth Edition', 'PHI India Edition'),
    },
    {
        'title': 'A Brief History of Time', 'isbn': '9780553380163',
        'summary': 'An accessible journey through cosmology, black holes, time, and the universe.',
        'author': ('Stephen', 'Hawking'), 'genres': ('Science', 'Non-Fiction'),
        'imprints': ('Bantam Updated Edition', 'Transworld Illustrated Edition'),
    },
    {
        'title': 'The Gene', 'isbn': '9781476733524',
        'summary': 'A history of genetics and the discoveries that reshaped our understanding of inheritance.',
        'author': ('Siddhartha', 'Mukherjee'), 'genres': ('Science', 'History'),
        'imprints': ('Scribner Hardcover', 'Vintage Paperback'),
    },
    {
        'title': 'The Silent Patient', 'isbn': '9781250301697',
        'summary': 'A psychotherapist becomes obsessed with discovering why a famous painter stopped speaking.',
        'author': ('Alex', 'Michaelides'), 'genres': ('Thriller', 'Mystery'),
        'imprints': ('Celadon Books', 'Orion Paperback'),
    },
    {
        'title': 'The Kite Runner', 'isbn': '9781594631931',
        'summary': 'A story of friendship, betrayal, and redemption spanning Afghanistan and America.',
        'author': ('Khaled', 'Hosseini'), 'genres': ('Fiction', 'Historical Fiction'),
        'imprints': ('Riverhead Books', 'Bloomsbury Reader Edition'),
    },
    {
        'title': 'Ikigai', 'isbn': '9780143130727',
        'summary': 'Everyday observations about purpose, longevity, community, and a meaningful life.',
        'author': ('Héctor', 'García'), 'genres': ('Self Development', 'Non-Fiction'),
        'imprints': ('Penguin Life', 'Hutchinson International'),
    },
    {
        'title': 'Wings of Fire', 'isbn': '9788173711466',
        'summary': 'A. P. J. Abdul Kalam recounts his childhood, scientific work, and service to India.',
        'author': ('A. P. J.', 'Abdul Kalam'), 'genres': ('Biography', 'Indian Writing'),
        'imprints': ('Universities Press', 'Orient BlackSwan Edition'),
    },
    {
        'title': 'The God of Small Things', 'isbn': '9780812979657',
        'summary': 'A lyrical family story shaped by memory, social boundaries, and irreversible choices.',
        'author': ('Arundhati', 'Roy'), 'genres': ('Fiction', 'Indian Writing'),
        'imprints': ('Random House Trade', 'IndiaInk Edition'),
    },
    {
        'title': 'The Palace of Illusions', 'isbn': '9780385515993',
        'summary': 'The Mahabharata is reimagined through the ambitions and perspective of Panchaali.',
        'author': ('Chitra Banerjee', 'Divakaruni'), 'genres': ('Mythology', 'Indian Writing'),
        'imprints': ('Doubleday First Edition', 'Picador India Edition'),
    },
    {
        'title': 'The White Tiger', 'isbn': '9781416562603',
        'summary': 'A darkly comic account of ambition, class, and transformation in contemporary India.',
        'author': ('Aravind', 'Adiga'), 'genres': ('Fiction', 'Indian Writing'),
        'imprints': ('Free Press Hardcover', 'Atlantic Paperback'),
    },
    {
        'title': 'Train to Pakistan', 'isbn': '9780802132215',
        'summary': 'A village on the border is transformed by the violence and upheaval of Partition.',
        'author': ('Khushwant', 'Singh'), 'genres': ('Historical Fiction', 'Indian Writing'),
        'imprints': ('Grove Press', 'Penguin India Modern Classics'),
    },
    {
        'title': 'The Discovery of India', 'isbn': '9780143031031',
        'summary': 'A sweeping reflection on Indian history, culture, philosophy, and national identity.',
        'author': ('Jawaharlal', 'Nehru'), 'genres': ('History', 'Indian Writing'),
        'imprints': ('Penguin India', 'Oxford India Paperbacks'),
    },
    {
        'title': 'Harry Potter and the Sorcerer’s Stone', 'isbn': '9780439708180',
        'summary': 'An orphan discovers a hidden magical world and begins his education at Hogwarts.',
        'author': ('J. K.', 'Rowling'), 'genres': ('Fantasy', 'Young Adult'),
        'imprints': ('Scholastic First Edition', 'Bloomsbury Children Edition'),
    },
]


class Command(BaseCommand):
    help = 'Create an idempotent set of demonstration library records.'

    @transaction.atomic
    def handle(self, *args, **options):
        today = datetime.date.today()
        student, _ = User.objects.get_or_create(username='demo.student')
        student.set_password('Demo@12345')
        student.first_name = 'Aarav'
        student.last_name = 'Sharma'
        student.email = 'demo.student@example.com'
        student.save()
        student.profile.role = 'student'
        student.profile.save(update_fields=['role'])

        teacher, _ = User.objects.get_or_create(username='demo.teacher')
        teacher.set_password('Demo@12345')
        teacher.first_name = 'Meera'
        teacher.last_name = 'Iyer'
        teacher.email = 'demo.teacher@example.com'
        teacher.save()
        teacher.profile.role = 'teacher'
        teacher.profile.save(update_fields=['role'])

        instances = []
        for item in DEMO_BOOKS:
            author, _ = Author.objects.get_or_create(
                first_name=item['author'][0],
                last_name=item['author'][1],
            )
            book, _ = Book.objects.update_or_create(
                isbn=item['isbn'],
                defaults={
                    'title': item['title'],
                    'summary': item['summary'],
                    'author': author,
                    'cover_url': item.get('cover_url', ''),
                },
            )
            book.genre.set(
                Genre.objects.get_or_create(name=name)[0]
                for name in item['genres']
            )
            for imprint in item['imprints']:
                instance, _ = BookInstance.objects.get_or_create(
                    book=book,
                    imprint=imprint,
                    defaults={'status': 'a'},
                )
                instance.status = 'a'
                instance.borrower = None
                instance.due_back = None
                instance.save(update_fields=['status', 'borrower', 'due_back'])
                instances.append(instance)

        loan_states = (
            (0, student, today + datetime.timedelta(days=9)),
            (3, teacher, today + datetime.timedelta(days=4)),
            (6, student, today - datetime.timedelta(days=3)),
            (11, teacher, today - datetime.timedelta(days=8)),
        )
        for index, borrower, due_back in loan_states:
            instance = instances[index]
            instance.status = 'o'
            instance.borrower = borrower
            instance.due_back = due_back
            instance.save(update_fields=['status', 'borrower', 'due_back'])
            Loan.objects.update_or_create(
                book_instance=instance,
                status='active',
                defaults={
                    'borrower': borrower,
                    'book_title': instance.book.title,
                    'due_date': due_back,
                },
            )

        active_instances = [instances[index] for index, _, _ in loan_states]
        Loan.objects.filter(
            book_instance__in=instances,
            status='active',
        ).exclude(book_instance__in=active_instances).update(
            status='returned',
            returned_at=timezone.now(),
        )

        instances[7].status = 'r'
        instances[7].borrower = None
        instances[7].due_back = None
        instances[7].save(update_fields=['status', 'borrower', 'due_back'])

        instances[14].status = 'm'
        instances[14].borrower = None
        instances[14].due_back = None
        instances[14].save(update_fields=['status', 'borrower', 'due_back'])

        student_penalty, _ = Penalty.objects.get_or_create(
            borrower=student,
            book_instance=instances[2],
            book_title=instances[2].book.title,
            amount=50,
            days_overdue=5,
            defaults={
                'status': 'unpaid',
                'notes': 'Demo overdue-return penalty.',
            },
        )
        if not student_penalty.loan_id:
            student_loan = Loan.objects.create(
                borrower=student,
                book_instance=instances[2],
                book_title=instances[2].book.title,
                due_date=today - datetime.timedelta(days=5),
                returned_at=student_penalty.assessed_at,
                status='returned',
            )
            student_penalty.loan = student_loan
            student_penalty.save(update_fields=['loan'])
        paid_penalty, _ = Penalty.objects.get_or_create(
            borrower=teacher,
            book_instance=instances[5],
            book_title=instances[5].book.title,
            amount=20,
            days_overdue=2,
            defaults={
                'status': 'paid',
                'notes': 'Demo resolved penalty.',
            },
        )
        if paid_penalty.status == 'paid' and not paid_penalty.resolved_at:
            paid_penalty.resolve('paid')
        if not paid_penalty.loan_id:
            teacher_loan = Loan.objects.create(
                borrower=teacher,
                book_instance=instances[5],
                book_title=instances[5].book.title,
                due_date=today - datetime.timedelta(days=2),
                returned_at=paid_penalty.assessed_at,
                status='returned',
            )
            paid_penalty.loan = teacher_loan
            paid_penalty.save(update_fields=['loan'])

        Reservation.objects.get_or_create(
            book=instances[6].book,
            borrower=teacher,
            status='active',
        )

        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {len(DEMO_BOOKS)} books, {len(DEMO_BOOKS) * 2} copies, '
            '2 members, loan history, reservations, and penalties.'
        ))
