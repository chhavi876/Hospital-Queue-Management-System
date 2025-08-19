from django.db import models

# Create your models here.
# models.py
from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator

class Service(models.Model):
    WEEKDAY_CHOICES = [
        (1, 'Monday'),
        (2, 'Tuesday'),
        (3, 'Wednesday'),
        (4, 'Thursday'),
        (5, 'Friday'),
        (6, 'Saturday'),
        (7, 'Sunday'),
    ]
    
    service_id = models.AutoField(primary_key=True)
    service_name = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    week_days = models.IntegerField(choices=WEEKDAY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.service_name

class Counter(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('break', 'On Break'),
        ('closed', 'Closed'),
    ]
    
    counter_id = models.AutoField(primary_key=True)
    counter_name = models.CharField(max_length=50)
    current_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='available')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    status_updated_at = models.DateTimeField(auto_now=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    staff = models.OneToOneField(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='counter'
    )

    def __str__(self):
        return f"{self.counter_name} - {self.service.service_name}"

class Patient(models.Model):
    phone_number = models.CharField(max_length=10, primary_key=True, validators=[MinLengthValidator(10)])
    name = models.CharField(max_length=100)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.phone_number})"
    

class Staff(models.Model):
    ROLE_CHOICES = [
        ('operator', 'Operator'),
        ('supervisor', 'Supervisor'),
        ('admin', 'Admin'),
    ]
    
    staff_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=20, unique=True)
    password = models.CharField(max_length=128)  # Will be hashed
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-hash password when saving
        if not self.password.startswith('pbkdf2_sha256$'):  # Check if already hashed
            self.password = make_password(self.password)
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.username} ({self.role})"

class OTP(models.Model):
    phone_number = models.CharField(max_length=10)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"OTP for {self.phone_number}"

class QueueEntry(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('serving', 'Serving'),
        ('skipped', 'Skipped'),
        ('completed', 'Completed'),
    ]
    
    queue_id = models.CharField(max_length=50, primary_key=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    counter = models.ForeignKey(Counter, on_delete=models.CASCADE, null=True, blank=True)
    current_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    skipped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    announcement_count = models.IntegerField(default=0) 
    def __str__(self):
        return self.queue_id

class QueueHistory(models.Model):
    STATUS_CHOICES = [
        ('served', 'Served'),
        ('skipped', 'Skipped'),
    ]
    
    queue_id = models.CharField(max_length=10)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    counter = models.ForeignKey(Counter, on_delete=models.CASCADE)
    current_status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    skipped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    date = models.DateField()
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.queue_id} - {self.current_status}"