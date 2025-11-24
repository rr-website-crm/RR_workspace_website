# accounts/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import CustomUser, LoginLog, UserSession, ProfileChangeRequest
from .services import log_activity_event
import logging
import re
from calendar import monthrange

logger = logging.getLogger('accounts')


def _apply_profile_updates(request, user):
    """
    Update user fields from request payload; returns True if anything changed.
    Only superadmins may change identity/role information directly.
    """
    changed_fields = []
    is_superadmin = request.user.role == 'superadmin'
    can_edit_sensitive = is_superadmin or user.profile_edit_allowed
    
    def set_field(field, value):
        if value is not None and value != getattr(user, field):
            setattr(user, field, value)
            changed_fields.append(field)
    
    # First name and last name
    first_name = request.POST.get('first_name', user.first_name or '').strip()
    last_name = request.POST.get('last_name', user.last_name or '').strip()
    set_field('first_name', first_name)
    set_field('last_name', last_name)
    
    # Email is locked in the self-service profile
    new_email = request.POST.get('email', user.email or '').strip()
    if new_email.lower() != (user.email or '').lower():
        messages.warning(request, 'Email changes are not allowed in the profile portal. Please contact the Super Admin.')
    
    # Role and department (superadmin only)
    if is_superadmin:
        new_role = request.POST.get('role', user.role)
        valid_roles = {choice[0] for choice in CustomUser.ROLE_CHOICES}
        if new_role in valid_roles:
            set_field('role', new_role)
        
        department_value = request.POST.get('department', user.department)
        set_field('department', department_value)
    else:
        # Ensure department always mirrors role for non-superadmins
        if user.department != user.role:
            user.department = user.role
            changed_fields.append('department')
    
    # Bio
    bio_value = request.POST.get('bio', user.bio or '')
    set_field('bio', bio_value)
    
    # WhatsApp number (locked)
    whatsapp_value = request.POST.get('whatsapp_number', user.whatsapp_number or '').strip()
    if whatsapp_value != (user.whatsapp_number or '').strip():
        messages.warning(request, 'WhatsApp number cannot be edited from the profile portal. Please contact the Super Admin.')
    
    # Alternate email
    alt_email_value = request.POST.get('alternate_email', user.alternate_email or '').strip()
    if can_edit_sensitive:
        if alt_email_value:
            try:
                validate_email(alt_email_value)
            except ValidationError:
                messages.error(request, 'Alternate email must be a valid email address.')
            else:
                set_field('alternate_email', alt_email_value.lower())
        else:
            set_field('alternate_email', '')
    elif alt_email_value != (user.alternate_email or ''):
        messages.warning(request, 'Alternate email changes require Super Admin approval.')
    
    # Phone number
    phone_value = request.POST.get('phone', user.phone or '').strip()
    phone_regex = re.compile(r'^\d{10}$')
    if phone_value:
        if not phone_regex.fullmatch(phone_value):
            messages.error(request, 'Phone number must be exactly 10 digits.')
        else:
            set_field('phone', phone_value)
    else:
        set_field('phone', '')
    
    # Profile image
    old_image_path = None
    if 'profile_image' in request.FILES:
        if user.profile_image:
            old_image_path = user.profile_image.name
        user.profile_image = request.FILES['profile_image']
        changed_fields.append('profile_image')
    
    # Save changes
    if changed_fields:
        timestamp = timezone.now()
        user.profile_updated_at = timestamp
        user.save(update_fields=list(set(changed_fields + ['profile_updated_at'])))
        
        # Delete old image if replaced
        if old_image_path and old_image_path != user.profile_image.name and default_storage.exists(old_image_path):
            default_storage.delete(old_image_path)
        
        log_activity_event(
            'user.profile_updated_at',
            subject_user=user,
            performed_by=user,
            metadata={'updated_fields': changed_fields},
        )
    
    return bool(changed_fields)


