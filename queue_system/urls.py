from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

# Standard HTTP URL patterns
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('queue_app.urls')),
]

# For development media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# No ProtocolTypeRouter here - it belongs in asgi.py