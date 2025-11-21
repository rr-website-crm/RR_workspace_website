# superadminpanel/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from datetime import datetime, timedelta
from bson import ObjectId
from bson.errors import InvalidId
import logging

from accounts.models import CustomUser
from accounts.services import log_activity_event
from .models import Holiday, PriceMaster, ReferencingMaster, AcademicWritingMaster
from . import user_services as portal_services

logger = logging.getLogger('superadmin')


def superadmin_required(view_func):
    """Decorator to check if user is superadmin"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        if request.user.role != 'superadmin':
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('home_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ========================================
# USER MANAGEMENT VIEWS
# ========================================

@login_required
@superadmin_required
def superadmin_dashboard(request):
    """SuperAdmin Dashboard"""
    context = portal_services.get_dashboard_context()
    return render(request, 'superadmin_dashboard.html', context)


@login_required
@superadmin_required
def role_details(request, role):
    """Return JSON list of today's active users for role"""
    users_data = portal_services.get_role_details_data(role)
    return JsonResponse({'users': users_data})


@login_required
@superadmin_required
def manage_users(request):
    """Manage all users"""
    context = portal_services.get_manage_users_context(performed_by=request.user)
    return render(request, 'manage_users.html', context)


@login_required
@superadmin_required
def update_user_role(request, user_id):
    """Update user role"""
    portal_services.update_user_role(request, user_id)
    return redirect('manage_users')


@login_required
@superadmin_required
def update_user_category(request, user_id):
    """Update user category/department"""
    portal_services.update_user_category(request, user_id)
    return redirect('manage_users')


@login_required
@superadmin_required
def update_user_level(request, user_id):
    """Update user level"""
    portal_services.update_user_level(request, user_id)
    return redirect('manage_users')


@login_required
@superadmin_required
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    portal_services.toggle_user_status(request, user_id)
    return redirect('manage_users')


@login_required
@superadmin_required
def edit_user(request, user_id):
    """Edit user profile"""
    edit_target = get_object_or_404(CustomUser, id=user_id)
    
    if request.method == 'POST':
        portal_services.process_edit_user_form(request, edit_target)
        return redirect('manage_users')
    
    context = {
        'edit_user': edit_target,
    }
    return render(request, 'edit_user.html', context)


@login_required
@superadmin_required
def pending_items(request):
    """Pending approvals page"""
    context = portal_services.get_pending_items_context()
    return render(request, 'pending_items.html', context)


@login_required
@superadmin_required
def approve_user(request, user_id):
    """Approve user registration"""
    portal_services.approve_user(request, user_id)
    return redirect('pending_items')


@login_required
@superadmin_required
def reject_user(request, user_id):
    """Reject user registration"""
    portal_services.reject_user(request, user_id)
    return redirect('pending_items')


@login_required
@superadmin_required
def approve_profile_request(request, request_id):
    """Approve profile change request"""
    portal_services.approve_profile_request(request, request_id)
    return redirect('pending_items')


@login_required
@superadmin_required
def reject_profile_request(request, request_id):
    """Reject profile change request"""
    portal_services.reject_profile_request(request, request_id)
    return redirect('pending_items')


# ========================================
# MASTER INPUT VIEWS
# ========================================

@login_required
@superadmin_required
def master_input(request):
    """Master Input Dashboard"""
    return render(request, 'master_input.html')


# ========================================
# HOLIDAY MASTER VIEWS
# ========================================

