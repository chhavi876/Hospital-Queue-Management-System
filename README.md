Queue Management System
A comprehensive queue management system designed for healthcare facilities to manage patient flow for OPD (Outpatient Department) and test services. The system includes QR code scanning, OTP-based authentication, real-time updates, and a display screen for announcements.

Table of Contents
Features

System Architecture

Prerequisites

Installation

Database Setup

Configuration

Running the Application

Usage Guide

API Endpoints

WebSocket Events

File Structure

Troubleshooting

Contributing

License

Features
Patient Features
QR code scanning for easy access

OTP-based phone verification with actual SMS delivery

Service selection (OPD/Test)

Queue position tracking

Real-time status updates

Patient dashboard with queue information and beautiful status messages

Staff Features
Secure staff authentication with session management

Counter management

Patient queue management

Serve/Skip patient functionality

Counter status management (Available, Busy, Break)

Break handling with patient redistribution

Real-time queue updates

System Features
Display screen with announcements in tabular format

Real-time WebSocket updates

Queue history tracking

Automatic patient redistribution during breaks

Audio announcements (3 times per patient call)

Twilio SMS integration for OTP delivery

System Architecture
Backend: Django + Django REST Framework

Database: MySQL

Real-time Communication: WebSockets (Django Channels)

Authentication: OTP-based phone verification with SMS

SMS Service: Twilio integration

Frontend: HTML, CSS, JavaScript

API: RESTful APIs

Prerequisites
Python 3.8+

MySQL 5.7+

Twilio account (for OTP SMS)

Redis (for production WebSocket layer - optional)

Installation
Clone the repository

bash
git clone https://github.com/yourusername/queue-management-system.git
cd queue-management-system
Create virtual environment

bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install dependencies

bash
pip install django djangorestframework channels mysql-connector-python twilio
Create Django project structure

bash
django-admin startproject queue_system .
python manage.py startapp queue_app
Database Setup
Create MySQL database

sql
CREATE DATABASE queue_system;
CREATE USER 'queue_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON queue_system.* TO 'queue_user'@'localhost';
FLUSH PRIVILEGES;
Configure database settings in settings.py

python
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
Run migrations

bash
python manage.py makemigrations
python manage.py migrate
Create superuser

bash
python manage.py createsuperuser
Configuration
1. Update settings.py
python
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

# Twilio Configuration for OTP SMS
TWILIO_ACCOUNT_SID = 'your_twilio_account_sid_here'
TWILIO_AUTH_TOKEN = 'your_twilio_auth_token_here'
TWILIO_PHONE_NUMBER = 'your_twilio_phone_number'  # Format: +1234567890

# Channels Configuration
ASGI_APPLICATION = 'queue_system.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
        # For production with Redis:
        # 'BACKEND': 'channels_redis.core.RedisChannelLayer',
        # 'CONFIG': {
        #     "hosts": [('127.0.0.1', 6379)],
        # },
    },
}

# Session settings for staff authentication
SESSION_COOKIE_NAME = 'queuesystem_staff_session'
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
2. Configure URLs (urls.py)
python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('queue_app.urls')),
]
3. Create queue_app/urls.py
python
from django.urls import path
from . import views

urlpatterns = [
    # Patient URLs
    path('', views.home_redirect, name='home_redirect'),
    path('patient/login/', views.patient_login, name='patient_login'),
    path('send_otp/', views.send_otp_view, name='send_otp'),
    path('verify_otp/', views.verify_otp_view, name='verify_otp'),
    path('check_patient/', views.check_patient, name='check_patient'),
    path('service/selection/', views.service_selection, name='service_selection'),
    path('queue/join/', views.join_queue, name='join_queue'),
    path('dashboard/', views.patient_dashboard, name='patient_dashboard'),
    
    # Staff URLs
    path('staff/login/', views.staff_login, name='staff_login'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/serve_next/', views.serve_next, name='serve_next'),
    path('staff/skip_patient/', views.skip_patient, name='skip_patient'),
    path('staff/update_status/', views.update_counter_status, name='update_counter_status'),
    path('staff/announce_patient/', views.announce_patient, name='announce_patient'),
    path('staff/get_queue_data/', views.get_queue_data, name='get_queue_data'),
    path('staff/logout/', views.staff_logout, name='staff_logout'),
    
    # Display URLs
    path('display/', views.display_screen, name='display_screen'),
    path('display/screen/data/', views.display_screen_data, name='display_screen_data'),
    
    # Debug URLs
    path('debug/counters/', views.debug_counters, name='debug_counters'),
    path('debug/session/', views.debug_session, name='debug_session'),
]
4. Configure WebSocket routing
Create queue_system/asgi.py:

python
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
Create queue_app/routing.py:

python
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/queue/updates/$', consumers.QueueUpdatesConsumer.as_asgi()),
]
Running the Application
Development Mode
Run Django development server

