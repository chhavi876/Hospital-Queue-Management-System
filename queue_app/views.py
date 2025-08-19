# views.py
import random
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth import authenticate, login
from django.conf import settings
from django.contrib.auth import login
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Patient, OTP, Service, QueueEntry, Counter, QueueHistory, Staff
from .utils import send_otp
import string
from datetime import date
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.contrib.humanize.templatetags.humanize import naturaltime
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
import uuid

logger = logging.getLogger(__name__)


@csrf_exempt
def send_otp_view(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        name = request.POST.get('name', '')
        
        # Validate phone number
        if not phone_number or len(phone_number) != 10 or not phone_number.isdigit():
            return JsonResponse({'status': 'error', 'message': 'Invalid phone number'}, status=400)
        
        try:
            # Check if patient exists
            patient = Patient.objects.get(phone_number=phone_number)
            is_new_patient = False
        except Patient.DoesNotExist:
            # New patient - require name
            if not name:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Name is required for new patients',
                    'new_patient': True
                }, status=400)
            patient = Patient.objects.create(
                phone_number=phone_number,
                name=name
            )
            is_new_patient = True
        
        # Generate and send OTP
        otp = str(random.randint(100000, 999999))
        expires_at = timezone.now() + timedelta(minutes=5)
        
        OTP.objects.create(
            phone_number=phone_number,
            otp=otp,
            expires_at=expires_at
        )
        
        # In development, log the OTP instead of sending SMS
        print(f"OTP for {phone_number}: {otp} (Expires at: {expires_at})")
        
        # In production, uncomment this:
        # send_otp(phone_number, otp)
        
        return JsonResponse({
            'status': 'success',
            'is_new_patient': is_new_patient,
            'message': 'OTP sent successfully'
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@csrf_exempt
def verify_otp_view(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        otp = request.POST.get('otp')
        
        try:
            # Use timezone.now() consistently
            now = timezone.now()
            otp_record = OTP.objects.filter(
                phone_number=phone_number,
                is_used=False,
                expires_at__gte=now  # Compare with current timezone-aware datetime
            ).latest('created_at')
            
            if otp_record.otp == otp:
                otp_record.is_used = True
                otp_record.save()
                
                patient = Patient.objects.get(phone_number=phone_number)
                patient.is_verified = True
                patient.save()
                
                request.session['patient_phone'] = phone_number
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid OTP'})
                
        except OTP.DoesNotExist:
            # Add debug logging
            print(f"No valid OTP found for {phone_number} at {now}")
            print(f"Existing OTPs: {OTP.objects.filter(phone_number=phone_number).values()}")
            return JsonResponse({
                'status': 'error', 
                'message': 'OTP expired or not found'
            })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def patient_login(request):
    return render(request, 'patient_login.html')

def patient_dashboard(request):
    if 'patient_phone' not in request.session:
        return redirect('patient_login')
    
    patient = Patient.objects.get(phone_number=request.session['patient_phone'])
    queue_entry = QueueEntry.objects.filter(patient=patient, current_status__in=['waiting', 'serving']).first()
    
    return render(request, 'patient_dashboard.html', {
        'patient': patient,
        'queue_entry': queue_entry
    })

@ensure_csrf_cookie
def service_selection(request):
    if 'patient_phone' not in request.session:
        return redirect('patient_login')
    
    # Only show services that have at least one available counter
    available_services = Service.objects.filter(
        is_active=True,
        counter__current_status='available'
    ).distinct()
    
    return render(request, 'service_selection.html', {
        'services': available_services
    })

def generate_queue_id(service, counter=None):
    prefix = service.service_name[:3].upper()
    counter_num = counter.counter_id if counter else "000"
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{prefix}_{counter_num}_{random_part}"

@csrf_exempt
def join_queue(request):
    if 'patient_phone' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    try:
        service_id = request.POST.get('service_id')
        if not service_id:
            return JsonResponse({'status': 'error', 'message': 'Service ID required'}, status=400)
        
        # Get patient
        patient = Patient.objects.get(phone_number=request.session['patient_phone'])
        
        # Check if already in queue
        if QueueEntry.objects.filter(patient=patient, current_status__in=['waiting', 'serving']).exists():
            return JsonResponse({'status': 'error', 'message': 'You are already in queue'}, status=400)
        
        # Get service with available counters
        try:
            service = Service.objects.get(
                service_id=service_id,
                is_active=True
            )
        except Service.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Service not available'}, status=404)
        
        # Get the next available counter for this service
        counter = Counter.objects.filter(
            service=service,
            current_status='available'
        ).order_by('counter_id').first()
        
        if not counter:
            return JsonResponse({'status': 'error', 'message': 'No counters available for this service'}, status=400)
        
        # Generate queue ID
        queue_id = f"{service.service_name[:3].upper()}_{counter.counter_id}_{random.randint(1000, 9999)}"
        
        # Create queue entry
        QueueEntry.objects.create(
            queue_id=queue_id,
            patient=patient,
            service=service,
            counter=counter,
            current_status='waiting'
        )
        
        # Mark counter as busy
        counter.current_status = 'busy'
        counter.save()
        
        return JsonResponse({
            'status': 'success',
            'queue_id': queue_id,
            'show_reminder': service.service_name.lower() == 'test',
            'message': 'Added to queue successfully'
        })
        
    except Exception as e:
        # Log the full error for debugging
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error', 
            'message': 'Internal server error',
            'debug': str(e)
        }, status=500)

def calculate_wait_time():
    """Calculate average wait time based on queue length"""
    from django.db.models import Avg
    from datetime import timedelta
    avg_wait = QueueHistory.objects.filter(
        completed_at__gte=timezone.now()-timedelta(hours=1)
    ).aggregate(Avg('completed_at'-'created_at'))['created_at__avg']
    return avg_wait.total_seconds() / 60 if avg_wait else 5  # Default 5 minutes


from django.contrib.auth.hashers import check_password

def staff_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            staff = Staff.objects.get(username=username)
            if check_password(password, staff.password):  # Secure password check
                request.session['staff_id'] = staff.staff_id
                request.session['staff_role'] = staff.role
                return redirect('staff_dashboard')
        except Staff.DoesNotExist:
            pass
        
        return render(request, 'staff_login.html', {'error': 'Invalid credentials'})
    
    return render(request, 'staff_login.html')

from django.shortcuts import render
from django.http import JsonResponse
from .models import Counter, QueueEntry, Staff

def staff_dashboard(request):
    if 'staff_id' not in request.session:
        return redirect('staff_login')
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = staff.counter
        
        queue_entries = QueueEntry.objects.filter(
            counter=counter,
            current_status='waiting'
        ).order_by('created_at')
        
        serving_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        return render(request, 'staff_dashboard.html', {
            'staff': staff,
            'counter': counter,
            'queue_entries': queue_entries,
            'serving_patient': serving_patient
        })
        
    except (Staff.DoesNotExist, AttributeError):
        return render(request, 'staff_dashboard.html', {
            'error': 'No counter assigned or invalid session. Please contact administrator.'
        })

@csrf_exempt
def serve_next(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = Counter.objects.get(staff=staff)
        
        # Complete current serving patient if exists
        current_serving = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        if current_serving:
            # Move to history
            QueueHistory.objects.create(
                queue_id=current_serving.queue_id,
                patient=current_serving.patient,
                service=current_serving.service,
                counter=current_serving.counter,
                current_status='completed',
                created_at=current_serving.created_at,
                updated_at=timezone.now(),
                date=date.today(),
                completed_at=timezone.now()
            )
            current_serving.delete()
        
        # Get next patient in queue
        next_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='waiting'
        ).order_by('created_at').first()
        
        if next_patient:
            next_patient.current_status = 'serving'
            next_patient.save()
            
            # Update counter status
            counter.current_status = 'busy'
            counter.save()
            
            return JsonResponse({
                'status': 'success',
                'patient_name': next_patient.patient.name,
                'queue_id': next_patient.queue_id
            })
        else:
            # No more patients, mark counter as available
            counter.current_status = 'available'
            counter.save()
            return JsonResponse({'status': 'empty', 'message': 'No patients in queue'})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



@csrf_exempt
@require_POST
def update_counter_status(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = Counter.objects.get(staff=staff)
        
        new_status = request.POST.get('status')
        if new_status not in ['available', 'busy', 'break']:
            return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
        
        counter.current_status = new_status
        counter.save()
        
        # Handle break transition
        if new_status == 'break' and counter.current_status != 'break':
            # Find next available counter
            next_counter = Counter.objects.filter(
                service=counter.service,
                counter_id__gt=counter.counter_id,
                current_status='available'
            ).order_by('counter_id').first()
            
            if next_counter:
                # Move all waiting patients to next counter
                QueueEntry.objects.filter(
                    counter=counter,
                    current_status='waiting'
                ).update(counter=next_counter)
        
        return JsonResponse({'status': 'success', 'message': 'Status updated'})
        
    except Staff.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Staff not found'}, status=404)
    except Counter.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Counter not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Update the remaining skip_patient() function:
@csrf_exempt
@require_POST
def skip_patient(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = Counter.objects.get(staff=staff)
        
        current_serving = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        if current_serving:
            # Move to history as skipped
            QueueHistory.objects.create(
                queue_id=current_serving.queue_id,
                patient=current_serving.patient,
                service=current_serving.service,
                counter=counter,
                current_status='skipped',
                skipped_at=timezone.now(),
                created_at=current_serving.created_at,
                updated_at=timezone.now(),
                date=timezone.now().date(),
                completed_at=timezone.now()
            )
            current_serving.delete()
            
            # Get next patient
            next_patient = QueueEntry.objects.filter(
                counter=counter,
                current_status='waiting'
            ).order_by('created_at').first()
            
            if next_patient:
                next_patient.current_status = 'serving'
                next_patient.save()
                return JsonResponse({'status': 'success', 'message': 'Patient skipped'})
            else:
                counter.current_status = 'available'
                counter.save()
                return JsonResponse({'status': 'success', 'message': 'Patient skipped, no more in queue'})
        else:
            return JsonResponse({'status': 'error', 'message': 'No patient currently being served'})
            
    except Staff.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Staff not found'}, status=404)
    except Counter.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Counter not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
def display_screen(request):
    counters = Counter.objects.filter(is_active=True).order_by('counter_id')
    serving_patients = {}
    
    for counter in counters:
        serving = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        if serving:
            serving_patients[counter.counter_id] = {
                'queue_id': serving.queue_id,
                'patient_name': serving.patient.name
            }
    
    return render(request, 'queue_app/display_screen.html', {
        'counters': counters,
        'serving_patients': serving_patients
    })

def home_redirect(request):
    """Redirect to appropriate dashboard based on session"""
    if 'staff_id' in request.session:
        return redirect('staff_dashboard')
    elif 'patient_phone' in request.session:
        return redirect('patient_dashboard')
    return redirect('patient_login')

def check_patient(request):
    
    phone = request.GET.get('phone')
    if phone and len(phone) == 10:
        exists = Patient.objects.filter(phone_number=phone).exists()
        return JsonResponse({'exists': exists})
    return JsonResponse({'error': 'Invalid phone'}, status=400)

@csrf_exempt
def get_queue_data(request):
    """AJAX endpoint for queue updates"""
    # Keep your existing authentication check
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = staff.counter
        
        # Get currently serving patient (keep your existing logic)
        serving_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        # waiting patients query 
        waiting_patients = QueueEntry.objects.filter(
            counter=counter,
            current_status='waiting'
        ).order_by('created_at')
        
        # Keep your break counter logic
        handling_break_counter = None
        if counter.current_status == 'available':
            handling_break_counter = Counter.objects.filter(
                service=counter.service,
                current_status='break',
                counter_id__lt=counter.counter_id
            ).last()
        
        # Return combined response
        return JsonResponse({
            'status': 'success',
            'counter_status': counter.current_status,
            'serving_patient': {
                'queue_id': serving_patient.queue_id if serving_patient else None,
                'patient_name': serving_patient.patient.name if serving_patient else None,
                'announcement_count': serving_patient.announcement_count if serving_patient else 0
            },
            'waiting_patients': [
                {
                    'queue_id': p.queue_id,
                    'patient_name': p.patient.name,
                    'waiting_time': naturaltime(p.created_at),
                    # Added ID for frontend reference
                    'id': p.queue_id  
                } for p in waiting_patients
            ],
            'handling_break_counter': handling_break_counter.counter_name if handling_break_counter else None,
            # Added simple queue count
            'queue_count': waiting_patients.count()  
        })
        
    except Exception as e:
        print(f"Error in get_queue_data: {str(e)}")  # Added debug print
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@require_POST
def announce_patient(request):
    """Handle patient announcements"""
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        queue_id = request.POST.get('queue_id')
        patient = QueueEntry.objects.get(queue_id=queue_id)
        
        patient.announcement_count += 1
        patient.save()
        
        if patient.announcement_count >= 3:
            # Skip patient after 3 announcements
            QueueHistory.objects.create(
                queue_id=patient.queue_id,
                patient=patient.patient,
                service=patient.service,
                counter=patient.counter,
                status='skipped',
                skipped_at=timezone.now(),
                created_at=patient.created_at,
                completed_at=timezone.now(),
                date=timezone.now().date()
            )
            patient.delete()
            
            # Get next patient
            next_patient = QueueEntry.objects.filter(
                counter=patient.counter,
                current_status='waiting'
            ).order_by('created_at').first()
            
            if next_patient:
                next_patient.current_status = 'serving'
                next_patient.save()
                return JsonResponse({
                    'status': 'skipped',
                    'next_patient': {
                        'name': next_patient.patient.name,
                        'queue_id': next_patient.queue_id
                    }
                })
            
            return JsonResponse({'status': 'skipped', 'next_patient': None})
        
        return JsonResponse({
            'status': 'announced',
            'count': patient.announcement_count
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
def get_queue_status(request):
    if 'patient_phone' not in request.session:
        return JsonResponse({'status': 'error'}, status=401)
    
    patient = Patient.objects.get(phone_number=request.session['patient_phone'])
    queue_entry = QueueEntry.objects.filter(patient=patient).first()
    
    return JsonResponse({
        'queue_status': queue_entry.current_status if queue_entry else 'none',
        'position': get_position_in_queue(queue_entry) if queue_entry else None
    })