@login_required
@superadmin_required
def holiday_master(request):
    """Holiday Master - List all holidays"""
    try:
        raw_holidays = list(Holiday.objects.all().order_by('-created_at'))
        holidays = [
            holiday for holiday in raw_holidays
            if not getattr(holiday, 'is_deleted', False)
        ]
        context = {
            'holidays': holidays,
            'total_holidays': len(holidays),
        }
        return render(request, 'holiday_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading holiday master: {str(e)}")
        messages.error(request, 'Error loading holidays.')
        return render(request, 'holiday_master.html', {'holidays': []})


@login_required
@superadmin_required
def create_holiday(request):
    """Create a new holiday"""
    if request.method == 'POST':
        try:
            # Get form data
            holiday_name = request.POST.get('holiday_name', '').strip()
            holiday_type = request.POST.get('holiday_type', 'full_day')
            date_type = request.POST.get('date_type', 'single')
            description = request.POST.get('description', '').strip()
            
            # Validation
            if not holiday_name:
                messages.error(request, 'Holiday name is required.')
                return redirect('holiday_master')
            
            # Create holiday object
            with transaction.atomic():
                holiday = Holiday()
                holiday.holiday_name = holiday_name
                holiday.holiday_type = holiday_type
                holiday.date_type = date_type
                holiday.description = description
                holiday.created_by = request.user
                holiday.created_at = timezone.now()
                
                # Handle dates based on type
                if date_type == 'single':
                    date_str = request.POST.get('date')
                    if not date_str:
                        messages.error(request, 'Date is required.')
                        return redirect('holiday_master')
                    
                    holiday.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_date = holiday.date
                    end_date = holiday.date
                    
                else:  # consecutive
                    from_date_str = request.POST.get('from_date')
                    to_date_str = request.POST.get('to_date')
                    
                    if not from_date_str or not to_date_str:
                        messages.error(request, 'From date and To date are required.')
                        return redirect('holiday_master')
                    
                    holiday.from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                    holiday.to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
                    
                    if holiday.from_date > holiday.to_date:
                        messages.error(request, 'From date must be before To date.')
                        return redirect('holiday_master')
                    
                    start_date = holiday.from_date
                    end_date = holiday.to_date
                
                # Save to database first
                holiday.save()
                
                # Log activity
                log_activity_event(
                    'holiday.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'holiday_id': holiday.id,
                        'holiday_name': holiday_name,
                        'date_type': date_type,
                    },
                )
                
                # Sync to Google Calendar (if service is available)
                holiday.google_calendar_sync_started_at = timezone.now()
                holiday.save(update_fields=['google_calendar_sync_started_at'])
                
                log_activity_event(
                    'holiday.google_calendar_sync_started_at',
                    subject_user=None,
                    performed_by=None,
                    metadata={'holiday_id': holiday.id, 'performed_by': 'system'},
                )
                
                try:
                    # Import Google Calendar service if available
                    from .services.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()
                    event_id = calendar_service.create_event(
                        holiday_name=holiday_name,
                        start_date=start_date,
                        end_date=end_date,
                        description=description,
                        holiday_type=holiday_type
                    )
                    
                    if event_id:
                        holiday.google_calendar_event_id = event_id
                        holiday.is_synced_to_calendar = True
                        holiday.google_calendar_synced_at = timezone.now()
                        holiday.save(update_fields=[
                            'google_calendar_event_id',
                            'is_synced_to_calendar',
                            'google_calendar_synced_at'
                        ])
                        
                        log_activity_event(
                            'holiday.google_calendar_synced_at',
                            subject_user=None,
                            performed_by=None,
                            metadata={
                                'holiday_id': holiday.id,
                                'event_id': event_id,
                                'performed_by': 'system',
                            },
                        )
                        
                        logger.info(f"Holiday '{holiday_name}' created and synced to Google Calendar")
                        messages.success(request, f'Holiday "{holiday_name}" created and synced to Google Calendar!')
                    else:
                        holiday.google_calendar_sync_failed_at = timezone.now()
                        holiday.save(update_fields=['google_calendar_sync_failed_at'])
                        
                        log_activity_event(
                            'holiday.google_calendar_sync_failed_at',
                            subject_user=None,
                            performed_by=None,
                            metadata={
                                'holiday_id': holiday.id,
                                'error': 'Failed to create calendar event',
                                'performed_by': 'system',
                            },
                        )
                        
                        logger.warning(f"Holiday created but failed to sync to Google Calendar")
                        messages.warning(request, f'Holiday "{holiday_name}" created but failed to sync to Google Calendar.')
                        
                except ImportError:
                    logger.info("Google Calendar service not available")
                    messages.success(request, f'Holiday "{holiday_name}" created successfully!')
                except Exception as calendar_error:
                    holiday.google_calendar_sync_failed_at = timezone.now()
                    holiday.save(update_fields=['google_calendar_sync_failed_at'])
                    
                    log_activity_event(
                        'holiday.google_calendar_sync_failed_at',
                        subject_user=None,
                        performed_by=None,
                        metadata={
                            'holiday_id': holiday.id,
                            'error': str(calendar_error),
                            'performed_by': 'system',
                        },
                    )
                    
                    logger.error(f"Google Calendar sync error: {str(calendar_error)}")
                    messages.warning(request, f'Holiday "{holiday_name}" created but Google Calendar sync failed.')
            
            return redirect('holiday_master')
            
        except Exception as e:
            logger.exception(f"Error creating holiday: {str(e)}")
            messages.error(request, 'An error occurred while creating the holiday.')
            return redirect('holiday_master')
    
    return redirect('holiday_master')


