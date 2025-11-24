from datetime import datetime, time
import logging
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from accounts.models import CustomUser, LoginLog, ProfileChangeRequest
from accounts.services import log_activity_event

logger = logging.getLogger('superadmin')

APPROVED_ROLES = [
    'superadmin',
    'admin',
    'marketing',
    'allocator',
    'writer',
    'process',
]

PRIVILEGED_MANAGE_ROLES = {'superadmin', 'admin'}
RESTRICTED_ROLE_MESSAGE = 'You do not have permission to manage Super Admin or Admin accounts.'
WRITER_ROLE_NAME = 'writer'
WRITER_ONLY_FIELDS_MESSAGE = 'Category and level can only be updated for Writer role.'


def _is_admin_actor(user):
    """Return True when the acting user is an admin."""
    return (getattr(user, 'role', '') or '').lower() == 'admin'


def _is_privileged_role(role_value):
    """Return True when a role value represents superadmin/admin."""
    return (role_value or '').lower() in PRIVILEGED_MANAGE_ROLES


def _admin_cannot_manage_target(actor, target):
    """Determine whether an admin is trying to manage a privileged account."""
    if not actor or not target:
        return False
    return _is_admin_actor(actor) and _is_privileged_role(getattr(target, 'role', ''))


def _is_writer_role(role_value):
    """True when the provided role value is Writer."""
    return (role_value or '').lower() == WRITER_ROLE_NAME


def get_dashboard_context():
    """Compute high-level dashboard metrics."""
    total_users = 0
    pending_approvals = 0
    total_approved = 0
    role_data = []
    total_active = 0
    
    try:
        approved_qs = CustomUser.objects.filter(
            approval_status='approved',
            role__in=APPROVED_ROLES,
        ).order_by('-date_joined')
        approved_list = list(approved_qs)
        total_users = len(approved_list)
        total_approved = total_users
        
        pending_qs = CustomUser.objects.filter(
            approval_status='pending',
        ).order_by('date_joined')
        pending_approvals = len(list(pending_qs))
        
        today = timezone.now().date()
        start = timezone.make_aware(datetime.combine(today, time.min))
        end = timezone.make_aware(datetime.combine(today, time.max))
        tz = timezone.get_current_timezone()
        
        raw_logs = list(LoginLog.objects.all())
        logs = []
        for entry in raw_logs:
            login_time = getattr(entry, 'login_time', None)
            if not entry.is_active or not login_time:
                continue
            if timezone.is_naive(login_time):
                login_time = timezone.make_aware(login_time, tz)
            entry.login_time = login_time
            if start <= login_time <= end:
                logs.append(entry)
        
        logs.sort(key=lambda log: log.login_time)
        
        user_ids = {log.user_id for log in logs}
        users_map = {
            user.id: user
            for user in CustomUser.objects.filter(id__in=user_ids).only(
                'id', 'role', 'first_name', 'last_name', 'email', 'employee_id'
            )
        }
        
        unique_logs = {}
        for log in logs:
            if log.user_id in unique_logs:
                continue
            user = users_map.get(log.user_id)
            if not user:
                continue
            role = getattr(user, 'role', 'user') or 'user'
            if role not in APPROVED_ROLES:
                continue
            unique_logs[log.user_id] = (log, role)
        
        role_count_map = {}
        for _, role in unique_logs.values():
            role_count_map[role] = role_count_map.get(role, 0) + 1
        
        role_data = [
            {'role': role_name, 'count': count}
            for role_name, count in sorted(role_count_map.items())
        ]
        total_active = sum(role_count_map.values())
        
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Error while preparing dashboard data: %s", exc)
    
    return {
        'total_users': total_users,
        'total_active': total_active,
        'pending_approvals': pending_approvals,
        'total_approved': total_approved,
        'role_active_counts': role_data,
    }


