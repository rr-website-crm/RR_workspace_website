# writer/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.http import JsonResponse
from .models import WriterProject, ProjectIssue, ProjectComment, WriterStatistics
from accounts.models import CustomUser
import logging

logger = logging.getLogger('writer')


def writer_required(view_func):
    """Decorator to ensure user is a writer"""
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'writer':
            messages.error(request, 'Access denied. Writer privileges required.')
            return redirect('home_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@writer_required
def writer_dashboard(request):
    """Writer Dashboard View"""
    writer = request.user
    
    # Get or create writer statistics (djongo-safe)
    stats, created = WriterStatistics.fetch_or_create_single(writer)
    if created or (timezone.now() - stats.last_updated).seconds > 300:  # Update every 5 mins
        stats.update_stats()
    
    # Get all projects for the writer
    all_projects = WriterProject.objects.filter(writer=writer)
    
    # Count by status
    total_projects = all_projects.count()
    pending_tasks = all_projects.filter(status='pending').count()
    in_progress = all_projects.filter(status='in_progress').count()
    completed = all_projects.filter(status='completed').count()
    issues = all_projects.filter(status='issues').count()
    hold = all_projects.filter(status='hold').count()
    
    # Recent projects for "My Tasks" table
    recent_projects = all_projects.exclude(status='completed').order_by('-created_at')[:5]
    
    # Calculate project status breakdown for chart
    status_breakdown = {
        'completed': completed,
        'in_progress': in_progress,
        'hold': hold,
        'pending': pending_tasks,
    }

    def percent(value, total):
        if not total:
            return 0
        return min(100, int(round((value / total) * 100)))

    progress_percent = {
        'completed': percent(completed, total_projects),
        'in_progress': percent(in_progress, total_projects),
        'hold': percent(hold, total_projects),
        'pending': percent(pending_tasks, total_projects),
    }

    context = {
        'total_projects': total_projects,
        'pending_tasks': pending_tasks,
        'in_progress': in_progress,
        'completed': completed,
        'issues': issues,
        'hold': hold,
        'recent_projects': recent_projects,
        'status_breakdown': status_breakdown,
        'stats': stats,
        'progress_percent': progress_percent,
    }
    
    return render(request, 'writer/writer_dashboard.html', context)


@login_required
@writer_required
def all_projects(request):
    """View all projects assigned to writer"""
    writer = request.user
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    projects = WriterProject.objects.filter(writer=writer)
    
    # Apply filters
    if status_filter:
        projects = projects.filter(status=status_filter)
    
    if search_query:
        projects = projects.filter(
            Q(job_id__icontains=search_query) |
            Q(topic__icontains=search_query)
        )
    
    # Order by created date
    projects = projects.order_by('-created_at')
    
    context = {
        'projects': projects,
        'status_filter': status_filter,
        'search_query': search_query,
        'STATUS_CHOICES': WriterProject.STATUS_CHOICES,
    }
    
    return render(request, 'writer/all_projects.html', context)


@login_required
@writer_required
def project_detail(request, project_id):
    """View project details"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    # Get comments and issues
    comments = project.comments.all().order_by('-created_at')
    issues = project.issues.all().order_by('-created_at')
    
    context = {
        'project': project,
        'comments': comments,
        'issues': issues,
    }
    
    return render(request, 'writer/project_detail.html', context)


@login_required
@writer_required
def start_project(request, project_id):
    """Mark project as in progress"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    if project.status == 'pending':
        project.mark_in_progress()
        messages.success(request, f'Project {project.job_id} marked as In Progress.')
        logger.info(f"Writer {writer.email} started project {project.job_id}")
    else:
        messages.warning(request, 'Project cannot be started from current status.')
    
    return redirect('project_detail', project_id=project.id)


@login_required
@writer_required
def submit_project(request, project_id):
    """Submit completed project"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    if request.method == 'POST':
        submission_file = request.FILES.get('submission_file')
        submission_notes = request.POST.get('submission_notes', '')
        
        if not submission_file:
            messages.error(request, 'Please upload the submission file.')
            return redirect('project_detail', project_id=project.id)
        
        project.submission_file = submission_file
        project.submission_notes = submission_notes
        project.submitted_at = timezone.now()
        project.mark_completed()
        
        messages.success(request, f'Project {project.job_id} submitted successfully!')
        logger.info(f"Writer {writer.email} submitted project {project.job_id}")
        return redirect('all_projects')
    
    return redirect('project_detail', project_id=project.id)


@login_required
@writer_required
def writer_issues(request):
    """View all issues"""
    writer = request.user
    
    # Get all projects with issues
    projects_with_issues = WriterProject.objects.filter(
        writer=writer,
        status='issues'
    ).order_by('-updated_at')
    
    # Get all project issues reported by writer
    all_issues = ProjectIssue.objects.filter(
        reported_by=writer
    ).order_by('-created_at')
    
    context = {
        'projects_with_issues': projects_with_issues,
        'all_issues': all_issues,
    }
    
    return render(request, 'writer/writer_issues.html', context)


@login_required
@writer_required
def report_issue(request, project_id):
    """Report an issue for a project"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    if request.method == 'POST':
        issue_type = request.POST.get('issue_type')
        title = request.POST.get('title')
        description = request.POST.get('description')
        
        if not all([issue_type, title, description]):
            messages.error(request, 'All fields are required.')
            return redirect('project_detail', project_id=project.id)
        
        # Create issue
        ProjectIssue.objects.create(
            project=project,
            issue_type=issue_type,
            title=title,
            description=description,
            reported_by=writer,
            status='open'
        )
        
        # Update project status
        project.status = 'issues'
        project.save()
        
        messages.success(request, 'Issue reported successfully.')
        logger.info(f"Writer {writer.email} reported issue for project {project.job_id}")
        return redirect('writer_issues')
    
    return redirect('project_detail', project_id=project.id)


@login_required
@writer_required
def writer_hold(request):
    """View projects on hold"""
    writer = request.user
    
    hold_projects = WriterProject.objects.filter(
        writer=writer,
        status='hold'
    ).order_by('-updated_at')
    
    context = {
        'hold_projects': hold_projects,
    }
    
    return render(request, 'writer/writer_hold.html', context)


@login_required
@writer_required
def request_hold(request, project_id):
    """Request to put project on hold"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        
        if not reason:
            messages.error(request, 'Please provide a reason for hold.')
            return redirect('project_detail', project_id=project.id)
        
        # Create issue for hold request
        ProjectIssue.objects.create(
            project=project,
            issue_type='other',
            title='Hold Request',
            description=f'Hold Reason: {reason}',
            reported_by=writer,
            status='open'
        )
        
        # Update project status
        project.status = 'hold'
        project.save()
        
        messages.success(request, 'Project put on hold. Admin will review your request.')
        logger.info(f"Writer {writer.email} put project {project.job_id} on hold")
        return redirect('writer_hold')
    
    return redirect('project_detail', project_id=project.id)


@login_required
@writer_required
def writer_close(request):
    """View closed/completed projects"""
    writer = request.user
    
    closed_projects = WriterProject.objects.filter(
        writer=writer,
        status__in=['completed', 'closed']
    ).order_by('-completed_at')
    
    context = {
        'closed_projects': closed_projects,
    }
    
    return render(request, 'writer/writer_close.html', context)


@login_required
@writer_required
def add_comment(request, project_id):
    """Add comment to a project"""
    writer = request.user
    project = get_object_or_404(WriterProject, id=project_id, writer=writer)
    
    if request.method == 'POST':
        comment_text = request.POST.get('comment', '')
        
        if not comment_text:
            messages.error(request, 'Comment cannot be empty.')
            return redirect('project_detail', project_id=project.id)
        
        ProjectComment.objects.create(
            project=project,
            user=writer,
            comment=comment_text
        )
        
        messages.success(request, 'Comment added successfully.')
        return redirect('project_detail', project_id=project.id)
    
    return redirect('project_detail', project_id=project.id)
