# from django.contrib.auth.models import AbstractUser
# from django.db import models
# from django.utils import timezone
# from datetime import datetime
# from .managers import CustomUserManager

# class CustomUser(AbstractUser):
#     """Extended User model with additional fields"""
    
#     ROLE_CHOICES = [
#         ('user', 'User'),  # Default role for new registrations
#         ('writer', 'Writer'),
#         ('process', 'Process Team'),
#         ('marketing', 'Marketing'),
#         ('allocator', 'Allocator'),
#         ('admin', 'Admin'),
#         ('superadmin', 'Super Admin'),
#     ]
    
#     APPROVAL_STATUS = [
#         ('pending', 'Pending'),
#         ('approved', 'Approved'),
#         ('rejected', 'Rejected'),
#     ]
#     objects = CustomUserManager()
#     # Basic Information
#     email = models.EmailField(unique=True)
#     whatsapp_number = models.CharField(max_length=10, blank=True, null=True)
#     phone = models.CharField(max_length=15, blank=True, null=True)
    
#     # Role and Department
#     role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
#     department = models.CharField(max_length=50, blank=True, null=True)
    
#     # Approval Status
#     is_approved = models.BooleanField(default=False)
#     approval_status = models.CharField(
#         max_length=20, 
#         choices=APPROVAL_STATUS, 
#         default='pending'
#     )
#     approved_by = models.ForeignKey(
#         'self', 
#         on_delete=models.SET_NULL, 
#         null=True, 
#         blank=True,
#         related_name='approved_users'
#     )
#     approved_at = models.DateTimeField(null=True, blank=True)
    
#     # Employee Information
#     employee_id = models.CharField(max_length=20, null=True, blank=True)
#     date_joined = models.DateTimeField(default=timezone.now)
#     first_login_date = models.DateTimeField(null=True, blank=True)
    
#     # Profile
#     profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    
#     # Metadata
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
    
#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
#     class Meta:
#         db_table = 'custom_users'
#         verbose_name = 'User'
#         verbose_name_plural = 'Users'
    
#     def __str__(self):
#         return f"{self.get_full_name()} ({self.email})"
    
#     def generate_employee_id(self):
#         """
#         Generate Employee ID: ASLNOM24
#         Format: FirstInitial + LastInitial + Month(3chars) + YY + SerialNo
#         Example: Arnab Mondal joined in November 2024 -> AMNOV24001
#         """
#         if not self.first_login_date:
#             self.first_login_date = timezone.now()
#             self.save()
        
#         first_initial = self.first_name[0].upper() if self.first_name else 'X'
#         last_initial = self.last_name[0].upper() if self.last_name else 'X'
        
#         # Get month (3 chars) and year (2 digits)
#         month = self.first_login_date.strftime('%b').upper()[:3]
#         year = self.first_login_date.strftime('%y')
        
#         # Get serial number for that month/year combination
#         prefix = f"{first_initial}{last_initial}{month}{year}"
        
#         # Count existing employees with same prefix
#         count = CustomUser.objects.filter(
#             employee_id__startswith=prefix
#         ).count()
        
#         serial = str(count + 1).zfill(3)  # 001, 002, etc.
        
#         return f"{prefix}{serial}"
    
#     def approve_user(self, approved_by_user):
#         """Approve user and generate employee ID"""
#         self.is_approved = True
#         self.approval_status = 'approved'
#         self.approved_by = approved_by_user
#         self.approved_at = timezone.now()
#         self.save()
    
#     def reject_user(self, rejected_by_user):
#         """Reject user registration"""
#         self.approval_status = 'rejected'
#         self.approved_by = rejected_by_user
#         self.approved_at = timezone.now()
#         self.save()


# class LoginLog(models.Model):
#     """Track user login and logout activities"""
    
#     user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='login_logs')
#     employee_id = models.CharField(max_length=20, blank=True, null=True)
    
#     # Login Information
#     login_time = models.DateTimeField(auto_now_add=True)
#     logout_time = models.DateTimeField(null=True, blank=True)
    
#     # Session Information
#     session_key = models.CharField(max_length=40, blank=True, null=True)
#     ip_address = models.GenericIPAddressField(null=True, blank=True)
#     user_agent = models.TextField(blank=True, null=True)
    
#     # Device Information
#     device_type = models.CharField(max_length=50, blank=True, null=True)
#     browser = models.CharField(max_length=50, blank=True, null=True)
#     os = models.CharField(max_length=50, blank=True, null=True)
    
#     # Status
#     is_active = models.BooleanField(default=True)
    
