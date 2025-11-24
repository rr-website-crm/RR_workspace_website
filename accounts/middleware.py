from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import logout
from datetime import timedelta
import logging

logger = logging.getLogger('accounts')


class LoginRequiredMiddleware:
    """
    Middleware to ensure users are logged in to access any page except public pages
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Define public URLs that don't require authentication
        self.public_urls = [
            reverse('login'),
            reverse('register'),
            '/accounts/password-reset/',
            '/accounts/password-reset-confirm/',
            '/admin/',  # Django admin has its own auth
            '/static/',
            '/media/',
        ]
    
    def __call__(self, request):
        # Check if the path is public
        is_public = any(request.path.startswith(url) for url in self.public_urls)
        
        # If not authenticated and trying to access protected page
        if not request.user.is_authenticated and not is_public:
            logger.warning(f"Unauthorized access attempt to {request.path} from IP: {self.get_client_ip(request)}")
            return redirect('login')
        
        # If authenticated but not approved, only allow logout
        if request.user.is_authenticated and not request.user.is_approved:
            if not is_public and request.path != reverse('logout'):
                logger.info(f"Unapproved user {request.user.email} attempted to access {request.path}")
                logout(request)
                return redirect('login')
        
        response = self.get_response(request)
        return response
    
    def get_client_ip(self, request):
        """Get the client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SessionSecurityMiddleware:
    """
    Middleware for session security:
    - Session rotation after login
    - Idle timeout
    - Absolute timeout
    - Concurrent session prevention
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            # Check for session timeout
            if self.is_session_expired(request):
                logger.info(f"Session expired for user: {request.user.email}")
                logout(request)
                return redirect('login')
            
            # Update last activity
            request.session['last_activity'] = timezone.now().isoformat()
            
            # Check for session hijacking indicators
            if self.detect_session_hijacking(request):
                logger.warning(f"Potential session hijacking detected for user: {request.user.email}")
                logout(request)
                return redirect('login')
        
        response = self.get_response(request)
        return response
    
    def is_session_expired(self, request):
        """Check if session has expired (idle or absolute timeout)"""
        
        # Check idle timeout
        last_activity = request.session.get('last_activity')
        if last_activity:
            last_activity_time = timezone.datetime.fromisoformat(last_activity)
            idle_duration = timezone.now() - last_activity_time
            
            if idle_duration.total_seconds() > getattr(settings, 'SESSION_IDLE_TIMEOUT', 1800):
                return True
        
        # Check absolute timeout
        session_start = request.session.get('session_start')
        if session_start:
            session_start_time = timezone.datetime.fromisoformat(session_start)
            session_duration = timezone.now() - session_start_time
            
            if session_duration.total_seconds() > getattr(settings, 'SESSION_ABSOLUTE_TIMEOUT', 3600):
                return True
        
        return False
    
    def detect_session_hijacking(self, request):
        """
        Detect potential session hijacking by checking:
        - IP address changes
        - User agent changes
        """
        current_ip = self.get_client_ip(request)
        current_user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Get stored session info
        stored_ip = request.session.get('session_ip')
        stored_user_agent = request.session.get('session_user_agent')
        
        # First time - store the info
        if not stored_ip:
            request.session['session_ip'] = current_ip
            request.session['session_user_agent'] = current_user_agent
            return False
        
        # Check for changes
        if stored_ip != current_ip:
            logger.warning(f"IP change detected: {stored_ip} -> {current_ip} for user: {request.user.email}")
            return True
        
        if stored_user_agent != current_user_agent:
            logger.warning(f"User agent change detected for user: {request.user.email}")
            return True
        
        return False
    
    def get_client_ip(self, request):
        """Get the client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CSPMiddleware:
    """
    Content Security Policy Middleware
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Set CSP headers
        csp_policy = "; ".join([
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com",
            "font-src 'self' fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
        ])
        
        response['Content-Security-Policy'] = csp_policy
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class RateLimitMiddleware:
    """
    Simple rate limiting middleware
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_cache = {}
    
    def __call__(self, request):
        # Only rate limit POST requests (login, registration)
        if request.method == 'POST' and request.path in [reverse('login'), reverse('register')]:
            client_ip = self.get_client_ip(request)
            
            # Check rate limit
            if self.is_rate_limited(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("Too many requests. Please try again later.")
        
        response = self.get_response(request)
        return response
    
    def is_rate_limited(self, ip):
        """Check if IP has exceeded rate limit"""
        current_time = timezone.now()
        
        if ip not in self.rate_limit_cache:
            self.rate_limit_cache[ip] = []
        
        # Remove old entries (older than 15 minutes)
        self.rate_limit_cache[ip] = [
            timestamp for timestamp in self.rate_limit_cache[ip]
            if current_time - timestamp < timedelta(minutes=15)
        ]
        
        # Check if exceeded limit (5 attempts in 15 minutes)
        if len(self.rate_limit_cache[ip]) >= 5:
            return True
        
        # Add current attempt
        self.rate_limit_cache[ip].append(current_time)
        return False
    
    def get_client_ip(self, request):
        """Get the client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip