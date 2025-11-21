from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='dashboard'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('pending/', views.pending_items, name='pending_items'),
    path('role-details/<str:role>/', views.role_details, name='role_details'),

    path('update-role/<int:user_id>/', views.update_user_role, name='update_user_role'),
    path('update-category/<int:user_id>/', views.update_user_category, name='update_user_category'),
    path('update-level/<int:user_id>/', views.update_user_level, name='update_user_level'),
    path('toggle-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('edit-user/<int:user_id>/', views.edit_user, name='edit_user'),

    path('approve-user/<int:user_id>/', views.approve_user, name='approve_user'),
    path('reject-user/<int:user_id>/', views.reject_user, name='reject_user'),
    path('profile-request/<int:request_id>/approve/', views.approve_profile_request, name='approve_profile_request'),
    path('profile-request/<int:request_id>/reject/', views.reject_profile_request, name='reject_profile_request'),
]
