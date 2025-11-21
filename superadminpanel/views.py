# superadminpanel/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from accounts.models import CustomUser, LoginLog
from accounts.services import log_activity_event
import logging
from datetime import datetime, time

from .models import Holiday,PriceMaster,ReferencingMaster,AcademicWritingMaster
from bson import ObjectId
from bson.errors import InvalidId
from .services.google_calendar_service import GoogleCalendarService
from datetime import datetime, timedelta

logger = logging.getLogger('superadmin')

# Roles we consider "administrative" (avoid exclude/NOT queries)
APPROVED_ROLES = [
    'superadmin',
    'admin',
    'marketing',
    'allocator',
    'writer',
    'process'
]


def superadmin_required(view_func):
    """Decorator to check if user is superadmin"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        if request.user.role != 'superadmin':
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('home_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@superadmin_required
def superadmin_dashboard(request):
    """SuperAdmin Dashboard — Djongo-safe implementation"""

    # Provide safe defaults
    total_users = 0
    pending_approvals = 0
    total_approved = 0
    role_data = []
    total_active = 0
    try:
        # Use positive filters Djongo can translate:
        approved_qs = CustomUser.objects.filter(
            approval_status='approved',
            role__in=APPROVED_ROLES
        ).order_by('-date_joined')

        # Evaluate in Python to avoid COUNT() SQL translation problems
        approved_list = list(approved_qs)
        total_users = len(approved_list)
        total_approved = total_users  # keep consistent

        # Pending approvals (use approval_status not boolean)
        pending_qs = CustomUser.objects.filter(
            approval_status='pending'
        ).order_by('date_joined')
        pending_approvals = len(list(pending_qs))

        # Today's active users by role (avoid DB aggregation; do grouping in Python)
        today = timezone.now().date()
        start = timezone.make_aware(datetime.combine(today, time.min))
        end   = timezone.make_aware(datetime.combine(today, time.max))

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

    except Exception as e:
        # Keep dashboard rendering even if Djongo errors — log full traceback
        logger.exception("Error while preparing superadmin dashboard data: %s", e)
        # defaults remain zero/empty so the template shows safe state

    context = {
        'total_users': total_users,
        'total_active': total_active,
        'pending_approvals': pending_approvals,
        'total_approved': total_approved,
        'role_active_counts': role_data,
    }

    return render(request, 'superadmin_dashboard.html', context)


@login_required
@superadmin_required
def role_details(request, role):
    """Return JSON list of today's active users for role (Djongo-safe)"""

    users_data = []
    if role not in APPROVED_ROLES:
        return JsonResponse({'users': users_data})

    try:
        today = timezone.now().date()
        start = timezone.make_aware(datetime.combine(today, time.min))
        end   = timezone.make_aware(datetime.combine(today, time.max))

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

        users_data = []
        for user_id in sorted(earliest_logs, key=lambda uid: earliest_logs[uid]['login_dt']):
            entry = earliest_logs[user_id]
            users_data.append({
                'employee_id': entry['employee_id'],
                'name': entry['name'],
                'email': entry['email'],
                'login_time': entry['login_dt'].strftime('%b %d, %Y %I:%M %p'),
            })

    except Exception as e:
        logger.exception("Error fetching role details for %s: %s", role, e)
        # return empty list in error case

    return JsonResponse({'users': users_data})


@login_required
@superadmin_required
def manage_users(request):
    """Manage all users — Djongo-friendly queries"""

    users = []
    total_users = 0
    pending_count = 0
    approved_count = 0

    try:
        # Use approval_status='approved' and role__in to avoid exclude/NOT
        users_qs = CustomUser.objects.filter(
            approval_status='approved',
            role__in=APPROVED_ROLES
        ).order_by('-date_joined')

        # Evaluate in Python - prevents problematic COUNT() translations
        users = list(users_qs)
        total_users = len(users)

        # Pending
        pending_qs = CustomUser.objects.filter(approval_status='pending').order_by('date_joined')
        pending_count = len(list(pending_qs))

        approved_count = total_users

    except Exception as e:
        logger.exception("Error fetching manage users data: %s", e)
        # leave defaults as zeros/empty and render page with friendly message

    context = {
        'users': users,
        'total_users': total_users,
        'pending_count': pending_count,
        'approved_count': approved_count,
    }

    log_activity_event(
        'manage_user.viewed_at',
        performed_by=request.user,
        metadata={
            'total_users': total_users,
            'pending_count': pending_count,
            'approved_count': approved_count,
        },
    )

    return render(request, 'manage_users.html', context)


