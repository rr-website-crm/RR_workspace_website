from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser
from superadminpanel import services as portal_services


def admin_required(view_func):
    """Ensure the signed-in user is an admin."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        if request.user.role != 'admin':
            messages.error(request, 'You do not have permission to access the admin panel.')
            return redirect('home_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@admin_required
def admin_dashboard(request):
    context = portal_services.get_dashboard_context()
    role_rows = context.get('role_active_counts') or []
    context['role_active_counts'] = [
        row for row in role_rows
        if (row.get('role') or '').lower() not in {'admin', 'superadmin'}
    ]
    return render(request, 'adminpanel/admin_dashboard.html', context)


@login_required
@admin_required
def role_details(request, role):
    users_data = portal_services.get_role_details_data(role)
    return JsonResponse({'users': users_data})


@login_required
@admin_required
def manage_users(request):
    context = portal_services.get_manage_users_context(performed_by=request.user)
    return render(request, 'adminpanel/manage_users.html', context)


@login_required
@admin_required
def update_user_role(request, user_id):
    portal_services.update_user_role(request, user_id)
    return redirect('adminpanel:manage_users')


@login_required
@admin_required
def update_user_category(request, user_id):
    portal_services.update_user_category(request, user_id)
    return redirect('adminpanel:manage_users')


@login_required
@admin_required
def update_user_level(request, user_id):
    portal_services.update_user_level(request, user_id)
    return redirect('adminpanel:manage_users')


@login_required
@admin_required
def toggle_user_status(request, user_id):
    portal_services.toggle_user_status(request, user_id)
    return redirect('adminpanel:manage_users')


@login_required
@admin_required
def edit_user(request, user_id):
    edit_target = get_object_or_404(CustomUser, id=user_id)
    target_role = (getattr(edit_target, 'role', '') or '').lower()
    actor_role = (getattr(request.user, 'role', '') or '').lower()
    if actor_role == 'admin' and target_role in {'superadmin', 'admin'}:
        messages.error(request, portal_services.RESTRICTED_ROLE_MESSAGE)
        return redirect('adminpanel:manage_users')
    if request.method == 'POST':
        portal_services.process_edit_user_form(request, edit_target)
        return redirect('adminpanel:manage_users')
    return render(request, 'adminpanel/edit_user.html', {'edit_user': edit_target})


@login_required
@admin_required
def pending_items(request):
    context = portal_services.get_pending_items_context()
    return render(request, 'adminpanel/pending_items.html', context)


@login_required
@admin_required
def approve_user(request, user_id):
    portal_services.approve_user(request, user_id)
    return redirect('adminpanel:pending_items')


@login_required
@admin_required
def reject_user(request, user_id):
    portal_services.reject_user(request, user_id)
    return redirect('adminpanel:pending_items')


@login_required
@admin_required
def approve_profile_request(request, request_id):
    portal_services.approve_profile_request(request, request_id)
    return redirect('adminpanel:pending_items')


@login_required
@admin_required
def reject_profile_request(request, request_id):
    portal_services.reject_profile_request(request, request_id)
    return redirect('adminpanel:pending_items')
