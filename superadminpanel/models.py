from django.db import models
from django.utils import timezone
from accounts.models import CustomUser

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