@login_required
@superadmin_required
def update_user_role(request, user_id):
    """Update user role"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        new_role = request.POST.get('role')

        if new_role in dict(CustomUser.ROLE_CHOICES).keys():
            old_role = user.role
            user.role = new_role
            user.role_assigned_at = timezone.now()
            user.save(update_fields=['role', 'role_assigned_at'])

            logger.info(f"User {user.email} role updated from {old_role} to {new_role} by {request.user.email}")
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

    return redirect('manage_users')


@login_required
@superadmin_required
def update_user_category(request, user_id):
    """Update user category/department"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        category = request.POST.get('category')

        user.department = category
        user.save(update_fields=['department'])

        logger.info(f"User {user.email} category updated to {category} by {request.user.email}")
        messages.success(request, 'User category updated successfully.')

    return redirect('manage_users')


@login_required
@superadmin_required
def update_user_level(request, user_id):
    """Update user level"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        try:
            level = int(request.POST.get('level', 0))
            if 0 <= level <= 5:
                user.level = level
                user.save(update_fields=['level'])

                logger.info(f"User {user.email} level updated to {level} by {request.user.email}")
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

    return redirect('manage_users')


@login_required
@superadmin_required
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        user.is_active = not user.is_active
        status_field = 'activated_at' if user.is_active else 'deactivated_at'
        timestamp = timezone.now()
        setattr(user, status_field, timestamp)
        user.save(update_fields=['is_active', status_field])

        status = 'activated' if user.is_active else 'deactivated'
        logger.info(f"User {user.email} {status} by {request.user.email}")
        log_activity_event(
            f'user.{status_field}',
            subject_user=user,
            performed_by=request.user,
            metadata={'status': status},
        )
        messages.success(request, f'User has been {status} successfully.')

    return redirect('manage_users')


@login_required
@superadmin_required
def edit_user(request, user_id):
    """Edit user profile"""
    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        changes = {}
        update_fields = set()
        profile_fields = []
        role_changed = False
        level_changed = False

        field_map = {
            'first_name': request.POST.get('first_name', user.first_name),
            'last_name': request.POST.get('last_name', user.last_name),
            'email': request.POST.get('email', user.email),
            'whatsapp_number': request.POST.get('whatsapp_number', user.whatsapp_number),
            'role': request.POST.get('role', user.role),
        }

        for field, new_value in field_map.items():
            old_value = getattr(user, field)
            if new_value != old_value:
                setattr(user, field, new_value)
                update_fields.add(field)
                changes[field] = {'old': old_value, 'new': new_value}

                if field not in {'email', 'role'}:
                    profile_fields.append(field)
                if field == 'role':
                    role_changed = True

        try:
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

        if update_fields:
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

            logger.info(f"User {user.email} profile updated by {request.user.email}")
            messages.success(request, 'User profile updated successfully.')
        else:
            messages.info(request, 'No changes detected for this user.')
        return redirect('manage_users')

    context = {
        'edit_user': user,
    }
    return render(request, 'edit_user.html', context)


@login_required
@superadmin_required
def pending_items(request):
    """Pending approvals page"""
    pending_users = []
    try:
        pending_qs = CustomUser.objects.filter(approval_status='pending').order_by('date_joined')
        pending_users = list(pending_qs)
    except Exception as e:
        logger.exception("Error fetching pending users: %s", e)

    context = {
        'pending_users': pending_users,
        'pending_total': len(pending_users),
    }
    return render(request, 'pending_items.html', context)


@login_required
@superadmin_required
def approve_user(request, user_id):
    """Approve user registration"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        role = request.POST.get('role')

        if not role or role not in dict(CustomUser.ROLE_CHOICES).keys():
            messages.error(request, 'Please select a valid role.')
            return redirect('pending_items')

        if role == 'user':
            messages.error(request, 'Cannot approve with "user" role. Please select a specific role.')
            return redirect('pending_items')

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

        logger.info(f"User {user.email} approved with role {role} by {request.user.email}")
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

    return redirect('pending_items')


@login_required
@superadmin_required
def reject_user(request, user_id):
    """Reject user registration"""
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, id=user_id)
        with transaction.atomic():
            user.approval_status = 'rejected'
            user.is_approved = False
            user.rejected_at = timezone.now()
            user.save()
        logger.info(f"User {user.email} rejected by {request.user.email}")
        log_activity_event(
            'user.rejected_at',
            subject_user=user,
            performed_by=request.user,
            metadata={'reason': request.POST.get('reason', 'not provided')},
        )
        messages.warning(request, 'User registration has been rejected.')
    return redirect('pending_items')