def _handle_identity_request(request, user):
    """Create or update a profile change request for protected fields."""
    if request.user.role == 'superadmin':
        messages.info(request, 'You can update these fields directly.')
        return
    
    # Check if there's already an approved request
    active_request = ProfileChangeRequest.objects.filter(
        user=user,
        status=ProfileChangeRequest.STATUS_APPROVED
    ).first()
    
    if active_request or user.profile_edit_allowed:
        messages.info(request, 'Edit access already granted. Save your profile changes before submitting another request.')
        return
    
    # Get requested values
    requested_first = request.POST.get('requested_first_name', user.first_name).strip()
    requested_last = request.POST.get('requested_last_name', user.last_name).strip()
    requested_email = request.POST.get('requested_email', user.email).strip()
    reason = request.POST.get('change_reason', '').strip()
    
    if not all([requested_first, requested_last, requested_email]):
        messages.error(request, 'Please provide first name, last name, and email.')
        return
    
    # Check if requested email is already taken
    if CustomUser.objects.exclude(pk=user.pk).filter(email__iexact=requested_email).exists():
        messages.error(request, 'Email address is already in use.')
        return
    
    # Check for existing pending request
    pending_request = ProfileChangeRequest.objects.filter(
        user=user,
        status=ProfileChangeRequest.STATUS_PENDING
    ).first()
    
    if pending_request:
        # Update existing request
        pending_request.current_first_name = user.first_name
        pending_request.current_last_name = user.last_name
        pending_request.current_email = user.email
        pending_request.requested_first_name = requested_first
        pending_request.requested_last_name = requested_last
        pending_request.requested_email = requested_email
        pending_request.reason = reason
        pending_request.save(update_fields=[
            'current_first_name', 'current_last_name', 'current_email',
            'requested_first_name', 'requested_last_name',
            'requested_email', 'reason', 'updated_at'
        ])
    else:
        # Create new request
        ProfileChangeRequest.objects.create(
            user=user,
            current_first_name=user.first_name,
            current_last_name=user.last_name,
            current_email=user.email,
            requested_first_name=requested_first,
            requested_last_name=requested_last,
            requested_email=requested_email,
            reason=reason
        )
    
    messages.success(request, 'Your change request has been sent to the Super Admin.')


def _consume_profile_edit_window(user):
    """Revoke the one-time edit window after it has been used."""
    if user.role == 'superadmin' or not user.profile_edit_allowed:
        return
    
    consume_time = timezone.now()
    user.profile_edit_allowed = False
    user.profile_edit_consumed_at = consume_time
    user.save(update_fields=['profile_edit_allowed', 'profile_edit_consumed_at'])
    
    # Mark the request as completed
    ProfileChangeRequest.objects.filter(
        user=user,
        status=ProfileChangeRequest.STATUS_APPROVED
    ).update(
        status=ProfileChangeRequest.STATUS_COMPLETED,
        completed_at=consume_time,
        updated_at=timezone.now()
    )


def _format_duration(start, end=None):
    """Return human readable years/months/days between two datetimes."""
    if not start:
        return 'N/A'
    
    if end is None:
        end = timezone.now()
    
    start_date = start.date()
    end_date = end.date()
    
    years = end_date.year - start_date.year
    months = end_date.month - start_date.month
    days = end_date.day - start_date.day
    
    if days < 0:
        months -= 1
        prev_month = (end_date.month - 1) or 12
        prev_year = end_date.year if end_date.month > 1 else end_date.year - 1
        days += monthrange(prev_year, prev_month)[1]
    
    if months < 0:
        years -= 1
        months += 12
    
    parts = []
    if years:
        parts.append(f"{years}y")
    if months:
        parts.append(f"{months}m")
    parts.append(f"{days}d")
    
    return ' '.join(parts)


def _process_password_change(request):
    """Process password change from profile page."""
    current_password = request.POST.get('current_password', '')
    new_password1 = request.POST.get('new_password1', '')
    new_password2 = request.POST.get('new_password2', '')
    
    if not request.user.check_password(current_password):
        messages.error(request, 'Current password is incorrect.')
        return redirect('profile')
    
    if new_password1 != new_password2:
        messages.error(request, 'New passwords do not match.')
        return redirect('profile')
    
    if len(new_password1) < 8:
        messages.error(request, 'Password must be at least 8 characters long.')
        return redirect('profile')
    
    change_timestamp = timezone.now()
    request.user.set_password(new_password1)
    request.user.password_changed_at = change_timestamp
    request.user.save(update_fields=['password', 'password_changed_at'])
    
    log_activity_event(
        'user.password_changed_at',
        subject_user=request.user,
        performed_by=request.user,
        metadata={'initiated_from': 'profile'},
    )
    
    messages.success(request, 'Password changed successfully! Please login again.')
    logout(request)
    return redirect('login')


