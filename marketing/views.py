from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.urls import reverse
from contextlib import contextmanager
from django.conf import settings
import json
import time
import os
from openai import OpenAI
from .models import Job, JobAttachment, JobSummaryVersion, JobActionLog, log_job_activity
from accounts.models import ActivityLog, CustomUser
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
    
    # Get all jobs created by this marketing user
    all_jobs = Job.objects.filter(created_by=user)
    
    # Get statistics
    stats = {
        'total_jobs': all_jobs.count(),
        'pending_jobs': all_jobs.filter(status='pending').count(),
        'allocated_jobs': all_jobs.filter(status='allocated').count(),
        'completed_jobs': all_jobs.filter(status='completed').count(),
        'hold_jobs': all_jobs.filter(status='hold').count(),
        'query_jobs': all_jobs.filter(status='query').count(),
    }
    
    # Get draft jobs (not yet finalized)
    draft_jobs = all_jobs.filter(status='draft').order_by('-created_at')
    
    # Get recent activities (pending and allocated jobs)
    recent_activities = all_jobs.exclude(status='draft').order_by('-created_at')[:10]
    
    context = {
        'user': user,
        'stats': stats,
        'draft_jobs': draft_jobs,
        'recent_activities': recent_activities,
        'today_date': timezone.now(),
    }
    
    logger.info(f"Marketing dashboard accessed by: {user.email}")
    return render(request, 'marketing/marketing_dashboard.html', context)
# Event keys for job activities
JOB_EVENTS = {
    'created': 'job.created',
    'initial_saved': 'job.initial_form.saved',
    'initial_submitted': 'job.initial_form.submitted',
    'id_validated': 'job.job_id.validated',
    'summary_requested': 'job.ai_summary.requested',
    'summary_generated': 'job.ai_summary.generated',
    'summary_accepted': 'job.ai_summary.accepted',
    'status_changed': 'job.status.changed',
}


PROXY_ENV_VARS = [
    'OPENAI_PROXY', 'HTTPS_PROXY', 'https_proxy',
    'HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'
]


# @contextmanager
# def openai_client():
#     """Create OpenAI client after stripping proxy env vars (djongo env sets them globally)."""
#     removed = {}
#     for key in PROXY_ENV_VARS:
#         if key in os.environ:
#             removed[key] = os.environ.pop(key)
    