@login_required
@superadmin_required
def master_input(request):
    """Master Input Dashboard"""
    return render(request, 'master_input.html')


@login_required
@superadmin_required
def holiday_master(request):
    """Holiday Master - List all holidays"""
    try:
        raw_holidays = list(Holiday.objects.all().order_by('-created_at'))
        holidays = [
            holiday for holiday in raw_holidays
            if not getattr(holiday, 'is_deleted', False)
        ]

        context = {
            'holidays': holidays,
            'total_holidays': len(holidays),
        }

        return render(request, 'holiday_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading holiday master: {str(e)}")
        messages.error(request, 'Error loading holidays.')
        return render(request, 'holiday_master.html', {'holidays': []})


@login_required
@superadmin_required
def create_holiday(request):
    """Create a new holiday"""
    if request.method == 'POST':
        try:
            # Get form data
            holiday_name = request.POST.get('holiday_name', '').strip()
            holiday_type = request.POST.get('holiday_type', 'full_day')
            date_type = request.POST.get('date_type', 'single')
            description = request.POST.get('description', '').strip()
            
            # Validation
            if not holiday_name:
                messages.error(request, 'Holiday name is required.')
                return redirect('holiday_master')
            
            # Create holiday object
            with transaction.atomic():
                holiday = Holiday()
                holiday.holiday_name = holiday_name
                holiday.holiday_type = holiday_type
                holiday.date_type = date_type
                holiday.description = description
                holiday.created_by = request.user
                holiday.created_at = timezone.now()
                
                # Handle dates based on type
                if date_type == 'single':
                    date_str = request.POST.get('date')
                    if not date_str:
                        messages.error(request, 'Date is required.')
                        return redirect('holiday_master')
                    
                    holiday.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_date = holiday.date
                    end_date = holiday.date
                    
                else:  # consecutive
                    from_date_str = request.POST.get('from_date')
                    to_date_str = request.POST.get('to_date')
                    
                    if not from_date_str or not to_date_str:
                        messages.error(request, 'From date and To date are required.')
                        return redirect('holiday_master')
                    
                    holiday.from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                    holiday.to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
                    
                    if holiday.from_date > holiday.to_date:
                        messages.error(request, 'From date must be before To date.')
                        return redirect('holiday_master')
                    
                    start_date = holiday.from_date
                    end_date = holiday.to_date
                
                # Save to database first
                holiday.save()
                
                # Log activity
                log_activity_event(
                    'holiday.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'holiday_id': holiday.id,
                        'holiday_name': holiday_name,
                        'date_type': date_type,
                    },
                )
                
                # Sync to Google Calendar
                holiday.google_calendar_sync_started_at = timezone.now()
                holiday.save(update_fields=['google_calendar_sync_started_at'])
                
                log_activity_event(
                    'holiday.google_calendar_sync_started_at',
                    subject_user=None,
                    performed_by=None,
                    metadata={'holiday_id': holiday.id, 'performed_by': 'system'},
                )
                
                try:
                    calendar_service = GoogleCalendarService()
                    event_id = calendar_service.create_event(
                        holiday_name=holiday_name,
                        start_date=start_date,
                        end_date=end_date,
                        description=description,
                        holiday_type=holiday_type
                    )
                    
                    if event_id:
                        holiday.google_calendar_event_id = event_id
                        holiday.is_synced_to_calendar = True
                        holiday.google_calendar_synced_at = timezone.now()
                        holiday.save(update_fields=[
                            'google_calendar_event_id',
                            'is_synced_to_calendar',
                            'google_calendar_synced_at'
                        ])
                        
                        log_activity_event(
                            'holiday.google_calendar_synced_at',
                            subject_user=None,
                            performed_by=None,
                            metadata={
                                'holiday_id': holiday.id,
                                'event_id': event_id,
                                'performed_by': 'system',
                            },
                        )
                        
                        logger.info(f"Holiday '{holiday_name}' created and synced to Google Calendar")
                        messages.success(request, f'Holiday "{holiday_name}" created and synced to Google Calendar!')
                    else:
                        holiday.google_calendar_sync_failed_at = timezone.now()
                        holiday.save(update_fields=['google_calendar_sync_failed_at'])
                        
                        log_activity_event(
                            'holiday.google_calendar_sync_failed_at',
                            subject_user=None,
                            performed_by=None,
                            metadata={
                                'holiday_id': holiday.id,
                                'error': 'Failed to create calendar event',
                                'performed_by': 'system',
                            },
                        )
                        
                        logger.warning(f"Holiday created but failed to sync to Google Calendar")
                        messages.warning(request, f'Holiday "{holiday_name}" created but failed to sync to Google Calendar.')
                        
                except Exception as calendar_error:
                    holiday.google_calendar_sync_failed_at = timezone.now()
                    holiday.save(update_fields=['google_calendar_sync_failed_at'])
                    
                    log_activity_event(
                        'holiday.google_calendar_sync_failed_at',
                        subject_user=None,
                        performed_by=None,
                        metadata={
                            'holiday_id': holiday.id,
                            'error': str(calendar_error),
                            'performed_by': 'system',
                        },
                    )
                    
                    logger.error(f"Google Calendar sync error: {str(calendar_error)}")
                    messages.warning(request, f'Holiday "{holiday_name}" created but Google Calendar sync failed.')
            
            return redirect('holiday_master')
            
        except Exception as e:
            logger.exception(f"Error creating holiday: {str(e)}")
            messages.error(request, 'An error occurred while creating the holiday.')
            return redirect('holiday_master')
    
    return redirect('holiday_master')


