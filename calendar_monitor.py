import os
import json
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
                
                # Parse the JSON credentials
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
        
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=future_time,
            singleEvents=True,
            orderBy='startTime',
            q='1on1'
        ).execute()
        
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
        
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=target_start.isoformat() + 'Z',
            timeMax=target_end.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime',
            q='1on1'
        ).execute()
        
        events = events_result.get('items', [])
        return self._parse_events(events)
