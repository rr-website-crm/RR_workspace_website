# writer/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.writer_dashboard, name='writer_dashboard'),
    
    # Projects
    path('projects/', views.all_projects, name='all_projects'),
    path('project/<int:project_id>/', views.project_detail, name='project_detail'),
    path('project/<int:project_id>/start/', views.start_project, name='start_project'),
    path('project/<int:project_id>/submit/', views.submit_project, name='submit_project'),
    
    # Issues
    path('issues/', views.writer_issues, name='writer_issues'),
    path('project/<int:project_id>/report-issue/', views.report_issue, name='report_issue'),
    
    # Hold
    path('hold/', views.writer_hold, name='writer_hold'),
    path('project/<int:project_id>/request-hold/', views.request_hold, name='request_hold'),
    
    # Close/Completed
    path('close/', views.writer_close, name='writer_close'),
    
    # Comments
    path('project/<int:project_id>/add-comment/', views.add_comment, name='add_comment'),
]