@login_required
@superadmin_required
def edit_holiday(request, holiday_id):
    """Update an existing holiday"""
    if request.method != 'POST':
        return redirect('holiday_master')

    holiday = next(
        (
            item for item in Holiday.objects.all()
            if item.id == holiday_id and not getattr(item, 'is_deleted', False)
        ),
        None
    )

    if not holiday:
        messages.error(request, 'Holiday not found.')
        return redirect('holiday_master')

    try:
        holiday_name = request.POST.get('holiday_name', '').strip()
        holiday_type = request.POST.get('holiday_type', 'full_day')
        date_type = request.POST.get('date_type', 'single')
        description = request.POST.get('description', '').strip()

        if not holiday_name:
            messages.error(request, 'Holiday name is required.')
            return redirect('holiday_master')

        if date_type == 'single':
            date_str = request.POST.get('date')
            if not date_str:
                messages.error(request, 'Date is required for single-day holiday.')
                return redirect('holiday_master')
            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            end_date = start_date
        else:
            from_date_str = request.POST.get('from_date')
            to_date_str = request.POST.get('to_date')
            if not from_date_str or not to_date_str:
                messages.error(request, 'Both From and To dates are required for consecutive holidays.')
                return redirect('holiday_master')
            start_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                messages.error(request, 'From date must be before To date.')
                return redirect('holiday_master')

        with transaction.atomic():
            holiday.holiday_name = holiday_name
            holiday.holiday_type = holiday_type
            holiday.date_type = date_type
            holiday.description = description
            holiday.updated_by = request.user
            holiday.updated_at = timezone.now()

            if date_type == 'single':
                holiday.date = start_date
                holiday.from_date = None
                holiday.to_date = None
            else:
                holiday.date = None
                holiday.from_date = start_date
                holiday.to_date = end_date

            holiday.google_calendar_sync_started_at = timezone.now()
            holiday.google_calendar_sync_failed_at = None
            holiday.save()

            log_activity_event(
                'holiday.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'holiday_id': holiday.id,
                    'holiday_name': holiday.holiday_name,
                },
            )

            try:
                calendar_service = GoogleCalendarService()
                if holiday.google_calendar_event_id:
                    sync_ok = calendar_service.update_event(
                        holiday.google_calendar_event_id,
                        holiday_name,
                        start_date,
                        end_date,
                        description=description,
                        holiday_type=holiday_type,
                    )
                else:
                    event_id = calendar_service.create_event(
                        holiday_name=holiday_name,
                        start_date=start_date,
                        end_date=end_date,
                        description=description,
                        holiday_type=holiday_type,
                    )
                    sync_ok = bool(event_id)
                    if event_id:
                        holiday.google_calendar_event_id = event_id

                if sync_ok:
                    holiday.is_synced_to_calendar = True
                    holiday.google_calendar_synced_at = timezone.now()
                    holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_synced_at', 'google_calendar_event_id'])
                else:
                    holiday.is_synced_to_calendar = False
                    holiday.google_calendar_sync_failed_at = timezone.now()
                    holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_sync_failed_at'])
                    logger.warning("Holiday updated but failed to sync to Google Calendar.")

            except Exception as calendar_error:
                holiday.is_synced_to_calendar = False
                holiday.google_calendar_sync_failed_at = timezone.now()
                holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_sync_failed_at'])
                logger.error(f"Google Calendar sync error during update: {str(calendar_error)}")

        messages.success(request, f'Holiday "{holiday.holiday_name}" updated successfully.')

    except Exception as e:
        logger.exception(f"Error updating holiday: {str(e)}")
        messages.error(request, 'An error occurred while updating the holiday.')

    return redirect('holiday_master')