@login_required
@superadmin_required
def edit_holiday(request, holiday_id):
    """Update an existing holiday"""
    if request.method != 'POST':
        return redirect('holiday_master')
    
    holiday = next(
        (
            item for item in Holiday.objects.all()
            if item.id == holiday_id and not getattr(item, 'is_deleted', False)
        ),
        None
    )
    
    if not holiday:
        messages.error(request, 'Holiday not found.')
        return redirect('holiday_master')
    
    try:
        holiday_name = request.POST.get('holiday_name', '').strip()
        holiday_type = request.POST.get('holiday_type', 'full_day')
        date_type = request.POST.get('date_type', 'single')
        description = request.POST.get('description', '').strip()
        
        if not holiday_name:
            messages.error(request, 'Holiday name is required.')
            return redirect('holiday_master')
        
        if date_type == 'single':
            date_str = request.POST.get('date')
            if not date_str:
                messages.error(request, 'Date is required for single-day holiday.')
                return redirect('holiday_master')
            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            end_date = start_date
        else:
            from_date_str = request.POST.get('from_date')
            to_date_str = request.POST.get('to_date')
            
            if not from_date_str or not to_date_str:
                messages.error(request, 'Both From and To dates are required for consecutive holidays.')
                return redirect('holiday_master')
            
            start_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            
            if start_date > end_date:
                messages.error(request, 'From date must be before To date.')
                return redirect('holiday_master')
        
        with transaction.atomic():
            holiday.holiday_name = holiday_name
            holiday.holiday_type = holiday_type
            holiday.date_type = date_type
            holiday.description = description
            holiday.updated_by = request.user
            holiday.updated_at = timezone.now()
            
            if date_type == 'single':
                holiday.date = start_date
                holiday.from_date = None
                holiday.to_date = None
            else:
                holiday.date = None
                holiday.from_date = start_date
                holiday.to_date = end_date
            
            holiday.google_calendar_sync_started_at = timezone.now()
            holiday.google_calendar_sync_failed_at = None
            holiday.save()
            
            log_activity_event(
                'holiday.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'holiday_id': holiday.id,
                    'holiday_name': holiday.holiday_name,
                },
            )
            
            try:
                from .services.google_calendar_service import GoogleCalendarService
                calendar_service = GoogleCalendarService()
                
                if holiday.google_calendar_event_id:
                    sync_ok = calendar_service.update_event(
                        holiday.google_calendar_event_id,
                        holiday_name,
                        start_date,
                        end_date,
                        description=description,
                        holiday_type=holiday_type,
                    )
                else:
                    event_id = calendar_service.create_event(
                        holiday_name=holiday_name,
                        start_date=start_date,
                        end_date=end_date,
                        description=description,
                        holiday_type=holiday_type,
                    )
                    sync_ok = bool(event_id)
                    if event_id:
                        holiday.google_calendar_event_id = event_id
                
                if sync_ok:
                    holiday.is_synced_to_calendar = True
                    holiday.google_calendar_synced_at = timezone.now()
                    holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_synced_at', 'google_calendar_event_id'])
                else:
                    holiday.is_synced_to_calendar = False
                    holiday.google_calendar_sync_failed_at = timezone.now()
                    holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_sync_failed_at'])
                    logger.warning("Holiday updated but failed to sync to Google Calendar.")
            
            except ImportError:
                logger.info("Google Calendar service not available")
            except Exception as calendar_error:
                holiday.is_synced_to_calendar = False
                holiday.google_calendar_sync_failed_at = timezone.now()
                holiday.save(update_fields=['is_synced_to_calendar', 'google_calendar_sync_failed_at'])
                logger.error(f"Google Calendar sync error during update: {str(calendar_error)}")
        
        messages.success(request, f'Holiday "{holiday.holiday_name}" updated successfully.')
    
    except Exception as e:
        logger.exception(f"Error updating holiday: {str(e)}")
        messages.error(request, 'An error occurred while updating the holiday.')
    
    return redirect('holiday_master')