#     class Meta:
#         db_table = 'login_logs'
#         ordering = ['-login_time']
#         verbose_name = 'Login Log'
#         verbose_name_plural = 'Login Logs'
    
#     def __str__(self):
#         return f"{self.user.email} - {self.login_time.strftime('%Y-%m-%d %H:%M:%S')}"
    
#     def get_session_duration(self):
#         """Calculate session duration"""
#         if self.logout_time:
#             duration = self.logout_time - self.login_time
#             hours, remainder = divmod(duration.total_seconds(), 3600)
#             minutes, seconds = divmod(remainder, 60)
#             return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
#         return "Active"
    
#     def mark_logout(self):
#         """Mark the session as logged out"""
#         self.logout_time = timezone.now()
#         self.is_active = False
#         self.save()


# class UserSession(models.Model):
#     """Track active user sessions"""
    
#     user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sessions')
#     session_key = models.CharField(max_length=40, unique=True)
    
#     # Session Details
#     created_at = models.DateTimeField(auto_now_add=True)
#     last_activity = models.DateTimeField(auto_now=True)
#     expires_at = models.DateTimeField()
    
#     # Security
#     ip_address = models.GenericIPAddressField()
#     user_agent = models.TextField()
    
#     # Status
#     is_active = models.BooleanField(default=True)
    
#     class Meta:
#         db_table = 'user_sessions'
#         ordering = ['-created_at']
    
#     def __str__(self):
#         return f"{self.user.email} - {self.session_key[:10]}..."
    
#     def is_expired(self):
#         """Check if session is expired"""
#         return timezone.now() > self.expires_at


# class PasswordResetToken(models.Model):
#     """Secure password reset tokens"""
    
#     user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
#     token = models.CharField(max_length=100, unique=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     expires_at = models.DateTimeField()
#     is_used = models.BooleanField(default=False)
    
#     class Meta:
#         db_table = 'password_reset_tokens'
    
#     def is_valid(self):
#         """Check if token is valid and not expired"""
#         return not self.is_used and timezone.now() < self.expires_at

# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random
import string
from .managers import CustomUserManager


class CustomUser(AbstractUser):
    """Extended User Model"""

    ROLE_CHOICES = [
        ('user', 'User'),
        ('writer', 'Writer'),
        ('process', 'Process Team'),
        ('marketing', 'Marketing'),
        ('allocator', 'Allocator'),
        ('admin', 'Admin'),
        ('superadmin', 'Super Admin'),
    ]

    APPROVAL_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    objects = CustomUserManager()

    # Basic Information
    email = models.EmailField(unique=True)
    whatsapp_number = models.CharField(max_length=15, default="")   # USER INPUT
    phone = models.CharField(max_length=15, blank=True, null=True)  # FILLED AUTOMATICALLY

    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)

    # Role and Department
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    level = models.PositiveSmallIntegerField(default=0)
    department = models.CharField(max_length=50, blank=True, null=True)

    # Approval Status
    is_approved = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='pending')
    approved_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_users'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Employee Information
    employee_id = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    date_joined = models.DateTimeField(default=timezone.now)
    first_login_date = models.DateTimeField(null=True, blank=True)

    # Lifecycle Tracking
    registered_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    approval_requested_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    first_successful_login_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    email_change_requested_at = models.DateTimeField(null=True, blank=True)
    email_change_approved_at = models.DateTimeField(null=True, blank=True)
    profile_updated_at = models.DateTimeField(null=True, blank=True)
    role_assigned_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    employee_id_generated_at = models.DateTimeField(null=True, blank=True)
    employee_id_assigned_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'custom_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    # ---------- EMPLOYEE ID GENERATOR ----------
    def generate_employee_id(self):
        # Format: EMP + PREFIX + random 6 digits
        prefix = {
            'superadmin': 'SA',
            'admin': 'AD',
            'marketing': 'MK',
            'allocator': 'AL',
            'writer': 'WR',
            'process': 'PR',
            'user': 'US',
        }.get(self.role, 'US')

        while True:
            random_digits = ''.join(random.choices(string.digits, k=6))
            emp_id = f"EMP{prefix}{random_digits}"

            if not CustomUser.objects.filter(employee_id=emp_id).exists():
                return emp_id

    # ---------- AUTO-FILL PHONE FROM WHATSAPP ----------
    def save(self, *args, **kwargs):
        if self.whatsapp_number and not self.phone:
            self.phone = self.whatsapp_number

        # Auto-assign employee ID if approved & missing
        if self.is_approved and not self.employee_id:
            self.employee_id = self.generate_employee_id()

        super().save(*args, **kwargs)

    # ---------- APPROVAL FUNCTIONS ----------
    def approve_user(self, approved_by_user):
        self.is_approved = True
        self.approval_status = 'approved'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save()

    def reject_user(self, rejected_by_user):
        self.approval_status = 'rejected'
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.save()