#     client = None
#     try:
#         client = OpenAI()
#         yield client
#     finally:
#         if client:
#             client.close()
#         for key, value in removed.items():
#             os.environ[key] = value
@contextmanager
def openai_client():
    """OpenAI client using API key only — NO PROXY."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        yield client
    finally:
        client.close()

def _render_job_list(request, queryset, page_title, filter_description=None,
                     empty_title=None, empty_description=None, template_name='marketing/job_list.html'):
    """Shared renderer for marketing job list pages"""
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    jobs_page = paginator.get_page(page_number)
    
    context = {
        'jobs': jobs_page,
        'page_title': page_title,
        'filter_description': filter_description,
        'total_jobs': queryset.count(),
        'empty_state': {
            'title': empty_title or 'No jobs found',
            'description': empty_description or 'Try adjusting the filters or create a new job to get started.',
            'cta_url': reverse('create_job'),
            'cta_label': 'Create Job'
        }
    }
    return render(request, template_name, context)
def validate_file(file):
    """Validate uploaded file"""
    ALLOWED_EXTENSIONS = ['pdf', 'docx', 'jpg', 'jpeg', 'png']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Get file extension
    ext = os.path.splitext(file.name)[1].lower().replace('.', '')
    
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '.{ext}' not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
    
    if file.size > MAX_FILE_SIZE:
        return False, f"File size exceeds 10MB. Current size: {file.size / (1024*1024):.2f}MB"
    
    return True, "Valid"


@login_required
@role_required(['marketing'])
def create_job(request):
    """Create a new job with two-step form"""
    
    # Check if editing existing draft
    job_id = request.GET.get('job_id')
    job = None
    
    if job_id:
        job = get_object_or_404(Job, system_id=job_id, created_by=request.user, status='draft')
    
    context = {
        'user': request.user,
        'job': job,
    }
    
    return render(request, 'marketing/create_job.html', context)


@login_required
@role_required(['marketing'])
@require_http_methods(["POST"])
def check_job_id_unique(request):
    """AJAX endpoint to check if job_id is unique"""
    try:
        data = json.loads(request.body)
        job_id = data.get('job_id', '').strip()
        current_system_id = data.get('system_id')
        
        if not job_id:
            return JsonResponse({'unique': False, 'message': 'Job ID is required'})
        
        # Check if job_id exists (excluding current job if editing)
        query = Job.objects.filter(job_id=job_id)
        if current_system_id:
            query = query.exclude(system_id=current_system_id)
        
        exists = query.exists()
        
        if exists:
            return JsonResponse({'unique': False, 'message': 'Job ID already exists'})
        else:
            return JsonResponse({'unique': True, 'message': 'Job ID is available'})
            
    except Exception as e:
        logger.error(f"Error checking job ID uniqueness: {str(e)}")
        return JsonResponse({'unique': False, 'message': 'Error checking uniqueness'})


@login_required
@role_required(['marketing'])
@require_http_methods(["POST"])
def save_initial_form(request):
    """Save or update initial form data"""
    try:
        job_id = request.POST.get('job_id', '').strip()
        instruction = request.POST.get('instruction', '').strip()
        files = request.FILES.getlist('attachments')
        system_id = request.POST.get('system_id')  # If editing existing
        
        # Validation
        if not job_id:
            return JsonResponse({'success': False, 'message': 'Job ID is required'}, status=400)
        
        if len(instruction) < 50:
            return JsonResponse({
                'success': False, 
                'message': f'Instruction must be at least 50 characters. Current: {len(instruction)}'
            }, status=400)
        
        if not files:
            return JsonResponse({'success': False, 'message': 'At least one attachment is required'}, status=400)
        
        if len(files) > 10:
            return JsonResponse({'success': False, 'message': 'Maximum 10 files allowed'}, status=400)
        
        # Validate each file
        for file in files:
            is_valid, msg = validate_file(file)
            if not is_valid:
                return JsonResponse({'success': False, 'message': msg}, status=400)
        
        with transaction.atomic():
            # Create or update job
            if system_id:
                job = Job.objects.get(system_id=system_id, created_by=request.user)
                job.job_id = job_id
                job.instruction = instruction
                job.initial_form_last_saved_at = timezone.now()
                
                # Delete old attachments if replacing
                if request.POST.get('replace_attachments') == 'true':
                    job.attachments.all().delete()
                
                log_action = 'initial_form_saved'
                event_key = JOB_EVENTS['initial_saved']
            else:
                # Create new job
                system_id = Job.generate_system_id()
                job = Job.objects.create(
                    system_id=system_id,
                    job_id=job_id,
                    instruction=instruction,
                    created_by=request.user,
                    status='draft',
                    job_name_validated_at=timezone.now()
                )
                log_action = 'created'
                event_key = JOB_EVENTS['created']
            
            # Save attachments
            for file in files:
                JobAttachment.objects.create(
                    job=job,
                    file=file,
                    original_filename=file.name,
                    file_size=file.size,
                    uploaded_by=request.user
                )
            
            # Log to JobActionLog
            JobActionLog.objects.create(
                job=job,
                action=log_action,
                performed_by=request.user,
                performed_by_type='user',
                details={
                    'job_id': job_id,
                    'instruction_length': len(instruction),
                    'attachments_count': len(files)
                }
            )
            
            # Log to ActivityLog (your system-wide log)
            ActivityLog.objects.create(
                event_key=event_key,
                category='job_management',
                subject_user=request.user,
                performed_by=request.user,
                metadata={
                    'job_system_id': system_id,
                    'job_id': job_id,
                    'instruction_length': len(instruction),
                    'attachments_count': len(files),
                    'status': 'draft'
                }
            )
            
            job.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Initial form saved successfully',
                'system_id': system_id,
                'job_id': job_id
            })
            
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
    except Exception as e:
        logger.error(f"Error saving initial form: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


# 
# @login_required
# @role_required(['marketing'])
# @require_http_methods(["POST"])
# def generate_ai_summary(request):
#     """Generate AI summary using OpenAI"""
#     try:
#         data = json.loads(request.body)
#         system_id = data.get('system_id')
        
#         if not system_id:
#             return JsonResponse({'success': False, 'message': 'System ID is required'}, status=400)
        
#         job = get_object_or_404(Job, system_id=system_id, created_by=request.user)
        
#         # Check if can regenerate
#         if not job.can_regenerate_summary():
#             return JsonResponse({
#                 'success': False,
#                 'message': 'Maximum 3 summary generations reached'
#             }, status=400)
        
#         # Update timestamps
#         job.ai_summary_requested_at = timezone.now()
        
#         # Prepare attachments content
#         attachments_text = []
#         for attachment in job.attachments.all():
#             try:
#                 if attachment.get_file_extension() in ['.pdf', '.docx']:
#                     attachments_text.append(f"Attachment: {attachment.original_filename} (Binary file - analyze based on instruction)")
#                 else:
#                     attachments_text.append(f"Image: {attachment.original_filename}")
#             except Exception as e:
#                 logger.error(f"Error reading attachment: {str(e)}")
        
#         # Create OpenAI prompt
#         prompt = f"""You are an Assignment Analysis Agent for a technical academic writing and student assignment support company. Your role is to carefully analyze the job instruction and any attachments provided.