@login_required
@superadmin_required
def delete_holiday(request, holiday_id):
    """Permanently delete a holiday"""
    if request.method != 'POST':
        return redirect('holiday_master')
    
    holiday = Holiday.objects.filter(id=holiday_id).first()
    
    if not holiday:
        messages.error(request, 'Holiday not found.')
        return redirect('holiday_master')
    
    holiday_id_ref = holiday.id
    holiday_name_ref = holiday.holiday_name
    calendar_event_id = holiday.google_calendar_event_id
    
    try:
        with transaction.atomic():
            if calendar_event_id:
                try:
                    from .services.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()
                    calendar_service.delete_event(calendar_event_id)
                    logger.info(f"Holiday deleted from Google Calendar: {holiday_name_ref}")
                except ImportError:
                    logger.info("Google Calendar service not available")
                except Exception as calendar_error:
                    logger.error(f"Error deleting from Google Calendar: {str(calendar_error)}")
            
            holiday.delete()
            
            log_activity_event(
                'holiday.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'holiday_id': holiday_id_ref,
                    'holiday_name': holiday_name_ref,
                },
            )
        
        messages.success(request, f'Holiday "{holiday_name_ref}" deleted successfully.')
    
    except Exception as e:
        logger.exception(f"Error deleting holiday: {str(e)}")
        messages.error(request, 'An error occurred while deleting the holiday.')
    
    return redirect('holiday_master')


# This is continuation of views.py - PRICE and REFERENCING MASTER sections
# Copy this after Holiday Master views

# ========================================
# PRICE MASTER VIEWS
# ========================================