def get_client_info(request):
    """Extract client information from request (without user_agents library)"""
    user_agent_string = request.META.get('HTTP_USER_AGENT', '')
    
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
    if ip_address:
        ip_address = ip_address.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    # Simple device detection
    device_type = 'Desktop'
    if 'Mobile' in user_agent_string or 'Android' in user_agent_string:
        device_type = 'Mobile'
    elif 'Tablet' in user_agent_string or 'iPad' in user_agent_string:
        device_type = 'Tablet'
    
    # Simple browser detection
    browser = 'Unknown'
    if 'Chrome' in user_agent_string:
        browser = 'Chrome'
    elif 'Firefox' in user_agent_string:
        browser = 'Firefox'
    elif 'Safari' in user_agent_string and 'Chrome' not in user_agent_string:
        browser = 'Safari'
    elif 'Edge' in user_agent_string or 'Edg' in user_agent_string:
        browser = 'Edge'
    elif 'MSIE' in user_agent_string or 'Trident' in user_agent_string:
        browser = 'Internet Explorer'
    
    # Simple OS detection
    os = 'Unknown'
    if 'Windows' in user_agent_string:
        os = 'Windows'
    elif 'Mac' in user_agent_string:
        os = 'macOS'
    elif 'Linux' in user_agent_string:
        os = 'Linux'
    elif 'Android' in user_agent_string:
        os = 'Android'
    elif 'iOS' in user_agent_string or 'iPhone' in user_agent_string or 'iPad' in user_agent_string:
        os = 'iOS'
    
    return {
        'ip_address': ip_address,
        'user_agent': user_agent_string,
        'device_type': device_type,
        'browser': browser,
        'os': os,
    }


