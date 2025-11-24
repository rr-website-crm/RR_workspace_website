from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils import timezone
from django.contrib import messages
from .models import CustomUser, LoginLog, UserSession, PasswordResetToken, ProfileChangeRequest
from .services import log_activity_event

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Custom User Admin with approval functionality"""
    list_display = [
        'employee_id', 'email', 'get_full_name', 'role',
        'approval_status_badge', 'is_active', 'date_joined'
    ]
    list_filter = ['role', 'approval_status', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id', 'username']
    ordering = ['-date_joined']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('username', 'email', 'first_name', 'last_name', 'password')
        }),
        ('Contact Information', {
            'fields': ('phone', 'whatsapp_number', 'department', 'bio')
        }),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Approval Status', {
            'fields': ('approval_status', 'is_approved', 'approved_by', 'approved_at')
        }),
        ('Employee Information', {
            'fields': ('employee_id', 'first_login_date', 'profile_image')
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')
        }),
    )
    
    readonly_fields = [
        'employee_id', 'first_login_date', 'last_login',
        'date_joined', 'created_at', 'updated_at'
    ]
    
    actions = ['approve_users', 'reject_users', 'activate_users', 'deactivate_users']
    
    # ---------------------------------------------
    # SUPERADMIN AUTO LOGIC HERE
    # ---------------------------------------------
    def save_model(self, request, obj, form, change):
        """Automatically approve superadmins and assign role"""
        if obj.is_superuser:
            obj.role = "superadmin"
            obj.is_approved = True
            obj.approval_status = "approved"
            obj.is_staff = True  # Ensure admin panel access
        super().save_model(request, obj, form, change)
    
    # ---------------------------------------------
    def approval_status_badge(self, obj):
        """Display approval status with color badge"""
        if obj.role == 'superadmin':
            return format_html(
                '<span style="background-color: #007BFF; color: white; padding: 3px 10px;'
                'border-radius: 3px; font-size: 11px;">SUPERADMIN</span>'
            )
        colors = {
            'pending': '#FFA500',
            'approved': '#28A745',
            'rejected': '#DC3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px;'
            'border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.approval_status, '#6c757d'),
            obj.approval_status.upper()
        )
    approval_status_badge.short_description = 'Status'
    
    # ---------------------------------------------
    # Protect Superadmin from modification
    # ---------------------------------------------
    def has_delete_permission(self, request, obj=None):
        if obj and obj.role == 'superadmin':
            return False
        return super().has_delete_permission(request, obj)
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users (superadmin protected)"""
        safe_qs = queryset.exclude(role='superadmin')
        count = safe_qs.update(is_active=False)
        self.message_user(request, f'{count} user(s) deactivated.')
    deactivate_users.short_description = 'Deactivate selected users'
    
    # ---------------------------------------------
    def approve_users(self, request, queryset):
        """Approve selected users"""
        count = 0
        for user in queryset.filter(approval_status='pending'):
            if user.role != 'superadmin':
                user.approve_user(request.user)
                count += 1
        self.message_user(request, f'{count} user(s) approved successfully.')
    approve_users.short_description = 'Approve selected users'


@admin.register(ProfileChangeRequest)
class ProfileChangeRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'current_email', 'requested_email', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__email', 'requested_email', 'requested_first_name', 'requested_last_name']
    actions = ['approve_requests', 'reject_requests']
    
    def approve_requests(self, request, queryset):
        success = 0
        for change_request in queryset.filter(status=ProfileChangeRequest.STATUS_PENDING):
            if change_request.approve(request.user):
                log_activity_event(
                    'user.email_change_approved_at',
                    subject_user=change_request.user,
                    performed_by=request.user,
                    metadata={
                        'old_email': change_request.current_email,
                        'new_email': change_request.requested_email,
                    }
                )
                success += 1
        if success:
            self.message_user(request, f"{success} request(s) approved.", messages.SUCCESS)
        else:
            self.message_user(request, "No requests approved.", messages.WARNING)
    approve_requests.short_description = "Approve selected requests"
    
    def reject_requests(self, request, queryset):
        success = 0
        for change_request in queryset.filter(status=ProfileChangeRequest.STATUS_PENDING):
            if change_request.reject(request.user):
                success += 1
        if success:
            self.message_user(request, f"{success} request(s) rejected.", messages.SUCCESS)
        else:
            self.message_user(request, "No requests rejected.", messages.WARNING)
    reject_requests.short_description = "Reject selected requests"