"""Utility helpers to store lifecycle logs in MongoDB."""

from __future__ import annotations

from typing import Any, Dict, Optional

from django.utils import timezone

from accounts.models import ActivityLog, CustomUser

EVENT_CATEGORY_MAP = {
    'user.registered_at': ActivityLog.CATEGORY_USER,
    'user.email_verified_at': ActivityLog.CATEGORY_USER,
    'user.approval_requested_at': ActivityLog.CATEGORY_USER,
    'user.approved_at': ActivityLog.CATEGORY_USER,
    'user.rejected_at': ActivityLog.CATEGORY_USER,
    'user.first_successful_login_at': ActivityLog.CATEGORY_USER,
    'user.last_login_at': ActivityLog.CATEGORY_USER,
    'user.password_changed_at': ActivityLog.CATEGORY_USER,
    'user.email_change_requested_at': ActivityLog.CATEGORY_USER,
    'user.email_change_approved_at': ActivityLog.CATEGORY_USER,
    'user.profile_updated_at': ActivityLog.CATEGORY_USER,
    'user.role_assigned_at': ActivityLog.CATEGORY_USER,
    'user.activated_at': ActivityLog.CATEGORY_USER,
    'user.deactivated_at': ActivityLog.CATEGORY_USER,
    'manage_user.viewed_at': ActivityLog.CATEGORY_SUPERADMIN,
    'manage_user.user_edit_at': ActivityLog.CATEGORY_SUPERADMIN,
    'manage_user.role_updated_at': ActivityLog.CATEGORY_SUPERADMIN,
    'manage_user.level_updated_at': ActivityLog.CATEGORY_SUPERADMIN,
    'employee_id.generated_at': ActivityLog.CATEGORY_EMPLOYEE,
    'employee_id.assigned_at': ActivityLog.CATEGORY_EMPLOYEE,
}


def log_activity_event(
    event_key: str,
    *,
    subject_user: Optional[CustomUser] = None,
    performed_by: Optional[CustomUser] = None,
    metadata: Optional[Dict[str, Any]] = None,
    category: Optional[str] = None,
) -> ActivityLog:
    """
    Persist a lifecycle/superadmin event so MongoDB holds an auditable trail.

    Parameters
    ----------
    event_key:
        Dot-notation identifier (e.g., ``user.registered_at``).
    subject_user:
        The user the event is about (can be None for page-level events).
    performed_by:
        The actor who triggered the event (superadmin/user/system).
    metadata:
        Optional structured context (stored as JSON).
    category:
        Overrides default category inference if provided.
    """

    payload = metadata.copy() if metadata else {}
    resolved_category = category or EVENT_CATEGORY_MAP.get(event_key, ActivityLog.CATEGORY_GENERAL)

    return ActivityLog.objects.create(
        event_key=event_key,
        category=resolved_category,
        subject_user=subject_user,
        performed_by=performed_by,
        metadata={
            **payload,
            'logged_at': timezone.now().isoformat(),
        },
    )
