# allocate/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.core.paginator import Paginator
from accounts.models import CustomUser
from marketing.models import Job as MarketingJob, log_job_activity
from .models import (
    Job, TaskAllocation, WriterProfile, ProcessTeamProfile,
    JobQuery, AllocationHistory, CountryBankingResource
)
import logging
from datetime import datetime, timedelta, date
import pytz


PORTAL_STATUS_DISPLAY = {
    'draft': 'Draft',
    'pending': 'Unallocated',
    'unallocated': 'Unallocated',
    'allocated': 'Allocated',
    'in_progress': 'Allocated',
    'active': 'Active',
    'hold': 'Hold',
    'query': 'Query',
    'completed': 'Closed',
    'close': 'Closed',
    'cancelled': 'Closed',
    'cancel_complete': 'Closed',
}

STATUS_FILTER_MAP = {
    'unallocated': ['pending', 'unallocated', 'draft'],
    'allocated': ['allocated', 'in_progress', 'active'],
    'closed': ['completed', 'cancelled', 'close', 'cancel_complete'],
}

IST_TZ = pytz.timezone('Asia/Kolkata')


TASK_CONFIG = {
    'content_creation': {
        'label': 'Content Creation',
        'description': 'Assign writers and manage the content production window.',
        'status_choices': [
            ('in_progress', 'In Progress'),
            ('hold', 'Hold'),
            ('completed', 'Close'),
        ],
        'allowed_roles': ['writer'],
        'dependent_on': None,
    },
    'ai_plag': {
        'label': 'AI & Plagiarism',
        'description': 'Process team review after content is produced.',
        'status_choices': [
            ('in_progress', 'In Progress'),
            ('hold', 'Hold'),
            ('completed', 'Close'),
        ],
        'allowed_roles': ['process'],
        'dependent_on': 'content_creation',
    },
    'decoration': {
        'label': 'Decoration',
        'description': 'Formatting & delivery polish across teams.',
        'status_choices': [
            ('in_progress', 'In Progress'),
            ('hold', 'Hold'),
            ('completed', 'Close'),
        ],
        'allowed_roles': ['writer', 'process'],
        'dependent_on': 'ai_plag',
    },
}