# RULE FOR ANALYSIS:
# - If attachments are available, analyze BOTH the instruction and the attachment content.
# - If attachments are NOT available or contain no readable text, analyze ONLY the instruction.
# - Do NOT generate any default summary; base all analysis strictly on the given content.

# Your tasks include:
# - Identifying whether the assignment requires the use of any specific software; if yes, specify the exact software name and version (if mentioned or typically required).
# - Providing a detailed task breakdown for any software-related work.
# - Detecting if a PowerPoint presentation is required (e.g., “10-minute presentation”). If yes:
#   - Approximate number of slides (default: 1 slide per minute)
#   - Estimated words per slide (default: 100 words per slide)
# - Detecting if a LaTeX file is required.
# - Detecting if a poster is required.
# - Estimating the word count if not explicitly mentioned (based on academic standards).
# - Providing a clear structured breakdown of what needs to be written or implemented—without giving the solution itself.

# Use the details below to generate the output.

# INSTRUCTION:
# {job.instruction}

# ATTACHMENTS:
# {chr(10).join(attachments_text) if attachments_text else 'No text content available'}

# Generate a detailed JSON response with the following fields:

# 1. **topic**: Extract or generate a clear, specific topic. If mentioned in instruction, use it. Otherwise, create based on content.

# 2. **word_count**: Estimate the required word count based on the instruction. Provide a realistic number.

# 3. **referencing_style**: Determine the appropriate referencing style. Choose from: harvard, apa, mla, ieee, vancouver, chicago. If not mentioned, suggest the most appropriate.

# 4. **writing_style**: Identify the writing style required. Choose from: proposal, report, essay, dissertation, business_report, personal_development, reflection_writing, case_study.

# 5. **job_summary**: Write a DETAILED summary (minimum 200 words) that includes:
#    - Full analysis of assignment requirements based on instruction and attachments
#    - Whether any software is required (with software name and version if relevant)
#    - If software is required, provide a detailed breakdown of software-based tasks
#    - Whether a PowerPoint is needed, number of slides, and estimated words per slide
#    - Whether a LaTeX file or poster is needed
#    - Specific tools, frameworks, or technical environments required
#    - Any case studies, companies, datasets, or examples referenced
#    - Key deliverables and expected outputs
#    - Structure, format, and academic expectations
#    - Any timelines, milestones, or special notes

# IMPORTANT: Never generate the actual solution. Only analyze the requirements clearly and professionally.





# Return ONLY valid JSON in this format:
# {{
#     "topic": "...",
#     "word_count": 0,
#     "referencing_style": "...",
#     "writing_style": "...",
#     "job_summary": "..."
# }}"""

#         # Call OpenAI API - FIXED: Remove proxy settings and use explicit API key
#         # Clear any proxy environment variables that might interfere
#         import os
#         api_key = os.getenv('OPENAI_API_KEY')
        
