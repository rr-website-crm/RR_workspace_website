# process/views.py - COMPLETE FILE
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from .models import Job, ProcessSubmission, JobComment, DecorationTask
from accounts.models import CustomUser
import logging

logger = logging.getLogger(__name__)


def process_required(view_func):
    """Decorator to ensure only process team members can access"""
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'process':
            messages.error(request, 'Access denied. Process team members only.')
            return redirect('home_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@process_required
def process_dashboard(request):
    """Process Team Dashboard"""
    
    # Get jobs allocated to this process member where writer has uploaded final file
    my_jobs = Job.objects.filter(
        process_member=request.user,
        writer_final_file__isnull=False,  # Writer has uploaded file
        status__in=['allocated', 'in_progress', 'submitted']
    ).exclude(
        status='cancelled'  # Exclude cancelled jobs
    ).order_by('-deadline')
    
    # Pagination
    paginator = Paginator(my_jobs, 25)
    page_number = request.GET.get('page')
    jobs = paginator.get_page(page_number)
    
    context = {
        'jobs': jobs,
        'total_jobs': my_jobs.count(),
        'process_member_name': request.user.get_full_name(),
    }
    
    return render(request, 'process/process_dashboard.html', context)


@login_required
@process_required
def my_jobs(request):
    """My Jobs - Active jobs assigned to me"""
    
    jobs = Job.objects.filter(
        process_member=request.user,
        writer_final_file__isnull=False,
        status__in=['allocated', 'in_progress']
    ).exclude(status='cancelled').order_by('-deadline')
    
    paginator = Paginator(jobs, 25)
    page_number = request.GET.get('page')
    jobs_page = paginator.get_page(page_number)
    
    context = {
        'jobs': jobs_page,
        'page_title': 'My Jobs',
    }
    
    return render(request, 'process/my_jobs.html', context)


@login_required
@process_required
def all_closed_jobs(request):
    """All Closed Jobs - Completed/Submitted jobs"""
    
    # Get all closed jobs (submitted or completed) for this process member
    closed_jobs = Job.objects.filter(
        process_member=request.user,
        status__in=['completed', 'submitted']
    ).order_by('-updated_at')
    
    # Count total closed jobs
    total_closed_jobs = closed_jobs.count()
    
    # Pagination - 25 per page
    paginator = Paginator(closed_jobs, 25)
    page_number = request.GET.get('page')
    jobs = paginator.get_page(page_number)
    
    context = {
        'jobs': jobs,
        'total_closed_jobs': total_closed_jobs,
    }
    
    return render(request, 'process/all_closed_jobs.html', context)


@login_required
@process_required
def view_job(request, job_id):
    """View Job Details"""
    
    job = get_object_or_404(Job, job_id=job_id)
    
    # Check if this job is assigned to current user OR has decoration task for user
    has_access = (
        job.process_member == request.user or
        hasattr(job, 'decoration_task') and job.decoration_task.process_member == request.user
    )
    
    if not has_access:
        messages.error(request, 'You do not have access to this job.')
        return redirect('process_dashboard')
    
    # Check if writer has uploaded final file
    if not job.writer_final_file:
        messages.warning(request, 'Writer has not uploaded the final file yet.')
        return redirect('process_dashboard')
    
    # Get previous submissions
    submissions = ProcessSubmission.objects.filter(
        job=job,
        process_member=request.user
    ).order_by('-submitted_at')
    
    # Get comments
    comments = JobComment.objects.filter(job=job).order_by('created_at')
    
    # Check decoration task
    decoration_task = None
    if hasattr(job, 'decoration_task') and job.decoration_task.process_member == request.user:
        decoration_task = job.decoration_task
    
    context = {
        'job': job,
        'submissions': submissions,
        'comments': comments,
        'decoration_task': decoration_task,
    }
    
    return render(request, 'process/view_job.html', context)


@login_required
@process_required
def submit_check_stage(request, job_id):
    """Submit Check Stage (AI & Plag files)"""
    
    if request.method != 'POST':
        return redirect('view_job', job_id=job_id)
    
    job = get_object_or_404(Job, job_id=job_id, process_member=request.user)
    
    ai_file = request.FILES.get('ai_file')
    plag_file = request.FILES.get('plag_file')
    
    if not ai_file or not plag_file:
        messages.error(request, 'Both AI and Plagiarism files are required for Check Stage.')
        return redirect('view_job', job_id=job_id)
    
    try:
        submission = ProcessSubmission.objects.create(
            job=job,
            process_member=request.user,
            stage='check',
            ai_file=ai_file,
            plag_file=plag_file
        )
        
        job.status = 'in_progress'
        job.save()
        
        logger.info(f"Check stage submitted by {request.user.email} for job {job_id}")
        messages.success(request, 'Check stage files uploaded successfully!')
        
    except Exception as e:
        logger.error(f"Error submitting check stage for job {job_id}: {str(e)}")
        messages.error(request, 'An error occurred while uploading files.')
    
    return redirect('view_job', job_id=job_id)


@login_required
@process_required
def submit_final_stage(request, job_id):
    """Submit Final Stage (Final File, AI, Plag, Grammarly, Other)"""
    
    if request.method != 'POST':
        return redirect('view_job', job_id=job_id)
    
    job = get_object_or_404(Job, job_id=job_id, process_member=request.user)
    
    final_file = request.FILES.get('final_file')
    ai_file = request.FILES.get('ai_file')
    plag_file = request.FILES.get('plag_file')
    grammarly_report = request.FILES.get('grammarly_report')
    other_files = request.FILES.get('other_files')
    
    if not all([final_file, ai_file, plag_file]):
        messages.error(request, 'Final File, AI File, and Plag File are required.')
        return redirect('view_job', job_id=job_id)
    
    try:
        submission = ProcessSubmission.objects.create(
            job=job,
            process_member=request.user,
            stage='final',
            final_file=final_file,
            ai_file=ai_file,
            plag_file=plag_file,
            grammarly_report=grammarly_report,
            other_files=other_files
        )
        
        job.status = 'submitted'
        job.save()
        
        logger.info(f"Final stage submitted by {request.user.email} for job {job_id}")
        messages.success(request, 'Final stage files uploaded successfully!')
        
    except Exception as e:
        logger.error(f"Error submitting final stage for job {job_id}: {str(e)}")
        messages.error(request, 'An error occurred while uploading files.')
    
    return redirect('view_job', job_id=job_id)


@login_required
@process_required
def submit_decoration(request, job_id):
    """Submit Decoration Stage"""
    
    if request.method != 'POST':
        return redirect('view_job', job_id=job_id)
    
    job = get_object_or_404(Job, job_id=job_id)
    
    # Check if user has decoration task for this job
    if not hasattr(job, 'decoration_task') or job.decoration_task.process_member != request.user:
        messages.error(request, 'You are not assigned to decoration for this job.')
        return redirect('process_dashboard')
    
    decoration_task = job.decoration_task
    
    final_file = request.FILES.get('final_file')
    ai_file = request.FILES.get('ai_file')
    plag_file = request.FILES.get('plag_file')
    other_files = request.FILES.get('other_files')
    
    if not all([final_file, ai_file, plag_file]):
        messages.error(request, 'Final File, AI File, and Plag File are required.')
        return redirect('view_job', job_id=job_id)
    
    try:
        decoration_task.final_file = final_file
        decoration_task.ai_file = ai_file
        decoration_task.plag_file = plag_file
        decoration_task.other_files = other_files
        decoration_task.is_completed = True
        decoration_task.completed_at = timezone.now()
        decoration_task.save()
        
        logger.info(f"Decoration submitted by {request.user.email} for job {job_id}")
        messages.success(request, 'Decoration files uploaded successfully!')
        
    except Exception as e:
        logger.error(f"Error submitting decoration for job {job_id}: {str(e)}")
        messages.error(request, 'An error occurred while uploading files.')
    
    return redirect('view_job', job_id=job_id)


@login_required
@process_required
def add_comment(request, job_id):
    """Add Comment to Job"""
    
    if request.method != 'POST':
        return redirect('view_job', job_id=job_id)
    
    job = get_object_or_404(Job, job_id=job_id)
    
    text = request.POST.get('comment_text', '').strip()
    attachment = request.FILES.get('attachment')
    link = request.POST.get('link', '').strip()
    
    if len(text) < 5 and not attachment:
        messages.error(request, 'Comment must be at least 5 characters or include an attachment.')
        return redirect('view_job', job_id=job_id)
    
    try:
        comment = JobComment.objects.create(
            job=job,
            user=request.user,
            text=text,
            attachment=attachment,
            link=link if link else None
        )
        
        logger.info(f"Comment added by {request.user.email} on job {job_id}")
        messages.success(request, 'Comment added successfully!')
        
    except Exception as e:
        logger.error(f"Error adding comment to job {job_id}: {str(e)}")
        messages.error(request, 'An error occurred while adding comment.')
    
    return redirect('view_job', job_id=job_id)


@login_required
@process_required
def edit_comment(request, comment_id):
    """Edit Comment"""
    
    if request.method != 'POST':
        return redirect('process_dashboard')
    
    comment = get_object_or_404(JobComment, id=comment_id, user=request.user)
    
    text = request.POST.get('comment_text', '').strip()
    
    if len(text) < 5:
        messages.error(request, 'Comment must be at least 5 characters.')
        return redirect('view_job', job_id=comment.job.job_id)
    
    try:
        comment.text = text
        comment.save()
        
        logger.info(f"Comment {comment_id} edited by {request.user.email}")
        messages.success(request, 'Comment updated successfully!')
        
    except Exception as e:
        logger.error(f"Error editing comment {comment_id}: {str(e)}")
        messages.error(request, 'An error occurred while updating comment.')
    
    return redirect('view_job', job_id=comment.job.job_id)


@login_required
@process_required
def delete_comment(request, comment_id):
    """Delete Comment"""
    
    comment = get_object_or_404(JobComment, id=comment_id, user=request.user)
    job_id = comment.job.job_id
    
    try:
        comment.delete()
        logger.info(f"Comment {comment_id} deleted by {request.user.email}")
        messages.success(request, 'Comment deleted successfully!')
        
    except Exception as e:
        logger.error(f"Error deleting comment {comment_id}: {str(e)}")
        messages.error(request, 'An error occurred while deleting comment.')
    
    return redirect('view_job', job_id=job_id)