@never_cache
@csrf_protect
def login_view(request):
    """Secure login view with session management"""
    
    # Redirect if already logged in
    if request.user.is_authenticated:
        return redirect('home_dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        remember = request.POST.get('remember')
        
        # Validate input
        if not email or not password:
            messages.error(request, 'Please provide both email and password.')
            logger.warning(f"Login attempt with missing credentials from IP: {get_client_info(request)['ip_address']}")
            return render(request, 'accounts/login.html')
        
        # Check if user exists
        try:
            user_obj = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            messages.error(request, 'Account does not exist. Please register first.')
            logger.info(f"Login attempt for non-existent account: {email}")
            return render(request, 'accounts/login.html')
        
        # Check if user is approved
        if not user_obj.is_approved:
            if user_obj.approval_status == 'rejected':
                messages.error(request, 'Your registration has been rejected. Please contact administrator.')
            else:
                messages.warning(request, 'Your account is pending approval. Please wait for admin to approve your request.')
            logger.info(f"Login attempt by unapproved user: {email}")
            return render(request, 'accounts/login.html')
        
        # Authenticate user
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            # Check if user is active
            if not user.is_active:
                messages.error(request, 'Your account has been deactivated. Please contact administrator.')
                logger.warning(f"Login attempt by inactive user: {email}")
                return render(request, 'accounts/login.html')
            
            # Generate Employee ID on first login
            if not user.employee_id:
                generated_at = timezone.now()
                with transaction.atomic():
                    user.first_login_date = generated_at
                    user.employee_id = user.generate_employee_id()
                    user.employee_id_generated_at = generated_at
                    user.employee_id_assigned_at = generated_at
                    user.save(update_fields=[
                        'first_login_date',
                        'employee_id',
                        'employee_id_generated_at',
                        'employee_id_assigned_at',
                    ])
                    logger.info(f"Generated Employee ID {user.employee_id} for user: {email}")
                
                log_activity_event(
                    'employee_id.generated_at',
                    subject_user=user,
                    metadata={
                        'employee_id': user.employee_id,
                        'source': 'login',
                        'performed_by': 'system',
                    },
                )
                log_activity_event(
                    'employee_id.assigned_at',
                    subject_user=user,
                    metadata={
                        'employee_id': user.employee_id,
                        'source': 'login',
                        'performed_by': 'system',
                    },
                )
            
            # Login the user
            login(request, user)
            
            # Session security setup
            request.session.cycle_key()  # Prevent session fixation
            request.session['session_start'] = timezone.now().isoformat()
            request.session['last_activity'] = timezone.now().isoformat()
            
            # Get client info
            client_info = get_client_info(request)
            request.session['session_ip'] = client_info['ip_address']
            request.session['session_user_agent'] = client_info['user_agent']
            
            # Set session expiry
            if user.role == 'superadmin':
                request.session.set_expiry(1209600)  # 14 days
            else:
                if not remember:
                    request.session.set_expiry(0)  # browser close
                else:
                    request.session.set_expiry(86400)  # 24 hours
            
            # Create login log
            LoginLog.objects.create(
                user=user,
                employee_id=user.employee_id,
                session_key=request.session.session_key,
                **client_info
            )
            
            # Create user session
            UserSession.objects.create(
                user=user,
                session_key=request.session.session_key,
                ip_address=client_info['ip_address'],
                user_agent=client_info['user_agent'],
                expires_at=timezone.now() + timezone.timedelta(hours=1)
            )
            
            logger.info(f"Successful login for user: {email} from IP: {client_info['ip_address']}")
            
            # Update login timestamps
            login_timestamp = timezone.now()
            updated_fields = []
            
            if not user.first_successful_login_at:
                user.first_successful_login_at = login_timestamp
                if not user.first_login_date:
                    user.first_login_date = login_timestamp
                updated_fields.extend(['first_successful_login_at', 'first_login_date'])
            
            user.last_login_at = login_timestamp
            updated_fields.append('last_login_at')
            
            if updated_fields:
                user.save(update_fields=list(dict.fromkeys(updated_fields)))
            
            if 'first_successful_login_at' in updated_fields:
                log_activity_event(
                    'user.first_successful_login_at',
                    subject_user=user,
                    performed_by=user,
                    metadata={'source': 'login'},
                )
            
            log_activity_event(
                'user.last_login_at',
                subject_user=user,
                performed_by=user,
                metadata={
                    'ip': client_info['ip_address'],
                    'session_key': request.session.session_key,
                },
            )
            
            messages.success(request, f'Welcome back, {user.get_full_name()}!')
            
            # Redirect based on role
            return redirect('home_dashboard')
        
        else:
            messages.error(request, 'Invalid email or password.')
            logger.warning(f"Failed login attempt for: {email} from IP: {get_client_info(request)['ip_address']}")
    
    return render(request, 'accounts/login.html')


@never_cache
@csrf_protect
def register_view(request):
    """Secure registration view"""
    
    if request.user.is_authenticated:
        return redirect('home_dashboard')
    
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        
        errors = []
        
        # Required fields
        if not all([full_name, email, whatsapp_number, password1, password2]):
            errors.append('All required fields must be filled.')
        
        # Split full name
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if not first_name:
            errors.append('Please enter your full name.')
        
        # Email regex
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            errors.append('Please enter a valid email address.')
        
        # WhatsApp validation
        if not whatsapp_number.isdigit() or len(whatsapp_number) != 10:
            errors.append('WhatsApp number must be exactly 10 digits.')
        
        # Password rules
        if len(password1) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        if password1 != password2:
            errors.append('Passwords do not match.')
        
        # Email exists?
        if CustomUser.objects.filter(email=email).exists():
            errors.append('Email is already registered.')
        
        # Return errors
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/register.html')
        
        try:
            # Generate username
            username = email.split('@')[0]
            base_username = username
            counter = 1
            
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            # Create user
            with transaction.atomic():
                now = timezone.now()
                user = CustomUser.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    whatsapp_number=whatsapp_number,
                    role='user',
                    is_approved=False,
                    approval_status='pending',
                    is_active=True,
                    registered_at=now,
                    approval_requested_at=now,
                )
                user.set_password(password1)
                user.save()
            
            client_info = get_client_info(request)
            
            log_activity_event(
                'user.registered_at',
                subject_user=user,
                performed_by=user,
                metadata={
                    'ip': client_info['ip_address'],
                    'user_agent': client_info['user_agent'],
                },
            )
            
            log_activity_event(
                'user.approval_requested_at',
                subject_user=user,
                performed_by=user,
                metadata={'approval_status': user.approval_status},
            )
            
            messages.success(
                request,
                "Registration successful! Wait for Admin approval."
            )
            return redirect('login')
        
        except Exception as e:
            logger.error(f"Registration error for {email}: {str(e)}")
            messages.error(request, "An error occurred. Please try again.")
            return render(request, 'accounts/register.html')
    
    return render(request, 'accounts/register.html')


