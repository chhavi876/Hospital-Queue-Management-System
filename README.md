# Queue Management System

A comprehensive queue management system designed for healthcare facilities to manage patient flow for OPD (Outpatient Department) and test services. The system includes QR code scanning, OTP-based authentication, real-time updates, and a display screen for announcements.

## Table of Contents

- [Features](#features)
- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Database Setup](#database-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage Guide](#usage-guide)
- [API Endpoints](#api-endpoints)
- [WebSocket Events](#websocket-events)
- [File Structure](#file-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

### Patient Features
- QR code scanning for easy access
- OTP-based phone verification
- Service selection (OPD/Test)
- Queue position tracking
- Real-time status updates
- Patient dashboard with queue information

### Staff Features
- Secure staff authentication
- Counter management
- Patient queue management
- Serve/Skip patient functionality
- Counter status management (Available, Busy, Break)
- Break handling with patient redistribution
- Real-time queue updates

### System Features
- Display screen with announcements
- Real-time WebSocket updates
- Queue history tracking
- Automatic patient redistribution during breaks
- Audio announcements (3 times per patient call)

## System Architecture

- **Backend**: Django + Django REST Framework
- **Database**: MySQL
- **Real-time Communication**: WebSockets (Django Channels)
- **Authentication**: OTP-based phone verification
- **Frontend**: HTML, CSS, JavaScript
- **API**: RESTful APIs

## Prerequisites

- Python 3.8+
- MySQL 5.7+
- Redis (for production WebSocket layer)
- SMS Gateway service (for OTP)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/queue-management-system.git
   cd queue-management-system
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install django djangorestframework channels mysql-connector-python channels-redis
   ```

4. **Create Django project structure**
   ```bash
   django-admin startproject queue_system
   cd queue_system
   python manage.py startapp queue_app
   ```

## Database Setup

1. **Create MySQL database**
   ```sql
   CREATE DATABASE queue_system;
   CREATE USER 'queue_user'@'localhost' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON queue_system.* TO 'queue_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. **Configure database settings in `settings.py`**
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.mysql',
           'NAME': 'queue_system',
           'USER': 'queue_user',
           'PASSWORD': 'your_password',
           'HOST': 'localhost',
           'PORT': '3306',
           'OPTIONS': {
               'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
           },
       }
   }
   ```

3. **Run migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

## Configuration

### 1. Update `settings.py`

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'channels',
    'queue_app',
]

# Channels Configuration
ASGI_APPLICATION = 'queue_system.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
        # For development without Redis:
        # 'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}

# SMS Configuration (Add your SMS provider settings)
SMS_API_KEY = 'your_sms_api_key'
SMS_API_URL = 'your_sms_provider_url'
```

### 2. Configure URLs (`urls.py`)

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('queue_app.urls')),
]
```

### 3. Create `queue_app/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    # Patient URLs
    path('', views.patient_login, name='patient_login'),
    path('send_otp/', views.send_otp_view, name='send_otp'),
    path('verify_otp/', views.verify_otp_view, name='verify_otp'),
    path('check_patient/', views.check_patient, name='check_patient'),
    path('service_selection/', views.service_selection, name='service_selection'),
    path('join_queue/', views.join_queue, name='join_queue'),
    path('patient_dashboard/', views.patient_dashboard, name='patient_dashboard'),
    
    # Staff URLs
    path('staff/login/', views.staff_login, name='staff_login'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/serve_next/', views.serve_next, name='serve_next'),
    path('staff/skip_patient/', views.skip_patient, name='skip_patient'),
    path('staff/update_status/', views.update_counter_status, name='update_counter_status'),
    
    # Display URLs
    path('display/', views.display_screen, name='display_screen'),
]
```

### 4. Configure WebSocket routing

Create `queue_system/asgi.py`:
```python
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import queue_app.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'queue_system.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            queue_app.routing.websocket_urlpatterns
        )
    ),
})
```

## Running the Application

### Development Mode

1. **Start Redis server** (if using Redis for channels)
   ```bash
   redis-server
   ```

2. **Run Django development server**
   ```bash
   python manage.py runserver
   ```

3. **Run ASGI server for WebSockets** (in another terminal)
   ```bash
   daphne -p 8001 queue_system.asgi:application
   ```

### Production Mode

1. **Install production dependencies**
   ```bash
   pip install gunicorn daphne nginx
   ```

2. **Configure Nginx** (`/etc/nginx/sites-available/queue_system`)
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       location /ws/ {
           proxy_pass http://127.0.0.1:8001;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }

       location /static/ {
           alias /path/to/your/staticfiles/;
       }
   }
   ```