def _parse_datetime_input(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _recent_load_count(user_id, task_type):
    threshold = timezone.now() - timedelta(hours=4)
    return TaskAllocation.objects.filter(
        allocated_to_id=user_id,
        task_type=task_type,
        allocated_at__gte=threshold
    ).count()


def _sync_allocator_status(job):
    allocations = list(job.task_allocations.all())
    if not allocations:
        return
    if all(
        alloc.status == 'completed'
        for alloc in allocations
        if alloc.allocated_to_id
    ):
        new_status = 'completed'
    elif any(
        alloc.task_type == 'content_creation' and alloc.status == 'in_progress'
        for alloc in allocations
    ):
        new_status = 'in_progress'
    elif any(alloc.allocated_to_id for alloc in allocations):
        new_status = 'allocated'
    else:
        new_status = 'pending'
    if job.status != new_status:
        job.status = new_status
        job.save(update_fields=['status'])


def _derive_allocator_recent_status(marketing_job, allocator_job):
    if allocator_job and allocator_job.status == 'cancelled':
        return 'Cancel'
    if allocator_job:
        tasks = list(allocator_job.task_allocations.all())
        if tasks and all(
            task.status == 'completed'
            for task in tasks
            if task.allocated_to_id
        ):
            return 'Close'
        content_task = next(
            (task for task in tasks if task.task_type == 'content_creation'),
            None
        )
        if content_task and content_task.status == 'in_progress':
            return 'InProgress'
        if any(task.allocated_to_id for task in tasks):
            return 'Assigned'
    if marketing_job.status in {'cancelled', 'cancel_complete'}:
        return 'Cancel'
    return 'Unallocated'

logger = logging.getLogger('allocator')


def role_required(allowed_roles):
    """Decorator to restrict access based on user role"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('home_dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


@login_required
@role_required(['allocator'])
def all_projects(request):
    """List all marketing jobs with filters and pagination."""
    search_query = (request.GET.get('q') or '').strip()
    status_filter = (request.GET.get('status') or 'all').lower()
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    jobs_qs = MarketingJob.objects.filter(
        status__iexact='unallocated'
    ).select_related('created_by').order_by('-created_at')

    if search_query:
        jobs_qs = jobs_qs.filter(
            Q(job_id__icontains=search_query) |
            Q(system_id__icontains=search_query) |
            Q(topic__icontains=search_query)
        )

    status_values = STATUS_FILTER_MAP.get(status_filter)
    if status_values:
        jobs_qs = jobs_qs.filter(status__in=status_values)

    def _parse_date(value, is_end=False):
        if not value:
            return None
        try:
            date_obj = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None
        if is_end:
            date_obj = date_obj.replace(hour=23, minute=59, second=59)
        aware_dt = IST_TZ.localize(date_obj)
        return aware_dt.astimezone(timezone.utc)

    start_dt = _parse_date(start_date_str)
    end_dt = _parse_date(end_date_str, is_end=True)

    if start_dt:
        jobs_qs = jobs_qs.filter(created_at__gte=start_dt)
    if end_dt:
        jobs_qs = jobs_qs.filter(created_at__lte=end_dt)

    paginator = Paginator(jobs_qs, 15)
    jobs_page = paginator.get_page(request.GET.get('page'))

    for job in jobs_page:
        job.portal_status = PORTAL_STATUS_DISPLAY.get(
            job.status,
            (job.get_status_display() if hasattr(job, 'get_status_display') else job.status.replace('_', ' ')).title()
        )
        job.marketing_owner = job.created_by.get_full_name() if job.created_by else 'System'

    preserved_query = request.GET.copy()
    if 'page' in preserved_query:
        preserved_query.pop('page')

    context = {
        'user': request.user,
        'jobs_page': jobs_page,
        'filters': {
            'q': search_query,
            'status': status_filter,
            'start_date': start_date_str,
            'end_date': end_date_str,
        },
        'status_options': [
            ('all', 'All'),
            ('unallocated', 'Unallocated'),
            ('allocated', 'Allocated'),
            ('closed', 'Closed'),
        ],
        'preserved_query': preserved_query.urlencode(),
    }

    return render(request, 'allocator/all_projects.html', context)


@login_required
@role_required(['allocator'])
def all_projects_detail(request, system_id):
    """View marketing job details for allocator overview."""
    job = get_object_or_404(
        MarketingJob.objects.select_related('created_by').prefetch_related('attachments'),
        system_id=system_id
    )

    job.portal_status = PORTAL_STATUS_DISPLAY.get(
        job.status,
        (job.get_status_display() if hasattr(job, 'get_status_display') else job.status.replace('_', ' ')).title()
    )

    context = {
        'user': request.user,
        'job': job,
        'attachments': job.attachments.all(),
    }
    return render(request, 'allocator/all_project_detail.html', context)


@login_required
@role_required(['allocator'])
def allocator_dashboard(request):
    """Allocator Dashboard - Overview of all allocation activities"""

    user = request.user
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    tz = timezone.get_current_timezone()

    def normalize_datetime(value):
        if not value:
            return now
        if timezone.is_naive(value):
            return timezone.make_aware(value, tz)
        return value

    jobs_all = list(Job.objects.only(
        'id', 'masking_id', 'topic', 'word_count', 'status', 'created_at', 'priority', 'job_category', 'deadline'
    ))
    allocations_raw = list(TaskAllocation.objects.values('id', 'job_id', 'task_type', 'status'))
    jobs_by_id = {job.id: job for job in jobs_all}
    allocations_by_id = {entry['id']: entry for entry in allocations_raw}

    role_counts = {'writer': 0, 'process': 0}
    for role, is_active in CustomUser.objects.filter(
        role__in=role_counts.keys()
    ).values_list('role', 'is_active'):
        if is_active:
            role_counts[role] += 1

    marketing_total_jobs = MarketingJob.objects.count()
    marketing_pending_jobs = MarketingJob.objects.filter(
        status__in=['pending', 'unallocated', 'draft']
    ).count()
    marketing_new_jobs = MarketingJob.objects.filter(
        created_at__gte=week_ago
    ).count()

    stats = {
        'total_jobs': marketing_total_jobs,
        'pending_allocation': marketing_pending_jobs,
        'assigned_jobs': sum(1 for alloc in allocations_raw if alloc['status'] == 'in_progress'),
        'new_jobs': marketing_new_jobs,
        'in_progress': sum(1 for job in jobs_all if job.status == 'in_progress'),
        'cancelled': sum(1 for job in jobs_all if job.status == 'cancelled'),
        'hold': sum(1 for job in jobs_all if job.status == 'hold'),
        'process_jobs': sum(
            1 for alloc in allocations_raw
            if alloc['task_type'] == 'ai_plag' and alloc['status'] == 'in_progress'
        ),
        'completed': sum(1 for job in jobs_all if job.status == 'completed'),
        'total_writers': role_counts['writer'],
        'total_process_team': role_counts['process'],
    }

    jobs = sorted(
        jobs_all,
        key=lambda job: normalize_datetime(job.created_at),
        reverse=True
    )[:10]

    # Recent marketing jobs (24h window, unallocated)
    recent_window_start = now - timedelta(hours=24)
    marketing_recent_qs = MarketingJob.objects.filter(
        created_at__gte=recent_window_start,
        status__iexact='unallocated'
    ).select_related('created_by').order_by('-created_at')

    system_ids = [job.system_id for job in marketing_recent_qs]
    allocator_jobs_map = {
        item.masking_id: item
        for item in Job.objects.filter(masking_id__in=system_ids).prefetch_related('task_allocations__allocated_to')
    }

    recent_jobs = []
    for idx, marketing_job in enumerate(marketing_recent_qs, 1):
        allocator_job = allocator_jobs_map.get(marketing_job.system_id)
        derived_status = _derive_allocator_recent_status(marketing_job, allocator_job)
        raw_deadline = marketing_job.deadline or marketing_job.strict_deadline or marketing_job.expected_deadline
        deadline_value = raw_deadline
        deadline_has_time = isinstance(raw_deadline, datetime)
        if isinstance(raw_deadline, datetime):
            if timezone.is_naive(raw_deadline):
                deadline_value = timezone.make_aware(raw_deadline)
            deadline_value = timezone.localtime(deadline_value)
        detail_url = (
            reverse('view_job_details', args=[allocator_job.id])
            if allocator_job else
            reverse('allocator_all_project_detail', args=[marketing_job.system_id])
        )
        status_label = derived_status or 'Unallocated'
        recent_jobs.append({
            'sl_no': idx,
            'system_id': marketing_job.system_id,
            'job_id': marketing_job.job_id,
            'topic': marketing_job.topic or '--',
            'word_count': marketing_job.word_count or '--',
            'deadline': deadline_value,
            'deadline_has_time': deadline_has_time,
            'marketing_owner': marketing_job.created_by.get_full_name() if marketing_job.created_by else 'System',
            'category': marketing_job.get_category_display() if marketing_job.category else '--',
            'status': derived_status,
            'status_display': status_label,
            'allocator_job_id': getattr(allocator_job, 'id', None),
            'row_href': detail_url,
            'view_url': detail_url,
        })

    raw_activities = list(
        AllocationHistory.objects.values(
            'id',
            'task_allocation_id',
            'action',
            'timestamp',
            'changed_by_id',
            'new_user_id',
        ).order_by('-timestamp')[:5]
    )

    user_ids = {
        entry['changed_by_id']
        for entry in raw_activities
        if entry['changed_by_id']
    } | {
        entry['new_user_id']
        for entry in raw_activities
        if entry['new_user_id']
    }

    users_lookup = {
        user.id: user
        for user in CustomUser.objects.filter(id__in=user_ids).only('first_name', 'last_name', 'email')
    }

    action_labels = dict(AllocationHistory.ACTION_CHOICES)
    recent_activities = []
    for entry in raw_activities:
        allocation = allocations_by_id.get(entry['task_allocation_id'])
        job = jobs_by_id.get(allocation['job_id']) if allocation else None

        changed_by = users_lookup.get(entry['changed_by_id'])
        new_user = users_lookup.get(entry['new_user_id'])

        recent_activities.append({
            'action_label': action_labels.get(entry['action'], entry['action'].replace('_', ' ').title()),
            'job_masking_id': getattr(job, 'masking_id', 'N/A'),
            'timestamp': normalize_datetime(entry['timestamp']),
            'changed_by_name': changed_by.get_full_name() if changed_by else 'System',
            'new_user_name': new_user.get_full_name() if new_user else None,
        })

    context = {
        'user': user,
        'stats': stats,
        'jobs': jobs,
        'recent_jobs': recent_jobs,
        'recent_activities': recent_activities,
        'today_date': now,
    }

    logger.info(f"Allocator dashboard accessed by: {user.email}")
    return render(request, 'allocator/allocator_dashboard.html', context)


@login_required
@role_required(['allocator'])
def pending_allocation(request):
    """View jobs pending allocation"""
    
    pending_jobs_qs = list(Job.objects.filter(status='pending').order_by('-created_at'))
    creator_ids = {job.created_by_id for job in pending_jobs_qs if getattr(job, 'created_by_id', None)}
    creators = {
        user.id: user
        for user in CustomUser.objects.filter(id__in=creator_ids).only('first_name', 'last_name')
    }

    pending_jobs = []
    categories = set()
    high_priority = 0
    for job in pending_jobs_qs:
        categories.add(job.job_category)
        if job.priority in {'urgent', 'high'}:
            high_priority += 1
        created_by_name = creators.get(job.created_by_id).get_full_name() if creators.get(job.created_by_id) else 'System'
        pending_jobs.append({
            'id': job.id,
            'masking_id': job.masking_id,
            'topic': job.topic,
            'word_count': job.word_count,
            'max_word_limit': job.max_word_limit,
            'deadline': job.deadline,
            'priority': job.priority,
            'priority_label': job.get_priority_display(),
            'job_category': job.job_category,
            'status_label': job.get_status_display(),
            'created_by': created_by_name,
        })

    pending_stats = {
        'total': len(pending_jobs),
        'categories': len(categories),
        'high_priority': high_priority,
    }
    
    context = {
        'user': request.user,
        'pending_jobs': pending_jobs,
        'pending_stats': pending_stats,
    }
    
    return render(request, 'allocator/pending_allocation.html', context)


@login_required
@role_required(['allocator'])
def allocate_job(request, job_id):
    """Allocate job to writers and process team"""
    
    job = get_object_or_404(Job, id=job_id)
    
    def _parse_datetime_value(raw_value):
        if not raw_value:
            return None
        dt = parse_datetime(raw_value)
        if not dt:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt

    def _assign_allocation(task_type, member, start_dt, end_dt, reason_label):
        allocation, created = TaskAllocation.objects.get_or_create(
            job=job,
            task_type=task_type,
            defaults={
                'allocated_to': member,
                'allocated_by': request.user,
                'start_date_time': start_dt,
                'end_date_time': end_dt,
                'status': 'pending',
            }
        )

        if created:
            AllocationHistory.objects.create(
                task_allocation=allocation,
                action='allocated',
                new_user=member,
                changed_by=request.user,
                reason=f"{reason_label} assigned",
            )
        else:
            AllocationHistory.objects.create(
                task_allocation=allocation,
                action='reallocated',
                previous_user=allocation.allocated_to,
                new_user=member,
                changed_by=request.user,
                reason=f"{reason_label} updated",
            )
            allocation.allocated_to = member
            allocation.allocated_by = request.user
            allocation.status = 'pending'
        allocation.start_date_time = start_dt
        allocation.end_date_time = end_dt
        allocation.save()
        return allocation

    if request.method == 'POST':
        # Handle allocation
        try:
            # Get form data
            content_writer_id = request.POST.get('content_writer')
            content_start = request.POST.get('content_start_datetime')
            content_end = request.POST.get('content_end_datetime')
            content_start_dt = _parse_datetime_value(content_start)
            content_end_dt = _parse_datetime_value(content_end)
            
            ai_plag_member_id = request.POST.get('ai_plag_member')
            ai_start = request.POST.get('ai_start_datetime')
            ai_end = request.POST.get('ai_end_datetime')
            ai_start_dt = _parse_datetime_value(ai_start)
            ai_end_dt = _parse_datetime_value(ai_end)
            
            decoration_member_id = request.POST.get('decoration_member')
            decoration_start = request.POST.get('decoration_start_datetime')
            decoration_end = request.POST.get('decoration_end_datetime')
            decoration_start_dt = _parse_datetime_value(decoration_start)
            decoration_end_dt = _parse_datetime_value(decoration_end)
            
            # Allocate Content Creation
            if content_writer_id:
                content_writer = CustomUser.objects.get(id=content_writer_id, role='writer')
                content_allocation = _assign_allocation(
                    'content_creation',
                    content_writer,
                    content_start_dt,
                    content_end_dt,
                    'Content Creation'
                )

                # Update writer profile
                writer_profile = WriterProfile.objects.get(user=content_writer)
                writer_profile.current_jobs += 1
                writer_profile.current_words += job.word_count
                writer_profile.total_jobs_assigned += 1
                writer_profile.save()
            
            # Allocate AI & Plag Check
            if ai_plag_member_id:
                ai_member = CustomUser.objects.get(id=ai_plag_member_id, role='process')
                _assign_allocation(
                    'ai_plag',
                    ai_member,
                    ai_start_dt,
                    ai_end_dt,
                    'AI & Plagiarism'
                )
            
            # Allocate Decoration
            if decoration_member_id:
                decoration_member = CustomUser.objects.get(id=decoration_member_id)
                _assign_allocation(
                    'decoration',
                    decoration_member,
                    decoration_start_dt,
                    decoration_end_dt,
                    'Decoration'
                )
            
            # Update job status
            job.status = 'allocated'
            comment_status = request.POST.get('marketing_comment_status')
            allocator_comment = request.POST.get('allocator_comment', '').strip()
            if comment_status in {'pending', 'approved', 'rejected'}:
                job.marketing_comment_status = comment_status
            if allocator_comment:
                job.allocator_comment = allocator_comment
            job.allocated_by = request.user
            job.allocated_at = timezone.now()
            job.save()
            
            messages.success(request, f'Job {job.masking_id} allocated successfully!')
            logger.info(f"Job {job.masking_id} allocated by {request.user.email}")
            return redirect('pending_allocation')
            
        except Exception as e:
            logger.error(f"Error allocating job {job_id}: {str(e)}")
            messages.error(request, f'Error allocating job: {str(e)}')
    
    writer_profiles = list(WriterProfile.objects.filter(is_available=True))
    writer_user_ids = [profile.user_id for profile in writer_profiles]
    writer_users = {}
    for user in CustomUser.objects.filter(
        id__in=writer_user_ids,
        role='writer'
    ).only('id', 'first_name', 'last_name', 'email', 'is_active'):
        if user.is_active:
            writer_users[user.id] = user

    writer_details = []
    for profile in writer_profiles:
        user = writer_users.get(profile.user_id)
        if not user:
            continue

        if job.job_category == 'IT' and not profile.is_it_writer:
            continue

        can_accept, reason = profile.can_accept_job(job)
        engagement = profile.get_engagement_status()

        writer_details.append({
            'user': user,
            'profile': profile,
            'can_accept': can_accept,
            'reason': reason,
            'engagement': engagement,
        })

    process_profiles = list(ProcessTeamProfile.objects.filter(is_available=True))
    process_user_ids = [profile.user_id for profile in process_profiles]
    process_users = {}
    for user in CustomUser.objects.filter(
        id__in=process_user_ids,
        role='process'
    ).only('id', 'first_name', 'last_name', 'email', 'is_active'):
        if user.is_active:
            process_users[user.id] = user

    available_process_team = []
    for profile in process_profiles:
        user = process_users.get(profile.user_id)
        if not user:
            continue
        available_process_team.append({
            'user': user,
            'profile': profile,
        })

    CATEGORY_CONFIG = [
        {'label': 'IT', 'flag': 'is_it_writer', 'color': '#2196F3'},
        {'label': 'Non-IT', 'flag': 'is_nonit_writer', 'color': '#9C27B0'},
        {'label': 'Finance', 'flag': 'is_finance_writer', 'color': '#4CAF50'},
    ]
    capacity_lookup = {}
    writer_capacity = []
    for cfg in CATEGORY_CONFIG:
        stats = {
            'label': cfg['label'],
            'color': cfg['color'],
            'total': 0,
            'available': 0,
            'engaged': 0,
            'overloaded': 0,
            'sunday_off': 0,
            'holiday': 0,
            'current_jobs': 0,
            'job_capacity': 0,
            'current_words': 0,
            'word_capacity': 0,
        }
        writer_capacity.append(stats)
        capacity_lookup[cfg['flag']] = stats

    for profile in writer_profiles:
        availability_flag = profile.is_available and not (
            profile.is_sunday_off or profile.is_on_holiday or profile.is_overloaded
        )
        current_jobs = getattr(profile, 'current_jobs', 0) or 0
        max_jobs = getattr(profile, 'max_jobs', 0) or 1
        current_words = getattr(profile, 'current_words', 0) or 0
        max_words = getattr(profile, 'max_words', 0) or max(job.word_count, 1)

        writer_categories = [
            ('is_it_writer', profile.is_it_writer),
            ('is_nonit_writer', profile.is_nonit_writer),
            ('is_finance_writer', profile.is_finance_writer),
        ]

        for flag, is_member in writer_categories:
            if not is_member:
                continue
            stats = capacity_lookup.get(flag)
            if not stats:
                continue
            stats['total'] += 1
            stats['current_jobs'] += current_jobs
            stats['job_capacity'] += max_jobs
            stats['current_words'] += current_words
            stats['word_capacity'] += max_words
            if availability_flag:
                stats['available'] += 1
            if current_jobs > 0:
                stats['engaged'] += 1
            if profile.is_overloaded:
                stats['overloaded'] += 1
            if profile.is_sunday_off:
                stats['sunday_off'] += 1
            if profile.is_on_holiday:
                stats['holiday'] += 1

    for stats in writer_capacity:
        job_cap = stats['job_capacity'] or 1
        word_cap = stats['word_capacity'] or 1
        stats['job_load_pct'] = min(100, int(round((stats['current_jobs'] / job_cap) * 100)))
        stats['word_load_pct'] = min(100, int(round((stats['current_words'] / word_cap) * 100)))

    existing_allocations = list(
        TaskAllocation.objects.filter(
            job=job,
            task_type__in=['content_creation', 'ai_plag', 'decoration']
        )
    )
    allocation_user_ids = {alloc.allocated_to_id for alloc in existing_allocations if alloc.allocated_to_id}
    allocation_users = {
        user.id: user
        for user in CustomUser.objects.filter(id__in=allocation_user_ids).only('id', 'first_name', 'last_name', 'email', 'role')
    }
    task_info = {}
    for alloc in existing_allocations:
        user = allocation_users.get(alloc.allocated_to_id)
        task_info[alloc.task_type] = {
            'assigned_id': alloc.allocated_to_id,
            'assigned_name': user.get_full_name() if user else 'Not assigned',
            'start': alloc.start_date_time,
            'end': alloc.end_date_time,
            'status': alloc.status,
            'role': user.role if user else None,
        }

    existing_writer_ids = {item['user'].id for item in writer_details}
    content_task = task_info.get('content_creation')
    if content_task and content_task['assigned_id'] and content_task['assigned_id'] not in existing_writer_ids:
        extra_user = allocation_users.get(content_task['assigned_id']) or CustomUser.objects.filter(id=content_task['assigned_id']).first()
        extra_profile = WriterProfile.objects.filter(user_id=content_task['assigned_id']).first()
        if extra_user and extra_profile:
            writer_details.append({
                'user': extra_user,
                'profile': extra_profile,
                'can_accept': False,
                'reason': 'Currently unavailable',
                'engagement': extra_profile.get_engagement_status(),
            })

    process_ids = {member['user'].id for member in available_process_team}
    for key in ['ai_plag', 'decoration']:
        task = task_info.get(key)
        if task and task['assigned_id'] and task['role'] == 'process' and task['assigned_id'] not in process_ids:
            extra_user = allocation_users.get(task['assigned_id']) or CustomUser.objects.filter(id=task['assigned_id']).first()
            extra_profile = ProcessTeamProfile.objects.filter(user_id=task['assigned_id']).first()
            if extra_user and extra_profile:
                available_process_team.append({
                    'user': extra_user,
                    'profile': extra_profile,
                })
                process_ids.add(task['assigned_id'])

    has_available_content = any(item['can_accept'] for item in writer_details)
    has_available_process = any(member['profile'].is_available for member in available_process_team)
    has_available_decoration = has_available_content or has_available_process

    context = {
        'user': request.user,
        'job': job,
        'writer_details': writer_details,
        'available_process_team': available_process_team,
        'can_have_query': job.can_have_query(),
        'writer_capacity': writer_capacity,
        'task_content': task_info.get('content_creation'),
        'task_ai': task_info.get('ai_plag'),
        'task_decoration': task_info.get('decoration'),
        'has_available_content': has_available_content,
        'has_available_process': has_available_process,
        'has_available_decoration': has_available_decoration,
    }

    return render(request, 'allocator/allocate_job.html', context)


@login_required
@role_required(['allocator'])
def assigned_jobs(request):
    """View all assigned jobs"""
    
    jobs = Job.objects.filter(
        status__in=['allocated', 'in_progress']
    ).select_related('created_by', 'allocated_by').order_by('-allocated_at')
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'allocator/assigned_jobs.html', context)


@login_required
@role_required(['allocator'])
def in_progress_jobs(request):
    """View jobs in progress"""
    
    jobs_qs = Job.objects.filter(status='in_progress').select_related(
        'created_by', 'allocated_by'
    ).prefetch_related('task_allocations__allocated_to').order_by('-updated_at')

    jobs = list(jobs_qs)
    now = timezone.now()
    today_local = timezone.localtime(now)
    due_today_count = 0
    overdue_count = 0

    for job in jobs:
        allocations = list(job.task_allocations.all())
        total_allocations = len(allocations)
        completed_allocations = sum(1 for alloc in allocations if alloc.status == 'completed')

        job.total_task_allocations = total_allocations
        job.completed_task_allocations = completed_allocations
        job.task_progress_percent = int(round((completed_allocations / total_allocations) * 100)) if total_allocations else 0

        deadline = job.deadline
        if deadline:
            deadline_local = timezone.localtime(deadline) if timezone.is_aware(deadline) else deadline
            if deadline_local.date() == today_local.date():
                due_today_count += 1
            if deadline_local < today_local:
                overdue_count += 1
    
    context = {
        'user': request.user,
        'jobs': jobs,
        'total_jobs': len(jobs),
        'due_today_count': due_today_count,
        'overdue_count': overdue_count,
        'today_date': today_local,
    }
    
    return render(request, 'allocator/in_progress_jobs.html', context)


@login_required
@role_required(['allocator'])
def cancel_jobs(request):
    """View and manage cancelled jobs"""
    
    if request.method == 'POST':
        job_id = request.POST.get('job_id')
        reason = request.POST.get('reason')
        
        try:
            job = Job.objects.get(id=job_id)
            job.status = 'cancelled'
            job.allocator_comment = reason
            job.save()
            
            # Free up writer resources
            for allocation in job.task_allocations.filter(task_type='content_creation'):
                if allocation.allocated_to:
                    writer_profile = allocation.allocated_to.writer_profile
                    writer_profile.current_jobs = max(0, writer_profile.current_jobs - 1)
                    writer_profile.current_words = max(0, writer_profile.current_words - job.word_count)
                    writer_profile.save()
            
            messages.success(request, f'Job {job.masking_id} cancelled successfully!')
            logger.info(f"Job {job.masking_id} cancelled by {request.user.email}")
            
        except Job.DoesNotExist:
            messages.error(request, 'Job not found!')
    
    jobs = Job.objects.filter(status='cancelled').select_related(
        'created_by'
    ).order_by('-updated_at')
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'allocator/cancel_jobs.html', context)


@login_required
@role_required(['allocator'])
def hold_jobs_allocator(request):
    """View and manage hold jobs"""
    
    if request.method == 'POST':
        action = request.POST.get('action')
        job_id = request.POST.get('job_id')
        comment = request.POST.get('comment', '')
        
        try:
            job = Job.objects.get(id=job_id)
            
            if action == 'hold':
                job.status = 'hold'
                job.allocator_comment = comment
                job.save()
                messages.success(request, f'Job {job.masking_id} put on hold!')
                
            elif action == 'activate':
                # Only marketing can activate hold jobs
                if request.user.role == 'marketing':
                    job.status = 'pending'
                    job.save()
                    messages.success(request, f'Job {job.masking_id} activated!')
                else:
                    messages.error(request, 'Only marketing team can activate hold jobs!')
            
            logger.info(f"Job {job.masking_id} status changed to {job.status} by {request.user.email}")
            
        except Job.DoesNotExist:
            messages.error(request, 'Job not found!')
    
    jobs = Job.objects.filter(status='hold').select_related(
        'created_by'
    ).order_by('-updated_at')
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'allocator/hold_jobs.html', context)


@login_required
@role_required(['allocator', 'process'])
def process_jobs(request):
    """View jobs in process team"""

    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        try:
            task = TaskAllocation.objects.get(
                id=task_id,
                task_type='ai_plag'
            )
        except TaskAllocation.DoesNotExist:
            messages.error(request, 'Task not found.')
            return redirect('process_jobs')

        writer_link = (request.POST.get('writer_final_link') or '').strip()
        summary_link = (request.POST.get('summary_link') or '').strip()
        process_link = (request.POST.get('process_final_link') or '').strip()
        temperature_score_raw = (request.POST.get('temperature_score') or '').strip()
        mark_complete = request.POST.get('mark_completed') == 'true'

        if writer_link:
            task.writer_final_link = writer_link
        if summary_link:
            task.summary_link = summary_link
        if process_link:
            task.process_final_link = process_link

        if temperature_score_raw:
            try:
                score = float(temperature_score_raw)
                task.temperature_score = score
                task.temperature_matched = score >= 70
            except ValueError:
                messages.error(request, 'Temperature score must be numeric.')
                return redirect('process_jobs')

        if mark_complete:
            if not task.writer_final_link or not task.process_final_link:
                messages.error(request, 'Provide both writer and process file links before marking complete.')
                return redirect('process_jobs')
            if task.temperature_score is None:
                messages.error(request, 'Please run a temperature check before marking complete.')
                return redirect('process_jobs')
            if not task.temperature_matched:
                messages.error(request, 'Temperature score below threshold. Cannot mark complete.')
                return redirect('process_jobs')
            task.status = 'completed'
            task.completed_at = timezone.now()
            task.job.status = 'decoration'
            task.job.save(update_fields=['status'])

        task.save()
        messages.success(request, 'Process task updated successfully.')
        logger.info(f"Process task {task.id} updated by {request.user.email}")
        return redirect('process_jobs')

    tasks = TaskAllocation.objects.filter(
        task_type='ai_plag',
        status__in=['pending', 'in_progress']
    ).select_related('job', 'allocated_to').order_by('-allocated_at')
    
    context = {
        'user': request.user,
        'tasks': tasks,
    }
    
    return render(request, 'allocator/process_jobs.html', context)


@login_required
@role_required(['allocator'])
def completed_jobs_allocator(request):
    """View completed jobs"""
    
    jobs = Job.objects.filter(status='completed').select_related(
        'created_by', 'allocated_by'
    ).order_by('-updated_at')
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'allocator/completed_jobs.html', context)


@login_required
@role_required(['allocator'])
def all_writers(request):
    """View all writers with their engagement status"""
    
    writers = CustomUser.objects.filter(
        role='writer'
    ).select_related('writer_profile').order_by('first_name')
    
    writer_data = []
    total_it_writers = 0
    total_nonit_writers = 0
    total_finance_writers = 0
    available_writers = 0
    engaged_writers = 0

    for writer in writers:
        if not writer.is_active:
            continue
        try:
            profile = writer.writer_profile
            engagement = profile.get_engagement_status()
            specializations = {
                'it': bool(profile.is_it_writer),
                'non_it': bool(profile.is_nonit_writer),
                'finance': bool(profile.is_finance_writer),
            }
            availability_status = 'Available' if profile.is_available and not (
                profile.is_sunday_off or profile.is_on_holiday or profile.is_overloaded
            ) else 'Not Available'

            assigned_category = (writer.department or '').strip()
            normalized_category = assigned_category.lower()
            if normalized_category == 'it':
                total_it_writers += 1
            elif normalized_category in {'non-it', 'nonit'}:
                total_nonit_writers += 1
            elif normalized_category == 'finance':
                total_finance_writers += 1
            if availability_status == 'Available':
                available_writers += 1
            if engagement.get('engaged_jobs', 0) > 0:
                engaged_writers += 1
            
            writer_data.append({
                'user': writer,
                'profile': profile,
                'engagement': engagement,
                'specializations': specializations,
                'availability_status': availability_status,
                'assigned_category': assigned_category or ''
            })
        except WriterProfile.DoesNotExist:
            # Create profile if doesn't exist
            WriterProfile.objects.create(user=writer)
    
    context = {
        'user': request.user,
        'writer_data': writer_data,
        'writer_stats': {
            'total_it': total_it_writers,
            'total_nonit': total_nonit_writers,
            'total_finance': total_finance_writers,
            'available': available_writers,
            'engaged': engaged_writers,
        },
    }
    
    return render(request, 'allocator/all_writers.html', context)


@login_required
@role_required(['allocator'])
def all_process_team(request):
    """View all process team members"""
    
    process_members = CustomUser.objects.filter(
        role='process'
    ).select_related('process_profile').order_by('first_name')
    
    process_data = []
    for member in process_members:
        if not member.is_active:
            continue
        try:
            profile = member.process_profile
            current_jobs = max(getattr(profile, 'current_jobs', 0), 0)
            max_jobs = max(getattr(profile, 'max_jobs', 1), 1)
            load_percent = min(100, int(round((current_jobs / max_jobs) * 100)))

            if current_jobs >= max_jobs:
                load_color_start, load_color_end = '#F44336', '#D32F2F'
            elif current_jobs >= 0.7 * max_jobs:
                load_color_start, load_color_end = '#FF9800', '#F57C00'
            else:
                load_color_start, load_color_end = '#4CAF50', '#388E3C'

            process_data.append({
                'user': member,
                'profile': profile,
                'current_load': f"{current_jobs}/{max_jobs}",
                'availability': 'Available' if profile.is_available else 'Not Available',
                'is_sunday_off': profile.is_sunday_off,
                'is_on_holiday': profile.is_on_holiday,
                'load_percent': load_percent,
                'load_color_start': load_color_start,
                'load_color_end': load_color_end,
            })
        except ProcessTeamProfile.DoesNotExist:
            ProcessTeamProfile.objects.create(user=member)
    
    context = {
        'user': request.user,
        'process_data': process_data,
    }
    
    return render(request, 'allocator/all_process_team.html', context)


@login_required
@role_required(['allocator'])
def switch_writer(request, allocation_id):
    """Switch writer for a task"""
    
    if request.method == 'POST':
        try:
            allocation = TaskAllocation.objects.get(id=allocation_id)
            new_writer_id = request.POST.get('new_writer_id')
            reason = request.POST.get('reason', '')
            
            old_writer = allocation.allocated_to
            new_writer = CustomUser.objects.get(id=new_writer_id, role='writer')
            
            # Update old writer profile
            if old_writer and old_writer.role == 'writer':
                old_profile = old_writer.writer_profile
                old_profile.current_jobs = max(0, old_profile.current_jobs - 1)
                old_profile.current_words = max(0, old_profile.current_words - allocation.job.word_count)
                old_profile.save()
            
            # Update new writer profile
            new_profile = new_writer.writer_profile
            new_profile.current_jobs += 1
            new_profile.current_words += allocation.job.word_count
            new_profile.total_jobs_assigned += 1
            new_profile.save()
            
            # Update allocation
            allocation.allocated_to = new_writer
            allocation.save()
            
            # Log history
            AllocationHistory.objects.create(
                task_allocation=allocation,
                action='switched',
                previous_user=old_writer,
                new_user=new_writer,
                changed_by=request.user,
                reason=reason
            )
            
            messages.success(request, 'Writer switched successfully!')
            logger.info(f"Writer switched for allocation {allocation_id} by {request.user.email}")
            
            return redirect('assigned_jobs')
            
        except Exception as e:
            logger.error(f"Error switching writer: {str(e)}")
            messages.error(request, f'Error switching writer: {str(e)}')
    
    return redirect('assigned_jobs')


@login_required
@role_required(['allocator', 'writer', 'process'])
def view_job_details(request, job_id):
    """View detailed job information with all allocations"""
    
    job = get_object_or_404(Job.objects.select_related('created_by', 'allocated_by'), id=job_id)
    job_category_upper = (job.job_category or '').upper()

    marketing_job = None
    initial_form_data = []
    final_form_data = []
    attachment_entries = []

    if job.masking_id:
        marketing_job = MarketingJob.objects.filter(
            system_id=job.masking_id
        ).select_related('created_by').prefetch_related('attachments').first()

    if marketing_job:
        initial_form_data = [
            {'label': 'Instruction', 'value': marketing_job.instruction or '--'},
            {'label': 'Category', 'value': marketing_job.get_category_display() if marketing_job.category else '--'},
            {'label': 'Level', 'value': marketing_job.get_level_display() if marketing_job.level else '--'},
            {'label': 'Created At', 'value': marketing_job.created_at},
        ]
        final_form_data = [
            {'label': 'Topic', 'value': marketing_job.topic or '--'},
            {'label': 'Word Count', 'value': marketing_job.word_count or '--'},
            {'label': 'Deadline', 'value': marketing_job.deadline},
            {'label': 'Writing Style', 'value': marketing_job.get_writing_style_display() if marketing_job.writing_style else '--'},
            {'label': 'Referencing', 'value': marketing_job.get_referencing_style_display() if marketing_job.referencing_style else '--'},
        ]
        for attachment in marketing_job.attachments.all():
            attachment_entries.append({
                'source': 'Marketing',
                'name': attachment.original_filename,
                'url': attachment.file.url,
                'uploaded_at': attachment.uploaded_at,
            })

    if job.attachment:
        attachment_entries.append({
            'source': 'Allocator',
            'name': job.attachment.name.split('/')[-1],
            'url': job.attachment.url,
            'uploaded_at': job.created_at,
        })
    if job.structure_file:
        attachment_entries.append({
            'source': 'Allocator',
            'name': job.structure_file.name.split('/')[-1],
            'url': job.structure_file.url,
            'uploaded_at': job.created_at,
        })

    # Prepare task data
    task_allocations = list(
        TaskAllocation.objects.filter(job=job).select_related('allocated_to').order_by('task_type')
    )
    allocation_map = {alloc.task_type: alloc for alloc in task_allocations}

    writer_qs = CustomUser.objects.filter(role='writer', is_active=True).select_related('writer_profile')
    if job_category_upper == 'IT':
        writer_qs = writer_qs.filter(writer_profile__is_it_writer=True)
    writer_options = []
    for writer in writer_qs:
        load_count = _recent_load_count(writer.id, 'content_creation')
        writer_options.append({
            'id': writer.id,
            'label': writer.get_full_name() or writer.email,
            'load': load_count,
            'available': getattr(writer.writer_profile, 'is_available', True) if hasattr(writer, 'writer_profile') else True,
        })

    process_qs = CustomUser.objects.filter(role='process', is_active=True).select_related('process_profile')
    process_options = []
    for member in process_qs:
        load_count = _recent_load_count(member.id, 'ai_plag')
        process_options.append({
            'id': member.id,
            'label': member.get_full_name() or member.email,
            'load': load_count,
            'available': getattr(member.process_profile, 'is_available', True) if hasattr(member, 'process_profile') else True,
        })

    decoration_options = process_options + writer_options
    options_map = {
        'content_creation': writer_options,
        'ai_plag': process_options,
        'decoration': decoration_options,
    }

    task_panels = []
    for code, config in TASK_CONFIG.items():
        allocation = allocation_map.get(code)
        dependent_ready = True
        dependent_code = config.get('dependent_on')
        if dependent_code:
            dep_alloc = allocation_map.get(dependent_code)
            dependent_ready = bool(dep_alloc and dep_alloc.allocated_to_id)
        task_panels.append({
            'code': code,
            'label': config['label'],
            'description': config['description'],
            'allocation': allocation,
            'options': options_map.get(code, []),
            'status_choices': config['status_choices'],
            'locked': not dependent_ready and code != 'content_creation',
            'dependent_label': TASK_CONFIG.get(dependent_code, {}).get('label') if dependent_code else None,
        })

    # GET or POST handling
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_task':
            if request.user.role != 'allocator':
                messages.error(request, 'Only allocators can update task assignments.')
                return redirect('view_job_details', job_id=job_id)
            task_type = request.POST.get('task_type')
            config = TASK_CONFIG.get(task_type)
            if not config:
                messages.error(request, 'Unknown task type.')
                return redirect('view_job_details', job_id=job_id)

            dependent_code = config.get('dependent_on')
            if dependent_code:
                prerequisite = TaskAllocation.objects.filter(job=job, task_type=dependent_code).first()
                if not prerequisite or not prerequisite.allocated_to_id:
                    messages.error(request, f'{config["label"]} unlocks after assigning {TASK_CONFIG[dependent_code]["label"]}.')
                    return redirect('view_job_details', job_id=job_id)

            status_value = request.POST.get('status')
            allowed_statuses = {choice[0] for choice in config['status_choices']}
            if status_value not in allowed_statuses:
                messages.error(request, 'Invalid status option.')
                return redirect('view_job_details', job_id=job_id)

            member_ids = request.POST.getlist('assigned_members')
            member = None
            if member_ids:
                try:
                    member = CustomUser.objects.get(id=int(member_ids[0]))
                except (ValueError, CustomUser.DoesNotExist):
                    messages.error(request, 'Selected team member was not found.')
                    return redirect('view_job_details', job_id=job_id)

                if member.role not in config['allowed_roles']:
                    messages.error(request, f"{config['label']} can only be assigned to {', '.join(config['allowed_roles'])} roles.")
                    return redirect('view_job_details', job_id=job_id)

                if task_type == 'content_creation' and job_category_upper == 'IT':
                    profile = getattr(member, 'writer_profile', None)
                    if not profile or not profile.is_it_writer:
                        messages.error(request, 'IT jobs require IT-certified writers.')
                        return redirect('view_job_details', job_id=job_id)

            start_dt = _parse_datetime_input(request.POST.get('start_datetime')) or timezone.now()
            end_dt = _parse_datetime_input(request.POST.get('end_datetime')) or (start_dt + timedelta(hours=2))
            if end_dt <= start_dt:
                messages.error(request, 'End date must be after start date.')
                return redirect('view_job_details', job_id=job_id)

            allocation, created = TaskAllocation.objects.get_or_create(
                job=job,
                task_type=task_type,
                defaults={
                    'allocated_by': request.user,
                    'allocated_to': member,
                    'start_date_time': start_dt,
                    'end_date_time': end_dt,
                    'status': status_value,
                }
            )
            if not created:
                allocation.allocated_by = request.user
                allocation.allocated_to = member
                allocation.start_date_time = start_dt
                allocation.end_date_time = end_dt
                allocation.status = status_value
            allocation.save()
            _sync_allocator_status(job)
            messages.success(request, f'{config["label"]} updated successfully.')
            logger.info(f"{config['label']} updated for {job.masking_id} by {request.user.email}")
            return redirect('view_job_details', job_id=job_id)

        elif action == 'close_job':
            all_completed = all(
                panel['allocation'] and panel['allocation'].status == 'completed'
                for panel in task_panels
            )
            if not all_completed:
                messages.error(request, 'All tasks must be closed before marking the job as complete.')
                return redirect('view_job_details', job_id=job_id)
            job.status = 'completed'
            job.save(update_fields=['status'])
            if marketing_job:
                marketing_job.status = 'completed'
                marketing_job.save(update_fields=['status'])
                log_job_activity(
                    marketing_job,
                    'job.completed',
                    performed_by=request.user,
                    metadata={'source': 'allocator_portal'}
                )
            messages.success(request, 'Job marked as closed.')
            return redirect('view_job_details', job_id=job_id)

        elif action == 'cancel_job':
            cancel_reason = (request.POST.get('cancel_reason') or '').strip()
            if len(cancel_reason) < 10:
                messages.error(request, 'Please provide a brief justification (at least 10 characters).')
                return redirect('view_job_details', job_id=job_id)
            job.status = 'cancelled'
            job.allocator_comment = cancel_reason
            job.save(update_fields=['status', 'allocator_comment'])
            if marketing_job:
                marketing_job.status = 'cancelled'
                marketing_job.save(update_fields=['status'])
                log_job_activity(
                    marketing_job,
                    'job.cancelled',
                    performed_by=request.user,
                    metadata={'reason': cancel_reason, 'source': 'allocator_portal'}
                )
            messages.success(request, 'Job cancelled successfully.')
            return redirect('view_job_details', job_id=job_id)

        elif action == 'raise_query':
            if not job.can_have_query():
                messages.error(request, 'Queries are not enabled for this job (requires degree 1-5 with software support).')
                return redirect('view_job_details', job_id=job_id)

            query_text = (request.POST.get('query_text') or '').strip()
            if len(query_text) < 10:
                messages.error(request, 'Please provide a detailed query (minimum 10 characters).')
                return redirect('view_job_details', job_id=job_id)

            JobQuery.objects.create(
                job=job,
                task_allocation=None,
                raised_by=request.user,
                query_text=query_text,
                status='open'
            )
            messages.success(request, 'Query submitted successfully and is now pending review.')
            logger.info(f"Query raised for job {job.masking_id} by {request.user.email}")
            return redirect('view_job_details', job_id=job_id)

    queries = JobQuery.objects.filter(job=job).select_related(
        'raised_by', 'resolved_by'
    ).order_by('-created_at')

    all_tasks_completed = all(
        panel['allocation'] and panel['allocation'].status == 'completed'
        for panel in task_panels
    )

    context = {
        'user': request.user,
        'job': job,
        'marketing_job': marketing_job,
        'initial_form_data': initial_form_data,
        'final_form_data': final_form_data,
        'attachments': attachment_entries,
        'task_panels': task_panels,
        'queries': queries,
        'can_have_query': job.can_have_query(),
        'today_date': timezone.now(),
        'all_tasks_completed': all_tasks_completed,
        'job_category_upper': job_category_upper,
    }
    
    return render(request, 'allocator/view_job_details.html', context)


@login_required
@role_required(['allocator'])
@require_http_methods(["POST"])
def approve_comment(request, job_id):
    """Approve or modify marketing comment"""
    
    try:
        job = Job.objects.get(id=job_id)
        modified_comment = request.POST.get('allocator_comment')
        approve = request.POST.get('approve') == 'true'
        
        job.allocator_comment = modified_comment
        job.allocator_comment_approved = approve
        job.save()
        
        messages.success(request, 'Comment updated successfully!')
        logger.info(f"Comment for job {job.masking_id} updated by {request.user.email}")
        
        return JsonResponse({'success': True})
        
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Job not found'}, status=404)




@login_required
@role_required(['allocator'])
def all_project_detail(request, system_id):
    """Simple detail view for marketing job in allocator portal."""
    job = get_object_or_404(MarketingJob.objects.select_related('created_by'), system_id=system_id)

    def _display_status(value):
        if not value:
            return 'Unknown'
        value_lower = value.lower()
        if value_lower in ('completed', 'cancelled'):
            return 'Closed'
        if value_lower in ('allocated', 'in_progress'):
            return 'Allocated'
        if value_lower in ('unallocated', 'pending'):
            return 'Unallocated'
        return value.replace('_', ' ').title()

    context = {
        'job': job,
        'status_display': _display_status(job.status),
    }
    return render(request, 'allocator/all_project_detail.html', context)







@login_required
@role_required(['allocator'])
def all_projects(request):
    """
    List all marketing jobs for allocator with search, status, and date range filters.
    """
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip().lower()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    status_buckets = {
        'unallocated': ['unallocated', 'pending'],
        'allocated': ['allocated', 'in_progress'],
        'closed': ['completed', 'cancelled'],
        'hold': ['hold'],
        'active': ['active'],
        'query': ['query'],
        'draft': ['draft'],
    }

    jobs_qs = MarketingJob.objects.select_related('created_by').all().order_by('-created_at')

    if search:
        jobs_qs = jobs_qs.filter(
            Q(system_id__icontains=search)
            | Q(job_id__icontains=search)
            | Q(topic__icontains=search)
        )

    if status_filter:
        if status_filter in status_buckets:
            jobs_qs = jobs_qs.filter(status__in=status_buckets[status_filter])
        else:
            jobs_qs = jobs_qs.filter(status__iexact=status_filter)

    def parse_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return None

    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)
    if start_dt:
        jobs_qs = jobs_qs.filter(created_at__date__gte=start_dt)
    if end_dt:
        jobs_qs = jobs_qs.filter(created_at__date__lte=end_dt)

    paginator = Paginator(jobs_qs, 25)
    page_number = request.GET.get('page')
    jobs_page = paginator.get_page(page_number)

    status_options = [
        ('', 'All Statuses'),
        ('unallocated', 'Unallocated'),
        ('allocated', 'Allocated'),
        ('closed', 'Closed'),
        ('hold', 'Hold'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('in_progress', 'In Progress'),
        ('query', 'Query'),
        ('draft', 'Draft'),
        ('completed', 'Completed'),
        ('pending', 'Pending'),
    ]

    context = {
        'user': request.user,
        'jobs': jobs_page,
        'search': search,
        'status_filter': status_filter,
        'start_date': start_date,
        'end_date': end_date,
        'status_options': status_options,
        'total_jobs': jobs_qs.count(),
    }
    return render(request, 'allocator/all_projects.html', context)
