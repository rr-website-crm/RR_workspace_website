from django.urls import path
from . import views

urlpatterns = [
    # Allocator Dashboard
    path('dashboard/', views.allocator_dashboard, name='allocator_dashboard'),
    
    # Job Allocation Management
    path('pending/', views.pending_allocation, name='pending_allocation'),
    path('allocate/<int:job_id>/', views.allocate_job, name='allocate_job'),
    path('assigned/', views.assigned_jobs, name='assigned_jobs'),
    path('in-progress/', views.in_progress_jobs, name='in_progress_jobs'),
    path('cancel/', views.cancel_jobs, name='cancel_jobs'),
    path('hold/', views.hold_jobs_allocator, name='hold_jobs_allocator'),
    path('process/', views.process_jobs, name='process_jobs'),
    path('completed/', views.completed_jobs_allocator, name='completed_jobs_allocator'),
    path('all-projects/', views.all_projects, name='allocator_all_projects'),
    path('all-projects/<str:system_id>/', views.all_project_detail, name='allocator_all_project_detail'),
    
    # Team Management
    path('writers/', views.all_writers, name='all_writers'),
    path('process-team/', views.all_process_team, name='all_process_team'),
    
    # Actions
    path('switch-writer/<int:allocation_id>/', views.switch_writer, name='switch_writer'),
    path('job/<int:job_id>/', views.view_job_details, name='view_job_details'),
    path('approve-comment/<int:job_id>/', views.approve_comment, name='approve_comment'),
]
