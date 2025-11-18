# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.utils import timezone
# from django.http import JsonResponse
# from django.db import transaction
# from accounts.models import CustomUser, LoginLog
# import logging

# logger = logging.getLogger('superadmin')


# def superadmin_required(view_func):
#     """Decorator to check if user is superadmin"""
#     def wrapper(request, *args, **kwargs):
#         if not request.user.is_authenticated:
#             messages.error(request, 'Please login to access this page.')
#             return redirect('login')
#         if request.user.role != 'superadmin':
#             messages.error(request, 'You do not have permission to access this page.')
#             return redirect('home_dashboard')
#         return view_func(request, *args, **kwargs)
#     return wrapper


# @login_required
# @superadmin_required
# def superadmin_dashboard(request):
#     """SuperAdmin Dashboard (Djongo-safe implementation)"""

#     # Safely initialise values
#     total_users = 0
#     pending_approvals = 0
#     total_approved = 0
#     role_data = []
#     total_active = 0

#     try:
#         # Basic counts (these are simple queries and should be safe)
#         total_users = CustomUser.objects.filter(is_approved=True).exclude(role='user').count()
#         pending_approvals = CustomUser.objects.filter(is_approved=False, approval_status='pending').count()
#         total_approved = CustomUser.objects.filter(is_approved=True).count()

#         # Get today's active users by role (avoid complex DB aggregation for Djongo)
#         today = timezone.now().date()
#         logs = LoginLog.objects.filter(
#             login_time__date=today,
#             is_active=True
#         ).select_related('user')

#         # Python-level grouping (MongoDB-friendly)
#         role_count_map = {}
#         for log in logs:
#             try:
#                 role = log.user.role or 'user'
#             except Exception:
#                 # If select_related failed for any reason, skip this log entry
#                 continue
#             if role == 'user':
#                 # skip generic 'user' role if you don't want to show it
#                 continue
#             role_count_map[role] = role_count_map.get(role, 0) + 1

#         # Build role_data list for template
#         role_data = [{'role': r, 'count': c} for r, c in role_count_map.items()]
#         total_active = sum(role_count_map.values())

#     except Exception as e:
#         # Log error but keep dashboard rendering (prevents 500 on DB driver errors)
#         logger.exception("Error while preparing superadmin dashboard data: %s", e)
#         # values remain default (0 / empty) so template will show zeros/empty state

#     context = {
#         'total_users': total_users,
#         'total_active': total_active,
#         'pending_approvals': pending_approvals,
#         'total_approved': total_approved,
#         'role_active_counts': role_data,
#     }

#     return render(request, 'superadmin_dashboard.html', context)


# @login_required
# @superadmin_required
# def role_details(request, role):
#     """Get role-specific active users for today"""

#     users_data = []
#     try:
#         today = timezone.now().date()
#         # Fetch today's login logs for the role
#         login_logs = LoginLog.objects.filter(
#             user__role=role,
#             login_time__date=today,
#             is_active=True
#         ).select_related('user').order_by('login_time')

#         for log in login_logs:
#             users_data.append({
#                 'employee_id': log.employee_id or 'N/A',
#                 'name': log.user.get_full_name(),
#                 'email': log.user.email,
#                 'login_time': log.login_time.strftime('%I:%M %p')
#             })

#     except Exception as e:
#         logger.exception("Error fetching role details for %s: %s", role, e)
#         # return empty list in error case

#     return JsonResponse({'users': users_data})


# @login_required
# @superadmin_required
# def manage_users(request):
#     """Manage all users"""
#     users = []
#     total_users = 0
#     pending_count = 0
#     approved_count = 0

#     try:
#         users_qs = CustomUser.objects.filter(is_approved=True).exclude(role='user').order_by('-date_joined')
#         users = users_qs
#         total_users = users_qs.count()
#         pending_count = CustomUser.objects.filter(is_approved=False, approval_status='pending').count()
#         approved_count = total_users
#     except Exception as e:
#         logger.exception("Error fetching manage users data: %s", e)

#     context = {
#         'users': users,
#         'total_users': total_users,
#         'pending_count': pending_count,
#         'approved_count': approved_count,
#     }

#     return render(request, 'manage_users.html', context)


# @login_required
# @superadmin_required
# def update_user_role(request, user_id):
#     """Update user role"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)
#         new_role = request.POST.get('role')

#         if new_role in dict(CustomUser.ROLE_CHOICES).keys():
#             old_role = user.role
#             user.role = new_role
#             user.save()

