import os
import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tzlocal import get_localzone_name

# Use the more specific .events scope. This may require re-authentication.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def get_calendar_service():
    """Handles Google Calendar API authentication and returns a service object."""
    creds = None
    
    # Try to get credentials from environment variables first (for deployment)
    if os.getenv("GOOGLE_CREDENTIALS_JSON") and os.getenv("GOOGLE_TOKEN_JSON"):
        try:
            # Load credentials from environment variables
            google_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            google_token_json = os.getenv("GOOGLE_TOKEN_JSON")
            
            if google_credentials_json is None or google_token_json is None:
                raise ValueError("Environment variables are None")
                
            credentials_data = json.loads(google_credentials_json)
            token_data = json.loads(google_token_json)
            
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            # Refresh token if needed
            if not creds.valid and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error loading credentials from environment: {e}")
            creds = None
    
    # Fallback to file-based authentication (for local development)
    if not creds or not creds.valid:
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists("credentials.json") and not os.getenv("GOOGLE_CREDENTIALS_JSON"):
                    raise FileNotFoundError("Error: credentials.json not found and GOOGLE_CREDENTIALS_JSON not set. Please follow README instructions.")
                
                if os.path.exists("credentials.json"):
                    try:
                        with open("credentials.json", 'r') as f:
                            client_config = json.load(f)
                            if "installed" not in client_config and "web" not in client_config:
                                raise ValueError("Error: Invalid credentials.json. Please use 'Desktop app' credentials.")
                    except json.JSONDecodeError:
                        raise ValueError("Error: Malformed credentials.json. Please re-download it.")

                    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    raise FileNotFoundError("Error: No credentials available. Please set environment variables or provide credentials.json file.")
                
            # Save token for local development only
            if os.path.exists("credentials.json"):
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
    
    return build("calendar", "v3", credentials=creds)

class CalendarEventInput(BaseModel):
    summary: str = Field(description="The summary or title of the event.")
    description: Optional[str] = Field(description="The detailed description of the event.")
    start_time: str = Field(description="The start time in ISO format, e.g., '2024-07-29T10:00:00'.")
    end_time: str = Field(description="The end time in ISO format, e.g., '2024-07-29T11:00:00'.")
    attendees: Optional[List[str]] = Field(description="A list of attendee emails.")

@tool("create_calendar_event", args_schema=CalendarEventInput)
def create_calendar_event(summary: str, start_time: str, end_time: str, description: Optional[str] = None, attendees: Optional[List[str]] = None) -> str:
    """Creates a Google Calendar event with the specified details."""
    try:
        service = get_calendar_service()
        local_timezone = get_localzone_name()
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": local_timezone},
            "end": {"dateTime": end_time, "timeZone": local_timezone},
            "attendees": [{"email": email} for email in attendees] if attendees else [],
        }
        event = service.events().insert(calendarId="primary", body=event).execute()
        
        event_link = event.get('htmlLink', 'No link available')
        event_id = event.get('id', 'No ID')
        
        return f"""✅ Event created successfully!

📅 **Event Details:**
- **Title:** {summary}
- **Time:** {start_time} to {end_time}
- **Event ID:** {event_id}

🔗 **View Event:** {event_link}

You can click the link above to view or edit the event in Google Calendar."""
    except (HttpError, FileNotFoundError, ValueError) as error:
        return f"An error occurred: {error}"

@tool
def find_events(query: str, max_results: int = 10) -> str:
    """
    Searches for an event in the user's calendar based on its title or keywords.

    **Instructions for the 'query' parameter:**
    - Use this tool to get an event's ID before you can update it.
    - The 'query' should **only** contain the essential title or keywords of the event.
    - **DO NOT** include dates, times, or conversational words like "my", "the", "for tomorrow".
    
    **Correct Usage Examples:**
    - User says: "edit my meeting about the Project Launch tomorrow" -> query: "Project Launch"
    - User says: "change the weekly sync at 10am" -> query: "weekly sync"
    - User says: "Find the dental appointment" -> query: "dental appointment"
    
    **Incorrect Usage:**
    - User says: "edit tomorrow's meeting" -> DO NOT use query: "tomorrow's meeting"
    """
    try:
        service = get_calendar_service()
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                q=query,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found matching that query."
        
        result = "📅 **Found the following events:**\n\n"
        for i, event in enumerate(events, 1):
            start = event["start"].get("dateTime", event["start"].get("date"))
            event_link = event.get("htmlLink", "No link available")
            event_summary = event.get("summary", "No title")
            event_id = event.get("id", "No ID")
            
            result += f"{i}. **{event_summary}**\n"
            result += f"   - Starts: {start}\n"
            result += f"   - ID: {event_id}\n"
            result += f"   - 🔗 Link: {event_link}\n\n"
        
        return result
    except (HttpError, FileNotFoundError, ValueError) as error:
        return f"An error occurred: {error}"

