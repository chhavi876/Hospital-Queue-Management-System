# views.py - FIXED VERSION
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
import time 
from django.db.models import Count, Q
logger = logging.getLogger(__name__)
from functools import wraps
from django.http import JsonResponse

def validate_staff_session(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if 'staff_id' not in request.session:
            return JsonResponse({'status': 'error', 'message': 'Session expired'}, status=401)
        
        # Verify session matches database and has unique identifier
        if not request.session.get('session_unique'):
            request.session.flush()
            return JsonResponse({'status': 'error', 'message': 'Invalid session'}, status=401)
        
        # Verify staff exists
        try:
            staff = Staff.objects.get(staff_id=request.session['staff_id'])
            request.staff = staff
            
            # Verify this staff member is assigned to a counter
            try:
                counter = Counter.objects.get(staff=staff)
                request.counter = counter
            except Counter.DoesNotExist:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No counter assigned to staff'
                }, status=403)
                
        except Staff.DoesNotExist:
            request.session.flush()
            return JsonResponse({'status': 'error', 'message': 'Invalid session'}, status=401)
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view



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
        
        # Generate OTP
        otp = str(random.randint(100000, 999999))
        expires_at = timezone.now() + timedelta(minutes=5)
        
        # Store OTP in database
        OTP.objects.create(
            phone_number=phone_number,
            otp=otp,
            expires_at=expires_at
        )
        
        # Send OTP via SMS using TextLocal
        sms_sent = False
        try:
            from .utils import send_otp
            sms_sent = send_otp(phone_number, otp)
        except Exception as e:
            print(f"SMS sending error: {str(e)}")
            # Even if there's an error, the OTP is still generated and stored
        
        return JsonResponse({
            'status': 'success',
            'is_new_patient': is_new_patient,
            'sms_sent': sms_sent,
            'message': 'OTP sent successfully via SMS' if sms_sent else 'OTP generated but SMS failed. OTP is still valid.'
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
    
    available_services = Service.objects.filter(is_active=True)
    
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
    print("--- Starting join_queue function ---")
    if 'patient_phone' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    try:
        service_id = request.POST.get('service_id')
        if not service_id:
            return JsonResponse({'status': 'error', 'message': 'Service ID required'}, status=400)
        
        patient = Patient.objects.get(phone_number=request.session['patient_phone'])
        
        # Check if already in queue
        if QueueEntry.objects.filter(patient=patient, current_status__in=['waiting', 'serving']).exists():
            return JsonResponse({'status': 'error', 'message': 'You are already in queue'}, status=400)
        
        service = Service.objects.get(service_id=service_id, is_active=True)
        
        # FIXED: Remove is_active filter since Counter model doesn't have this field
        counter = Counter.objects.filter(
            service=service,
            current_status__in=['available', 'busy']  # Only available/busy counters
        ).annotate(
            waiting_count=Count('queueentry', filter=Q(queueentry__current_status='waiting'))
        ).order_by('waiting_count', 'counter_id').first()

        if not counter:
            return JsonResponse({'status': 'error', 'message': 'No counters available for this service'}, status=400)
        
        print(f"DEBUG: Selected counter: {counter.counter_name} with {getattr(counter, 'waiting_count', 0)} waiting patients")
        
        # Generate unique queue ID
        queue_id = f"{service.service_name[:3].upper()}_{counter.counter_id}_{random.randint(1000, 9999)}"
        
        # Create queue entry
        QueueEntry.objects.create(
            queue_id=queue_id,
            patient=patient,
            service=service,
            counter=counter,
            current_status='waiting'
        )
        
        # Update counter status if it was available
        if counter.current_status == 'available':
            counter.current_status = 'busy'
            counter.save()
            print(f"DEBUG: Updated counter {counter.counter_name} status to 'busy'")
        
        # Send WebSocket notification
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "staff_updates",
                {
                    "type": "send_update",
                    "message": {
                        "action": "new_patient",
                        "queue_id": queue_id,
                        "patient_name": patient.name,
                        "service_name": service.service_name,
                        "counter_name": counter.counter_name,
                        "timestamp": str(timezone.now())
                    }
                }
            )
        except Exception as ws_error:
            print(f"WebSocket error: {ws_error}")
        
        return JsonResponse({
            'status': 'success',
            'queue_id': queue_id,
            'message': 'Added to queue successfully'
        })
        
    except Exception as e:
        print(f"join_queue error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
       
def calculate_wait_time():
    """Calculate average wait time based on queue length"""
    from django.db.models import Avg
    from datetime import timedelta
    avg_wait = QueueHistory.objects.filter(
        completed_at__gte=timezone.now()-timedelta(hours=1)
    ).aggregate(Avg('completed_at'-'created_at'))['created_at__avg']
    return avg_wait.total_seconds() / 60 if avg_wait else 5  # Default 5 minutes


from django.contrib.auth.hashers import check_password


@csrf_exempt
def staff_login(request):
    # If already logged in and accessing login page, offer logout
    if request.method == 'GET' and 'staff_id' in request.session:
        # Check if this is a different tab trying to login
        tab_id = request.GET.get('tab_id') or request.session.get('tab_id')
        if tab_id:
            tab_key = f"tab_{tab_id}_staff"
            if tab_key in request.session:
                # This tab already has a staff session
                return render(request, 'staff_login.html', {
                    'error': 'Already logged in. Please use a new browser tab or logout first.',
                    'show_logout': True
                })
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            staff = Staff.objects.get(username=username)
            if check_password(password, staff.password):
                # COMPLETELY CREATE NEW SESSION - This is the fix
                old_session_key = None
                if request.session.session_key:
                    old_session_key = request.session.session_key
                
                # Create completely new session by flushing and creating
                request.session.flush()
                request.session.create()
                
                # Set new session data
                request.session['staff_id'] = staff.staff_id
                request.session['staff_role'] = staff.role
                request.session['session_created'] = timezone.now().isoformat()
                request.session['session_unique'] = str(uuid.uuid4())
                
                # Set tab-specific data
                tab_id = request.GET.get('tab_id') or f"tab_{int(time.time())}_{random.randint(1000, 9999)}"
                request.session['tab_id'] = tab_id
                tab_key = f"tab_{tab_id}_staff"
                request.session[tab_key] = {
                    'staff_id': staff.staff_id,
                    'session_unique': request.session['session_unique']
                }
                
                # Delete the old session from database if it exists
                if old_session_key:
                    from django.contrib.sessions.models import Session
                    try:
                        Session.objects.filter(session_key=old_session_key).delete()
                    except:
                        pass
                
                print(f"LOGIN DEBUG: New Session Key: {request.session.session_key}")
                print(f"LOGIN DEBUG: Staff ID: {staff.staff_id}, Username: {staff.username}")
                print(f"LOGIN DEBUG: Tab ID: {tab_id}")
                
                return redirect('staff_dashboard')
            else:
                return render(request, 'staff_login.html', {'error': 'Invalid password'})
        except Staff.DoesNotExist:
            return render(request, 'staff_login.html', {'error': 'Invalid username'})
    
    return render(request, 'staff_login.html')

from django.shortcuts import render
from django.http import JsonResponse
from .models import Counter, QueueEntry, Staff

@validate_staff_session
def staff_dashboard(request):
    try:
        staff = request.staff
        counter = Counter.objects.get(staff=staff)
        
        # DEBUG: Print session information
        print(f"SESSION DEBUG: Session Key: {request.session.session_key}")
        print(f"SESSION DEBUG: Staff ID in session: {request.session.get('staff_id')}")
        print(f"SESSION DEBUG: Session Unique: {request.session.get('session_unique')}")
        print(f"SESSION DEBUG: Actual staff: {staff.staff_id}, Counter: {counter.counter_name}")
        
        # Only show patients assigned to THIS specific counter
        queue_entries = QueueEntry.objects.filter(
            counter=counter,
            current_status='waiting'
        ).order_by('created_at')
        
        # Only show patient being served by THIS counter
        serving_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        return render(request, 'staff_dashboard.html', {
            'staff': staff,
            'counter': counter,
            'queue_entries': queue_entries,
            'serving_patient': serving_patient,
            'session_unique': request.session.get('session_unique', 'none')
        })
        
    except Staff.DoesNotExist:
        request.session.flush()
        return redirect('staff_login')
    except Counter.DoesNotExist:
        return render(request, 'staff_dashboard.html', {
            'error': 'No counter assigned to this staff member. Please contact administrator.'
        })

def staff_logout(request):
    """Properly logout staff by clearing session"""
    tab_id = request.GET.get('tab_id') or request.session.get('tab_id')
    
    if tab_id:
        # Clear tab-specific data
        tab_key = f"tab_{tab_id}_staff"
        if tab_key in request.session:
            del request.session[tab_key]
    
    # Clear the entire session
    request.session.flush()
    return redirect('staff_login')

@validate_staff_session
@csrf_exempt
def serve_next(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = request.staff
        counter = Counter.objects.get(staff=staff)
        
        # Complete current serving patient if exists - FIXED: Only from THIS counter
        current_serving = QueueEntry.objects.filter(
            counter=counter,  # FIXED: Only THIS counter
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
        
        # FIXED: Get next patient assigned to THIS counter only
        next_patient = QueueEntry.objects.filter(
            counter=counter,  # FIXED: Only THIS counter's patients
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

@validate_staff_session
@csrf_exempt
@require_POST
def update_counter_status(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = request.staff
        counter = Counter.objects.get(staff=staff)

        new_status = request.POST.get('status')
        print(f"Update status request for counter {counter.counter_name}: {new_status}")
        
        if new_status not in ['available', 'busy', 'break']:
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid status. Use: available, busy, or break'
            }, status=400)
        
        # FIXED: If going on break, redistribute patients from THIS counter only
        if new_status == 'break':
            redistribute_patients_on_break(counter)  # Pass the specific counter
        
        # FIXED: Update only THIS counter's status
        counter.current_status = new_status
        counter.save()
        
        print(f"Counter {counter.counter_id} status updated to {new_status}")
        return JsonResponse({'status': 'success', 'message': 'Status updated'})
        
    except Staff.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Staff not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@validate_staff_session
@csrf_exempt
@require_POST
def skip_patient(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    try:
        # FIXED: Handle both JSON and form data
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            queue_id = data.get('queue_id')
        else:
            queue_id = request.POST.get('queue_id')
        
        if not queue_id:
            return JsonResponse({'status': 'error', 'message': 'Queue ID required'}, status=400)
        
        staff = request.staff  # Use staff from decorator
        counter = Counter.objects.get(staff=staff)
        
        # FIXED: Only skip patients being served by THIS counter
        current_serving = QueueEntry.objects.filter(
            counter=counter,  # FIXED: Only THIS counter
            current_status='serving',
            queue_id=queue_id
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
            
            # FIXED: Get next patient from THIS counter only
            next_patient = QueueEntry.objects.filter(
                counter=counter,  # FIXED: Only THIS counter
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
            return JsonResponse({'status': 'error', 'message': 'No matching patient being served'})
            
    except Exception as e:
        print(f"skip_patient error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def display_screen(request):
    """Display screen showing all counters in tabular format"""
    counters = Counter.objects.filter(is_active=True).order_by('counter_id')
    
    # Get currently serving patients for each counter
    serving_data = {}
    for counter in counters:
        serving_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).select_related('patient').first()
        
        if serving_patient:
            serving_data[counter.counter_id] = {
                'queue_id': serving_patient.queue_id,
                'patient_name': serving_patient.patient.name,
                'service_name': serving_patient.service.service_name,
                'announcement_count': serving_patient.announcement_count
            }
    
    return render(request, 'display_screen.html', {
        'counters': counters,
        'serving_data': serving_data,
        'current_time': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@csrf_exempt
def display_screen_data(request):
    """API endpoint for display screen data"""
    counters = Counter.objects.filter(is_active=True).order_by('counter_id')
    
    counter_data = []
    for counter in counters:
        serving_patient = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).select_related('patient', 'service').first()
        
        counter_data.append({
            'counter_id': counter.counter_id,
            'counter_name': counter.counter_name,
            'service_name': counter.service.service_name,
            'current_status': counter.current_status,
            'serving_patient': {
                'queue_id': serving_patient.queue_id,
                'patient_name': serving_patient.patient.name,
                'service_name': serving_patient.service.service_name,
                'announcement_count': serving_patient.announcement_count
            } if serving_patient else None
        })
    
    return JsonResponse({
        'counters': counter_data,
        'timestamp': timezone.now().isoformat()
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

@validate_staff_session
@csrf_exempt
def get_queue_data(request):
    """FIXED: AJAX endpoint for queue updates - Only show data for THIS staff's counter"""
    try:
        # Use request.staff from the decorator
        staff = request.staff
        
        # FIXED: Get counter using the reverse relationship
        # The Counter model has a OneToOneField to Staff, so we query Counter
        counter = Counter.objects.get(staff=staff)
        
        print(f"DEBUG: Staff {staff.username}, Counter {counter.counter_name}, Service: {counter.service.service_name}")
        
        # FIXED: Get currently serving patient for THIS counter ONLY
        serving_patient = QueueEntry.objects.filter(
            counter=counter,  # Only THIS counter
            current_status='serving'
        ).first()
        
        # FIXED: Get waiting patients assigned to THIS counter only
        waiting_patients = QueueEntry.objects.filter(
            counter=counter,  # Only THIS counter's patients
            current_status='waiting'
        ).select_related('patient', 'service').order_by('created_at')
        
        print(f"DEBUG: Found {waiting_patients.count()} waiting patients for counter {counter.counter_name}")
        
        response_data = {
            'status': 'success',
            'counter_status': counter.current_status,
            'counter_name': counter.counter_name,
            'service_name': counter.service.service_name,
            'serving_patient': None,
            'waiting_patients': [],
            'queue_count': waiting_patients.count()
        }
        
        # Add waiting patients data
        for patient in waiting_patients:
            response_data['waiting_patients'].append({
                'queue_id': patient.queue_id,
                'name': patient.patient.name,
                'waiting_time': naturaltime(patient.created_at),
                'counter_name': patient.counter.counter_name,
                'service_name': patient.service.service_name,
                'is_my_counter': True,  # All patients shown are from this counter
            })
        
        # Add serving patient if exists
        if serving_patient:
            response_data['serving_patient'] = {
                'queue_id': serving_patient.queue_id,
                'name': serving_patient.patient.name,
                'phone': serving_patient.patient.phone_number,
                'announcement_count': serving_patient.announcement_count,
                'service_name': serving_patient.service.service_name
            }
        
        return JsonResponse(response_data)
        
    except Counter.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No counter assigned to staff'}, status=404)
    except Exception as e:
        print(f"Error in get_queue_data: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@csrf_exempt
def start_serving(request):
    """FIXED: Start serving the next patient assigned to THIS counter"""
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = request.staff  # Use staff from decorator
        counter = Counter.objects.get(staff=staff)
        
        # Check if already serving someone
        currently_serving = QueueEntry.objects.filter(
            counter=counter,
            current_status='serving'
        ).first()
        
        if currently_serving:
            return JsonResponse({
                'status': 'error', 
                'message': 'Already serving a patient'
            })
        
        # FIXED: Get next patient assigned to THIS counter only
        next_patient = QueueEntry.objects.filter(
            counter=counter,  # FIXED: Only THIS counter's patients
            current_status='waiting'
        ).order_by('created_at').first()
        
        if next_patient:
            # Mark as serving
            next_patient.current_status = 'serving'
            next_patient.save()
            
            # Update counter status
            counter.current_status = 'busy'
            counter.save()
            
            print(f"DEBUG: Started serving {next_patient.patient.name} ({next_patient.queue_id})")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Started serving patient',
                'patient': {
                    'name': next_patient.patient.name,
                    'queue_id': next_patient.queue_id
                }
            })
        else:
            return JsonResponse({
                'status': 'empty',
                'message': 'No patients waiting'
            })
            
    except Exception as e:
        print(f"start_serving error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@validate_staff_session
@csrf_exempt
def announce_patient(request):
    """Handle patient announcements and trigger display updates"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    try:
        queue_id = request.POST.get('queue_id')
        if not queue_id:
            return JsonResponse({'status': 'error', 'message': 'Queue ID required'}, status=400)
        
        staff = request.staff
        counter = Counter.objects.get(staff=staff)
        
        patient = QueueEntry.objects.filter(
            queue_id=queue_id,
            counter=counter,
            current_status='serving'
        ).first()
        
        if not patient:
            return JsonResponse({'status': 'error', 'message': 'Patient not found'}, status=404)
        
        patient.announcement_count += 1
        patient.save()
        
        # Send WebSocket update to refresh display screens
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "display_updates",
                {
                    "type": "display_update",
                    "message": {
                        "action": "announcement",
                        "counter_id": counter.counter_id,
                        "queue_id": patient.queue_id,
                        "patient_name": patient.patient.name,
                        "announcement_count": patient.announcement_count
                    }
                }
            )
        except Exception as e:
            print(f"WebSocket error: {e}")
        
        if patient.announcement_count >= 3:
            # Skip patient after 3 announcements
            QueueHistory.objects.create(
                queue_id=patient.queue_id,
                patient=patient.patient,
                service=patient.service,
                counter=patient.counter,
                current_status='skipped',
                skipped_at=timezone.now(),
                created_at=patient.created_at,
                updated_at=timezone.now(),
                date=timezone.now().date(),
                completed_at=timezone.now()
            )
            patient.delete()
            
            # Get next patient
            next_patient = QueueEntry.objects.filter(
                counter=counter,
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
            else:
                counter.current_status = 'available'
                counter.save()
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
        'position': None  # Temporarily disable until function is fixed
    })

def get_position_in_queue(queue_entry):
    """Calculate patient's position in the queue"""
    if not queue_entry or queue_entry.current_status != 'waiting':
        return None
    
    # Count how many patients are ahead in the same counter
    ahead_count = QueueEntry.objects.filter(
        counter=queue_entry.counter,
        current_status='waiting',
        created_at__lt=queue_entry.created_at
    ).count()
    
    return ahead_count + 1  # +1 because position starts from 1

@csrf_exempt
@require_POST
def handle_counter_break(request):
    """When a counter goes on break, redistribute its patients"""
    if 'staff_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        breaking_counter = staff.counter
        
        redistributed_count = redistribute_patients_on_break(breaking_counter)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Redistributed {redistributed_count} patients',
            'redistributed_count': redistributed_count
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
def redistribute_patients_on_break(breaking_counter):
    """
    FIXED: Redistribute patients from a counter going on break to other counters
    in the SAME SERVICE only
    """
    print(f"DEBUG: Redistributing patients from {breaking_counter.counter_name} ({breaking_counter.service.service_name})")
    
    # Get all waiting patients from the breaking counter
    waiting_patients = QueueEntry.objects.filter(
        counter=breaking_counter,
        current_status='waiting'
    )
    
    redistributed_count = 0
    
    for patient_entry in waiting_patients:
        # FIXED: Remove is_active filter since Counter model doesn't have this field
        alternative_counter = Counter.objects.filter(
            service=breaking_counter.service,  # Same service only
            current_status__in=['available', 'busy']  # Only available/busy counters
        ).exclude(counter_id=breaking_counter.counter_id).annotate(
            waiting_count=Count('queueentry', filter=Q(queueentry__current_status='waiting'))
        ).order_by('waiting_count', 'counter_id').first()
        
        if alternative_counter:
            print(f"DEBUG: Moving {patient_entry.patient.name} from {breaking_counter.counter_name} to {alternative_counter.counter_name}")
            
            # Update the patient's counter
            patient_entry.counter = alternative_counter
            patient_entry.save()
            redistributed_count += 1
            
            # Send WebSocket update
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "staff_updates",
                    {
                        "type": "send_update",
                        "message": {
                            "action": "patient_redistributed",
                            "queue_id": patient_entry.queue_id,
                            "old_counter": breaking_counter.counter_name,
                            "new_counter": alternative_counter.counter_name,
                            "patient_name": patient_entry.patient.name,
                            "service_name": breaking_counter.service.service_name
                        }
                    }
                )
            except Exception as e:
                print(f"DEBUG: WebSocket error during redistribution: {e}")
    
    print(f"DEBUG: Redistributed {redistributed_count} patients from {breaking_counter.counter_name}")
    return redistributed_count

# Add to views.py
@csrf_exempt
def debug_counters(request):
    """Debug endpoint to check all counters and their assignments"""
    counters = Counter.objects.all().select_related('service', 'staff')
    counter_data = []
    
    for counter in counters:
        counter_data.append({
            'id': counter.counter_id,
            'name': counter.counter_name,
            'service': counter.service.service_name if counter.service else 'None',
            'status': counter.current_status,
            'staff': counter.staff.username if counter.staff else 'None',
            'staff_id': counter.staff.staff_id if counter.staff else 'None',
            'waiting_patients': QueueEntry.objects.filter(counter=counter, current_status='waiting').count()
        })
    
    # Check session staff
    session_staff_id = request.session.get('staff_id')
    current_staff = None
    current_counter = None
    
    if session_staff_id:
        try:
            current_staff = Staff.objects.get(staff_id=session_staff_id)
            current_counter = Counter.objects.filter(staff=current_staff).first()
        except (Staff.DoesNotExist, Counter.DoesNotExist):
            pass
    
    return JsonResponse({
        'counters': counter_data,
        'session': {
            'staff_id': session_staff_id,
            'current_staff': current_staff.username if current_staff else 'None',
            'current_counter': current_counter.counter_name if current_counter else 'None'
        }
    })

@csrf_exempt
def debug_session(request):
    if 'staff_id' not in request.session:
        return JsonResponse({'error': 'No session'})
    
    try:
        staff = Staff.objects.get(staff_id=request.session['staff_id'])
        counter = Counter.objects.get(staff=staff)
        return JsonResponse({
            'staff': f"{staff.username} (ID: {staff.staff_id})",
            'counter': f"{counter.counter_name} (Service: {counter.service.service_name})",
            'session_key': request.session.session_key,
            'session_staff_id': request.session.get('staff_id')
        })
    except (Staff.DoesNotExist, Counter.DoesNotExist):
        return JsonResponse({'error': 'Invalid session data'})
    
@csrf_exempt
def debug_staff_counters(request):
    """Debug endpoint to check staff-counter relationships"""
    staff_with_counters = Staff.objects.filter(counter__isnull=False).select_related('counter')
    staff_data = []
    
    for staff in staff_with_counters:
        staff_data.append({
            'staff_id': staff.staff_id,
            'username': staff.username,
            'counter_id': staff.counter.counter_id if staff.counter else None,
            'counter_name': staff.counter.counter_name if staff.counter else None,
            'service': staff.counter.service.service_name if staff.counter else None
        })
    
    return JsonResponse({'staff_counters': staff_data})