bash
python manage.py runserver
Run ASGI server for WebSockets

bash
daphne queue_system.asgi:application --port 8001
Production Mode
Install production dependencies

bash
pip install gunicorn daphne
Run with Gunicorn and Daphne

bash
# Terminal 1 - HTTP
gunicorn queue_system.wsgi:application -b 0.0.0.0:8000

# Terminal 2 - WebSockets
daphne queue_system.asgi:application -b 0.0.0.0:8001
Usage Guide
For Patients
Visit the application URL

Enter phone number and name (for new users) or just phone number (for existing users)

Verify OTP sent to your phone via SMS

Select service (OPD or Test)

Get queue ID and wait for your turn

Monitor dashboard for real-time updates with beautiful status messages

For Staff
Login with username and password

Manage patient queue from your dashboard

Call next patient or skip if patient is absent

Update counter status (Available, Busy, Break)

Announce patients (calls 3 times with audio)

Display Screen
Shows all counters in tabular format with current serving patients

Updates in real-time via WebSocket

Announces patient names 3 times with audio

Accessible at /display/

API Endpoints
Authentication
POST /send_otp/ - Send OTP to phone number (via SMS)

POST /verify_otp/ - Verify OTP and login

GET /check_patient/ - Check if patient exists

Queue Management
POST /queue/join/ - Join a service queue

GET /dashboard/ - Get patient dashboard data

POST /staff/serve_next/ - Serve next patient

POST /staff/skip_patient/ - Skip current patient

POST /staff/update_status/ - Update counter status

POST /staff/announce_patient/ - Announce patient

Real-time Updates
WS /ws/queue/updates/ - WebSocket for real-time updates

WebSocket Events
Client Receives:
new_patient - New patient joined queue

patient_served - Patient served

patient_redistributed - Patient moved to different counter

counter_status_update - Counter status changed

Event Format:
json
{
    "type": "queue_update",
    "counter_id": 1,
    "serving_patient": {
        "queue_id": "OPD_001_1234",
        "patient_name": "John Doe"
    },
    "queue_length": 5
}
File Structure
text
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
│   ├── middleware.py
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
Troubleshooting
Common Issues
Database Connection Error

Check MySQL service is running

Verify database credentials in settings.py

Ensure database exists

OTP Not Sending

Verify Twilio credentials in settings.py

Check phone number format

Ensure sufficient Twilio balance

WebSocket Not Connecting

Check Daphne server is running

Verify WebSocket URL in templates

Session Mixing Issues

Ensure proper session management middleware

Use different browser tabs for different staff logins

Logs
Django logs: Check console output

Database logs: Check MySQL error logs

WebSocket logs: Check Daphne output

Initial Data Setup
Create Services
python
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
Create Counters
python
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
Create Staff Users
python
from queue_app.models import Staff

Staff.objects.create(
    username='operator1',
    password='password123',  # Will be hashed automatically
    role='operator',
    is_active=True
)
Security Considerations
Use HTTPS in production

Implement proper password hashing for staff accounts

Add rate limiting for OTP requests

Validate and sanitize all user inputs

Use CSRF protection

Implement proper session management

Secure Twilio credentials

Contributing
Fork the repository

Create a feature branch

Make your changes

Add tests

Submit a pull request

License
This project is licensed under the MIT License - see the LICENSE file for details.
