import os
import json
import base64
import tempfile
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pytz
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_CREDENTIALS_JSON

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class CalendarMonitor:
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        # If we have JSON credentials from environment (GitHub Actions/CI)
        if GOOGLE_CREDENTIALS_JSON:
            try:
                # Debug: Check if credentials are properly formatted
                if not GOOGLE_CREDENTIALS_JSON.strip():
                    raise ValueError("GOOGLE_CREDENTIALS_JSON is empty or contains only whitespace")
                
                # Decode base64 encoded JSON credentials
                try:
                    decoded_json = base64.b64decode(GOOGLE_CREDENTIALS_JSON.strip()).decode('utf-8')
                    creds_info = json.loads(decoded_json)
                except Exception as decode_error:
                    # If base64 decoding fails, try parsing as plain JSON (fallback)
                    print(f"Base64 decode failed, trying plain JSON: {decode_error}")
                    creds_info = json.loads(GOOGLE_CREDENTIALS_JSON.strip())
                
                # Check if it's a service account
                if creds_info.get('type') == 'service_account':
                    creds = ServiceAccountCredentials.from_service_account_info(
                        creds_info, scopes=SCOPES)
                else:
                    # It's OAuth2 credentials
                    creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
                
                return build('calendar', 'v3', credentials=creds)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error parsing GOOGLE_CREDENTIALS_JSON: {e}")
                raise
        
        # Fall back to file-based authentication (local development)
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                    raise FileNotFoundError(f"Google credentials file not found: {GOOGLE_CREDENTIALS_FILE}")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    GOOGLE_CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        return build('calendar', 'v3', credentials=creds)
    
    def get_upcoming_1on1s(self, hours_ahead=24):
        """Get 1on1 meetings within the next specified hours"""
        now = datetime.utcnow().isoformat() + 'Z'
        future_time = (datetime.utcnow() + timedelta(hours=hours_ahead)).isoformat() + 'Z'
        
        # Try multiple calendar IDs to find the right one
        calendar_ids_to_try = [
            os.getenv('ZENDESK_EMAIL'),  # Try your email first (most likely to work)
            'primary',  # Default (service account's own calendar)
            os.getenv('GOOGLE_CALENDAR_ID'),  # If you want to set a specific calendar ID
        ]
        
        # Remove None values
        calendar_ids_to_try = [cal_id for cal_id in calendar_ids_to_try if cal_id]
        
        events_result = None
        
        for calendar_id in calendar_ids_to_try:
            if not calendar_id:
                continue
            try:
                print(f"🔍 Trying calendar ID: {calendar_id}")
                events_result = self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=now,
                    timeMax=future_time,
                    singleEvents=True,
                    orderBy='startTime',
                    q='1on1'
                ).execute()
                print(f"✅ Successfully accessed calendar: {calendar_id}")
                break
            except Exception as e:
                print(f"❌ Failed to access calendar {calendar_id}: {e}")
                continue
        
        if not events_result:
            print("❌ Could not access any calendar")
            return []
        
        events = events_result.get('items', [])
        return self._parse_events(events)
    
    def _parse_events(self, events):
        """Parse calendar events to extract relevant information"""
        parsed_events = []
        
        for event in events:
            if '1on1' in event.get('summary', '').lower():
                start_time = event['start'].get('dateTime', event['start'].get('date'))
                
                # Parse attendees to find the agent (non-organizer)
                attendees = event.get('attendees', [])
                agent_email = None
                
                for attendee in attendees:
                    if not attendee.get('organizer', False):
                        agent_email = attendee.get('email')
                        break
                
                parsed_events.append({
                    'id': event['id'],
                    'summary': event.get('summary'),
                    'start_time': start_time,
                    'agent_email': agent_email,
                    'attendees': attendees
                })
        
        return parsed_events
    
    def get_meetings_starting_in_minutes(self, minutes=30):
        """Get 1on1 meetings starting in exactly the specified minutes"""
        target_time = datetime.utcnow() + timedelta(minutes=minutes)
        target_start = target_time - timedelta(minutes=2)  # 2-minute window
        target_end = target_time + timedelta(minutes=2)
        
        print(f"🔍 Searching calendar from {target_start.isoformat()}Z to {target_end.isoformat()}Z (looking {minutes} min ahead)")
        
        # First, try to list all calendars to see what we have access to
        if minutes == 25:  # Only do this once
            try:
                calendars_result = self.service.calendarList().list().execute()
                calendars = calendars_result.get('items', [])
                print(f"📋 Available calendars ({len(calendars)}):")
                for cal in calendars:
                    print(f"   - '{cal.get('summary', 'No name')}' (ID: {cal.get('id')}) - Access: {cal.get('accessRole')}")
            except Exception as e:
                print(f"❌ Could not list calendars: {e}")
        
        # Try multiple calendar IDs to find the right one
        calendar_ids_to_try = [
            os.getenv('ZENDESK_EMAIL'),  # Try your email first (most likely to work)
            'primary',  # Default (service account's own calendar)
            os.getenv('GOOGLE_CALENDAR_ID'),  # If you want to set a specific calendar ID
        ]
        
        # Remove None values
        calendar_ids_to_try = [cal_id for cal_id in calendar_ids_to_try if cal_id]
        
        events_result = None
        successful_calendar_id = None
        
        for calendar_id in calendar_ids_to_try:
            if not calendar_id:
                continue
            try:
                print(f"   🔍 Trying calendar ID: {calendar_id}")
                events_result = self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=target_start.isoformat() + 'Z',
                    timeMax=target_end.isoformat() + 'Z',
                    singleEvents=True,
                    orderBy='startTime',
                    q='1on1'
                ).execute()
                successful_calendar_id = calendar_id
                print(f"   ✅ Successfully accessed calendar: {calendar_id}")
                break
            except Exception as e:
                print(f"   ❌ Failed to access calendar {calendar_id}: {e}")
                continue
        
        if not events_result:
            print("   ❌ Could not access any calendar")
            return []
        
        events = events_result.get('items', [])
        print(f"📅 Found {len(events)} events with '1on1' in search")
        
        # Debug: Also search without query to see all events in time range
        if successful_calendar_id:
            all_events_result = self.service.events().list(
                calendarId=successful_calendar_id,
                timeMin=target_start.isoformat() + 'Z',
                timeMax=target_end.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
        else:
            all_events_result = {'items': []}
        
        all_events = all_events_result.get('items', [])
        print(f"📅 Found {len(all_events)} total events in time range:")
        for event in all_events:
            print(f"   - '{event.get('summary', 'No title')}' at {event.get('start', {}).get('dateTime', 'No time')}")
        
        # Also search in a much wider time range to see if there are ANY events today
        if minutes == 25:  # Only do this once
            try:
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                wide_search = self.service.events().list(
                    calendarId=successful_calendar_id if successful_calendar_id else 'primary',
                    timeMin=today_start.isoformat() + 'Z',
                    timeMax=today_end.isoformat() + 'Z',
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                wide_events = wide_search.get('items', [])
                print(f"🌅 Found {len(wide_events)} total events today:")
                for event in wide_events[:5]:  # Show first 5
                    start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'No time'))
                    print(f"   - '{event.get('summary', 'No title')}' at {start_time}")
                if len(wide_events) > 5:
                    print(f"   ... and {len(wide_events) - 5} more events")
            except Exception as e:
                print(f"❌ Could not search today's events: {e}")
        
        return self._parse_events(events)