class UpdateEventInput(BaseModel):
    event_id: str = Field(description="The unique ID of the event to update.")
    summary: Optional[str] = Field(None, description="The new summary or title for the event.")
    description: Optional[str] = Field(None, description="The new description for the event.")
    start_time: Optional[str] = Field(None, description="The new start time in ISO format.")
    end_time: Optional[str] = Field(None, description="The new end time in ISO format.")
    attendees_to_add: Optional[List[str]] = Field(None, description="A list of attendee emails to add.")
    attendees_to_remove: Optional[List[str]] = Field(None, description="A list of attendee emails to remove.")

@tool("update_calendar_event", args_schema=UpdateEventInput)
def update_calendar_event(event_id: str, **kwargs) -> str:
    """
    Updates an existing calendar event using its ID.
    
    This tool is smart: if you provide only a new start_time, it will automatically
    adjust the end_time to preserve the event's original duration.
    """
    try:
        service = get_calendar_service()
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        local_timezone = get_localzone_name()

        update_data = {k: v for k, v in kwargs.items() if v is not None}
        
        # Smart duration handling
        if 'start_time' in update_data and 'end_time' not in update_data:
            start_dt_str = event['start'].get('dateTime')
            end_dt_str = event['end'].get('dateTime')
            if start_dt_str and end_dt_str:
                original_start = datetime.datetime.fromisoformat(start_dt_str)
                original_end = datetime.datetime.fromisoformat(end_dt_str)
                duration = original_end - original_start
                
                # Use the provided start_time to calculate the new end_time
                new_start = datetime.datetime.fromisoformat(update_data['start_time'])
                new_end = new_start + duration
                
                event['start']['dateTime'] = new_start.isoformat()
                event['end']['dateTime'] = new_end.isoformat()
                # Unset them from update_data to avoid double processing
                del update_data['start_time']

        if 'summary' in update_data:
            event['summary'] = update_data['summary']
        if 'description' in update_data:
            event['description'] = update_data['description']
        # Handle cases where start/end time are explicitly provided together
        if 'start_time' in update_data:
            event['start']['dateTime'] = update_data['start_time']
            event['start']['timeZone'] = local_timezone
        if 'end_time' in update_data:
            event['end']['dateTime'] = update_data['end_time']
            event['end']['timeZone'] = local_timezone

        if 'attendees' not in event:
            event['attendees'] = []
            
        if 'attendees_to_add' in update_data:
            existing_emails = {a['email'] for a in event['attendees']}
            for email in update_data['attendees_to_add']:
                if email not in existing_emails:
                    event['attendees'].append({'email': email})

        if 'attendees_to_remove' in update_data:
            emails_to_remove = set(update_data['attendees_to_remove'])
            event['attendees'] = [a for a in event['attendees'] if a['email'] not in emails_to_remove]

        updated_event = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        
        event_link = updated_event.get('htmlLink', 'No link available')
        event_title = updated_event.get('summary', 'Unknown')
        
        return f"""✅ Event updated successfully!

📅 **Updated Event:**
- **Title:** {event_title}
- **Event ID:** {event_id}

🔗 **View Updated Event:** {event_link}

You can click the link above to view the updated event in Google Calendar."""
    except (HttpError, FileNotFoundError, ValueError) as error:
        return f"An error occurred: {error}"

@tool
def find_todays_events() -> str:
    """
    Lists all events scheduled for today in the user's calendar.
    """
    try:
        service = get_calendar_service()
        local_timezone = get_localzone_name()
        
        # Get today's start and end times in local timezone
        today = datetime.datetime.now()
        start_of_day = datetime.datetime.combine(today, datetime.time.min)
        end_of_day = datetime.datetime.combine(today, datetime.time.max)
        
        # Convert to UTC for the API
        start_of_day = start_of_day.astimezone(datetime.timezone.utc).isoformat()
        end_of_day = end_of_day.astimezone(datetime.timezone.utc).isoformat()
        
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        
        if not events:
            return "No events scheduled for today."
        
        result = "📅 **Today's Events:**\n\n"
        for i, event in enumerate(events, 1):
            start = event["start"].get("dateTime", event["start"].get("date"))
            event_link = event.get("htmlLink", "No link available")
            event_summary = event.get("summary", "No title")
            event_id = event.get("id", "No ID")
            
            # Convert the start time to local timezone for display
            if "T" in start:  # If it's a datetime (not just a date)
                start_dt = datetime.datetime.fromisoformat(start)
                start = start_dt.astimezone().strftime("%I:%M %p")  # Format as "HH:MM AM/PM"
            
            result += f"{i}. **{event_summary}**\n"
            result += f"   - Time: {start}\n"
            result += f"   - ID: {event_id}\n"
            result += f"   - 🔗 Link: {event_link}\n\n"
        
        return result
    except (HttpError, FileNotFoundError, ValueError) as error:
        return f"An error occurred: {error}"
