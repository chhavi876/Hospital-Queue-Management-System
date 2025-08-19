# consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Counter, QueueEntry, Staff

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add("queue_updates", self.channel_name)
        
        # Send initial data
        counters = await self.get_counters()
        serving_patients = await self.get_serving_patients()
        
        await self.send(text_data=json.dumps({
            'type': 'initial_data',
            'counters': counters,
            'serving_patients': serving_patients
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("queue_updates", self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'staff_auth':
                # Authenticate staff and subscribe to counter updates
                staff = await self.authenticate_staff(data.get('staff_id'), data.get('token'))
                if staff:
                    counter_group = f'counter_{staff.counter.counter_id}'
                    await self.channel_layer.group_add(
                        counter_group,
                        self.channel_name
                    )
        except Exception as e:
            print(f"WebSocket receive error: {str(e)}")

    async def queue_update(self, event):
        # Send general queue updates
        await self.send(text_data=json.dumps(event))

    async def counter_update(self, event):
        # Send counter-specific updates
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_counters(self):
        counters = Counter.objects.filter(is_active=True).order_by('counter_id')
        return [{
            'counter_id': c.counter_id,
            'counter_name': c.counter_name,
            'current_status': c.current_status,
            'service_name': c.service.service_name,
            'staff_name': c.staff.username if c.staff else None
        } for c in counters]

    @database_sync_to_async
    def get_serving_patients(self):
        serving = QueueEntry.objects.filter(current_status='serving').select_related('counter', 'patient')
        return {
            s.counter.counter_id: {
                'queue_id': s.queue_id,
                'patient_name': s.patient.name,
                'service_name': s.service.service_name
            } for s in serving
        }

    @database_sync_to_async
    def authenticate_staff(self, staff_id, token):
        try:
            staff = Staff.objects.get(
                staff_id=staff_id,
                auth_token=token  # You should implement proper token auth
            )
            return staff
        except Staff.DoesNotExist:
            return None