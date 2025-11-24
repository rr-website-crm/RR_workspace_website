# writer/models.py
from django.db import models
from django.utils import timezone
from accounts.models import CustomUser
from decimal import Decimal
try:
    from bson.decimal128 import Decimal128 as BsonDecimal128
except ImportError:  # pragma: no cover
    BsonDecimal128 = None


class WriterProject(models.Model):
    """Writer Project Model"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('hold', 'Hold'),
        ('issues', 'Issues'),
        ('closed', 'Closed'),
    ]
    
    REFERENCING_CHOICES = [
        ('apa', 'APA'),
        ('mla', 'MLA'),
        ('harvard', 'Harvard'),
        ('chicago', 'Chicago'),
        ('ieee', 'IEEE'),
        ('other', 'Other'),
    ]
    
    # Job Information
    job_id = models.CharField(max_length=50, unique=True, db_index=True)
    topic = models.TextField()
    word_count = models.PositiveIntegerField()
    deadline = models.DateTimeField()
    referencing = models.CharField(max_length=20, choices=REFERENCING_CHOICES)
    
    # Assignment
    writer = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='writer_projects',
        limit_choices_to={'role': 'writer'}
    )
    allocated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='allocated_projects',
        limit_choices_to={'role': 'allocator'}
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Additional Details
    description = models.TextField(blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    attachments = models.FileField(upload_to='project_attachments/', null=True, blank=True)
    
    # Submission
    submission_file = models.FileField(upload_to='submissions/', null=True, blank=True)
    submission_notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    assigned_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'writer_projects'
        ordering = ['-created_at']
        verbose_name = 'Writer Project'
        verbose_name_plural = 'Writer Projects'
    
    def __str__(self):
        return f"{self.job_id} - {self.writer.get_full_name()}"
    
    def mark_in_progress(self):
        """Mark project as in progress"""
        if not self.started_at:
            self.started_at = timezone.now()
        self.status = 'in_progress'
        self.save()
    
    def mark_completed(self):
        """Mark project as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def is_overdue(self):
        """Check if project is overdue"""
        return timezone.now() > self.deadline and self.status != 'completed'
    
    def time_remaining(self):
        """Calculate time remaining until deadline"""
        if self.status == 'completed':
            return None
        delta = self.deadline - timezone.now()
        return delta


class ProjectIssue(models.Model):
    """Project Issues Model"""
    
    ISSUE_TYPE_CHOICES = [
        ('technical', 'Technical Issue'),
        ('clarification', 'Need Clarification'),
        ('resources', 'Missing Resources'),
        ('deadline', 'Deadline Extension'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    project = models.ForeignKey(
        WriterProject,
        on_delete=models.CASCADE,
        related_name='issues'
    )
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Assignment
    reported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='reported_issues'
    )
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_issues'
    )
    
    # Resolution
    resolution_notes = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_issues'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'project_issues'
        ordering = ['-created_at']
        verbose_name = 'Project Issue'
        verbose_name_plural = 'Project Issues'
    
    def __str__(self):
        return f"{self.project.job_id} - {self.title}"
    
    def resolve(self, resolved_by, notes=''):
        """Mark issue as resolved"""
        self.status = 'resolved'
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save()


class ProjectComment(models.Model):
    """Project Comments Model"""
    
    project = models.ForeignKey(
        WriterProject,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='project_comments'
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'project_comments'
        ordering = ['created_at']
        verbose_name = 'Project Comment'
        verbose_name_plural = 'Project Comments'
    
    def __str__(self):
        return f"{self.user.get_full_name()} on {self.project.job_id}"


class WriterStatistics(models.Model):
    """Writer Statistics Model"""
    
    writer = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='writer_stats',
        limit_choices_to={'role': 'writer'}
    )
    
    # Project Counts
    total_projects = models.PositiveIntegerField(default=0)
    completed_projects = models.PositiveIntegerField(default=0)
    pending_projects = models.PositiveIntegerField(default=0)
    in_progress_projects = models.PositiveIntegerField(default=0)
    issues_count = models.PositiveIntegerField(default=0)
    hold_count = models.PositiveIntegerField(default=0)
    
    # Performance Metrics
    total_words_written = models.PositiveIntegerField(default=0)
    on_time_delivery = models.PositiveIntegerField(default=0)
    late_delivery = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.00'))
    
    # Timestamps
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'writer_statistics'
        verbose_name = 'Writer Statistics'
        verbose_name_plural = 'Writer Statistics'
    
    def __str__(self):
        return f"Stats for {self.writer.get_full_name()}"
    
    @classmethod
    def fetch_or_create_single(cls, writer):
        """
        Return a single statistics row for the given writer, deleting any accidental duplicates.
        Djongo doesn't always enforce the one-to-one constraint, so we consolidate here.
        """
        stats = list(cls.objects.filter(writer=writer).order_by('id'))
        if stats:
            primary = stats[0]
            if len(stats) > 1:
                cls.objects.filter(id__in=[s.id for s in stats[1:]]).delete()
            return primary, False
        return cls.objects.create(writer=writer), True
    
    def _normalize_average_rating(self):
        """Ensure average_rating is stored as Decimal for Djongo compatibility."""
        value = self.average_rating
        if BsonDecimal128 and isinstance(value, BsonDecimal128):
            self.average_rating = value.to_decimal()
        elif isinstance(value, str):
            self.average_rating = Decimal(value or '0')
        elif isinstance(value, (int, float)):
            self.average_rating = Decimal(str(value))
        elif value is None:
            self.average_rating = Decimal('0')

    def update_stats(self):
        """Update writer statistics"""
        projects = WriterProject.objects.filter(writer=self.writer)
        
        self.total_projects = projects.count()
        self.completed_projects = projects.filter(status='completed').count()
        self.pending_projects = projects.filter(status='pending').count()
        self.in_progress_projects = projects.filter(status='in_progress').count()
        self.issues_count = projects.filter(status='issues').count()
        self.hold_count = projects.filter(status='hold').count()
        
        # Calculate total words
        completed = projects.filter(status='completed')
        self.total_words_written = sum(p.word_count for p in completed)
        
        # Calculate on-time delivery
        self.on_time_delivery = sum(
            1 for p in completed 
            if p.completed_at and p.completed_at <= p.deadline
        )
        self.late_delivery = self.completed_projects - self.on_time_delivery
        self._normalize_average_rating()
        self.save()
