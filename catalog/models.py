import uuid
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import date

class Genre(models.Model):
    """Model representing a book genre."""
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Enter a book genre (e.g. Science Fiction, Non-Fiction etc.)"
    )

    def __str__(self):
        """String for representing the Model object."""
        return self.name


class Author(models.Model):
    """Model representing an author."""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_death = models.DateField('died', null=True, blank=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def get_absolute_url(self):
        """Returns the URL to access a particular author instance."""
        return reverse('author-detail', args=[str(self.id)])

    def __str__(self):
        """String for representing the Model object."""
        return f'{self.last_name}, {self.first_name}'


class Book(models.Model):
    """Model representing a book (but not a specific copy of a book)."""
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True)
    summary = models.TextField(max_length=1000, help_text="Enter a brief description of the book")
    isbn = models.CharField(
        'ISBN',
        max_length=13,
        unique=True,
        help_text='13 Character <a href="https://www.isbn-international.org/content/what-isbn">ISBN number</a>'
    )
    genre = models.ManyToManyField(Genre, help_text="Select a genre for this book")
    cover_url = models.CharField(
        max_length=700,
        blank=True,
        help_text='Local asset path or public image URL.',
    )

    def __str__(self):
        """String for representing the Model object."""
        return self.title

    def get_absolute_url(self):
        """Returns the URL to access a detail record for this book."""
        return reverse('book-detail', args=[str(self.id)])


class BookInstance(models.Model):
    """Model representing a specific copy of a book (i.e. that can be borrowed from the library)."""
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        help_text="Unique ID for this particular book across whole library"
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, null=True)
    imprint = models.CharField(max_length=200)
    accession_number = models.CharField(max_length=40, unique=True, null=True, blank=True)
    shelf_location = models.CharField(max_length=80, blank=True)
    condition_notes = models.TextField(blank=True)
    due_back = models.DateField(null=True, blank=True)
    borrower = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    LOAN_STATUS = (
        ('m', 'Maintenance'),
        ('o', 'On loan'),
        ('a', 'Available'),
        ('r', 'Reserved'),
        ('l', 'Lost'),
    )

    status = models.CharField(
        max_length=1,
        choices=LOAN_STATUS,
        blank=True,
        default='m',
        help_text='Book availability'
    )

    class Meta:
        ordering = ['due_back']
        permissions = (("can_mark_returned", "Set book as returned"),)

    def __str__(self):
        """String for representing the Model object."""
        return f'{self.id} ({self.book.title})'

    @property
    def is_overdue(self):
        """Determines if the book instance is overdue based on due date and today's date."""
        return bool(self.due_back and self.due_back < date.today())

    @property
    def fine_amount(self):
        """Calculates the fine if the book copy is overdue (10 RS per day)."""
        if self.status == 'o' and self.due_back and self.due_back < date.today():
            overdue_days = (date.today() - self.due_back).days
            return overdue_days * settings.PENALTY_PER_DAY
        return 0


class Profile(models.Model):
    """Model representing extended user roles."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('library', 'Library In-charge'),
        ('superadmin', 'Superadmin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    can_view = models.BooleanField(default=True, help_text='May open staff record screens within the assigned role.')
    can_add = models.BooleanField(default=False, help_text='May create records within the assigned role.')
    can_change = models.BooleanField(default=False, help_text='May edit records and run update workflows within the assigned role.')
    can_delete = models.BooleanField(default=False, help_text='May permanently delete records within the assigned role.')
    photo_url = models.CharField(
        max_length=700,
        blank=True,
        help_text='Local asset path or public image URL.',
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class Loan(models.Model):
    """Permanent circulation record for a borrowed physical copy."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('lost', 'Lost'),
    )

    borrower = models.ForeignKey(User, on_delete=models.PROTECT, related_name='loans')
    book_instance = models.ForeignKey(
        BookInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loans',
    )
    book_title = models.CharField(max_length=200)
    issued_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    renewal_count = models.PositiveSmallIntegerField(default=0)
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loans_issued',
    )
    returned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loans_returned',
    )

    class Meta:
        ordering = ('-issued_at',)
        constraints = (
            models.UniqueConstraint(
                fields=('book_instance',),
                condition=Q(status='active'),
                name='one_active_loan_per_copy',
            ),
        )

    def __str__(self):
        return f'{self.book_title} · {self.borrower.username} · {self.get_status_display()}'

    @property
    def is_overdue(self):
        return self.status == 'active' and self.due_date < date.today()