#             logger.info(f"User {user.email} role updated from {old_role} to {new_role} by {request.user.email}")
#             messages.success(request, f'User role updated successfully to {new_role}.')
#         else:
#             messages.error(request, 'Invalid role selected.')

#     return redirect('manage_users')


# @login_required
# @superadmin_required
# def update_user_category(request, user_id):
#     """Update user category/department"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)
#         category = request.POST.get('category')

#         user.department = category
#         user.save()

#         logger.info(f"User {user.email} category updated to {category} by {request.user.email}")
#         messages.success(request, 'User category updated successfully.')

#     return redirect('manage_users')


# @login_required
# @superadmin_required
# def update_user_level(request, user_id):
#     """Update user level"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)
#         try:
#             level = int(request.POST.get('level', 0))
#             if 0 <= level <= 5:
#                 user.level = level
#                 user.save()

#                 logger.info(f"User {user.email} level updated to {level} by {request.user.email}")
#                 messages.success(request, 'User level updated successfully.')
#             else:
#                 messages.error(request, 'Level must be between 0 and 5.')
#         except ValueError:
#             messages.error(request, 'Invalid level value.')

#     return redirect('manage_users')


# @login_required
# @superadmin_required
# def toggle_user_status(request, user_id):
#     """Toggle user active status"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)
#         user.is_active = not user.is_active
#         user.save()

#         status = 'activated' if user.is_active else 'deactivated'
#         logger.info(f"User {user.email} {status} by {request.user.email}")
#         messages.success(request, f'User has been {status} successfully.')

#     return redirect('manage_users')


# @login_required
# @superadmin_required
# def edit_user(request, user_id):
#     """Edit user profile"""
#     user = get_object_or_404(CustomUser, id=user_id)

#     if request.method == 'POST':
#         # Update user details
#         user.first_name = request.POST.get('first_name', user.first_name)
#         user.last_name = request.POST.get('last_name', user.last_name)
#         user.email = request.POST.get('email', user.email)
#         user.whatsapp_number = request.POST.get('whatsapp_number', user.whatsapp_number)
#         user.role = request.POST.get('role', user.role)

#         try:
#             level = int(request.POST.get('level', 0))
#             if 0 <= level <= 5:
#                 user.level = level
#         except ValueError:
#             pass

#         user.save()

#         logger.info(f"User {user.email} profile updated by {request.user.email}")
#         messages.success(request, 'User profile updated successfully.')
#         return redirect('manage_users')

#     context = {
#         'edit_user': user,
#     }

#     return render(request, 'edit_user.html', context)


# @login_required
# @superadmin_required
# def pending_items(request):
#     """Pending approvals page"""
#     pending_users = []
#     try:
#         pending_users_qs = list(CustomUser.objects
#         .filter(is_approved=False, approval_status='pending')
#         .order_by('date_joined'))
#         pending_users = pending_users_qs
#         pending_total = len(pending_users_qs)

#     except Exception as e:
#         logger.exception("Error fetching pending users: %s", e)

#     context = {
#         'pending_users': pending_users,
#     }

#     return render(request, 'pending_items.html', context)


# @login_required
# @superadmin_required
# def approve_user(request, user_id):
#     """Approve user registration"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)
#         role = request.POST.get('role')

#         if not role or role not in dict(CustomUser.ROLE_CHOICES).keys():
#             messages.error(request, 'Please select a valid role.')
#             return redirect('pending_items')

#         if role == 'user':
#             messages.error(request, 'Cannot approve with "user" role. Please select a specific role.')
#             return redirect('pending_items')

#         with transaction.atomic():
#             user.role = role
#             user.is_approved = True
#             user.approval_status = 'approved'
#             user.level = 0  # Initial level
#             user.save()

#         logger.info(f"User {user.email} approved with role {role} by {request.user.email}")
#         messages.success(request, f'User approved successfully as {role}.')

#     return redirect('pending_items')


# @login_required
# @superadmin_required
# def reject_user(request, user_id):
#     """Reject user registration"""
#     if request.method == 'POST':
#         user = get_object_or_404(CustomUser, id=user_id)

#         with transaction.atomic():
#             user.is_approved = False
#             user.approval_status = 'rejected'
#             user.save()

#         logger.info(f"User {user.email} rejected by {request.user.email}")
#         messages.warning(request, 'User registration has been rejected.')

#     return redirect('pending_items')




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