@login_required
@superadmin_required
def price_master(request):
    """Price Master - List all prices"""
    try:
        raw_prices = list(PriceMaster.objects.all().order_by('-created_at'))
        prices = [
            price for price in raw_prices
            if not getattr(price, 'is_deleted', False)
        ]
        context = {
            'prices': prices,
            'total_prices': len(prices),
        }
        return render(request, 'price_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading price master: {str(e)}")
        messages.error(request, 'Error loading prices.')
        return render(request, 'price_master.html', {'prices': [], 'total_prices': 0})


@login_required
@superadmin_required
def create_price(request):
    """Create a new price entry"""
    if request.method == 'POST':
        try:
            category = request.POST.get('category', '').strip()
            level = request.POST.get('level', '').strip()
            price_per_word = request.POST.get('price_per_word', '').strip()
            
            # Validation
            if not category or not level or not price_per_word:
                messages.error(request, 'All fields are required.')
                return redirect('price_master')
            
            try:
                price_per_word = float(price_per_word)
                if price_per_word <= 0:
                    messages.error(request, 'Price per word must be greater than 0.')
                    return redirect('price_master')
            except ValueError:
                messages.error(request, 'Invalid price format.')
                return redirect('price_master')
            
            # Check for existing combination
            all_matching = list(PriceMaster.objects.filter(
                category=category,
                level=level
            ))
            
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Price already exists for {category} - {level}.')
                return redirect('price_master')
            
            with transaction.atomic():
                price_obj = PriceMaster()
                price_obj.category = category
                price_obj.level = level
                price_obj.price_per_word = price_per_word
                price_obj.created_by = request.user
                price_obj.created_at = timezone.now()
                price_obj.save()
                
                log_activity_event(
                    'price.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'price_id': str(price_obj.id),
                        'category': category,
                        'level': level,
                        'price_per_word': str(price_per_word),
                    },
                )
                
                logger.info(f"Price created for {category} - {level} by {request.user.email}")
                messages.success(request, f'Price for {category} - {level} created successfully!')
            
            return redirect('price_master')
            
        except Exception as e:
            logger.exception(f"Error creating price: {str(e)}")
            messages.error(request, 'An error occurred while creating the price.')
            return redirect('price_master')
    
    return redirect('price_master')


@login_required
@superadmin_required
def edit_price(request, price_id):
    """Update an existing price entry"""
    if request.method != 'POST':
        return redirect('price_master')
    
    all_prices = list(PriceMaster.objects.filter(id=price_id))
    price_obj = next(
        (item for item in all_prices if not getattr(item, 'is_deleted', False)),
        None
    )
    
    if not price_obj:
        messages.error(request, 'Price entry not found.')
        return redirect('price_master')
    
    try:
        category = request.POST.get('category', '').strip()
        level = request.POST.get('level', '').strip()
        price_per_word = request.POST.get('price_per_word', '').strip()
        
        if not category or not level or not price_per_word:
            messages.error(request, 'All fields are required.')
            return redirect('price_master')
        
        try:
            price_per_word = float(price_per_word)
            if price_per_word <= 0:
                messages.error(request, 'Price per word must be greater than 0.')
                return redirect('price_master')
        except ValueError:
            messages.error(request, 'Invalid price format.')
            return redirect('price_master')
        
        # Check for duplicate combination (excluding current record)
        all_matching = list(PriceMaster.objects.filter(
            category=category,
            level=level
        ))
        
        existing = next(
            (item for item in all_matching 
             if item.id != price_id and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Price already exists for {category} - {level}.')
            return redirect('price_master')
        
        with transaction.atomic():
            price_obj.category = category
            price_obj.level = level
            price_obj.price_per_word = price_per_word
            price_obj.updated_by = request.user
            price_obj.updated_at = timezone.now()
            price_obj.save()
            
            log_activity_event(
                'price.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'price_id': str(price_obj.id),
                    'category': category,
                    'level': level,
                    'price_per_word': str(price_per_word),
                },
            )
        
        messages.success(request, f'Price for {category} - {level} updated successfully.')
    
    except Exception as e:
        logger.exception(f"Error updating price: {str(e)}")
        messages.error(request, 'An error occurred while updating the price.')
    
    return redirect('price_master')


@login_required
@superadmin_required
def delete_price(request, price_id):
    """Delete a price entry"""
    if request.method != 'POST':
        return redirect('price_master')
    
    price_obj = None
    try:
        price_obj = PriceMaster.objects.get(id=price_id)
    except PriceMaster.DoesNotExist:
        messages.error(request, 'Price entry not found.')
        return redirect('price_master')
    
    price_id_ref = str(price_obj.id)
    category_ref = price_obj.category
    level_ref = price_obj.level
    
    try:
        with transaction.atomic():
            price_obj.delete()
            
            log_activity_event(
                'price.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'price_id': price_id_ref,
                    'category': category_ref,
                    'level': level_ref,
                },
            )
        
        messages.success(request, f'Price for {category_ref} - {level_ref} deleted successfully.')
    
    except Exception as e:
        logger.exception(f"Error deleting price: {str(e)}")
        messages.error(request, 'An error occurred while deleting the price.')
    
    return redirect('price_master')