class Penalty(models.Model):
    """Persistent charge assessed when an overdue copy is returned."""

    STATUS_CHOICES = (
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('waived', 'Waived'),
    )

    borrower = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='penalties',
    )
    book_instance = models.ForeignKey(
        BookInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penalties',
    )
    book_title = models.CharField(max_length=200)
    loan = models.OneToOneField(
        Loan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penalty',
    )
    amount = models.PositiveIntegerField(help_text='Penalty amount in Indian rupees')
    days_overdue = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid')
    assessed_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('-assessed_at',)

    def __str__(self):
        return f'{self.borrower.username} · {self.book_title} · ₹{self.amount}'

    def resolve(self, status):
        if status not in {'paid', 'waived'}:
            raise ValueError('A penalty can only be marked paid or waived.')
        self.status = status
        self.resolved_at = timezone.now()
        self.save(update_fields=['status', 'resolved_at'])


class PenaltyTransaction(models.Model):
    """Immutable payment or waiver entry used to generate receipts."""

    METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('bank', 'Bank transfer'),
        ('waiver', 'Waiver'),
    )
    penalty = models.ForeignKey(Penalty, on_delete=models.PROTECT, related_name='transactions')
    resolution = models.CharField(max_length=10, choices=(('paid', 'Paid'), ('waived', 'Waived')))
    amount = models.PositiveIntegerField(default=0)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Receipt {self.pk} - {self.get_resolution_display()}'


class Reservation(models.Model):
    """A member's place in the queue for a book title."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    )

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reservations')
    borrower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('created_at',)
        constraints = (
            models.UniqueConstraint(
                fields=('book', 'borrower'),
                condition=Q(status='active'),
                name='one_active_reservation_per_book_member',
            ),
        )

    def __str__(self):
        return f'{self.book.title} · {self.borrower.username} · {self.get_status_display()}'

    def resolve(self, status):
        if status not in {'fulfilled', 'cancelled'}:
            raise ValueError('A reservation can only be fulfilled or cancelled.')
        self.status = status
        self.resolved_at = timezone.now()
        self.save(update_fields=['status', 'resolved_at'])


class Notification(models.Model):
    """In-app alert with optional email delivery tracking."""

    TYPE_CHOICES = (
        ('due_soon', 'Due soon'),
        ('due_today', 'Due today'),
        ('overdue', 'Overdue'),
        ('reservation', 'Reservation available'),
        ('admin_digest', 'Administrator digest'),
    )
    EMAIL_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=160)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    dedupe_key = models.CharField(max_length=255, unique=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(
        max_length=10,
        choices=EMAIL_STATUS_CHOICES,
        default='pending',
    )
    email_error = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user.username} · {self.title}'

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class ScanAudit(models.Model):
    """Immutable audit trail for QR circulation activity."""

    ACTION_CHOICES = (
        ('lookup', 'Lookup'),
        ('issue', 'Issue'),
        ('return', 'Return'),
        ('error', 'Error'),
    )

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='scan_actions',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    raw_code = models.CharField(max_length=300)
    book_instance = models.ForeignKey(
        BookInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scan_audits',
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scan_transactions',
    )
    success = models.BooleanField(default=False)
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.get_action_display()} · {self.message}'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.is_superuser:
            role = 'superadmin'
        elif instance.is_staff:
            role = 'library'
        else:
            role = 'student'
        from .permissions import ROLE_CRUD_DEFAULTS
        Profile.objects.create(user=instance, role=role, **ROLE_CRUD_DEFAULTS[role])

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()