def get_role_details_data(role):
    """Return today's active login details for the given role."""
    if role not in APPROVED_ROLES:
        return []
    
    users_data = []
    
    try:
        today = timezone.now().date()
        start = timezone.make_aware(datetime.combine(today, time.min))
        end = timezone.make_aware(datetime.combine(today, time.max))
        tz = timezone.get_current_timezone()
        
        raw_logs = list(LoginLog.objects.all())
        logs = []
        for entry in raw_logs:
            login_time = getattr(entry, 'login_time', None)
            if not entry.is_active or not login_time:
                continue
            if timezone.is_naive(login_time):
                login_time = timezone.make_aware(login_time, tz)
            entry.login_time = login_time
            if start <= login_time <= end:
                logs.append(entry)
        
        logs.sort(key=lambda log: log.login_time)
        
        user_ids = {log.user_id for log in logs}
        users_map = {
            user.id: user
            for user in CustomUser.objects.filter(
                id__in=user_ids,
                role=role
            ).only('id', 'role', 'first_name', 'last_name', 'email', 'employee_id')
        }
        
        earliest_logs = {}
        for log in logs:
            if log.user_id in earliest_logs:
                continue
            user = users_map.get(log.user_id)
            if not user:
                continue
            login_time_local = timezone.localtime(log.login_time)
            earliest_logs[log.user_id] = {
                'employee_id': log.employee_id or getattr(user, 'employee_id', 'N/A'),
                'name': user.get_full_name() or user.email,
                'email': user.email,
                'login_dt': login_time_local,
            }
        
        for user_id in sorted(earliest_logs, key=lambda uid: earliest_logs[uid]['login_dt']):
            entry = earliest_logs[user_id]
            users_data.append({
                'employee_id': entry['employee_id'],
                'name': entry['name'],
                'email': entry['email'],
                'login_time': entry['login_dt'].strftime('%b %d, %Y %I:%M %p'),
            })
    
    except Exception as exc:  # pragma: no cover
        logger.exception("Error fetching role details for %s: %s", role, exc)
    
    return users_data


def get_manage_users_context(performed_by=None):
    """Return data required for manage users screen."""
    users = []
    total_users = 0
    pending_count = 0
    approved_count = 0
    
    try:
        users_qs = CustomUser.objects.filter(
            approval_status='approved',
            role__in=APPROVED_ROLES,
        ).order_by('-date_joined')
        
        if performed_by and _is_admin_actor(performed_by):
            users_qs = users_qs.exclude(role__in=PRIVILEGED_MANAGE_ROLES)
        
        users = list(users_qs)
        total_users = len(users)
        
        pending_qs = CustomUser.objects.filter(
            approval_status='pending',
        ).order_by('date_joined')
        pending_count = len(list(pending_qs))
        
        approved_count = total_users
    
    except Exception as exc:  # pragma: no cover
        logger.exception("Error fetching manage users data: %s", exc)
    
    context = {
        'users': users,
        'total_users': total_users,
        'pending_count': pending_count,
        'approved_count': approved_count,
    }
    
    if performed_by:
        log_activity_event(
            'manage_user.viewed_at',
            performed_by=performed_by,
            metadata={
                'total_users': total_users,
                'pending_count': pending_count,
                'approved_count': approved_count,
            },
        )
    
    return context