3. **Run with Gunicorn and Daphne**
   ```bash
   gunicorn queue_system.wsgi: application
   daphne queue_system.asgi: application
   ```

## Usage Guide

### For Patients

1. **Scan QR Code or visit the URL**
2. **Enter phone number and name** (for new users) or **just phone number** (for existing users)
3. **Verify OTP** sent to your phone
4. **Select service** (OPD or Test)
5. **Get queue ID** and wait for your turn
6. **Monitor dashboard** for real-time updates

### For Staff

1. **Login with username and password**
2. **Select your role** (Operator, Supervisor, Admin)
3. **Manage patient queue** from your dashboard
4. **Call next patient** or **skip** if patient is absent
5. **Update counter status** (Available, Busy, Break)

### Display Screen

- Shows all counters with current serving patients
- Updates in real-time via WebSocket
- Announces patient names 3 times

## API Endpoints

### Authentication
- `POST /send_otp/` - Send OTP to phone number
- `POST /verify_otp/` - Verify OTP and login
- `GET /check_patient/` - Check if patient exists

### Queue Management
- `POST /join_queue/` - Join a service queue
- `GET /patient_dashboard/` - Get patient dashboard data
- `POST /staff/serve_next/` - Serve next patient
- `POST /staff/skip_patient/` - Skip current patient
- `POST /staff/update_status/` - Update counter status

### Real-time Updates
- `WS /ws/queue/updates/` - WebSocket for real-time updates

## WebSocket Events

### Client Receives:
- `initial_data` - Initial counter and queue data
- `queue_update` - Real-time queue updates
- `counter_status_update` - Counter status changes
- `patient_called` - Patient announcement

### Event Format:
```json
{
    "type": "queue_update",
    "counter_id": 1,
    "serving_patient": {
        "queue_id": "OPD_001_1234",
        "patient_name": "John Doe"
    },
    "queue_length": 5
}
```

## File Structure

```
queue_system/
├── queue_system/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── queue_app/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── consumers.py
│   ├── routing.py
│   ├── utils.py
│   ├── migrations/
│   └── templates/
│       ├── patient_login.html
│       ├── service_selection.html
│       ├── patient_dashboard.html
│       ├── staff_login.html
│       ├── staff_dashboard.html
│       └── display_screen.html
├── static/
├── media/
├── requirements.txt
└── manage.py
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check the MySQL service is running
   - Verify database credentials in settings.py
   - Ensure database exists

2. **WebSocket Not Connecting**
   - Check the Redis server is running
   - Verify the ASGI application is running on the correct port
   - Check firewall settings

3. **OTP Not Sending**
   - Verify SMS gateway configuration
   - Check API credentials
   - Ensure phone number format is correct

4. **Static Files Not Loading**
   - Run `python manage.py collectstatic`
   - Check STATIC_URL and STATIC_ROOT settings

### Logs

- Django logs: Check console output
- Database logs: Check MySQL error logs
- WebSocket logs: Check Daphne output

## Initial Data Setup

1. **Create Services**
   ```python
   # Using Django shell: python manage.py shell
   from queue_app.models import Service
   
   Service.objects.create(
       service_name='OPD',
       description='Outpatient Department',
       week_days=1,  # Monday
       is_active=True
   )
   
   Service.objects.create(
       service_name='Test',
       description='Laboratory Tests',
       week_days=1,  # Monday
       is_active=True
   )
   ```

2. **Create Counters**
   ```python
   from queue_app.models import Counter, Service
   from datetime import time
   
   opd_service = Service.objects.get(service_name='OPD')
   test_service = Service.objects.get(service_name='Test')
   
   Counter.objects.create(
       counter_name='Counter 1',
       service=opd_service,
       start_time=time(9, 0),
       end_time=time(17, 0),
       current_status='available'
   )
   
   Counter.objects.create(
       counter_name='Counter 2',
       service=test_service,
       start_time=time(9, 0),
       end_time=time(17, 0),
       current_status='available'
   )
   ```

3. **Create Staff Users**
   ```python
   from queue_app.models import Staff
   
   Staff.objects.create(
       username='operator1',
       password='password123',  # Use proper hashing in production
       role='operator',
       is_active=True
   )
   ```

## Security Considerations

- Use HTTPS in production
- Implement proper password hashing for staff accounts
- Add rate limiting for OTP requests
- Validate and sanitize all user inputs
- Use CSRF protection
- Implement proper session management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

