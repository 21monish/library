from django import forms

from .isbn import normalize_isbn
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Author, Book, BookInstance, Genre, Profile
from .permissions import (
    BORROWER_ROLES,
    CRUD_ACTIONS,
    ROLE_CRUD_DEFAULTS,
    is_superadmin,
    set_role_permission_defaults,
    sync_user_role,
)


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ('first_name', 'last_name', 'date_of_birth', 'date_of_death')
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'}), 'date_of_death': forms.DateInput(attrs={'type': 'date'})}


class GenreForm(forms.ModelForm):
    class Meta:
        model = Genre
        fields = ('name',)
from .storage import upload_public_image, validate_image_upload


class BookForm(forms.ModelForm):
    asset_upload = forms.ImageField(
        required=False,
        validators=(validate_image_upload,),
        label='Book cover',
        help_text='Optional JPEG, PNG, or WebP image up to 3 MB.',
    )

    class Meta:
        model = Book
        fields = ('title', 'author', 'summary', 'isbn', 'genre', 'cover_url')
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 5}),
            'genre': forms.SelectMultiple(attrs={'size': 7}),
        }

    def clean_isbn(self):
        return normalize_isbn(self.cleaned_data['isbn'])

    def save(self, commit=True):
        book = super().save(commit=False)
        upload = self.cleaned_data.get('asset_upload')
        if upload:
            book.cover_url = upload_public_image(upload, 'book-covers')
        if commit:
            book.save()
            self.save_m2m()
        return book


class MemberForm(forms.ModelForm):
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Required for new members. Leave blank while editing to keep the current password.',
    )
    photo_upload = forms.ImageField(
        required=False,
        validators=(validate_image_upload,),
        help_text='Optional JPEG, PNG, or WebP image up to 3 MB.',
    )
    can_view = forms.BooleanField(required=False, label='View', help_text='Open staff record screens.')
    can_add = forms.BooleanField(required=False, label='Add', help_text='Create new records.')
    can_change = forms.BooleanField(required=False, label='Change', help_text='Edit records and run update workflows.')
    can_delete = forms.BooleanField(required=False, label='Delete', help_text='Permanently delete eligible records.')
    permissions_configured = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')

    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        self.is_new_account = not self.instance.pk
        self.original_role = self.instance.profile.role if self.instance.pk else None
        self.fields['email'].required = True
        self.fields['email'].help_text = 'Required for notifications and secure password recovery.'
        if self.instance.pk:
            self.fields['role'].initial = self.instance.profile.role
            for action in CRUD_ACTIONS:
                self.fields[f'can_{action}'].initial = getattr(self.instance.profile, f'can_{action}')
        if not is_superadmin(actor):
            self.fields['role'].choices = [
                choice for choice in Profile.ROLE_CHOICES
                if choice[0] in BORROWER_ROLES
            ]
            self.fields['role'].help_text = (
                'Library staff can create student and teacher accounts. '
                'Only the superadmin can assign privileged roles.'
            )
            for field_name in (*[f'can_{action}' for action in CRUD_ACTIONS], 'permissions_configured'):
                self.fields.pop(field_name)
        else:
            self.fields['role'].help_text = (
                'The role sets the maximum access level. CRUD checkboxes can further restrict staff accounts.'
            )
            if self.is_new_account:
                for field_name, value in ROLE_CRUD_DEFAULTS['student'].items():
                    self.fields[field_name].initial = value

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This email address is already used by another account.')
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if not self.instance.pk and not password:
            raise forms.ValidationError('A password is required for a new member.')
        if password:
            validate_password(password, self.instance if self.instance.pk else None)
        return password

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.actor == self.instance and not cleaned.get('is_active', True):
            self.add_error('is_active', 'You cannot deactivate your own account.')
        if (
            self.instance.pk
            and self.actor == self.instance
            and self.instance.profile.role == 'superadmin'
            and cleaned.get('role') != 'superadmin'
        ):
            self.add_error('role', 'You cannot remove your own superadmin access.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data['role']
            upload = self.cleaned_data.get('photo_upload')
            if upload:
                profile.photo_url = upload_public_image(upload, 'profiles')
            permission_fields = [f'can_{action}' for action in CRUD_ACTIONS]
            if is_superadmin(self.actor):
                if 'permissions_configured' in self.data:
                    for field_name in permission_fields:
                        setattr(profile, field_name, bool(self.cleaned_data.get(field_name)))
                elif self.is_new_account or self.original_role != profile.role:
                    set_role_permission_defaults(profile, profile.role)
                if profile.role == 'superadmin':
                    set_role_permission_defaults(profile, profile.role)
            elif self.is_new_account or self.original_role != profile.role:
                set_role_permission_defaults(profile, profile.role)
            profile.save(update_fields=['role', 'photo_url', *permission_fields])
            sync_user_role(user, profile.role)
        return user


class AccountForm(forms.ModelForm):
    """Safe self-service fields that never allow role or permission changes."""

    email = forms.EmailField(
        required=True,
        help_text='Used for due-date notifications and password recovery.',
    )
    photo_upload = forms.ImageField(
        required=False,
        validators=(validate_image_upload,),
        help_text='Optional JPEG, PNG, or WebP image up to 3 MB.',
        label='Profile photo',
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This email address is already used by another account.')
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        upload = self.cleaned_data.get('photo_upload')
        if commit and upload:
            user.profile.photo_url = upload_public_image(upload, 'profiles')
            user.profile.save(update_fields=['photo_url'])
        return user


class BookInstanceForm(forms.ModelForm):
    class Meta:
        model = BookInstance
        fields = ('book', 'accession_number', 'imprint', 'shelf_location', 'status', 'condition_notes')
        widgets = {'condition_notes': forms.Textarea(attrs={'rows': 4})}

    def clean_accession_number(self):
        value = (self.cleaned_data.get('accession_number') or '').strip().upper()
        return value or None

    def clean_status(self):
        status = self.cleaned_data['status']
        if self.instance.pk and self.instance.status == 'o' and status != 'o':
            raise forms.ValidationError('Use the Return action to close an active loan.')
        return status


class CopyIssueForm(forms.Form):
    borrower = forms.ModelChoiceField(
        queryset=User.objects.none(),
        help_text='Only active member accounts are listed.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['borrower'].queryset = User.objects.filter(
            is_active=True,
            profile__role__in=('student', 'teacher'),
        ).select_related('profile').order_by('profile__role', 'username')
        self.fields['borrower'].label_from_instance = lambda user: (
            f'{user.get_full_name() or user.username} — {user.profile.get_role_display()}'
        )


class ISBNImportForm(forms.Form):
    isbn = forms.CharField(max_length=17, label='ISBN')
    title = forms.CharField(max_length=200, required=False)
    author = forms.CharField(max_length=200, required=False, help_text='Use the author’s full name.')
    summary = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    genres = forms.CharField(required=False, help_text='Separate genres with commas.')
    cover_url = forms.URLField(max_length=700, required=False)

    def clean_isbn(self):
        isbn = normalize_isbn(self.cleaned_data['isbn'])
        if len(isbn) not in {10, 13}:
            raise forms.ValidationError('Enter a valid 10- or 13-character ISBN.')
        if Book.objects.filter(isbn=isbn).exists():
            raise forms.ValidationError('A book with this ISBN already exists.')
        return isbn

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if self.data.get('action') == 'create' and not title:
            raise forms.ValidationError('Title is required before creating the book.')
        return title