def update_user_role(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    if _admin_cannot_manage_target(request.user, user):
        messages.error(request, RESTRICTED_ROLE_MESSAGE)
        return
    
    new_role = request.POST.get('role')
    valid_roles = dict(CustomUser.ROLE_CHOICES).keys()
    
    if new_role in valid_roles:
        old_role = user.role
        user.role = new_role
        user.role_assigned_at = timezone.now()
        user.save(update_fields=['role', 'role_assigned_at'])
        
        logger.info("User %s role updated from %s to %s by %s",
                    user.email, old_role, new_role, request.user.email)
        
        log_activity_event(
            'user.role_assigned_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'from': old_role, 'to': new_role},
        )
        
        log_activity_event(
            'manage_user.role_updated_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'from': old_role, 'to': new_role},
        )
        
        messages.success(request, f'User role updated successfully to {new_role}.')
    else:
        messages.error(request, 'Invalid role selected.')


def update_user_category(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    if _admin_cannot_manage_target(request.user, user):
        messages.error(request, RESTRICTED_ROLE_MESSAGE)
        return
    
    if not _is_writer_role(getattr(user, 'role', '')):
        messages.error(request, WRITER_ONLY_FIELDS_MESSAGE)
        return
    
    category = request.POST.get('category')
    user.department = category
    user.save(update_fields=['department'])
    
    logger.info("User %s category updated to %s by %s",
                user.email, category, request.user.email)
    messages.success(request, 'User category updated successfully.')


def update_user_level(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    if _admin_cannot_manage_target(request.user, user):
        messages.error(request, RESTRICTED_ROLE_MESSAGE)
        return
    
    if not _is_writer_role(getattr(user, 'role', '')):
        messages.error(request, WRITER_ONLY_FIELDS_MESSAGE)
        return
    
    try:
        level = int(request.POST.get('level', 0))
        if 0 <= level <= 5:
            user.level = level
            user.save(update_fields=['level'])
            
            logger.info("User %s level updated to %s by %s",
                        user.email, level, request.user.email)
            
            log_activity_event(
                'manage_user.level_updated_at',
                subject_user=user,
                performed_by=request.user,
                metadata={'level': level},
            )
            
            messages.success(request, 'User level updated successfully.')
        else:
            messages.error(request, 'Level must be between 0 and 5.')
    except ValueError:
        messages.error(request, 'Invalid level value.')


def toggle_user_status(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    if _admin_cannot_manage_target(request.user, user):
        messages.error(request, RESTRICTED_ROLE_MESSAGE)
        return
    
    user.is_active = not user.is_active
    status_field = 'activated_at' if user.is_active else 'deactivated_at'
    timestamp = timezone.now()
    setattr(user, status_field, timestamp)
    user.save(update_fields=['is_active', status_field])
    
    status = 'activated' if user.is_active else 'deactivated'
    
    logger.info("User %s %s by %s", user.email, status, request.user.email)
    
    log_activity_event(
        f'user.{status_field}',
        subject_user=user,
        performed_by=request.user,
        metadata={'status': status},
    )
    
    messages.success(request, f'User has been {status} successfully.')


def process_edit_user_form(request, user):
    if _admin_cannot_manage_target(request.user, user):
        messages.error(request, RESTRICTED_ROLE_MESSAGE)
        return
    
    changes = {}
    update_fields = set()
    profile_fields = []
    role_changed = False
    level_changed = False
    
    submitted_role = request.POST.get('role')
    resolved_role = submitted_role if submitted_role not in (None, '') else getattr(user, 'role', '')
    current_role_lower = (resolved_role or getattr(user, 'role', '') or '').strip().lower()
    
    field_map = {
        'first_name': request.POST.get('first_name', user.first_name),
        'last_name': request.POST.get('last_name', user.last_name),
        'email': request.POST.get('email', user.email),
        'alternate_email': request.POST.get('alternate_email', getattr(user, 'alternate_email', '') or ''),
        'whatsapp_number': request.POST.get('whatsapp_number', user.whatsapp_number),
        'role': resolved_role,
        'department': request.POST.get('category', getattr(user, 'department', '') or ''),
    }
    
    for field, new_value in field_map.items():
        if field == 'department' and not _is_writer_role(current_role_lower):
            continue
        
        if field == 'alternate_email':
            new_value = (new_value or '').strip()
            if new_value:
                try:
                    validate_email(new_value)
                except ValidationError:
                    messages.error(request, f'Alternate email for {user.email} must be a valid email address.')
                    continue
                new_value = new_value.lower()
        
        if field == 'email' and new_value:
            new_value = new_value.strip().lower()
        
        old_value = getattr(user, field)
        if new_value != old_value:
            setattr(user, field, new_value)
            update_fields.add(field)
            changes[field] = {'old': old_value, 'new': new_value}
            
            if field not in {'email', 'role'}:
                profile_fields.append(field)
            
            if field == 'role':
                role_changed = True
                current_role_lower = (new_value or '').strip().lower()
    
    try:
        if _is_writer_role(current_role_lower):
            level_value = int(request.POST.get('level', getattr(user, 'level', 0)))
            if 0 <= level_value <= 5:
                old_level = getattr(user, 'level', 0)
                if level_value != old_level:
                    user.level = level_value
                    update_fields.add('level')
                    changes['level'] = {'old': old_level, 'new': level_value}
                    level_changed = True
                    profile_fields.append('level')
    except (ValueError, TypeError):
        pass
    
    if not update_fields:
        messages.info(request, 'No changes detected for this user.')
        return
    
    timestamp = timezone.now()
    cleaned_profile_fields = sorted(set(profile_fields))
    
    if cleaned_profile_fields:
        user.profile_updated_at = timestamp
        update_fields.add('profile_updated_at')
    
    if role_changed:
        user.role_assigned_at = timestamp
        update_fields.add('role_assigned_at')
    
    user.save(update_fields=list(update_fields))
    
    if cleaned_profile_fields:
        log_activity_event(
            'user.profile_updated_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'updated_fields': cleaned_profile_fields},
        )
    
    if role_changed:
        log_activity_event(
            'user.role_assigned_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'changes': changes.get('role')},
        )
        log_activity_event(
            'manage_user.role_updated_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'changes': changes.get('role')},
        )
    
    if level_changed:
        log_activity_event(
            'manage_user.level_updated_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'level': getattr(user, 'level', 0)},
        )
    
    log_activity_event(
        'manage_user.user_edit_at',
        subject_user=user,
        performed_by=request.user,
        metadata={'changes': changes},
    )
    
    logger.info("User %s profile updated by %s", user.email, request.user.email)
    messages.success(request, 'User profile updated successfully.')


def get_pending_items_context():
    pending_users = []
    profile_requests_pending = []
    profile_requests_active = []
    
    try:
        pending_qs = CustomUser.objects.filter(
            approval_status='pending'
        ).order_by('date_joined')
        pending_users = list(pending_qs)
    except Exception as exc:  # pragma: no cover
        logger.exception("Error fetching pending users: %s", exc)
    
    try:
        profile_requests_pending = list(
            ProfileChangeRequest.objects.select_related('user')
            .filter(status=ProfileChangeRequest.STATUS_PENDING)
            .order_by('-created_at')
        )
        profile_requests_active = list(
            ProfileChangeRequest.objects.select_related('user')
            .filter(status=ProfileChangeRequest.STATUS_APPROVED)
            .order_by('-reviewed_at')
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Error fetching profile change requests: %s", exc)
    
    return {
        'pending_users': pending_users,
        'pending_total': len(pending_users),
        'profile_requests_pending': profile_requests_pending,
        'profile_requests_active': profile_requests_active,
        'profile_pending_total': len(profile_requests_pending),
        'profile_active_total': len(profile_requests_active),
    }


def approve_user(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    role = request.POST.get('role')
    roles = dict(CustomUser.ROLE_CHOICES).keys()
    
    if not role or role not in roles:
        messages.error(request, 'Please select a valid role.')
        return
    
    if role == 'user':
        messages.error(request, 'Cannot approve with "user" role. Please select a specific role.')
        return
    
    previous_employee_id = user.employee_id
    approval_time = timezone.now()
    
    with transaction.atomic():
        user.role = role
        user.approval_status = 'approved'
        user.is_approved = True
        user.level = getattr(user, 'level', 0) or 0
        user.approved_at = approval_time
        user.role_assigned_at = approval_time
        user.save()
    
    if user.employee_id and not previous_employee_id:
        user.employee_id_generated_at = approval_time
        user.employee_id_assigned_at = approval_time
        user.save(update_fields=['employee_id_generated_at', 'employee_id_assigned_at'])
        
        log_activity_event(
            'employee_id.generated_at',
            subject_user=user,
            metadata={'employee_id': user.employee_id, 'source': 'approval', 'performed_by': 'system'},
        )
        log_activity_event(
            'employee_id.assigned_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'employee_id': user.employee_id, 'source': 'approval'},
        )
    
    logger.info("User %s approved with role %s by %s", user.email, role, request.user.email)
    
    log_activity_event(
        'user.approved_at',
        subject_user=user,
        performed_by=request.user,
        metadata={'role': role},
    )
    log_activity_event(
        'user.role_assigned_at',
        subject_user=user,
        performed_by=request.user,
        metadata={'role': role},
    )
    log_activity_event(
        'manage_user.role_updated_at',
        subject_user=user,
        performed_by=request.user,
        metadata={'role': role},
    )
    
    messages.success(request, f'User approved successfully as {role}.')


def reject_user(request, user_id):
    if request.method != 'POST':
        return
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    with transaction.atomic():
        user.approval_status = 'rejected'
        user.is_approved = False
        user.rejected_at = timezone.now()
        user.save()
    
    logger.info("User %s rejected by %s", user.email, request.user.email)
    
    log_activity_event(
        'user.rejected_at',
        subject_user=user,
        performed_by=request.user,
        metadata={'reason': request.POST.get('reason', 'not provided')},
    )
    
    messages.warning(request, 'User registration has been rejected.')


def approve_profile_request(request, request_id):
    if request.method != 'POST':
        return
    
    change_request = get_object_or_404(ProfileChangeRequest, id=request_id)
    
    if change_request.status != ProfileChangeRequest.STATUS_PENDING:
        messages.info(request, 'This request has already been processed.')
        return
    
    if change_request.approve(request.user):
        log_activity_event(
            'profile_edit_request.approved',
            subject_user=change_request.user,
            performed_by=request.user,
            metadata={'request_id': change_request.id},
        )
        messages.success(request, 'Profile edit request approved.')
    else:
        messages.error(request, 'Could not approve this request.')


def reject_profile_request(request, request_id):
    if request.method != 'POST':
        return
    
    change_request = get_object_or_404(ProfileChangeRequest, id=request_id)
    
    if change_request.reject(request.user):
        log_activity_event(
            'profile_edit_request.rejected',
            subject_user=change_request.user,
            performed_by=request.user,
            metadata={'request_id': change_request.id},
        )
        messages.warning(request, 'Profile edit request rejected.')
    else:
        messages.error(request, 'Could not reject this request.')