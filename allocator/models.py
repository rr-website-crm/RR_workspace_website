from django.db import models
from django.utils import timezone
from accounts.models import CustomUser


class Job(models.Model):
    """Main Job Model for the CRM System"""
    
    CATEGORY_CHOICES = [
        ('IT', 'IT'),
        ('NONIT', 'Non-IT'),
        ('Finance', 'Finance'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Allocation'),
        ('allocated', 'Allocated'),
        ('in_progress', 'In Progress'),
        ('hold', 'On Hold'),
        ('query', 'Query'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    DEGREE_CHOICES = [
        (0, '0 Degree'),
        (1, '1 Degree'),
        (2, '2 Degree'),
        (3, '3 Degree'),
        (4, '4 Degree'),
        (5, '5 Degree'),
    ]
    
    SOFTWARE_CHOICES = [
        ('management_withsoftware', 'Management with Software'),
        ('management_withoutsoftware', 'Management without Software'),
        ('IT_withsoftware', 'IT with Software'),
        ('IT_withoutsoftware', 'IT without Software'),
        ('finance_withsoftware', 'Finance with Software'),
        ('finance_withoutsoftware', 'Finance without Software'),
    ]
    
    # Basic Information
    masking_id = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=500)
    topic = models.TextField()
    client_name = models.CharField(max_length=255)
    
    # Job Details
    job_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    software_type = models.CharField(max_length=50, choices=SOFTWARE_CHOICES, null=True, blank=True)
    degree = models.IntegerField(choices=DEGREE_CHOICES, default=0)
    word_count = models.IntegerField()
    max_word_limit = models.IntegerField(help_text="Maximum word limit allowed")
    
    # Description and Instructions
    description = models.TextField()
    special_instructions = models.TextField(blank=True, null=True)
    marketing_comment = models.TextField(blank=True, null=True)
    marketing_comment_status = models.CharField(
        max_length=16,
        choices=[
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Needs Update'),
        ],
        default='pending'
    )
    allocator_comment = models.TextField(blank=True, null=True)
    allocator_comment = models.TextField(blank=True, null=True)
    allocator_comment_approved = models.BooleanField(default=False)
    
    # Status & Priority
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Assignment
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='created_jobs',
        limit_choices_to={'role': 'marketing'}
    )
    allocated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='allocated_jobs_by',
        limit_choices_to={'role': 'allocator'}
    )
    
    # Files
    attachment = models.FileField(upload_to='job_attachments/', null=True, blank=True)
    structure_file = models.FileField(upload_to='job_structures/', null=True, blank=True)
    
    # Additional Resources
    country = models.CharField(max_length=100, blank=True, null=True)
    banking_sector = models.CharField(max_length=100, blank=True, null=True)
    
    # Dates
    deadline = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    allocated_at = models.DateTimeField(null=True, blank=True)
    
    # Query Management
    has_query = models.BooleanField(default=False)
    query_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['masking_id']),
            models.Index(fields=['status', 'job_category']),
            models.Index(fields=['created_by', 'status']),
        ]
    
    def __str__(self):
        return f"{self.masking_id} - {self.title}"
    
    def can_have_query(self):
        """Check if job can have query based on degree and software"""
        if self.degree == 0:
            return False
        if self.degree >= 1 and self.software_type and 'withsoftware' in self.software_type:
            return True
        return False
    
    def generate_structure(self):
        """Generate structure from attachment based on LO, marking criteria"""
        # This will be implemented based on attachment parsing logic
        pass


class TaskAllocation(models.Model):
    """Task allocation for Content, AI&Plag, Decoration"""
    
    TASK_CHOICES = [
        ('content_creation', 'Content Creation'),
        ('ai_plag', 'AI & Plagiarism Check'),
        ('decoration', 'Decoration'),
    ]
    
    TASK_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('hold', 'On Hold'),
        ('query', 'Query'),
    ]
    
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='task_allocations')
    task_type = models.CharField(max_length=30, choices=TASK_CHOICES)
    
    # Assignment
    allocated_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_allocations_received'
    )
    allocated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='allocated_tasks'
    )
    
    # Time Management
    start_date_time = models.DateTimeField()
    end_date_time = models.DateTimeField()
    allocated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default='pending')
    
    # Files
    submission_file = models.FileField(upload_to='task_submissions/', null=True, blank=True)
    ai_summary_file = models.FileField(upload_to='ai_summaries/', null=True, blank=True)
    final_file = models.FileField(upload_to='final_submissions/', null=True, blank=True)
    writer_final_link = models.URLField(blank=True, null=True)
    summary_link = models.URLField(blank=True, null=True)
    process_final_link = models.URLField(blank=True, null=True)
    
    # Temperature Check (AI Matching)
    temperature_matched = models.BooleanField(default=False)
    temperature_score = models.FloatField(null=True, blank=True)
    
    class Meta:
        db_table = 'task_allocations'
        ordering = ['job', 'task_type']
        unique_together = ['job', 'task_type']
    
    def __str__(self):
        return f"{self.job.masking_id} - {self.get_task_type_display()}"
    
    def can_allocate_to_user(self, user):
        """Check if user can be allocated this task"""
        if self.task_type == 'content_creation':
            return user.role == 'writer'
        elif self.task_type == 'ai_plag':
            return user.role == 'process'
        elif self.task_type == 'decoration':
            return user.role in ['writer', 'process']
        return False