# ========================================
# REFERENCING MASTER VIEWS
# ========================================

@login_required
@superadmin_required
def referencing_master(request):
    """Referencing Master - List all references"""
    try:
        raw_references = list(ReferencingMaster.objects.all().order_by('-created_at'))
        references = [
            reference for reference in raw_references
            if not getattr(reference, 'is_deleted', False)
        ]
        context = {
            'references': references,
            'total_references': len(references),
        }
        return render(request, 'referencing_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading referencing master: {str(e)}")
        messages.error(request, 'Error loading references.')
        return render(request, 'referencing_master.html', {'references': [], 'total_references': 0})


@login_required
@superadmin_required
def create_reference(request):
    """Create a new reference entry"""
    if request.method == 'POST':
        try:
            referencing_style = request.POST.get('referencing_style', '').strip()
            used_in = request.POST.get('used_in', '').strip()
            
            # Validation
            if not referencing_style or not used_in:
                messages.error(request, 'All fields are required.')
                return redirect('referencing_master')
            
            # Check for existing combination
            all_matching = list(ReferencingMaster.objects.filter(
                referencing_style=referencing_style,
                used_in=used_in
            ))
            
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Reference already exists for {referencing_style} - {used_in}.')
                return redirect('referencing_master')
            
            with transaction.atomic():
                reference_obj = ReferencingMaster()
                reference_obj.referencing_style = referencing_style
                reference_obj.used_in = used_in
                reference_obj.created_by = request.user
                reference_obj.created_at = timezone.now()
                reference_obj.save()
                
                log_activity_event(
                    'reference.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'reference_id': str(reference_obj.id),
                        'referencing_style': referencing_style,
                        'used_in': used_in,
                    },
                )
                
                logger.info(f"Reference created for {referencing_style} - {used_in} by {request.user.email}")
                messages.success(request, f'Reference for {referencing_style} - {used_in} created successfully!')
            
            return redirect('referencing_master')
            
        except Exception as e:
            logger.exception(f"Error creating reference: {str(e)}")
            messages.error(request, 'An error occurred while creating the reference.')
            return redirect('referencing_master')
    
    return redirect('referencing_master')


@login_required
@superadmin_required
def edit_reference(request, reference_id):
    """Update an existing reference entry"""
    if request.method != 'POST':
        return redirect('referencing_master')
    
    reference_obj = _find_reference_by_id(reference_id)
    
    if not reference_obj:
        messages.error(request, 'Reference entry not found.')
        return redirect('referencing_master')
    
    try:
        referencing_style = request.POST.get('referencing_style', '').strip()
        used_in = request.POST.get('used_in', '').strip()
        
        if not referencing_style or not used_in:
            messages.error(request, 'All fields are required.')
            return redirect('referencing_master')
        
        # Check for duplicate combination (excluding current record)
        all_matching = list(ReferencingMaster.objects.filter(
            referencing_style=referencing_style,
            used_in=used_in
        ))
        
        existing = next(
            (item for item in all_matching 
             if str(item.id) != str(reference_id) and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Reference already exists for {referencing_style} - {used_in}.')
            return redirect('referencing_master')
        
        with transaction.atomic():
            reference_obj.referencing_style = referencing_style
            reference_obj.used_in = used_in
            reference_obj.updated_by = request.user
            reference_obj.updated_at = timezone.now()
            reference_obj.save()
            
            log_activity_event(
                'reference.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'reference_id': str(reference_obj.id),
                    'referencing_style': referencing_style,
                    'used_in': used_in,
                },
            )
        
        messages.success(request, f'Reference for {referencing_style} - {used_in} updated successfully.')
    
    except Exception as e:
        logger.exception(f"Error updating reference: {str(e)}")
        messages.error(request, 'An error occurred while updating the reference.')
    
    return redirect('referencing_master')


@login_required
@superadmin_required
def delete_reference(request, reference_id):
    """Delete a reference entry"""
    if request.method != 'POST':
        return redirect('referencing_master')
    
    reference_obj = _find_reference_by_id(reference_id)
    
    if not reference_obj:
        messages.error(request, 'Reference entry not found.')
        return redirect('referencing_master')
    
    reference_id_ref = str(reference_obj.id)
    referencing_style_ref = reference_obj.referencing_style
    used_in_ref = reference_obj.used_in
    
    try:
        with transaction.atomic():
            reference_obj.delete()
            
            log_activity_event(
                'reference.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'reference_id': reference_id_ref,
                    'referencing_style': referencing_style_ref,
                    'used_in': used_in_ref,
                },
            )
        
        messages.success(request, f'Reference for {referencing_style_ref} - {used_in_ref} deleted successfully.')
    
    except Exception as e:
        logger.exception(f"Error deleting reference: {str(e)}")
        messages.error(request, 'An error occurred while deleting the reference.')
    
    return redirect('referencing_master')


