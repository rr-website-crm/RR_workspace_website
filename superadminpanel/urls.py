from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('pending/', views.pending_items, name='pending_items'),
    
    # User Management Actions
    path('update-role/<int:user_id>/', views.update_user_role, name='update_user_role'),
    path('update-category/<int:user_id>/', views.update_user_category, name='update_user_category'),
    path('update-level/<int:user_id>/', views.update_user_level, name='update_user_level'),
    path('toggle-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('edit-user/<int:user_id>/', views.edit_user, name='edit_user'),
    
    # Approval Actions
    path('approve-user/<int:user_id>/', views.approve_user, name='approve_user'),
    path('reject-user/<int:user_id>/', views.reject_user, name='reject_user'),
    
    # API Endpoints
    path('role-details/<str:role>/', views.role_details, name='role_details'),

    # Master Input
    path('master-input/', views.master_input, name='master_input'),
    
    # Holiday Master
    path('holiday-master/', views.holiday_master, name='holiday_master'),
    path('holiday-master/create/', views.create_holiday, name='create_holiday'),
    path('holiday-master/<int:holiday_id>/edit/', views.edit_holiday, name='edit_holiday'),
    path('holiday-master/delete/<int:holiday_id>/', views.delete_holiday, name='delete_holiday'),
]