@login_required
def logout_view(request):
    """Secure logout view with session cleanup"""
    
    try:
        session_key = request.session.session_key
        if session_key:
            login_log = LoginLog.objects.filter(
                user=request.user,
                session_key=session_key,
                is_active=True
            ).first()
            
            if login_log:
                login_log.mark_logout()
            
            user_session = UserSession.objects.filter(
                user=request.user,
                session_key=session_key,
                is_active=True
            ).first()
            
            if user_session:
                user_session.is_active = False
                user_session.save()
        
        logger.info(f"User logged out: {request.user.email}")
        
    except Exception as e:
        logger.error(f"Error during logout for {request.user.email}: {str(e)}")
    
    logout(request)
    request.session.flush()  # ENSURES SESSION EXPIRES ONLY ON LOGOUT
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


@login_required
def profile_view(request):
    """User profile view"""
    user = request.user
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')
        
        if form_type == 'profile':
            consume_after_post = user.role != 'superadmin' and user.profile_edit_allowed
            updated = _apply_profile_updates(request, user)
            
            if updated:
                logger.info(f"Profile updated for user: {user.email}")
                messages.success(request, 'Profile updated successfully!')
            else:
                messages.info(request, 'No changes detected.')
            
            if consume_after_post:
                _consume_profile_edit_window(user)
        
        elif form_type == 'identity_request':
            _handle_identity_request(request, user)
        
        return redirect('profile')
    
    # Get user's login history
    login_logs = LoginLog.objects.filter(user=user).order_by('-login_time')[:10]
    
    # Get pending and active requests
    pending_request = ProfileChangeRequest.objects.filter(
        user=user,
        status=ProfileChangeRequest.STATUS_PENDING
    ).first()
    
    active_request = ProfileChangeRequest.objects.filter(
        user=user,
        status=ProfileChangeRequest.STATUS_APPROVED
    ).first()
    
    # Determine if user can self-edit profile
    can_self_edit_profile = user.role == 'superadmin' or user.profile_edit_allowed
    
    # Profile edit state
    if user.role == 'superadmin':
        profile_edit_state = 'superadmin'
    elif user.profile_edit_allowed:
        profile_edit_state = 'active'
    elif pending_request:
        profile_edit_state = 'pending'
    else:
        profile_edit_state = 'locked'
    
    # Request button label
    request_button_label = 'Update Request' if pending_request else 'Request for Edit'
    show_request_button = user.role != 'superadmin'
    request_button_disabled = bool(active_request or user.profile_edit_allowed)
    
    context = {
        'user': user,
        'login_logs': login_logs,
        'is_superadmin': user.role == 'superadmin',
        'role_choices': CustomUser.ROLE_CHOICES,
        'pending_request': pending_request,
        'active_request': active_request,
        'pending_identity_request': pending_request,
        'active_identity_request': active_request,
        'can_self_edit_profile': can_self_edit_profile,
        'profile_edit_state': profile_edit_state,
        'profile_edit_granted_at': user.profile_edit_granted_at,
        'profile_edit_consumed_at': user.profile_edit_consumed_at,
        'show_request_button': show_request_button,
        'request_button_label': request_button_label,
        'request_button_disabled': request_button_disabled,
        'account_age_display': _format_duration(user.date_joined),
        'role_tenure_display': _format_duration(user.role_assigned_at or user.date_joined),
    }
    
    return render(request, 'accounts/profile.html', context)


@login_required
def change_password_view(request):
    """Change password view"""
    
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # Validate current password
        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'accounts/change_password.html')
        
        # Validate new passwords
        if new_password1 != new_password2:
            messages.error(request, 'New passwords do not match.')
            return render(request, 'accounts/change_password.html')
        
        if len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'accounts/change_password.html')
        
        # Change password
        change_timestamp = timezone.now()
        request.user.set_password(new_password1)
        request.user.password_changed_at = change_timestamp
        request.user.save(update_fields=['password', 'password_changed_at'])
        
        log_activity_event(
            'user.password_changed_at',
            subject_user=request.user,
            performed_by=request.user,
            metadata={'initiated_from': 'profile'},
        )
        
        logger.info(f"Password changed for user: {request.user.email}")
        messages.success(request, 'Password changed successfully! Please login again.')
        
        logout(request)
        return redirect('login')
    
    return render(request, 'accounts/change_password.html')


@login_required
def superadmin_dashboard(request):
    return redirect('superadmin_dashboard')


@login_required
def manage_users(request):
    users = CustomUser.objects.all()
    return render(request, 'superadminpanel/manage_users.html', {'users': users})


@login_required
def pending_items(request):
    pending_users = CustomUser.objects.filter(approval_status='pending')
    return render(request, 'superadminpanel/pending_items.html', {'pending_users': pending_users})