def _find_reference_by_id(reference_id):
    """Helper function to find reference by ID (supports ObjectId and int)"""
    if not reference_id:
        return None
    
    candidates = []
    try:
        candidates = list(ReferencingMaster.objects.filter(id=reference_id))
    except Exception:
        candidates = []
    
    if not candidates and isinstance(reference_id, str) and reference_id.isdigit():
        try:
            candidates = list(ReferencingMaster.objects.filter(id=int(reference_id)))
        except Exception:
            candidates = []
    
    if not candidates:
        try:
            object_id = ObjectId(str(reference_id))
            candidates = list(ReferencingMaster.objects.filter(id=object_id))
        except (InvalidId, Exception):
            candidates = []
    
    return next(
        (item for item in candidates if not getattr(item, 'is_deleted', False)),
        None
    )



# This is continuation of views.py - ACADEMIC WRITING MASTER section
# Copy this after Referencing Master views

# ========================================
# ACADEMIC WRITING MASTER VIEWS
# ========================================

@login_required
@superadmin_required
def academic_writing_master(request):
    """Academic Writing Master - List all writing styles"""
    try:
        raw_writings = list(AcademicWritingMaster.objects.all().order_by('-created_at'))
        writings = [
            writing for writing in raw_writings
            if not getattr(writing, 'is_deleted', False)
        ]
        context = {
            'writings': writings,
            'total_writings': len(writings),
        }
        return render(request, 'academic_writing_master.html', context)
        
    except Exception as e:
        logger.exception(f"Error loading academic writing master: {str(e)}")
        messages.error(request, 'Error loading writing styles.')
        return render(request, 'academic_writing_master.html', {'writings': [], 'total_writings': 0})


@login_required
@superadmin_required
def create_writing(request):
    """Create a new writing style entry"""
    if request.method == 'POST':
        try:
            writing_style = request.POST.get('writing_style', '').strip()
            
            # Validation
            if not writing_style:
                messages.error(request, 'Writing style is required.')
                return redirect('academic_writing_master')
            
            # Check for existing writing style
            all_matching = list(AcademicWritingMaster.objects.filter(
                writing_style=writing_style
            ))
            
            existing = next(
                (item for item in all_matching if not getattr(item, 'is_deleted', False)),
                None
            )
            
            if existing:
                messages.error(request, f'Writing style "{writing_style}" already exists.')
                return redirect('academic_writing_master')
            
            with transaction.atomic():
                writing_obj = AcademicWritingMaster()
                writing_obj.writing_style = writing_style
                writing_obj.created_by = request.user
                writing_obj.created_at = timezone.now()
                writing_obj.save()
                
                log_activity_event(
                    'writing.created_at',
                    subject_user=None,
                    performed_by=request.user,
                    metadata={
                        'writing_id': str(writing_obj.id),
                        'writing_style': writing_style,
                    },
                )
                
                logger.info(f"Writing style '{writing_style}' created by {request.user.email}")
                messages.success(request, f'Writing style "{writing_style}" created successfully!')
            
            return redirect('academic_writing_master')
            
        except Exception as e:
            logger.exception(f"Error creating writing style: {str(e)}")
            messages.error(request, 'An error occurred while creating the writing style.')
            return redirect('academic_writing_master')
    
    return redirect('academic_writing_master')