#         if not api_key:
#             return JsonResponse({
#                 'success': False,
#                 'message': 'OpenAI API key not configured'
#             }, status=500)
        
#         # Initialize client with explicit settings to avoid proxy issues
#         from openai import OpenAI
#         client = OpenAI(
#             api_key=api_key,
#             timeout=60.0,  # Explicit timeout
#             max_retries=2   # Explicit retry count
#         )
        
#         response = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are an expert academic job analyzer. Always return valid JSON."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7,
#             max_tokens=2000
#         )
        
#         # Parse response
#         ai_response = response.choices[0].message.content.strip()
        
#         # Remove markdown code blocks if present
#         if ai_response.startswith('```'):
#             ai_response = ai_response.split('```')[1]
#             if ai_response.startswith('json'):
#                 ai_response = ai_response[4:]
#             ai_response = ai_response.strip()
        
#         summary_data = json.loads(ai_response)
        
#         # Update job with AI summary
#         with transaction.atomic():
#             job.topic = summary_data.get('topic')
#             job.word_count = summary_data.get('word_count')
#             job.referencing_style = summary_data.get('referencing_style')
#             job.writing_style = summary_data.get('writing_style')
#             job.job_summary = summary_data.get('job_summary')
            
#             # Increment version
#             job.ai_summary_version += 1
            
#             # Add generation timestamp
#             generation_timestamps = job.ai_summary_generated_at or []
#             generation_timestamps.append(timezone.now().isoformat())
#             job.ai_summary_generated_at = generation_timestamps
            
#             # Calculate degree
#             degree = job.calculate_degree()
            
#             # Save version
#             JobSummaryVersion.objects.create(
#                 job=job,
#                 version_number=job.ai_summary_version,
#                 topic=job.topic,
#                 word_count=job.word_count,
#                 referencing_style=job.referencing_style,
#                 writing_style=job.writing_style,
#                 job_summary=job.job_summary,
#                 degree=degree,
#                 performed_by='system',
#                 ai_model_used='gpt-4o-mini'
#             )
            
#             # Log action
#             JobActionLog.objects.create(
#                 job=job,
#                 action='ai_summary_generated',
#                 performed_by=request.user,
#                 performed_by_type='system',
#                 details={
#                     'version': job.ai_summary_version,
#                     'degree': degree,
#                     'model': 'gpt-4o-mini'
#                 }
#             )
            
#             # Log to ActivityLog
#             ActivityLog.objects.create(
#                 event_key=JOB_EVENTS['summary_generated'],
#                 category='job_management',
#                 subject_user=request.user,
#                 performed_by=request.user,
#                 metadata={
#                     'job_system_id': job.system_id,
#                     'job_id': job.job_id,
#                     'version': job.ai_summary_version,
#                     'degree': degree,
#                     'model': 'gpt-4o-mini',
#                     'topic': job.topic,
#                     'word_count': job.word_count,
#                     'referencing_style': job.referencing_style,
#                     'writing_style': job.writing_style
#                 }
#             )
            
#             # Check if should auto-accept
#             auto_accept = job.should_auto_accept()
#             if auto_accept:
#                 job.ai_summary_accepted_at = timezone.now()
#                 job.status = 'pending'
                
#                 JobActionLog.objects.create(
#                     job=job,
#                     action='ai_summary_accepted',
#                     performed_by=request.user,
#                     performed_by_type='system',
#                     details={
#                         'auto_accepted': True,
#                         'reason': 'degree_0' if degree == 0 else 'version_3'
#                     }
#                 )
                
#                 # Log auto-acceptance
#                 ActivityLog.objects.create(
#                     event_key=JOB_EVENTS['summary_accepted'],
#                     category='job_management',
#                     subject_user=request.user,
#                     performed_by=request.user,
#                     metadata={
#                         'job_system_id': job.system_id,
#                         'job_id': job.job_id,
#                         'auto_accepted': True,
#                         'reason': 'degree_0' if degree == 0 else 'version_3',
#                         'version': job.ai_summary_version,
#                         'degree': degree
#                     }
#                 )
            
#             job.save()
            
