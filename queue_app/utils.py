# queue_app/utils.py
import random
from datetime import datetime, timedelta
from .models import OTP

def send_otp(phone_number, otp):
    """
    Mock OTP sender - replace with actual SMS service in production
    """
    print(f"\n--- Mock OTP ---\nTo: {phone_number}\nOTP: {otp}\nValid for 5 minutes\n")
    return True

def generate_queue_id(service, counter=None):
    import string
    prefix = service.service_name[:3].upper()
    counter_num = str(counter.counter_id).zfill(3) if counter else "000"
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{prefix}_{counter_num}_{random_part}"