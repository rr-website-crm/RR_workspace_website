# account view.py:
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.hashers import make_password
from django.db import transaction
from .models import CustomUser, LoginLog, UserSession
from .services import log_activity_event
import logging
import re

logger = logging.getLogger('accounts')


def _apply_profile_updates(request, user):
    """Update user fields from request payload; returns True if anything changed."""
    track_fields = ['first_name', 'last_name', 'phone', 'whatsapp_number', 'department']
    changed_fields = []

    for field in track_fields:
        new_value = request.POST.get(field, getattr(user, field))
        if new_value != getattr(user, field):
            setattr(user, field, new_value)
            changed_fields.append(field)

    if 'profile_image' in request.FILES:
        user.profile_image = request.FILES['profile_image']
        changed_fields.append('profile_image')

    if changed_fields:
        timestamp = timezone.now()
        user.profile_updated_at = timestamp
        user.save()

        log_activity_event(
            'user.profile_updated_at',
            subject_user=user,
            performed_by=user,
            metadata={'updated_fields': changed_fields},
        )

    return bool(changed_fields)


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
                request.session.set_expiry(1209600)  # 14 days (or choose higher)
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


# @never_cache
# @csrf_protect
# def register_view(request):
#     """Secure registration view"""
    
#     # Redirect if already logged in
#     if request.user.is_authenticated:
#         return redirect('home_dashboard')
    
#     if request.method == 'POST':
#         # Get form data
#         full_name = request.POST.get('full_name', '').strip()
#         email = request.POST.get('email', '').strip().lower()
#         whatsapp_number = request.POST.get('whatsapp_number', '').strip()
#         password1 = request.POST.get('password1', '')
#         password2 = request.POST.get('password2', '')
        
#         # Validation
#         errors = []
        
#         # Validate required fields
#         if not all([full_name, email, whatsapp_number, password1, password2]):
#             errors.append('All required fields must be filled.')
        
#         # Parse full name into first and last name
#         name_parts = full_name.split(' ', 1)
#         first_name = name_parts[0] if name_parts else ''
#         last_name = name_parts[1] if len(name_parts) > 1 else ''
        
#         if not first_name:
#             errors.append('Please enter your full name.')
        
#         # Validate email format
#         email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
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


# @login_required
# def logout_view(request):
#     """Secure logout view with session cleanup"""
    
#     try:
#         # Mark the current login log as logged out
#         session_key = request.session.session_key
#         if session_key:
#             login_log = LoginLog.objects.filter(
#                 user=request.user,
#                 session_key=session_key,
#                 is_active=True
#             ).first()
            
#             if login_log:
#                 login_log.mark_logout()
            
#             # Deactivate user session
#             user_session = UserSession.objects.filter(
#                 user=request.user,
#                 session_key=session_key,
#                 is_active=True
#             ).first()
            
#             if user_session:
#                 user_session.is_active = False
#                 user_session.save()
        
#         logger.info(f"User logged out: {request.user.email}")
        
#     except Exception as e:
#         logger.error(f"Error during logout for {request.user.email}: {str(e)}")
    
#     # Logout user
#     logout(request)
#     messages.success(request, 'You have been logged out successfully.')
#     return redirect('login')
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
    request.session.flush()   # <-- ENSURES SESSION EXPIRES ONLY ON LOGOUT
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

@login_required
def profile_view(request):
    """User profile view"""
    
    if request.method == 'POST':
        user = request.user
        
        updated = _apply_profile_updates(request, user)
        
        if updated:
            logger.info(f"Profile updated for user: {user.email}")
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    # Get user's login history
    login_logs = LoginLog.objects.filter(user=request.user).order_by('-login_time')[:10]
    
    context = {
        'user': request.user,
        'login_logs': login_logs,
    }
    
    return render(request, 'accounts/profile.html', context)


# @login_required
# def change_password_view(request):
#     """Change password view"""
    