@login_required
@superadmin_required
def delete_holiday(request, holiday_id):
    """Permanently delete a holiday"""
    if request.method != 'POST':
        return redirect('holiday_master')

    holiday = Holiday.objects.filter(id=holiday_id).first()

    if not holiday:
        messages.error(request, 'Holiday not found.')
        return redirect('holiday_master')

    holiday_id_ref = holiday.id
    holiday_name_ref = holiday.holiday_name
    calendar_event_id = holiday.google_calendar_event_id

    try:
        with transaction.atomic():
            if calendar_event_id:
                try:
                    calendar_service = GoogleCalendarService()
                    calendar_service.delete_event(calendar_event_id)
                    logger.info(f"Holiday deleted from Google Calendar: {holiday_name_ref}")
                except Exception as calendar_error:
                    logger.error(f"Error deleting from Google Calendar: {str(calendar_error)}")

            holiday.delete()

            log_activity_event(
                'holiday.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'holiday_id': holiday_id_ref,
                    'holiday_name': holiday_name_ref,
                },
            )

        messages.success(request, f'Holiday "{holiday_name_ref}" deleted successfully.')

    except Exception as e:
        logger.exception(f"Error deleting holiday: {str(e)}")
        messages.error(request, 'An error occurred while deleting the holiday.')

    return redirect('holiday_master')


@login_required
@superadmin_required
def price_master(request):
    """Price Master - List all prices (Djongo-safe)"""
    try:
        raw_prices = list(PriceMaster.objects.all().order_by('-created_at'))
        prices = [
            price for price in raw_prices
            if not getattr(price, 'is_deleted', False)
        ]
        context = {
            'prices': prices,
            'total_prices': len(prices),
        }
        return render(request, 'price_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading price master: {str(e)}")
        messages.error(request, 'Error loading prices.')
        return render(request, 'price_master.html', {'prices': [], 'total_prices': 0})


@login_required
@superadmin_required
def create_price(request):
    """Create a new price entry (Djongo-safe)"""
    if request.method == 'POST':
        try:
            category = request.POST.get('category', '').strip()
            level = request.POST.get('level', '').strip()
            price_per_word = request.POST.get('price_per_word', '').strip()
            
            # Validation
            if not category or not level or not price_per_word:
                messages.error(request, 'All fields are required.')
                return redirect('price_master')
            
            try:
                price_per_word = float(price_per_word)
                if price_per_word <= 0:
                    messages.error(request, 'Price per word must be greater than 0.')
                    return redirect('price_master')
            except ValueError:
                messages.error(request, 'Invalid price format.')
                return redirect('price_master')
            
            # Check for existing combination (Djongo-safe approach)
            all_matching = list(PriceMaster.objects.filter(
                category=category,
                level=level
            ))
            
            # Filter in Python to avoid Djongo NOT operator issues
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Price already exists for {category} - {level}.')
                return redirect('price_master')
            
            with transaction.atomic():
                price_obj = PriceMaster()
                price_obj.category = category
                price_obj.level = level
                price_obj.price_per_word = price_per_word
                price_obj.created_by = request.user
                price_obj.created_at = timezone.now()
                price_obj.save()
                
                log_activity_event(
                    'price.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'price_id': str(price_obj.id),
                        'category': category,
                        'level': level,
                        'price_per_word': str(price_per_word),
                    },
                )
                
                logger.info(f"Price created for {category} - {level} by {request.user.email}")
                messages.success(request, f'Price for {category} - {level} created successfully!')
            
            return redirect('price_master')
            
        except Exception as e:
            logger.exception(f"Error creating price: {str(e)}")
            messages.error(request, 'An error occurred while creating the price.')
            return redirect('price_master')
    
    return redirect('price_master')


