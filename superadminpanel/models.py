from django.db import models
from django.utils import timezone
from accounts.models import CustomUser
from django.db import models
from django.utils import timezone
from accounts.models import CustomUser
import random
import string

class Holiday(models.Model):
    """Holiday Master Model"""
    
    HOLIDAY_TYPE_CHOICES = [
        ('full_day', 'Full Day'),
        ('half_day', 'Half Day'),
    ]
    
    DATE_TYPE_CHOICES = [
        ('single', 'Single'),
        ('consecutive', 'Consecutive Days'),
    ]
    
    # Basic Information
    holiday_name = models.CharField(max_length=255, null=True, blank=True)
    holiday_type = models.CharField(max_length=20, choices=HOLIDAY_TYPE_CHOICES, default='full_day')
    date_type = models.CharField(max_length=20, choices=DATE_TYPE_CHOICES, default='single')
    
    # Date fields
    date = models.DateField(null=True, blank=True)  # For single date
    from_date = models.DateField(null=True, blank=True)  # For consecutive dates
    to_date = models.DateField(null=True, blank=True)  # For consecutive dates
    
    # Description
    description = models.TextField(blank=True, null=True)
    
    # Google Calendar Integration
    google_calendar_event_id = models.CharField(max_length=255, blank=True, null=True)
    is_synced_to_calendar = models.BooleanField(default=False)
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    
    google_calendar_sync_started_at = models.DateTimeField(null=True, blank=True)
    google_calendar_synced_at = models.DateTimeField(null=True, blank=True)
    google_calendar_sync_failed_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='holidays_created')
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='holidays_updated')
    deleted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='holidays_deleted')
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'holidays'
        ordering = ['-created_at']
        verbose_name = 'Holiday'
        verbose_name_plural = 'Holidays'
    
    def __str__(self):
        if self.date_type == 'single':
            return f"{self.holiday_name} - {self.date}"
        return f"{self.holiday_name} - {self.from_date} to {self.to_date}"
    

class PriceMaster(models.Model):
    """Price Master Model"""
    
    CATEGORY_CHOICES = [
        ('IT', 'IT'),
        ('NON-IT', 'NON-IT'),
    ]
    
    LEVEL_CHOICES = [
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advance', 'Advance'),
    ]
    
    # Basic Information
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    price_per_word = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='prices_created'
    )
    updated_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='prices_updated'
    )
    deleted_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='prices_deleted'
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'price_master'
        ordering = ['-created_at']
        verbose_name = 'Price Master'
        verbose_name_plural = 'Price Masters'
        unique_together = ['category', 'level']
    
    def __str__(self):
        return f"{self.get_category_display()} - {self.get_level_display()} - ₹{self.price_per_word}/word"


class ReferencingMaster(models.Model):
    """Referencing Master Model"""
    
    # Basic Information
    referencing_style = models.CharField(max_length=100)
    used_in = models.CharField(max_length=255)
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='references_created'
    )
    updated_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='references_updated'
    )
    deleted_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='references_deleted'
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'referencing_master'
        ordering = ['-created_at']
        verbose_name = 'Referencing Master'
        verbose_name_plural = 'Referencing Masters'
    
    def __str__(self):
        return f"{self.referencing_style} - {self.used_in}"
    
class AcademicWritingMaster(models.Model):
    """Academic Writing Style Master Model"""
    
    # Basic Information
    writing_style = models.CharField(max_length=100)
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='writings_created'
    )
    updated_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='writings_updated'
    )
    deleted_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='writings_deleted'
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'academic_writing_master'
        ordering = ['-created_at']
        verbose_name = 'Academic Writing Style'
        verbose_name_plural = 'Academic Writing Styles'
    
    def __str__(self):
        return self.writing_style
    
class ProjectGroupMaster(models.Model):
    """Project Group Master Model"""
    
    # Basic Information
    project_group_name = models.CharField(max_length=255)
    project_group_prefix = models.CharField(max_length=50, unique=True)
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='project_groups_created'
    )
    updated_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='project_groups_updated'
    )
    deleted_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='project_groups_deleted'
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'project_group_master'
        ordering = ['-created_at']
        verbose_name = 'Project Group Master'
        verbose_name_plural = 'Project Group Masters'
    
    def __str__(self):
        return f"{self.project_group_name} ({self.project_group_prefix})"
    
 # Templatemaster model can be added here similarly if needed