#     if request.method == 'POST':
#         current_password = request.POST.get('current_password')
#         new_password1 = request.POST.get('new_password1')
#         new_password2 = request.POST.get('new_password2')
        
#         # Validate current password
#         if not request.user.check_password(current_password):
#             messages.error(request, 'Current password is incorrect.')
#             return render(request, 'accounts/change_password.html')
        
#         # Validate new passwords
#         if new_password1 != new_password2:
#             messages.error(request, 'New passwords do not match.')
#             return render(request, 'accounts/change_password.html')
        
#         if len(new_password1) < 8:
#             messages.error(request, 'Password must be at least 8 characters long.')
#             return render(request, 'accounts/change_password.html')
        
#         # Change password
#         request.user.set_password(new_password1)
#         request.user.save()
        
#         logger.info(f"Password changed for user: {request.user.email}")
#         messages.success(request, 'Password changed successfully! Please login again.')
        
#         # Logout user after password change
#         logout(request)
#         return redirect('login')
    
#     return render(request, 'accounts/change_password.html')

#         if not re.match(email_regex, email):
#             errors.append('Please enter a valid email address.')
        
#         # Validate WhatsApp number (10 digits)
#         if not whatsapp_number.isdigit() or len(whatsapp_number) != 10:
#             errors.append('WhatsApp number must be exactly 10 digits.')
        
#         # Validate password
#         if len(password1) < 8:
#             errors.append('Password must be at least 8 characters long.')
        
#         # Validate password match
#         if password1 != password2:
#             errors.append('Passwords do not match.')
        
#         # Check if user exists
#         if CustomUser.objects.filter(email=email).exists():
#             errors.append('Email is already registered.')
        
#         # If there are errors, display them
#         if errors:
#             for error in errors:
#                 messages.error(request, error)
#             logger.warning(f"Registration validation failed for email: {email}")
#             return render(request, 'accounts/register.html')
        
#         try:
#             # Generate username from email (part before @)
#             username = email.split('@')[0]
#             base_username = username
#             counter = 1
            
#             # Ensure username is unique
#             while CustomUser.objects.filter(username=username).exists():
#                 username = f"{base_username}{counter}"
#                 counter += 1
            
#             # Create user
#             with transaction.atomic():
#                 user = CustomUser.objects.create(
#                     username=username,
#                     email=email,
#                     first_name=first_name,
#                     last_name=last_name,
#                     whatsapp_number=whatsapp_number,
#                     role='user',  # Default role
#                     is_approved=False,  # Requires admin approval
#                     approval_status='pending',
#                     is_active=True,
#                 )
#                 user.set_password(password1)  # Hash the password
#                 user.save()
            
#             logger.info(f"New user registered: {email} - Awaiting approval")
#             messages.success(
#                 request, 
#                 'Registration successful! Wait for the Admin to Approve it. '
#                 'You will be able to login once your account is approved.'
#             )
#             return redirect('login')
        
#         except Exception as e:
#             logger.error(f"Error during registration for {email}: {str(e)}")
#             messages.error(request, 'An error occurred during registration. Please try again.')
#             return render(request, 'accounts/register.html')
    
#     return render(request, 'accounts/register.html')

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
def logout_view(request):
    """Secure logout view with session cleanup"""
    
    try:
        # Mark the current login log as logged out
        session_key = request.session.session_key
        if session_key:
            login_log = LoginLog.objects.filter(
                user=request.user,
                session_key=session_key,
                is_active=True
            ).first()
            
            if login_log:
                login_log.mark_logout()
            
            # Deactivate user session
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
    
    # Logout user
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


@login_required
def profile_view(request):
    """User profile view"""
    
    if request.method == 'POST':
        user = request.user
        
        updated = _apply_profile_updates(request, user)
        
        if updated:
            logger.info(f"Profile updated for user: {user.email}")
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    # Get user's login history
    login_logs = LoginLog.objects.filter(user=request.user).order_by('-login_time')[:10]
    
    context = {
        'user': request.user,
        'login_logs': login_logs,
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
        
        # Logout user after password change
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
