# consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class QueueUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Accept the connection
        await self.accept()
        
        # Add this connection to the "staff_updates" group
        await self.channel_layer.group_add(
            "staff_updates",
            self.channel_name
        )
        
        print(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        # Remove from group
        await self.channel_layer.group_discard(
            "staff_updates",
            self.channel_name
        )
        print(f"WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data):
        # Handle incoming messages (if needed)
        try:
            data = json.loads(text_data)
            print("Received:", data)
        except Exception as e:
            print(f"WebSocket receive error: {str(e)}")

    # This method handles messages sent to the group
    async def send_update(self, event):
        # Send message to WebSocket
        message = event["message"]
        await self.send(text_data=json.dumps(message))
        print(f"WebSocket message sent: {message}")


class DisplayUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(
            "display_updates",
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            "display_updates",
            self.channel_name
        )

    async def display_update(self, event):
        await self.send(text_data=json.dumps(event["message"]))
