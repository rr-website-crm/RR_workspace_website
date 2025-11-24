from django.urls import path
from . import views

urlpatterns = [
    # Marketing Dashboard
    path('dashboard/', views.marketing_dashboard, name='marketing_dashboard'),
    
    # Job Creation - Two Form System
    path('jobs/create/', views.create_job, name='create_job'),
    path('jobs/check-job-id/', views.check_job_id_unique, name='check_job_id_unique'),
    path('jobs/save-initial/', views.save_initial_form, name='save_initial_form'),
    path('jobs/generate-summary/', views.generate_ai_summary, name='generate_ai_summary'),
    path('jobs/accept-summary/', views.accept_summary, name='accept_summary'),
    path('jobs/summary-versions/<str:system_id>/', views.get_summary_versions, name='get_summary_versions'),
    
    # Job Management
    path('jobs/my-jobs/', views.my_jobs, name='my_jobs'),
    path('jobs/hold/', views.hold_jobs, name='hold_jobs'),
    path('jobs/query/', views.query_jobs, name='query_jobs'),
    path('jobs/unallocated/', views.unallocated_jobs, name='unallocated_jobs'),
    path('jobs/completed/', views.completed_jobs, name='completed_jobs'),
    path('jobs/allocated/', views.allocated_jobs, name='allocated_jobs'),
]