class WriterProfile(models.Model):
    """Extended Writer Profile with job management"""
    
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='writer_profile',
        limit_choices_to={'role': 'writer'}
    )
    
    # Writer Specialization
    is_it_writer = models.BooleanField(default=False, help_text="Can handle IT jobs")
    is_nonit_writer = models.BooleanField(default=True, help_text="Can handle Non-IT jobs")
    is_finance_writer = models.BooleanField(default=True, help_text="Can handle Finance jobs")
    
    # Availability
    is_available = models.BooleanField(default=True)
    is_sunday_off = models.BooleanField(default=False)
    is_on_holiday = models.BooleanField(default=False)
    is_overloaded = models.BooleanField(default=False)
    
    # Capacity Management
    max_jobs = models.IntegerField(default=5, help_text="Maximum concurrent jobs")
    current_jobs = models.IntegerField(default=0)
    max_words = models.IntegerField(default=0, help_text="Maximum words can handle")
    current_words = models.IntegerField(default=0)
    
    # Performance
    total_jobs_completed = models.IntegerField(default=0)
    total_jobs_assigned = models.IntegerField(default=0)
    rating = models.FloatField(default=0.0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'writer_profiles'
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Writer Profile"
    
    def can_accept_job(self, job):
        """Check if writer can accept a job"""
        # Check availability
        if not self.is_available or self.is_sunday_off or self.is_on_holiday or self.is_overloaded:
            return False, "Writer is not available"
        
        # Check job limit
        if self.current_jobs >= self.max_jobs:
            return False, f"Maximum job limit reached ({self.max_jobs})"
        
        # Check word limit
        if self.current_words + job.word_count > self.max_words:
            return False, f"Word limit would be exceeded"
        
        # Check category specialization
        if job.job_category == 'IT' and not self.is_it_writer:
            return False, "Not an IT writer"
        
        return True, "Can accept job"
    
    def get_engagement_status(self):
        """Get current engagement status"""
        return {
            'engaged_jobs': self.current_jobs,
            'total_words': self.current_words,
            'available_slots': self.max_jobs - self.current_jobs,
            'available_words': self.max_words - self.current_words,
        }


class ProcessTeamProfile(models.Model):
    """Extended Process Team Profile"""
    
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='process_profile',
        limit_choices_to={'role': 'process'}
    )
    
    # Availability
    is_available = models.BooleanField(default=True)
    is_sunday_off = models.BooleanField(default=False)
    is_on_holiday = models.BooleanField(default=False)
    
    # Capacity
    max_jobs = models.IntegerField(default=5)
    current_jobs = models.IntegerField(default=0)
    
    # Performance
    total_jobs_completed = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'process_team_profiles'
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Process Team"


class JobQuery(models.Model):
    """Job Query Management"""
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
        ('pending', 'Pending'),
    ]
    
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='queries')
    task_allocation = models.ForeignKey(
        TaskAllocation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='queries'
    )
    
    raised_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='raised_queries'
    )
    query_text = models.TextField()
    response_text = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_queries'
    )
    
    class Meta:
        db_table = 'job_queries'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Query #{self.id} - {self.job.masking_id}"


class AllocationHistory(models.Model):
    """Track allocation history and changes"""
    
    ACTION_CHOICES = [
        ('allocated', 'Allocated'),
        ('reallocated', 'Reallocated'),
        ('switched', 'Switched Writer'),
        ('edited', 'Edited'),
        ('cancelled', 'Cancelled'),
    ]
    
    task_allocation = models.ForeignKey(
        TaskAllocation,
        on_delete=models.CASCADE,
        related_name='history'
    )
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    previous_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='previous_allocations'
    )
    new_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='new_allocations'
    )
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='allocation_changes'
    )
    
    reason = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'allocation_history'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.action} - {self.task_allocation}"


class CountryBankingResource(models.Model):
    """Country and Banking Sector Resources (from Excel)"""
    
    country_name = models.CharField(max_length=100, unique=True)
    banking_sectors = models.JSONField(default=list)
    other_resources = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'country_banking_resources'
    
    def __str__(self):
        return self.country_name
