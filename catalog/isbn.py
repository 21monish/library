import json
import urllib.error
import urllib.parse
import urllib.request


class ISBNLookupError(Exception):
    pass


def normalize_isbn(value):
    return ''.join(character for character in value.upper() if character.isdigit() or character == 'X')


def lookup_isbn(value):
    """Fetch one ISBN record from Open Library's Search and Covers APIs."""
    isbn = normalize_isbn(value)
    if len(isbn) not in {10, 13}:
        raise ISBNLookupError('Enter a valid 10- or 13-character ISBN.')
    query = urllib.parse.urlencode({
        'isbn': isbn,
        'limit': 1,
        'fields': 'title,author_name,subject,first_publish_year,publisher,cover_i,isbn',
    })
    request = urllib.request.Request(
        f'https://openlibrary.org/search.json?{query}',
        headers={'User-Agent': 'ShelfwiseLibrary/1.0 (library catalog ISBN lookup)'},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ISBNLookupError('The book service is temporarily unavailable. Try again or enter the book manually.') from exc
    documents = payload.get('docs') or []
    if not documents:
        raise ISBNLookupError('No book was found for this ISBN. You can still add it manually.')
    record = documents[0]
    authors = record.get('author_name') or []
    subjects = [str(subject).strip() for subject in (record.get('subject') or []) if str(subject).strip()][:5]
    publishers = record.get('publisher') or []
    year = record.get('first_publish_year')
    details = []
    if publishers:
        details.append(f'Publisher: {publishers[0]}')
    if year:
        details.append(f'First published: {year}')
    summary = '. '.join(details)
    if summary:
        summary += '.'
    cover_id = record.get('cover_i')
    cover_url = f'https://covers.openlibrary.org/b/id/{cover_id}-L.jpg' if cover_id else ''
    return {
        'isbn': isbn,
        'title': (record.get('title') or '').strip(),
        'author': authors[0].strip() if authors else '',
        'summary': summary,
        'genres': ', '.join(subjects),
        'cover_url': cover_url,
    }
