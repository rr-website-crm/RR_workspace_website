# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from pathlib import Path
from uuid import uuid4
import random
import string
from .managers import CustomUserManager


def profile_image_upload_path(instance, filename):
    """
    Store profile pictures in media/profile as EmployeeID_Name.ext.
    Falls back to user id if employee id is missing.
    """
    base_id = instance.employee_id or f"user{instance.pk or uuid4().hex[:6]}"
    name_source = instance.get_full_name() or instance.username or 'profile'
    name_part = slugify(name_source, allow_unicode=True) or 'profile'
    ext = Path(filename).suffix or '.jpg'
    return f"profile/{base_id}_{name_part}{ext.lower()}"


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
    alternate_email = models.EmailField(blank=True, default="")
    profile_image = models.ImageField(upload_to=profile_image_upload_path, null=True, blank=True)
    
    # Role and Department
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    level = models.PositiveSmallIntegerField(default=0)
    department = models.CharField(max_length=50, blank=True, null=True)
    bio = models.TextField(blank=True, default='')
    
    # Profile Edit Permission Fields
    profile_edit_allowed = models.BooleanField(default=False)
    profile_edit_granted_at = models.DateTimeField(null=True, blank=True)
    profile_edit_granted_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profile_edit_grants'
    )
    profile_edit_consumed_at = models.DateTimeField(null=True, blank=True)
    
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


# --------------------------------------------------
# ACTIVITY LOG MODEL
# --------------------------------------------------
class ActivityLog(models.Model):
    """Stores lifecycle and all system actions."""
    
    # Categories
    CATEGORY_USER = 'user_lifecycle'
    CATEGORY_SUPERADMIN = 'superadmin'
    CATEGORY_EMPLOYEE = 'employee_id'
    CATEGORY_HOLIDAY = 'holiday_master'
    CATEGORY_JOB = 'job_management'
    CATEGORY_GENERAL = 'general'
    
    CATEGORY_CHOICES = [
        (CATEGORY_USER, 'User Lifecycle'),
        (CATEGORY_SUPERADMIN, 'Superadmin / Manage Users'),
        (CATEGORY_EMPLOYEE, 'Employee ID'),
        (CATEGORY_HOLIDAY, 'Holiday Master'),
        (CATEGORY_JOB, 'Job Management'),
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


# --------------------------------------------------
# PROFILE CHANGE REQUEST MODEL
# --------------------------------------------------
class ProfileChangeRequest(models.Model):
    """Stores user requests to update protected profile fields."""
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_COMPLETED = 'completed'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_COMPLETED, 'Completed'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='profile_change_requests')
    current_first_name = models.CharField(max_length=150, blank=True, default='')
    current_last_name = models.CharField(max_length=150, blank=True, default='')
    current_email = models.EmailField(blank=True, default='')
    requested_first_name = models.CharField(max_length=150)
    requested_last_name = models.CharField(max_length=150)
    requested_email = models.EmailField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profile_change_reviews'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'profile_change_requests'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Change request for {self.user.email} ({self.status})"
    
    def approve(self, reviewer):
        if self.status != self.STATUS_PENDING:
            return False
        
        approval_time = timezone.now()
        self.status = self.STATUS_APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = approval_time
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        
        user = self.user
        user.profile_edit_allowed = True
        user.profile_edit_granted_at = approval_time
        user.profile_edit_granted_by = reviewer
        user.profile_edit_consumed_at = None
        user.save(update_fields=[
            'profile_edit_allowed',
            'profile_edit_granted_at',
            'profile_edit_granted_by',
            'profile_edit_consumed_at'
        ])
        
        return True
    
    def mark_completed(self):
        if self.status != self.STATUS_APPROVED:
            return False
        
        completion_time = timezone.now()
        self.status = self.STATUS_COMPLETED
        self.completed_at = completion_time
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        
        return True
    
    def reject(self, reviewer):
        if self.status not in (self.STATUS_PENDING, self.STATUS_APPROVED):
            return False
        
        rejection_time = timezone.now()
        self.status = self.STATUS_REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = rejection_time
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        
        if self.user.profile_edit_allowed:
            user = self.user
            user.profile_edit_allowed = False
            user.profile_edit_consumed_at = rejection_time
            user.save(update_fields=['profile_edit_allowed', 'profile_edit_consumed_at'])
        
        return True