class TemplateMaster(models.Model):
    """Template Master Model - Created by Superadmin"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    # Basic Information
    template_name = models.CharField(max_length=255)
    template_description = models.TextField(blank=True, null=True)
    
    # Default Tasks Configuration (JSON field to store task structure)
    default_tasks = models.JSONField(
        default=list,
        help_text="Default tasks that will be created when this template is used"
    )
    
    # Visibility Configuration
    # Controls which fields are visible to which roles
    visibility_config = models.JSONField(
        default=dict,
        help_text="Configuration for field visibility per role"
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='templates_created'
    )
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates_updated'
    )
    deleted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates_deleted'
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'template_master'
        ordering = ['-created_at']
        verbose_name = 'Template Master'
        verbose_name_plural = 'Template Masters'
    
    def __str__(self):
        return self.template_name
    
    def get_default_tasks_structure(self):
        """Return default task structure"""
        return [
            {
                'task_number': 1,
                'task_name': 'Content Creation',
                'task_code': 'T1',
                'assignable_roles': ['writer'],
                'description': 'Initial content creation by writer'
            },
            {
                'task_number': 2,
                'task_name': 'AI–Plag',
                'task_code': 'T2',
                'assignable_roles': ['writer', 'process'],
                'description': 'AI and plagiarism check'
            },
            {
                'task_number': 3,
                'task_name': 'Decoration',
                'task_code': 'T3',
                'assignable_roles': ['writer', 'process'],
                'description': 'Final decoration and formatting'
            }
        ]


class JobTemplate(models.Model):
    """Instance of a template used for a specific job"""
    
    # Link to job and template
    job = models.OneToOneField(
        'marketing.Job',
        on_delete=models.CASCADE,
        related_name='job_template'
    )
    template = models.ForeignKey(
        TemplateMaster,
        on_delete=models.PROTECT,
        related_name='job_instances'
    )
    
    # Masking ID
    masking_id = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Project Group Info
    project_group = models.ForeignKey(
        'ProjectGroupMaster',
        on_delete=models.PROTECT,
        related_name='job_templates'
    )
    project_prefix = models.CharField(max_length=10)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    masking_id_generated_at = models.DateTimeField(null=True, blank=True)
    
    # Created by (Marketing team member)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='job_templates_created'
    )
    
    class Meta:
        db_table = 'job_templates'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.masking_id} - {self.job.job_id}"
    
    @staticmethod
    def generate_project_prefix(project_group):
        """Generate unique project prefix: PREFIX + 2 alphanumeric chars"""
        base_prefix = project_group.project_group_prefix
        
        while True:
            # Generate 2 random alphanumeric characters
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
            full_prefix = f"{base_prefix}{random_part}"
            
            # Check if exists
            if not JobTemplate.objects.filter(project_prefix=full_prefix).exists():
                return full_prefix
    
    @staticmethod
    def generate_masking_id(category, project_prefix):
        """Generate unique masking ID: JOB-{8_chars}-{Category}"""
        category_map = {
            'IT': 'IT',
            'NON-IT': 'NonIT',
            'Finance': 'Finance'
        }
        category_suffix = category_map.get(category, 'Other')
        
        while True:
            # Generate 8 random alphanumeric characters
            random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            masking_id = f"JOB-{random_chars}-{category_suffix}"
            
            # Check if exists
            if not JobTemplate.objects.filter(masking_id=masking_id).exists():
                return masking_id


class JobTask(models.Model):
    """Individual tasks within a job template"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
    ]
    
    # Link to job template
    job_template = models.ForeignKey(
        JobTemplate,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    
    # Task Information
    task_id = models.CharField(max_length=50, unique=True, db_index=True)
    task_number = models.IntegerField()
    task_name = models.CharField(max_length=255)
    task_code = models.CharField(max_length=10)  # T1, T2, T3
    
    # Assignment
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_tasks_assigned'
    )
    assignable_roles = models.JSONField(default=list)  # ['writer', 'process']
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Progress
    completed_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Work tracking
    work_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Total work hours spent on this task"
    )
    
    # Task-specific fields
    word_count = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'job_tasks'
        ordering = ['task_number']
        indexes = [
            models.Index(fields=['task_id']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.task_id} - {self.task_name}"
    
    @staticmethod
    def generate_task_id(project_prefix, task_code):
        """Generate task ID: {ProjectPrefix}-{TaskCode}"""
        return f"{project_prefix}-{task_code}"
    
    def calculate_duration(self):
        """Calculate duration between start and completion"""
        if self.start_date and self.completed_at:
            duration = self.completed_at - self.start_date
            return duration
        return None
    
    def update_work_hours(self):
        """Update work hours based on status timestamps"""
        if self.start_date and self.completed_at:
            duration = self.completed_at - self.start_date
            self.work_hours = duration.total_seconds() / 3600  # Convert to hours
            self.save(update_fields=['work_hours'])
 
