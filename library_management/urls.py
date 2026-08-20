"""
URL configuration for library_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.db import connection
from django.http import HttpResponse, JsonResponse


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

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('sw.js', legacy_service_worker, name='legacy-service-worker'),
    path('', include('catalog.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
