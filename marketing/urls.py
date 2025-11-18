from django.urls import path
from . import views

urlpatterns = [
    # Marketing Dashboard
    path('dashboard/', views.marketing_dashboard, name='marketing_dashboard'),
    
    # Job Management
    path('jobs/create/', views.create_job, name='create_job'),
    path('jobs/my-jobs/', views.my_jobs, name='my_jobs'),
    path('jobs/hold/', views.hold_jobs, name='hold_jobs'),
    path('jobs/query/', views.query_jobs, name='query_jobs'),
    path('jobs/unallocated/', views.unallocated_jobs, name='unallocated_jobs'),
    path('jobs/completed/', views.completed_jobs, name='completed_jobs'),
    path('jobs/allocated/', views.allocated_jobs, name='allocated_jobs'),
]