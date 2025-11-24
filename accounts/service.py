from .models import ActivityLog
from django.utils import timezone
import logging

logger = logging.getLogger('accounts')


def log_activity_event(event_key, subject_user=None, performed_by=None, metadata=None):
    """
    Log an activity event to MongoDB via ActivityLog model.
    
    Args:
        event_key: String identifier for the event (e.g., 'user.registered_at')
        subject_user: User the action is about (optional)
        performed_by: User who performed the action (optional)
        metadata: Dict of additional data (optional)
    """
    try:
        # Determine category from event_key
        category = ActivityLog.CATEGORY_GENERAL
        
        if event_key.startswith('user.'):
            category = ActivityLog.CATEGORY_USER
        elif event_key.startswith('manage_user.') or event_key.startswith('superadmin.'):
            category = ActivityLog.CATEGORY_SUPERADMIN
        elif event_key.startswith('employee_id.'):
            category = ActivityLog.CATEGORY_EMPLOYEE
        elif event_key.startswith('holiday.'):
            category = ActivityLog.CATEGORY_HOLIDAY
        elif event_key.startswith('job.'):
            category = ActivityLog.CATEGORY_JOB
        
        # Create activity log
        ActivityLog.objects.create(
            event_key=event_key,
            category=category,
            subject_user=subject_user,
            performed_by=performed_by,
            metadata=metadata or {},
            created_at=timezone.now(),
        )
        
        logger.debug(f"Activity logged: {event_key}")
        
    except Exception as e:
        logger.error(f"Failed to log activity event '{event_key}': {str(e)}")