@login_required
@superadmin_required
def edit_writing(request, writing_id):
    """Update an existing writing style entry"""
    if request.method != 'POST':
        return redirect('academic_writing_master')
    
    writing_obj = _find_writing_by_id(writing_id)
    
    if not writing_obj:
        messages.error(request, 'Writing style not found.')
        return redirect('academic_writing_master')
    
    try:
        writing_style = request.POST.get('writing_style', '').strip()
        
        if not writing_style:
            messages.error(request, 'Writing style is required.')
            return redirect('academic_writing_master')
        
        # Check for duplicate (excluding current record)
        all_matching = list(AcademicWritingMaster.objects.filter(
            writing_style=writing_style
        ))
        
        existing = next(
            (item for item in all_matching 
             if str(item.id) != str(writing_id) and not getattr(item, 'is_deleted', False)),
            None
        )
        
        if existing:
            messages.error(request, f'Writing style "{writing_style}" already exists.')
            return redirect('academic_writing_master')
        
        with transaction.atomic():
            writing_obj.writing_style = writing_style
            writing_obj.updated_by = request.user
            writing_obj.updated_at = timezone.now()
            writing_obj.save()
            
            log_activity_event(
                'writing.updated_at',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'writing_id': str(writing_obj.id),
                    'writing_style': writing_style,
                },
            )
        
        messages.success(request, f'Writing style "{writing_style}" updated successfully.')
    
    except Exception as e:
        logger.exception(f"Error updating writing style: {str(e)}")
        messages.error(request, 'An error occurred while updating the writing style.')
    
    return redirect('academic_writing_master')


@login_required
@superadmin_required
def delete_writing(request, writing_id):
    """Delete a writing style entry"""
    if request.method != 'POST':
        return redirect('academic_writing_master')
    
    writing_obj = _find_writing_by_id(writing_id)
    
    if not writing_obj:
        messages.error(request, 'Writing style not found.')
        return redirect('academic_writing_master')
    
    writing_id_ref = str(writing_obj.id)
    writing_style_ref = writing_obj.writing_style
    
    try:
        with transaction.atomic():
            writing_obj.delete()
            
            log_activity_event(
                'writing.deleted',
                subject_user=None,
                performed_by=request.user,
                metadata={
                    'writing_id': writing_id_ref,
                    'writing_style': writing_style_ref,
                },
            )
        
        messages.success(request, f'Writing style "{writing_style_ref}" deleted successfully.')
    
    except Exception as e:
        logger.exception(f"Error deleting writing style: {str(e)}")
        messages.error(request, 'An error occurred while deleting the writing style.')
    
    return redirect('academic_writing_master')


def _find_writing_by_id(writing_id):
    """Helper function to find writing by ID (supports ObjectId and int)"""
    if not writing_id:
        return None
    
    candidates = []
    try:
        candidates = list(AcademicWritingMaster.objects.filter(id=writing_id))
    except Exception:
        candidates = []
    
    if not candidates and isinstance(writing_id, str) and writing_id.isdigit():
        try:
            candidates = list(AcademicWritingMaster.objects.filter(id=int(writing_id)))
        except Exception:
            candidates = []
    
    if not candidates:
        try:
            object_id = ObjectId(str(writing_id))
            candidates = list(AcademicWritingMaster.objects.filter(id=object_id))
        except (InvalidId, Exception):
            candidates = []
    
    return next(
        (item for item in candidates if not getattr(item, 'is_deleted', False)),
        None
    )