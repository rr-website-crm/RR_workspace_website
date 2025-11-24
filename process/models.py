# process/models.py
from django.db import models
from django.utils import timezone
from accounts.models import CustomUser

class Job(models.Model):
    """Main Job Model"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('allocated', 'Allocated'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    REFERENCING_CHOICES = [
        ('APA', 'APA'),
        ('MLA', 'MLA'),
        ('Harvard', 'Harvard'),
        ('Chicago', 'Chicago'),
        ('IEEE', 'IEEE'),
        ('Vancouver', 'Vancouver'),
        ('Other', 'Other'),
    ]
    
    # Basic Information
    job_id = models.CharField(max_length=50, unique=True, db_index=True)
    topic = models.TextField()
    word_count = models.PositiveIntegerField()
    deadline = models.DateTimeField()
    referencing = models.CharField(max_length=50, choices=REFERENCING_CHOICES)
    
    # Assignment
    writer = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='writer_jobs',
        limit_choices_to={'role': 'writer'}
    )
    process_member = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='process_jobs',
        limit_choices_to={'role': 'process'}
    )
    allocator = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='allocated_jobs',
        limit_choices_to={'role': 'allocator'}
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Files from Writer
    writer_final_file = models.FileField(upload_to='jobs/writer_files/', null=True, blank=True)
    writer_uploaded_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    allocated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'process_jobs'
        ordering = ['-created_at']
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
    
    def __str__(self):
        return f"{self.job_id} - {self.topic[:50]}"
    
    def get_masked_job_id(self):
        """Return masked job ID for display"""
        if len(self.job_id) > 4:
            return f"{self.job_id[:2]}***{self.job_id[-2:]}"
        return "***"


class ProcessSubmission(models.Model):
    """Process Team Submissions"""
    
    STAGE_CHOICES = [
        ('check', 'Check Stage'),
        ('final', 'Final Stage'),
        ('decoration', 'Decoration Stage'),
    ]
    
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='process_submissions')
    process_member = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    
    # Check Stage Files
    ai_file = models.FileField(upload_to='process/ai_files/', null=True, blank=True)
    plag_file = models.FileField(upload_to='process/plag_files/', null=True, blank=True)
    
    # Final Stage Files
    final_file = models.FileField(upload_to='process/final_files/', null=True, blank=True)
    grammarly_report = models.FileField(upload_to='process/grammarly/', null=True, blank=True)
    other_files = models.FileField(upload_to='process/other_files/', null=True, blank=True)
    
    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'process_submissions'
        ordering = ['-submitted_at']
        verbose_name = 'Process Submission'
        verbose_name_plural = 'Process Submissions'
    
    def __str__(self):
        return f"{self.job.job_id} - {self.stage} - {self.process_member.get_full_name()}"


class JobComment(models.Model):
    """Comments on Jobs"""
    
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    
    # Comment Content
    text = models.TextField()
    
    # Attachments
    attachment = models.FileField(upload_to='job_comments/attachments/', null=True, blank=True)
    link = models.URLField(max_length=500, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'job_comments'
        ordering = ['created_at']
        verbose_name = 'Job Comment'
        verbose_name_plural = 'Job Comments'
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.job.job_id} - {self.created_at}"


class DecorationTask(models.Model):
    """Decoration tasks assigned by allocator"""
    
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name='decoration_task')
    process_member = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='decoration_tasks',
        limit_choices_to={'role': 'process'}
    )
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_decorations'
    )
    
    # Files
    final_file = models.FileField(upload_to='decoration/final_files/', null=True, blank=True)
    ai_file = models.FileField(upload_to='decoration/ai_files/', null=True, blank=True)
    plag_file = models.FileField(upload_to='decoration/plag_files/', null=True, blank=True)
    other_files = models.FileField(upload_to='decoration/other_files/', null=True, blank=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    
    # Timestamps
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'decoration_tasks'
        ordering = ['-assigned_at']
        verbose_name = 'Decoration Task'
        verbose_name_plural = 'Decoration Tasks'
    
    def __str__(self):
        return f"Decoration - {self.job.job_id} - {self.process_member.get_full_name()}"
