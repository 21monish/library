"""
URL configuration for library_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.urls import path, include, re_path
from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views.static import serve


def health_check(request):
    """Small database-aware endpoint for deployment health monitoring."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    response = JsonResponse({'status': 'ok'})
    response['Cache-Control'] = 'no-store'
    return response


def legacy_service_worker(request):
    """Gracefully retire service workers registered by older local builds."""
    script = (
        "self.addEventListener('install',()=>self.skipWaiting());"
        "self.addEventListener('activate',event=>event.waitUntil("
        "self.registration.unregister().then(()=>self.clients.claim())));"
    )
    response = HttpResponse(script, content_type='application/javascript')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Service-Worker-Allowed'] = '/'
    return response


def media_file(request, path):
    """Serve public uploaded images from the configured persistent media root."""
    return serve(request, path, document_root=settings.MEDIA_ROOT)

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('sw.js', legacy_service_worker, name='legacy-service-worker'),
    path('', include('catalog.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    # Uploaded covers and profile photos live on Sevalla persistent storage.
    # django.views.static.serve performs safe path resolution and conditional
    # responses; it is suitable here because uploads are small public images.
    re_path(
        rf'^{settings.MEDIA_URL.lstrip("/")}(?P<path>.*)$',
        media_file,
        name='media-file',
    ),
]
