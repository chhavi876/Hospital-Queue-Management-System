# queue_app/urls.py
from django.urls import path
from . import views
from . import consumers
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic.base import RedirectView


urlpatterns = [
    # Authentication URLs
    path('', views.home_redirect, name='home'),
    path('login/', views.patient_login, name='patient_login'),
    path('staff/login/', views.staff_login, name='staff_login'),
    
    # OTP URLs
    path('api/send-otp/', views.send_otp_view, name='send_otp'),
    path('api/verify-otp/', views.verify_otp_view, name='verify_otp'),
    
    # Patient Flow URLs
    path('staff/announce_patient/', views.announce_patient, name='announce_patient'),
    path('staff/get_queue_data/', views.get_queue_data, name='get_queue_data'),
    path('services/', views.service_selection, name='service_selection'),
    path('queue/join/', views.join_queue, name='join_queue'),
    path('dashboard/', views.patient_dashboard, name='patient_dashboard'),
    
    # Staff Flow URLs
    path('patient/get_queue_status/', views.get_queue_status, name='get_queue_status'),
    path('staff/update_status/', views.update_counter_status, name='update_counter_status'),
    path('staff/skip_patient/', views.skip_patient, name='skip_patient'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('service_selection/', views.service_selection, name='service_selection'),
    path('staff/serve_next/', views.serve_next, name='serve_next'),
    path('staff/handle_break/', views.handle_counter_break, name='handle_break'),
    path('staff/start_serving/', views.start_serving, name='start_serving'),
    
    path('ws/queue/updates/', consumers.QueueUpdatesConsumer.as_asgi()),
    # Display Screen URL
    
    #path('favicon.ico', RedirectView.as_view(url=staticfiles_storage.url('img/favicon.ico'))),
    # API Endpoints (for AJAX calls)
    path('api/check-patient/', views.check_patient, name='check_patient'),
    path('staff/logout/', views.staff_logout, name='staff_logout'),
    path('display/', views.display_screen, name='display_screen'),
    path('display/screen/data/', views.display_screen_data, name='display_screen_data'),

    path('debug/counters/', views.debug_counters, name='debug_counters'),
    path('staff/debug_session/', views.debug_session, name='debug_session'),
    path('debug/staff_counters/', views.debug_staff_counters, name='debug_staff_counters'),
]
