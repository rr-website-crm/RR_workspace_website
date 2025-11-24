import os
import json
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from django.conf import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('superadmin')


class GoogleCalendarService:
    """Service to interact with Google Calendar API"""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self):
        self.service = None
        self.calendar_id = getattr(settings, 'GOOGLE_CALENDAR_ID', 'primary')
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar using service account"""
        try:
            # Get service account credentials path from settings
            credentials_path = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
            
            if not credentials_path or not os.path.exists(credentials_path):
                logger.error("Google service account credentials file not found")
                return None
            
            # Load credentials
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=self.SCOPES
            )
            
            # Build service
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("Successfully authenticated with Google Calendar API")
            
        except Exception as e:
            logger.error(f"Error authenticating with Google Calendar: {str(e)}")
            self.service = None
    
    def create_event(self, holiday_name, start_date, end_date, description='', holiday_type='full_day'):
        """Create a calendar event"""
        if not self.service:
            logger.error("Google Calendar service not initialized")
            return None
        
        try:
            # Prepare event data
            event_body = {
                'summary': holiday_name,
                'description': description or f'Holiday: {holiday_name}',
                'start': {},
                'end': {},
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 60},  # 1 hour before
                    ],
                },
                'colorId': '9',  # Blue color for holidays
            }
            
            # Handle date format based on holiday type
            if holiday_type == 'full_day':
                # All-day event
                event_body['start']['date'] = start_date.strftime('%Y-%m-%d')
                
                # For all-day events, end date should be next day
                actual_end_date = end_date + timedelta(days=1)
                event_body['end']['date'] = actual_end_date.strftime('%Y-%m-%d')
            else:
                # Timed event (half day)
                event_body['start']['dateTime'] = start_date.strftime('%Y-%m-%dT09:00:00')
                event_body['start']['timeZone'] = 'Asia/Kolkata'
                
                event_body['end']['dateTime'] = start_date.strftime('%Y-%m-%dT13:00:00')
                event_body['end']['timeZone'] = 'Asia/Kolkata'
            
            # Create event
            event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body
            ).execute()
            
            logger.info(f"Created calendar event: {event.get('id')} for {holiday_name}")
            return event.get('id')
            
        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return None
        except Exception as e:
            logger.error(f"Error creating calendar event: {str(e)}")
            return None
    
    def update_event(self, event_id, holiday_name, start_date, end_date, description='', holiday_type='full_day'):
        """Update an existing calendar event"""
        if not self.service:
            logger.error("Google Calendar service not initialized")
            return False
        
        try:
            # Get existing event
            event = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            # Update event data
            event['summary'] = holiday_name
            event['description'] = description or f'Holiday: {holiday_name}'
            
            if holiday_type == 'full_day':
                event['start']['date'] = start_date.strftime('%Y-%m-%d')
                actual_end_date = end_date + timedelta(days=1)
                event['end']['date'] = actual_end_date.strftime('%Y-%m-%d')
                
                # Remove dateTime if exists
                event['start'].pop('dateTime', None)
                event['start'].pop('timeZone', None)
                event['end'].pop('dateTime', None)
                event['end'].pop('timeZone', None)
            else:
                event['start']['dateTime'] = start_date.strftime('%Y-%m-%dT09:00:00')
                event['start']['timeZone'] = 'Asia/Kolkata'
                event['end']['dateTime'] = start_date.strftime('%Y-%m-%dT13:00:00')
                event['end']['timeZone'] = 'Asia/Kolkata'
                
                # Remove date if exists
                event['start'].pop('date', None)
                event['end'].pop('date', None)
            
            # Update event
            updated_event = self.service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Updated calendar event: {event_id}")
            return True
            
        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return False
        except Exception as e:
            logger.error(f"Error updating calendar event: {str(e)}")
            return False
    
    def delete_event(self, event_id):
        """Delete a calendar event"""
        if not self.service:
            logger.error("Google Calendar service not initialized")
            return False
        
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"Deleted calendar event: {event_id}")
            return True
            
        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return False
        except Exception as e:
            logger.error(f"Error deleting calendar event: {str(e)}")
            return False