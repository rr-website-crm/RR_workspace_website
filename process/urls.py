# process/urls.py - COMPLETE AND UPDATED
from django.urls import path
from . import views

urlpatterns = [
    # =====================================
    # DASHBOARD & MAIN VIEWS
    # =====================================
    path('dashboard/', views.process_dashboard, name='process_dashboard'),
    
    # =====================================
    # JOBS MANAGEMENT
    # =====================================
    path('my-jobs/', views.my_jobs, name='process_my_jobs'),
    path('closed-jobs/', views.all_closed_jobs, name='process_closed_jobs'),
    path('job/<str:job_id>/', views.view_job, name='view_job'),
    
    # =====================================
    # SUBMISSIONS - CHECK, FINAL, DECORATION
    # =====================================
    path('job/<str:job_id>/submit-check/', views.submit_check_stage, name='submit_check_stage'),
    path('job/<str:job_id>/submit-final/', views.submit_final_stage, name='submit_final_stage'),
    path('job/<str:job_id>/submit-decoration/', views.submit_decoration, name='submit_decoration'),
    
    # =====================================
    # COMMENTS SYSTEM
    # =====================================
    path('job/<str:job_id>/add-comment/', views.add_comment, name='add_comment'),
    path('comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
]
