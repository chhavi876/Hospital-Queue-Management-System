from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    
    re_path(r'ws/queue/updates/$', consumers.QueueUpdatesConsumer.as_asgi()),
    
]