@login_required
@superadmin_required
def edit_price(request, price_id):
    """Update an existing price entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('price_master')
    
    # Djongo-safe lookup
    all_prices = list(PriceMaster.objects.filter(id=price_id))
    price_obj = next(
        (item for item in all_prices if not getattr(item, 'is_deleted', False)),
        None
    )
    
    if not price_obj:
        messages.error(request, 'Price entry not found.')
        return redirect('price_master')
    
    try:
        category = request.POST.get('category', '').strip()
        level = request.POST.get('level', '').strip()
        price_per_word = request.POST.get('price_per_word', '').strip()
        
        if not category or not level or not price_per_word:
            messages.error(request, 'All fields are required.')
            return redirect('price_master')
        
        try:
            price_per_word = float(price_per_word)
            if price_per_word <= 0:
                messages.error(request, 'Price per word must be greater than 0.')
                return redirect('price_master')
        except ValueError:
            messages.error(request, 'Invalid price format.')
            return redirect('price_master')
        
        # Check for duplicate combination (excluding current record) - Djongo-safe
        all_matching = list(PriceMaster.objects.filter(
            category=category,
            level=level
        ))
        
        # Filter in Python to avoid Djongo issues
        existing = next(
            (item for item in all_matching 
             if item.id != price_id and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Price already exists for {category} - {level}.')
            return redirect('price_master')
        
        with transaction.atomic():
            price_obj.category = category
            price_obj.level = level
            price_obj.price_per_word = price_per_word
            price_obj.updated_by = request.user
            price_obj.updated_at = timezone.now()
            price_obj.save()
            
            log_activity_event(
                'price.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'price_id': str(price_obj.id),
                    'category': category,
                    'level': level,
                    'price_per_word': str(price_per_word),
                },
            )
        
        messages.success(request, f'Price for {category} - {level} updated successfully.')
    except Exception as e:
        logger.exception(f"Error updating price: {str(e)}")
        messages.error(request, 'An error occurred while updating the price.')
    
    return redirect('price_master')


@login_required
@superadmin_required
def delete_price(request, price_id):
    """Delete a price entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('price_master')
    
    # Safe lookup
    price_obj = None
    try:
        price_obj = PriceMaster.objects.get(id=price_id)
    except PriceMaster.DoesNotExist:
        messages.error(request, 'Price entry not found.')
        return redirect('price_master')
    
    price_id_ref = str(price_obj.id)
    category_ref = price_obj.category
    level_ref = price_obj.level
    
    try:
        with transaction.atomic():
            price_obj.delete()
            
            log_activity_event(
                'price.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'price_id': price_id_ref,
                    'category': category_ref,
                    'level': level_ref,
                },
            )
        
        messages.success(request, f'Price for {category_ref} - {level_ref} deleted successfully.')
    except Exception as e:
        logger.exception(f"Error deleting price: {str(e)}")
        messages.error(request, 'An error occurred while deleting the price.')
    
    return redirect('price_master')


@login_required
@superadmin_required
def referencing_master(request):
    """Referencing Master - List all references (Djongo-safe)"""
    try:
        raw_references = list(ReferencingMaster.objects.all().order_by('-created_at'))
        references = [
            reference for reference in raw_references
            if not getattr(reference, 'is_deleted', False)
        ]
        context = {
            'references': references,
            'total_references': len(references),
        }
        return render(request, 'referencing_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading referencing master: {str(e)}")
        messages.error(request, 'Error loading references.')
        return render(request, 'referencing_master.html', {'references': [], 'total_references': 0})


@login_required
@superadmin_required
def create_reference(request):
    """Create a new reference entry (Djongo-safe)"""
    if request.method == 'POST':
        try:
            referencing_style = request.POST.get('referencing_style', '').strip()
            used_in = request.POST.get('used_in', '').strip()
            
            # Validation
            if not referencing_style or not used_in:
                messages.error(request, 'All fields are required.')
                return redirect('referencing_master')
            
            # Check for existing combination (Djongo-safe approach)
            all_matching = list(ReferencingMaster.objects.filter(
                referencing_style=referencing_style,
                used_in=used_in
            ))
            
            # Filter in Python to avoid Djongo NOT operator issues
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Reference already exists for {referencing_style} - {used_in}.')
                return redirect('referencing_master')
            
            with transaction.atomic():
                reference_obj = ReferencingMaster()
                reference_obj.referencing_style = referencing_style
                reference_obj.used_in = used_in
                reference_obj.created_by = request.user
                reference_obj.created_at = timezone.now()
                reference_obj.save()
                
                log_activity_event(
                    'reference.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'reference_id': str(reference_obj.id),
                        'referencing_style': referencing_style,
                        'used_in': used_in,
                    },
                )
                
                logger.info(f"Reference created for {referencing_style} - {used_in} by {request.user.email}")
                messages.success(request, f'Reference for {referencing_style} - {used_in} created successfully!')
            
            return redirect('referencing_master')
            
        except Exception as e:
            logger.exception(f"Error creating reference: {str(e)}")
            messages.error(request, 'An error occurred while creating the reference.')
            return redirect('referencing_master')
    
    return redirect('referencing_master')


