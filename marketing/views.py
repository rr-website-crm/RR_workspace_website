from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from accounts.models import CustomUser
import logging

logger = logging.getLogger('marketing')


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
@role_required(['marketing'])
def marketing_dashboard(request):
    """Marketing Dashboard - Overview of all marketing activities"""
    
    user = request.user
    
    # Get statistics (placeholder - replace with actual job model queries when available)
    stats = {
        'total_jobs': 0,  # Total jobs created by this marketing user
        'pending_jobs': 0,  # Jobs awaiting allocation
        'allocated_jobs': 0,  # Jobs allocated to writers
        'completed_jobs': 0,  # Completed jobs
        'hold_jobs': 0,  # Jobs on hold
        'query_jobs': 0,  # Jobs with queries
    }
    
    # Recent activities placeholder
    recent_activities = []
    
    context = {
        'user': user,
        'stats': stats,
        'recent_activities': recent_activities,
        'today_date': timezone.now(),
    }
    
    logger.info(f"Marketing dashboard accessed by: {user.email}")
    return render(request, 'marketing/marketing_dashboard.html', context)


@login_required
@role_required(['marketing'])
def create_job(request):
    """Create a new job"""
    
    if request.method == 'POST':
        # Job creation logic will go here
        # This is a placeholder for now
        messages.success(request, 'Job created successfully!')
        logger.info(f"Job created by: {request.user.email}")
        return redirect('my_jobs')
    
    context = {
        'user': request.user,
    }
    
    return render(request, 'marketing/create_job.html', context)


@login_required
@role_required(['marketing'])
def my_jobs(request):
    """View all jobs created by current marketing user"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/my_jobs.html', context)


@login_required
@role_required(['marketing'])
def hold_jobs(request):
    """View jobs on hold"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/hold_jobs.html', context)


@login_required
@role_required(['marketing'])
def query_jobs(request):
    """View jobs with queries"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/query_jobs.html', context)


@login_required
@role_required(['marketing'])
def unallocated_jobs(request):
    """View unallocated jobs"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/unallocated_jobs.html', context)


@login_required
@role_required(['marketing'])
def completed_jobs(request):
    """View completed jobs"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/completed_jobs.html', context)


@login_required
@role_required(['marketing'])
def allocated_jobs(request):
    """View allocated jobs"""
    
    # Placeholder - replace with actual job queries
    jobs = []
    
    context = {
        'user': request.user,
        'jobs': jobs,
    }
    
    return render(request, 'marketing/allocated_jobs.html', context)