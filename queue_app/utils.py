# queue_app/utils.py
import random
from datetime import datetime, timedelta
from django.conf import settings
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

def send_otp(phone_number, otp):
    """
    Send OTP via SMS using Twilio
    Replace mock function with actual SMS service
    """
    try:
        # Check if Twilio is configured
        if not all([hasattr(settings, 'TWILIO_ACCOUNT_SID'), 
                   hasattr(settings, 'TWILIO_AUTH_TOKEN'),
                   hasattr(settings, 'TWILIO_PHONE_NUMBER')]):
            logger.warning("Twilio not configured. Using mock OTP sender.")
            return mock_send_otp(phone_number, otp)
        
        # Initialize Twilio client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Format phone number (add country code if missing)
        formatted_number = format_phone_number(phone_number)
        
        # Create and send message
        message = client.messages.create(
            body=f'Your OTP for queue system is: {otp}. This OTP is valid for 5 minutes.',
            from_=settings.TWILIO_PHONE_NUMBER,
            to=formatted_number
        )
        
        logger.info(f"OTP SMS sent to {formatted_number}. Message SID: {message.sid}")
        return True
        
    except TwilioRestException as e:
        logger.error(f"Twilio error sending OTP to {phone_number}: {str(e)}")
        # Fallback to mock for development
        return mock_send_otp(phone_number, otp)
    except Exception as e:
        logger.error(f"Unexpected error sending OTP to {phone_number}: {str(e)}")
        return mock_send_otp(phone_number, otp)

def mock_send_otp(phone_number, otp):
    """
    Mock OTP sender for development when SMS is not configured
    """
    print(f"\n--- Mock OTP (Development) ---\nTo: {phone_number}\nOTP: {otp}\nValid for 5 minutes\n")
    logger.info(f"Mock OTP sent to {phone_number}: {otp}")
    return True

def format_phone_number(phone_number):
    """
    Format phone number for international dialing
    """
    # Remove any non-digit characters
    cleaned_number = ''.join(filter(str.isdigit, phone_number))
    
    # Add country code if missing (assuming +91 for India)
    if not cleaned_number.startswith('+'):
        if cleaned_number.startswith('0'):
            cleaned_number = cleaned_number[1:]  # Remove leading 0
        
        if len(cleaned_number) == 10:  # Indian mobile numbers
            cleaned_number = '+91' + cleaned_number
        else:
            # For other formats, just ensure it starts with +
            cleaned_number = '+' + cleaned_number
    
    return cleaned_number

def generate_queue_id(service, counter=None):
    import string
    prefix = service.service_name[:3].upper()
    counter_num = str(counter.counter_id).zfill(3) if counter else "000"
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{prefix}_{counter_num}_{random_part}"

def is_twilio_configured():
    """
    Check if Twilio is properly configured
    """
    return all([
        hasattr(settings, 'TWILIO_ACCOUNT_SID'),
        hasattr(settings, 'TWILIO_AUTH_TOKEN'), 
        hasattr(settings, 'TWILIO_PHONE_NUMBER'),
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
        settings.TWILIO_PHONE_NUMBER
    ])