@login_required
@superadmin_required
def edit_reference(request, reference_id):
    """Update an existing reference entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('referencing_master')
    
    # Djongo-safe lookup using helper function
    reference_obj = _find_reference_by_id(reference_id)
    
    if not reference_obj:
        messages.error(request, 'Reference entry not found.')
        return redirect('referencing_master')
    
    try:
        referencing_style = request.POST.get('referencing_style', '').strip()
        used_in = request.POST.get('used_in', '').strip()
        
        if not referencing_style or not used_in:
            messages.error(request, 'All fields are required.')
            return redirect('referencing_master')
        
        # Check for duplicate combination (excluding current record) - Djongo-safe
        all_matching = list(ReferencingMaster.objects.filter(
            referencing_style=referencing_style,
            used_in=used_in
        ))
        
        # Filter in Python to avoid Djongo issues
        existing = next(
            (item for item in all_matching 
             if str(item.id) != str(reference_id) and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Reference already exists for {referencing_style} - {used_in}.')
            return redirect('referencing_master')
        
        with transaction.atomic():
            reference_obj.referencing_style = referencing_style
            reference_obj.used_in = used_in
            reference_obj.updated_by = request.user
            reference_obj.updated_at = timezone.now()
            reference_obj.save()
            
            log_activity_event(
                'reference.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'reference_id': str(reference_obj.id),
                    'referencing_style': referencing_style,
                    'used_in': used_in,
                },
            )
        
        messages.success(request, f'Reference for {referencing_style} - {used_in} updated successfully.')
    except Exception as e:
        logger.exception(f"Error updating reference: {str(e)}")
        messages.error(request, 'An error occurred while updating the reference.')
    
    return redirect('referencing_master')


@login_required
@superadmin_required
def delete_reference(request, reference_id):
    """Delete a reference entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('referencing_master')
    
    # Safe lookup using helper function
    reference_obj = _find_reference_by_id(reference_id)
    
    if not reference_obj:
        messages.error(request, 'Reference entry not found.')
        return redirect('referencing_master')
    
    reference_id_ref = str(reference_obj.id)
    referencing_style_ref = reference_obj.referencing_style
    used_in_ref = reference_obj.used_in
    
    try:
        with transaction.atomic():
            reference_obj.delete()
            
            log_activity_event(
                'reference.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'reference_id': reference_id_ref,
                    'referencing_style': referencing_style_ref,
                    'used_in': used_in_ref,
                },
            )
        
        messages.success(request, f'Reference for {referencing_style_ref} - {used_in_ref} deleted successfully.')
    except Exception as e:
        logger.exception(f"Error deleting reference: {str(e)}")
        messages.error(request, 'An error occurred while deleting the reference.')
    
    return redirect('referencing_master')


@login_required
@superadmin_required
def academic_writing_master(request):
    """Academic Writing Master - List all writing styles (Djongo-safe)"""
    try:
        raw_writings = list(AcademicWritingMaster.objects.all().order_by('-created_at'))
        writings = [
            writing for writing in raw_writings
            if not getattr(writing, 'is_deleted', False)
        ]
        context = {
            'writings': writings,
            'total_writings': len(writings),
        }
        return render(request, 'academic_writing_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading academic writing master: {str(e)}")
        messages.error(request, 'Error loading writing styles.')
        return render(request, 'academic_writing_master.html', {'writings': [], 'total_writings': 0})


@login_required
@superadmin_required
def create_writing(request):
    """Create a new writing style entry (Djongo-safe)"""
    if request.method == 'POST':
        try:
            writing_style = request.POST.get('writing_style', '').strip()
            
            # Validation
            if not writing_style:
                messages.error(request, 'Writing style is required.')
                return redirect('academic_writing_master')
            
            # Check for existing writing style (Djongo-safe approach)
            all_matching = list(AcademicWritingMaster.objects.filter(
                writing_style=writing_style
            ))
            
            # Filter in Python to avoid Djongo NOT operator issues
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Writing style "{writing_style}" already exists.')
                return redirect('academic_writing_master')
            
            with transaction.atomic():
                writing_obj = AcademicWritingMaster()
                writing_obj.writing_style = writing_style
                writing_obj.created_by = request.user
                writing_obj.created_at = timezone.now()
                writing_obj.save()
                
                log_activity_event(
                    'writing.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'writing_id': str(writing_obj.id),
                        'writing_style': writing_style,
                    },
                )
                
                logger.info(f"Writing style '{writing_style}' created by {request.user.email}")
                messages.success(request, f'Writing style "{writing_style}" created successfully!')
            
            return redirect('academic_writing_master')
            
        except Exception as e:
            logger.exception(f"Error creating writing style: {str(e)}")
            messages.error(request, 'An error occurred while creating the writing style.')
            return redirect('academic_writing_master')
    
    return redirect('academic_writing_master')


