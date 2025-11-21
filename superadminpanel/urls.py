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
    path('profile-request/<int:request_id>/approve/', views.approve_profile_request, name='approve_profile_request'),
    path('profile-request/<int:request_id>/reject/', views.reject_profile_request, name='reject_profile_request'),
    
    # API Endpoints
    path('role-details/<str:role>/', views.role_details, name='role_details'),

    # Master Input
    path('master-input/', views.master_input, name='master_input'),
    
    # Holiday Master
    path('holiday-master/', views.holiday_master, name='holiday_master'),
    path('holiday-master/create/', views.create_holiday, name='create_holiday'),
    path('holiday-master/<int:holiday_id>/edit/', views.edit_holiday, name='edit_holiday'),
    path('holiday-master/delete/<int:holiday_id>/', views.delete_holiday, name='delete_holiday'),

    # Price Master
    path('price-master/', views.price_master, name='price_master'),
    path('price-master/create/', views.create_price, name='create_price'),
    path('price-master/<int:price_id>/edit/', views.edit_price, name='edit_price'),
    path('price-master/delete/<int:price_id>/', views.delete_price, name='delete_price'),

    # Referencing Master
    path('referencing-master/', views.referencing_master, name='referencing_master'),
    path('referencing-master/create/', views.create_reference, name='create_reference'),
    path('referencing-master/<str:reference_id>/edit/', views.edit_reference, name='edit_reference'),
    path('referencing-master/delete/<str:reference_id>/', views.delete_reference, name='delete_reference'),

    # Add these URLs to your superadminpanel/urls.py

    # Academic Writing Style Master
    path('academic-writing-master/', views.academic_writing_master, name='academic_writing_master'),
    path('academic-writing-master/create/', views.create_writing, name='create_writing'),
    path('academic-writing-master/<str:writing_id>/edit/', views.edit_writing, name='edit_writing'),
    path('academic-writing-master/delete/<str:writing_id>/', views.delete_writing, name='delete_writing'),
]
