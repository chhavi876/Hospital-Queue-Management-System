from django.urls import path
from . import consumers

websocket_urlpatterns = [
    # Add your WebSocket routes here
    path(r'ws/queue/updates/$', consumers.QueueConsumer.as_asgi()),
    
    # Example additional WebSocket route:
    # re_path(r'ws/counter/(?P<counter_id>\w+)/$', consumers.CounterConsumer.as_asgi()),
]