@login_required
@superadmin_required
def edit_writing(request, writing_id):
    """Update an existing writing style entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('academic_writing_master')
    
    # Djongo-safe lookup using helper function
    writing_obj = _find_writing_by_id(writing_id)
    
    if not writing_obj:
        messages.error(request, 'Writing style not found.')
        return redirect('academic_writing_master')
    
    try:
        writing_style = request.POST.get('writing_style', '').strip()
        
        if not writing_style:
            messages.error(request, 'Writing style is required.')
            return redirect('academic_writing_master')
        
        # Check for duplicate (excluding current record) - Djongo-safe
        all_matching = list(AcademicWritingMaster.objects.filter(
            writing_style=writing_style
        ))
        
        # Filter in Python to avoid Djongo issues
        existing = next(
            (item for item in all_matching 
             if str(item.id) != str(writing_id) and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Writing style "{writing_style}" already exists.')
            return redirect('academic_writing_master')
        
        with transaction.atomic():
            writing_obj.writing_style = writing_style
            writing_obj.updated_by = request.user
            writing_obj.updated_at = timezone.now()
            writing_obj.save()
            
            log_activity_event(
                'writing.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'writing_id': str(writing_obj.id),
                    'writing_style': writing_style,
                },
            )
        
        messages.success(request, f'Writing style "{writing_style}" updated successfully.')
    except Exception as e:
        logger.exception(f"Error updating writing style: {str(e)}")
        messages.error(request, 'An error occurred while updating the writing style.')
    
    return redirect('academic_writing_master')


@login_required
@superadmin_required
def delete_writing(request, writing_id):
    """Delete a writing style entry (Djongo-safe)"""
    if request.method != 'POST':
        return redirect('academic_writing_master')
    
    # Safe lookup using helper function
    writing_obj = _find_writing_by_id(writing_id)
    
    if not writing_obj:
        messages.error(request, 'Writing style not found.')
        return redirect('academic_writing_master')
    
    writing_id_ref = str(writing_obj.id)
    writing_style_ref = writing_obj.writing_style
    
    try:
        with transaction.atomic():
            writing_obj.delete()
            
            log_activity_event(
                'writing.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'writing_id': writing_id_ref,
                    'writing_style': writing_style_ref,
                },
            )
        
        messages.success(request, f'Writing style "{writing_style_ref}" deleted successfully.')
    except Exception as e:
        logger.exception(f"Error deleting writing style: {str(e)}")
        messages.error(request, 'An error occurred while deleting the writing style.')
    
    return redirect('academic_writing_master')


def _find_writing_by_id(writing_id):
    """
    Djongo-safe lookup that supports integer and ObjectId primary keys.
    """
    if not writing_id:
        return None

    candidates = []
    try:
        candidates = list(AcademicWritingMaster.objects.filter(id=writing_id))
    except Exception:
        candidates = []

    if not candidates:
        # Try int conversion
        if isinstance(writing_id, str) and writing_id.isdigit():
            try:
                candidates = list(AcademicWritingMaster.objects.filter(id=int(writing_id)))
            except Exception:
                candidates = []

    if not candidates:
        # Try ObjectId conversion
        try:
            object_id = ObjectId(str(writing_id))
            candidates = list(AcademicWritingMaster.objects.filter(id=object_id))
        except (InvalidId, Exception):
            candidates = []

    return next(
        (item for item in candidates if not getattr(item, 'is_deleted', False)),
        None
    )