# --------------------------------------------------
# LOGIN LOG MODEL
# --------------------------------------------------

class LoginLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='login_logs')
    employee_id = models.CharField(max_length=20, blank=True, null=True)

    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)

    session_key = models.CharField(max_length=255, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)

    device_type = models.CharField(max_length=50, blank=True, null=True)
    browser = models.CharField(max_length=50, blank=True, null=True)
    os = models.CharField(max_length=50, blank=True, null=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'login_logs'
        ordering = ['-login_time']
        verbose_name = 'Login Log'
        verbose_name_plural = 'Login Logs'

    def __str__(self):
        return f"{self.user.email} - {self.login_time}"

    def mark_logout(self):
        self.logout_time = timezone.now()
        self.is_active = False
        self.save()


# --------------------------------------------------
# USER SESSION MODEL
# --------------------------------------------------

class UserSession(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=255, unique=True)

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()

    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_sessions'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.session_key[:12]}"

    def is_expired(self):
        return timezone.now() > self.expires_at


# --------------------------------------------------
# PASSWORD RESET TOKEN MODEL
# --------------------------------------------------

class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_tokens'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class ActivityLog(models.Model):
    """Stores lifecycle and superadmin actions in MongoDB."""

    CATEGORY_USER = 'user_lifecycle'
    CATEGORY_SUPERADMIN = 'superadmin'
    CATEGORY_EMPLOYEE = 'employee_id'
    CATEGORY_GENERAL = 'general'

    CATEGORY_CHOICES = [
        (CATEGORY_USER, 'User Lifecycle'),
        (CATEGORY_SUPERADMIN, 'Superadmin / Manage Users'),
        (CATEGORY_EMPLOYEE, 'Employee ID'),
        (CATEGORY_GENERAL, 'General'),
    ]

    event_key = models.CharField(max_length=64, db_index=True)
    category = models.CharField(
        max_length=32,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
        db_index=True,
    )
    subject_user = models.ForeignKey(
        CustomUser,
        related_name='subject_activity_logs',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    performed_by = models.ForeignKey(
        CustomUser,
        related_name='performed_activity_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activity_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_key} - {self.created_at:%Y-%m-%d %H:%M:%S}"



class ActivityLog(models.Model):
    """Stores lifecycle and all system actions."""
    
    # Categories
    CATEGORY_USER = 'user_lifecycle'
    CATEGORY_SUPERADMIN = 'superadmin'
    CATEGORY_EMPLOYEE = 'employee_id'
    CATEGORY_HOLIDAY = 'holiday_master'
    CATEGORY_JOB = 'job_management'  # NEW CATEGORY
    CATEGORY_GENERAL = 'general'
    
    CATEGORY_CHOICES = [
        (CATEGORY_USER, 'User Lifecycle'),
        (CATEGORY_SUPERADMIN, 'Superadmin / Manage Users'),
        (CATEGORY_EMPLOYEE, 'Employee ID'),
        (CATEGORY_HOLIDAY, 'Holiday Master'),
        (CATEGORY_JOB, 'Job Management'),  # NEW CATEGORY
        (CATEGORY_GENERAL, 'General'),
    ]
    
    event_key = models.CharField(max_length=64, db_index=True)
    category = models.CharField(
        max_length=32,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
        db_index=True,
    )
    subject_user = models.ForeignKey(
        CustomUser,
        related_name='subject_activity_logs',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    performed_by = models.ForeignKey(
        CustomUser,
        related_name='performed_activity_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'activity_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_key']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.event_key} - {self.created_at:%Y-%m-%d %H:%M:%S}"


# Job-specific event keys for ActivityLog
JOB_EVENT_KEYS = {
    'job_created': 'job.created',
    'job_initial_form_saved': 'job.initial_form.saved',
    'job_initial_form_submitted': 'job.initial_form.submitted',
    'job_id_validated': 'job.job_id.validated',
    'job_ai_summary_requested': 'job.ai_summary.requested',
    'job_ai_summary_generated': 'job.ai_summary.generated',
    'job_ai_summary_accepted': 'job.ai_summary.accepted',
    'job_ai_summary_auto_accepted': 'job.ai_summary.auto_accepted',
    'job_status_changed': 'job.status.changed',
    'job_allocated': 'job.allocated',
    'job_updated': 'job.updated',
    'job_deleted': 'job.deleted',
    'job_attachment_uploaded': 'job.attachment.uploaded',
    'job_attachment_deleted': 'job.attachment.deleted',
}