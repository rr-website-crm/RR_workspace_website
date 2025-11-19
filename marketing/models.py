from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from accounts.models import CustomUser
import os
import time


def job_attachment_path(instance, filename):
    """Generate file path for job attachments"""
    return f'job_attachments/{instance.job.system_id}/{filename}'


class Job(models.Model):
    """Main Job model with comprehensive tracking"""
    
    REFERENCING_STYLE_CHOICES = [
        ('harvard', 'Harvard'),
        ('apa', 'APA'),
        ('mla', 'MLA'),
        ('ieee', 'IEEE'),
        ('vancouver', 'Vancouver'),
        ('chicago', 'Chicago'),
    ]
    
    WRITING_STYLE_CHOICES = [
        ('proposal', 'Proposal'),
        ('report', 'Report'),
        ('essay', 'Essay'),
        ('dissertation', 'Dissertation'),
        ('business_report', 'Business Report'),
        ('personal_development', 'Personal Development'),
        ('reflection_writing', 'Reflection Writing'),
        ('case_study', 'Case Study'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('allocated', 'Allocated'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('hold', 'Hold'),
        ('query', 'Query'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Primary identifiers
    system_id = models.CharField(max_length=50, unique=True, db_index=True)
    job_id = models.CharField(max_length=200, unique=True, db_index=True)
    
    # Initial Form Fields
    instruction = models.TextField(help_text="Minimum 50 characters required")
    
    # AI Generated Summary Fields
    topic = models.CharField(max_length=500, blank=True, null=True)
    word_count = models.IntegerField(blank=True, null=True)
    referencing_style = models.CharField(
        max_length=20, 
        choices=REFERENCING_STYLE_CHOICES,
        blank=True, 
        null=True
    )
    writing_style = models.CharField(
        max_length=30,
        choices=WRITING_STYLE_CHOICES,
        blank=True,
        null=True
    )
    job_summary = models.TextField(blank=True, null=True)
    
    # AI Summary Metadata
    ai_summary_version = models.IntegerField(default=0)
    ai_summary_generated_at = models.JSONField(default=list, blank=True)  # Array of timestamps
    job_card_degree = models.IntegerField(default=5)  # 0-5 based on missing fields
    
    # User Relations (using string reference for MongoDB compatibility)
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='jobs_created'
    )
    allocated_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jobs_allocated'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    
    # Timestamps - Initial Form
    created_at = models.DateTimeField(default=timezone.now)
    initial_form_submitted_at = models.DateTimeField(null=True, blank=True)
    initial_form_last_saved_at = models.DateTimeField(null=True, blank=True)
    job_name_validated_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps - AI Summary
    ai_summary_requested_at = models.DateTimeField(null=True, blank=True)
    ai_summary_accepted_at = models.DateTimeField(null=True, blank=True)
    
    # General timestamps
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'marketing_jobs'
        ordering = ['-created_at']
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
        indexes = [
            models.Index(fields=['system_id']),
            models.Index(fields=['job_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_by']),
        ]
    
    def __str__(self):
        return f"{self.system_id} - {self.job_id}"
    
    @staticmethod
    def generate_system_id():
        """Generate unique system ID: CH-timestamp_ms"""
        timestamp_ms = int(time.time() * 1000)
        return f"CH-{timestamp_ms}"
    
    def calculate_degree(self):
        """Calculate job card degree based on missing fields"""
        required_fields = [
            self.topic,
            self.word_count,
            self.referencing_style,
            self.writing_style,
            self.job_summary
        ]
        missing_count = sum(1 for field in required_fields if not field)
        self.job_card_degree = missing_count
        return missing_count
    
    def can_regenerate_summary(self):
        """Check if summary can be regenerated (max 3 versions)"""
        return self.ai_summary_version < 3
    
    def should_auto_accept(self):
        """Determine if summary should be auto-accepted"""
        return self.job_card_degree == 0 or self.ai_summary_version >= 3


class JobAttachment(models.Model):
    """Model for job attachments with validation"""
    
    ALLOWED_EXTENSIONS = ['pdf', 'docx', 'jpg', 'jpeg', 'png']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes
    
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to=job_attachment_path,
        validators=[
            FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)
        ]
    )
    original_filename = models.CharField(max_length=255)
    file_size = models.IntegerField()  # in bytes
    uploaded_at = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='uploaded_attachments'
    )
    
    class Meta:
        db_table = 'job_attachments'
        ordering = ['uploaded_at']
    
    def __str__(self):
        return f"{self.job.system_id} - {self.original_filename}"
    
    def clean(self):
        """Validate file size"""
        from django.core.exceptions import ValidationError
        if self.file.size > self.MAX_FILE_SIZE:
            raise ValidationError(
                f'File size must not exceed 10MB. Current size: {self.file.size / (1024*1024):.2f}MB'
            )
    
    def get_file_extension(self):
        """Get file extension"""
        return os.path.splitext(self.original_filename)[1].lower()


class JobSummaryVersion(models.Model):
    """Store each AI summary generation version"""
    
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='summary_versions'
    )
    version_number = models.IntegerField()
    
    # Summary fields for this version
    topic = models.CharField(max_length=500, blank=True, null=True)
    word_count = models.IntegerField(blank=True, null=True)
    referencing_style = models.CharField(max_length=20, blank=True, null=True)
    writing_style = models.CharField(max_length=30, blank=True, null=True)
    job_summary = models.TextField(blank=True, null=True)
    
    # Metadata
    degree = models.IntegerField()  # 0-5 missing fields
    generated_at = models.DateTimeField(default=timezone.now)
    performed_by = models.CharField(max_length=50, default='system')
    ai_model_used = models.CharField(max_length=50, default='gpt-4o-mini')
    
    class Meta:
        db_table = 'job_summary_versions'
        ordering = ['version_number']
        indexes = [
            models.Index(fields=['job', 'version_number']),
        ]
    
    def __str__(self):
        return f"{self.job.system_id} - V{self.version_number} (Degree: {self.degree})"


class JobActionLog(models.Model):
    """Audit log for all job actions - integrates with your ActivityLog pattern"""
    
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('initial_form_submitted', 'Initial Form Submitted'),
        ('initial_form_saved', 'Initial Form Saved'),
        ('job_name_validated', 'Job Name Validated'),
        ('ai_summary_requested', 'AI Summary Requested'),
        ('ai_summary_generated', 'AI Summary Generated'),
        ('ai_summary_accepted', 'AI Summary Accepted'),
        ('status_changed', 'Status Changed'),
        ('allocated', 'Allocated'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
    ]
    
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='action_logs'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    performed_by_type = models.CharField(
        max_length=20,
        choices=[('user', 'User'), ('system', 'System')],
        default='user'
    )
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'job_action_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['job']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.job.system_id} - {self.action} at {self.timestamp}"


# Utility function to log job actions to ActivityLog
def log_job_activity(job, event_key, category='job_management', performed_by=None, metadata=None):
    """
    Logs job-related activities to the main ActivityLog table
    This integrates with your existing ActivityLog system
    """
    from accounts.models import ActivityLog
    
    if metadata is None:
        metadata = {}
    
    # Add job-specific metadata
    metadata.update({
        'job_system_id': job.system_id,
        'job_id': job.job_id,
        'job_status': job.status,
    })
    
    # Add new category for jobs if not exists
    ActivityLog.objects.create(
        event_key=event_key,
        category=category,
        subject_user=job.created_by,  # The marketing user who created the job
        performed_by=performed_by,
        metadata=metadata,
    )