#             return JsonResponse({
#                 'success': True,
#                 'message': 'AI summary generated successfully',
#                 'data': {
#                     'topic': job.topic,
#                     'word_count': job.word_count,
#                     'referencing_style': job.referencing_style,
#                     'writing_style': job.writing_style,
#                     'job_summary': job.job_summary,
#                     'version': job.ai_summary_version,
#                     'degree': degree,
#                     'auto_accepted': auto_accept,
#                     'can_regenerate': job.can_regenerate_summary()
#                 }
#             })
            
#     except Job.DoesNotExist:
#         return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
#     except json.JSONDecodeError as e:
#         logger.error(f"Error parsing AI response: {str(e)}")
#         return JsonResponse({'success': False, 'message': 'Error parsing AI response'}, status=500)
#     except Exception as e:
#         logger.error(f"Error generating AI summary: {str(e)}")
#         return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


@login_required
@role_required(['marketing'])
@require_http_methods(["POST"])
def generate_ai_summary(request):
    """Generate AI summary using OpenAI"""
    try:
        data = json.loads(request.body)
        system_id = data.get('system_id')
        
        if not system_id:
            return JsonResponse({'success': False, 'message': 'System ID is required'}, status=400)
        
        job = get_object_or_404(Job, system_id=system_id, created_by=request.user)
        
        # Check if can regenerate
        if not job.can_regenerate_summary():
            return JsonResponse({
                'success': False,
                'message': 'Maximum 3 summary generations reached'
            }, status=400)
        
        # Update timestamps
        job.ai_summary_requested_at = timezone.now()

        # -------------------------------------------------------------------
        # UPDATED: Extract REAL TEXT from PDF, DOCX and Image OCR
        # -------------------------------------------------------------------
        attachments_text = []
        for attachment in job.attachments.all():
            try:
                ext = attachment.get_file_extension().lower()
                file_path = attachment.file.path

                # -------- PDF Extraction --------
                if ext == ".pdf":
                    try:
                        from pdfminer.high_level import extract_text
                        pdf_text = extract_text(file_path)

                        if pdf_text.strip():
                            attachments_text.append(
                                f"[PDF TEXT - {attachment.original_filename}]\n{pdf_text}"
                            )
                        else:
                            attachments_text.append(
                                f"[PDF - {attachment.original_filename}] (No extractable text)"
                            )
                    except Exception:
                        attachments_text.append(
                            f"[PDF - {attachment.original_filename}] (Unable to extract text)"
                        )

                # -------- DOCX Extraction --------
                elif ext == ".docx":
                    try:
                        import docx
                        doc = docx.Document(file_path)

                        docx_text = "\n".join(
                            [p.text for p in doc.paragraphs if p.text.strip()]
                        )

                        if docx_text.strip():
                            attachments_text.append(
                                f"[DOCX TEXT - {attachment.original_filename}]\n{docx_text}"
                            )
                        else:
                            attachments_text.append(
                                f"[DOCX - {attachment.original_filename}] (Empty or unreadable)"
                            )
                    except:
                        attachments_text.append(
                            f"[DOCX - {attachment.original_filename}] (Unable to extract text)"
                        )

                # -------- IMAGE OCR --------
                elif ext in ['.png', '.jpg', '.jpeg']:
                    try:
                        from PIL import Image
                        import pytesseract

                        img_text = pytesseract.image_to_string(Image.open(file_path))

                        if img_text.strip():
                            attachments_text.append(
                                f"[IMAGE OCR - {attachment.original_filename}]\n{img_text}"
                            )
                        else:
                            attachments_text.append(
                                f"[IMAGE - {attachment.original_filename}] (No readable text)"
                            )
                    except Exception:
                        attachments_text.append(
                            f"[IMAGE - {attachment.original_filename}] (OCR not available)"
                        )

                else:
                    attachments_text.append(
                        f"[Unsupported File - {attachment.original_filename}]"
                    )

            except Exception as e:
                logger.error(f"Error processing attachment: {str(e)}")
                attachments_text.append(
                    f"[Error reading {attachment.original_filename}]"
                )

        # -------------------------------------------------------------------
        # OpenAI Prompt (UNCHANGED BY REQUEST)
        # -------------------------------------------------------------------
        prompt = f"""You are an Assignment Analysis Agent for a technical academic writing and student assignment support company. Your role is to carefully analyze the job instruction and any attachments provided.

            RULE FOR ANALYSIS:
            - If attachments are available, analyze BOTH the instruction and the attachment content.
            - If attachments are NOT available or contain no readable text, analyze ONLY the instruction.
            - Do NOT generate any default summary; base all analysis strictly on the given content.

            Your tasks include:
            - Identifying whether the assignment requires the use of any specific software; if yes, specify the exact software name and version (if mentioned or typically required).
            - Providing a detailed task breakdown for any software-related work.
            - Detecting if a PowerPoint presentation is required (e.g., “10-minute presentation”). If yes:
            - Approximate number of slides (default: 1 slide per minute)
            - Estimated words per slide (default: 100 words per slide)
            - Detecting if a LaTeX file is required.
            - Detecting if a poster is required.
            - Estimating the word count if not explicitly mentioned (based on academic standards).
            - Providing a clear structured breakdown of what needs to be written or implemented—without giving the solution itself.

            Use the details below to generate the output.

            INSTRUCTION:
            {job.instruction}

            ATTACHMENTS:
            {chr(10).join(attachments_text) if attachments_text else 'No text content available'}

            Generate a detailed JSON response with the following fields:

            1. **topic**: Extract or generate a clear, specific topic. If mentioned in instruction, use it. Otherwise, create based on content.

            2. **word_count**: use the word count that provide in the instruction or attachment , dont assume any wordcount.

            3. **referencing_style**: use the referencing style  that provide in the instruction or attachment , dont assume any referencing style.

            4. **writing_style**: Identify the writing style required. Choose from: proposal, report, essay, dissertation, business_report, personal_development, reflection_writing, case_study from attachment or instrution , if there is not present dont assume any.

            5. **job_summary**: Write a DETAILED summary (minimum 200 words) that includes:
            - Full analysis of assignment requirements based on instruction and attachments
            - Whether any software is required (with software name and version if relevant)
            - If software is required, provide a detailed breakdown of software-based tasks
            - Whether a PowerPoint is needed, number of slides, and estimated words per slide
            - Whether a LaTeX file or poster is needed
            - Specific tools, frameworks, or technical environments required
            - Any case studies, companies, datasets, or examples referenced
            - Key deliverables and expected outputs
            - Structure, format, and academic expectations
            - Any timelines, milestones, or special notes

            IMPORTANT: Never generate the actual solution. Only analyze the requirements clearly and professionally.

            Return ONLY valid JSON in this format:
            {{
                "topic": "...",
                "word_count": 0,
                "referencing_style": "...",
                "writing_style": "...",
                "job_summary": "..."
            }}"""

        # -------------------------------------------------------------------
        # OpenAI CLIENT (UNCHANGED)
        # -------------------------------------------------------------------
        import os
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            return JsonResponse({
                'success': False,
                'message': 'OpenAI API key not configured'
            }, status=500)
        
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            timeout=60.0,
            max_retries=2
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert academic job analyzer. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Clean JSON
        if ai_response.startswith('```'):
            ai_response = ai_response.split('```')[1]
            if ai_response.startswith('json'):
                ai_response = ai_response[4:]
            ai_response = ai_response.strip()
        
        summary_data = json.loads(ai_response)

        # -------------------------------------------------------------------
        # SAVE SUMMARY (UNCHANGED)
        # -------------------------------------------------------------------
        with transaction.atomic():
            job.topic = summary_data.get('topic')
            job.word_count = summary_data.get('word_count')
            job.referencing_style = summary_data.get('referencing_style')
            job.writing_style = summary_data.get('writing_style')
            job.job_summary = summary_data.get('job_summary')
            
            # Increment version
            job.ai_summary_version += 1
            
            generation_timestamps = job.ai_summary_generated_at or []
            generation_timestamps.append(timezone.now().isoformat())
            job.ai_summary_generated_at = generation_timestamps
            
            degree = job.calculate_degree()
            
            JobSummaryVersion.objects.create(
                job=job,
                version_number=job.ai_summary_version,
                topic=job.topic,
                word_count=job.word_count,
                referencing_style=job.referencing_style,
                writing_style=job.writing_style,
                job_summary=job.job_summary,
                degree=degree,
                performed_by='system',
                ai_model_used='gpt-4o-mini'
            )
            
            JobActionLog.objects.create(
                job=job,
                action='ai_summary_generated',
                performed_by=request.user,
                performed_by_type='system',
                details={
                    'version': job.ai_summary_version,
                    'degree': degree,
                    'model': 'gpt-4o-mini'
                }
            )

            # -----------------------------
            # AUTO ACCEPT & REDIRECT LOGIC
            # -----------------------------
            auto_accept = False
            auto_redirect = False

            # Rule 1: Perfect summary (degree 0) → Auto accept AND redirect
            if degree == 0:
                auto_accept = True
                auto_redirect = True

            # Rule 2: Version 3 reached → Auto accept but NO redirect
            elif job.ai_summary_version >= 3:
                auto_accept = True
                auto_redirect = False

            # Apply auto-accept
            if auto_accept:
                job.ai_summary_accepted_at = timezone.now()
                job.status = "pending"

                JobActionLog.objects.create(
                    job=job,
                    action="ai_summary_accepted",
                    performed_by=request.user,
                    performed_by_type="system",
                    details={
                        "version": job.ai_summary_version,
                        "degree": degree,
                        "auto_accepted": True,
                        "redirect": auto_redirect
                    }
                )

            
            # auto_accept = job.should_auto_accept()
            # if auto_accept:
            #     job.ai_summary_accepted_at = timezone.now()
            #     job.status = 'pending'
                
            #     JobActionLog.objects.create(
            #         job=job,
            #         action='ai_summary_accepted',
            #         performed_by=request.user,
            #         performed_by_type='system',
            #         details={
            #             'auto_accepted': True,
            #             'reason': 'degree_0' if degree == 0 else 'version_3'
            #         }
            #     )
                
                ActivityLog.objects.create(
                    event_key=JOB_EVENTS['summary_generated'],
                    category='job_management',
                    subject_user=request.user,
                    performed_by=request.user,
                    metadata={
                        'job_system_id': job.system_id,
                        'job_id': job.job_id,
                        'version': job.ai_summary_version,
                        'degree': degree,
                        'model': 'gpt-4o-mini'
                    }
                )
            
            job.save()
            
            return JsonResponse({
                'success': True,
                'message': 'AI summary generated successfully',
                'data': {
                    'topic': job.topic,
                    'word_count': job.word_count,
                    'referencing_style': job.referencing_style,
                    'writing_style': job.writing_style,
                    'job_summary': job.job_summary,
                    'version': job.ai_summary_version,
                    'degree': degree,
                    'auto_accepted': auto_accept,
                    'auto_redirect': auto_redirect,
                    'can_regenerate': job.can_regenerate_summary()

                }
            })

    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Error parsing AI response'}, status=500)
    except Exception as e:
        logger.error(f"Error generating AI summary: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)




@login_required
@role_required(['marketing'])
@require_http_methods(["POST"])
def accept_summary(request):
    """Accept AI summary and finalize job"""
    try:
        data = json.loads(request.body)
        system_id = data.get('system_id')
        
        job = get_object_or_404(Job, system_id=system_id, created_by=request.user)
        
        with transaction.atomic():
            job.ai_summary_accepted_at = timezone.now()
            job.status = 'pending'
            job.initial_form_submitted_at = timezone.now()
            
            # Log to JobActionLog
            JobActionLog.objects.create(
                job=job,
                action='ai_summary_accepted',
                performed_by=request.user,
                performed_by_type='user',
                details={
                    'version': job.ai_summary_version,
                    'degree': job.job_card_degree
                }
            )
            
            JobActionLog.objects.create(
                job=job,
                action='initial_form_submitted',
                performed_by=request.user,
                performed_by_type='user'
            )
            
            # Log to ActivityLog
            ActivityLog.objects.create(
                event_key=JOB_EVENTS['summary_accepted'],
                category='job_management',
                subject_user=request.user,
                performed_by=request.user,
                metadata={
                    'job_system_id': job.system_id,
                    'job_id': job.job_id,
                    'version': job.ai_summary_version,
                    'degree': job.job_card_degree,
                    'manual_acceptance': True
                }
            )
            
            ActivityLog.objects.create(
                event_key=JOB_EVENTS['initial_submitted'],
                category='job_management',
                subject_user=request.user,
                performed_by=request.user,
                metadata={
                    'job_system_id': job.system_id,
                    'job_id': job.job_id,
                    'status': 'pending'
                }
            )
            
            job.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Job created successfully',
                'redirect': '/marketing/dashboard/'
            })
            
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
    except Exception as e:
        logger.error(f"Error accepting summary: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


@login_required
@role_required(['marketing'])
def get_summary_versions(request, system_id):
    """Get all summary versions for a job"""
    try:
        job = get_object_or_404(Job, system_id=system_id, created_by=request.user)
        versions = job.summary_versions.all()
        
        versions_data = [{
            'version': v.version_number,
            'topic': v.topic,
            'word_count': v.word_count,
            'referencing_style': v.referencing_style,
            'writing_style': v.writing_style,
            'job_summary': v.job_summary,
            'degree': v.degree,
            'generated_at': v.generated_at.isoformat()
        } for v in versions]
        
        return JsonResponse({
            'success': True,
            'versions': versions_data,
            'current_version': job.ai_summary_version
        })
        
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
@role_required(['marketing'])
def my_jobs(request):
    """List all jobs created by the current marketing user"""
    queryset = Job.objects.filter(
        created_by=request.user
    ).select_related('allocated_to').order_by('-created_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='My Jobs',
        filter_description='Full history of every job you have created.',
        empty_title='No jobs yet',
        empty_description='Create a job to see it listed here.'
    )


@login_required
@role_required(['marketing'])
def hold_jobs(request):
    """Jobs currently on hold"""
    queryset = Job.objects.filter(
        created_by=request.user,
        status='hold'
    ).select_related('allocated_to').order_by('-updated_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='Hold Jobs',
        filter_description='Jobs paused for clarification or awaiting client confirmation.',
        empty_title='No jobs on hold',
        empty_description='When you pause a job it will surface here for quick follow-up.'
    )


@login_required
@role_required(['marketing'])
def query_jobs(request):
    """Jobs flagged with queries"""
    queryset = Job.objects.filter(
        created_by=request.user,
        status='query'
    ).select_related('allocated_to').order_by('-updated_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='Query Jobs',
        filter_description='Jobs that need action because the allocator or writer raised queries.',
        empty_title='No query jobs',
        empty_description='Great news—no active queries right now.'
    )


@login_required
@role_required(['marketing'])
def unallocated_jobs(request):
    """Jobs that have not been allocated yet"""
    queryset = Job.objects.filter(
        created_by=request.user,
        allocated_to__isnull=True
    ).exclude(
        status__in=['draft', 'completed', 'cancelled']
    ).order_by('-created_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='Unallocated Jobs',
        filter_description='Submitted jobs still waiting for allocator assignment.',
        empty_title='No unallocated jobs',
        empty_description='All submitted jobs have already been assigned.'
    )


@login_required
@role_required(['marketing'])
def completed_jobs(request):
    """Jobs completed by delivery teams"""
    queryset = Job.objects.filter(
        created_by=request.user,
        status='completed'
    ).select_related('allocated_to').order_by('-updated_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='Completed Jobs',
        filter_description='Finished jobs delivered back by the production teams.',
        empty_title='No completed jobs yet',
        empty_description='Once a job is delivered successfully, it will be archived here.'
    )


@login_required
@role_required(['marketing'])
def allocated_jobs(request):
    """Jobs that are currently allocated to a downstream team"""
    queryset = Job.objects.filter(
        created_by=request.user,
        status__in=['allocated', 'in_progress']
    ).select_related('allocated_to').order_by('-updated_at')
    
    return _render_job_list(
        request,
        queryset,
        page_title='Allocated Jobs',
        filter_description='Live jobs currently being worked on by writers or process teams.',
        empty_title='No allocated jobs',
        empty_description='Jobs will appear here as soon as the allocator assigns them.'
    )