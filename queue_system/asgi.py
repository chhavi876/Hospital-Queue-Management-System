import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import queue_app.routing  # Import your app's routing

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'queue_system.settings')

# Get the standard Django ASGI application for HTTP requests
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # First, handle HTTP requests with standard Django
    "http": django_asgi_app,
    
    # Then, handle WebSocket requests with Channels
    "websocket": AuthMiddlewareStack(
        URLRouter(
            queue_app.routing.websocket_urlpatterns  # Your WebSocket routes
        )
    ),
})
