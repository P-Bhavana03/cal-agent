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
from dateutil.parser import parse as date_parse
from dateutil.tz import gettz

# Use the more specific .events scope. This may require re-authentication.
SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]

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

class GetCalendarEventsInput(BaseModel):
    start_date: Optional[str] = Field(None, description="The start date for the event search, in 'YYYY-MM-DD' format. If not provided, the search starts from the current time.")
    end_date: Optional[str] = Field(None, description="The end date for the event search, in 'YYYY-MM-DD' format. If not provided, it defaults to the start_date.")
    query: Optional[str] = Field(None, description="A keyword query to search for in event titles.")
    max_results: int = Field(10, description="The maximum number of events to return.")

@tool("get_calendar_events", args_schema=GetCalendarEventsInput)
def get_calendar_events(start_date: Optional[str] = None, end_date: Optional[str] = None, query: Optional[str] = None, max_results: int = 10) -> str:
    """
    Searches for events in the user's calendar.
    It can search by a date range, a text query, or both.
    If no dates are provided, it searches for all upcoming future events.
    """
    try:
        service = get_calendar_service()
        local_tz_name = get_localzone_name()
        local_tz = gettz(local_tz_name)

        time_min = None
        time_max = None

        if start_date:
            try:
                start_dt = date_parse(start_date)
                # Localize the start time to the beginning of the day
                time_min = datetime.datetime.combine(start_dt.date(), datetime.time.min).astimezone(local_tz).isoformat()
            except ValueError:
                return "Error: Invalid start_date format. Please use YYYY-MM-DD."
        else:
            # If no start date, search from now
            time_min = datetime.datetime.utcnow().isoformat() + "Z"

        if end_date:
            try:
                end_dt = date_parse(end_date)
                # Localize the end time to the end of the day
                time_max = datetime.datetime.combine(end_dt.date(), datetime.time.max).astimezone(local_tz).isoformat()
            except ValueError:
                return "Error: Invalid end_date format. Please use YYYY-MM-DD."
        elif start_date:
            # If start_date is given but not end_date, search for the whole day.
            start_dt = date_parse(start_date)
            time_max = datetime.datetime.combine(start_dt.date(), datetime.time.max).astimezone(local_tz).isoformat()

        list_kwargs = {
            "calendarId": "primary",
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            list_kwargs["timeMax"] = time_max
        if query:
            list_kwargs["q"] = query

        events_result = service.events().list(**list_kwargs).execute()
        events = events_result.get("items", [])

        if not events:
            return "No events found matching your criteria."

        result = "📅 **Found the following events:**\n\n"
        for i, event in enumerate(events, 1):
            start = event["start"].get("dateTime", event["start"].get("date"))
            start_dt = date_parse(start)

            if 'dateTime' in event['start']:
                time_info = start_dt.astimezone(local_tz).strftime("%I:%M %p").lstrip('0')
                end_str = event["end"].get("dateTime", event["end"].get("date"))
                end_dt = date_parse(end_str)
                end_time_info = end_dt.astimezone(local_tz).strftime("%I:%M %p").lstrip('0')
                duration = end_dt - start_dt
                duration_str = f"({duration})"
            else:
                time_info = "All-day"
                end_time_info = ""
                duration_str = ""

            event_summary = event.get("summary", "No title")
            event_id = event.get("id", "No ID")
            event_link = event.get('htmlLink', 'No link available')
            
            result += f"{i}. **{event_summary}**\n"
            result += f"   - Time: {time_info} to {end_time_info} {duration_str}\n"
            result += f"   - ID: `{event_id}`\n"
            result += f"   - Link: [View Event]({event_link})\n\n"
        
        return result
    except (HttpError, FileNotFoundError, ValueError) as error:
        return f"An error occurred: {error}"

class GetEventDetailsInput(BaseModel):
    event_id: str = Field(description="The unique ID of the event to get details for.")

@tool("get_event_details", args_schema=GetEventDetailsInput)
def get_event_details(event_id: str) -> str:
    """
    Fetches the complete details for a single calendar event using its ID.
    """
    try:
        service = get_calendar_service()
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        local_tz = gettz(get_localzone_name())

        # Extract details
        summary = event.get("summary", "No Title")
        description = event.get("description", "No description provided.")
        start_str = event["start"].get("dateTime", event["start"].get("date"))
        end_str = event["end"].get("dateTime", event["end"].get("date"))
        
        start_dt = date_parse(start_str).astimezone(local_tz)
        end_dt = date_parse(end_str).astimezone(local_tz)

        if 'dateTime' in event['start']:
            time_str = f"{start_dt.strftime('%A, %B %d, %Y from %I:%M %p')} to {end_dt.strftime('%I:%M %p %Z')}"
            duration = end_dt - start_dt
            duration_str = str(duration)
        else:
            time_str = f"{start_dt.strftime('%A, %B %d, %Y')} (All-day)"
            duration_str = "All-day event"

        attendees = event.get("attendees", [])
        attendee_list = "\n".join([f"- {att['email']}" for att in attendees]) if attendees else "No attendees."
        
        event_link = event.get('htmlLink', 'No link available')

        return f"""✅ **Event Details**
- **Title:** {summary}
- **Time:** {time_str}
- **Duration:** {duration_str}
- **Description:** {description}
- **Attendees:**
{attendee_list}
- **Event ID:** `{event_id}`
- **Link:** [View in Google Calendar]({event_link})"""

    except HttpError as error:
        if error.resp.status == 404:
            return f"Error: No event found with ID '{event_id}'."
        return f"An error occurred: {error}"
    except (FileNotFoundError, ValueError) as error:
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
    
    This tool is smart:
    - If you provide only a new start_time, it will automatically adjust the end_time to preserve the event's original duration.
    - It automatically handles timezone conversions.
    """
    try:
        service = get_calendar_service()
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        
        # Use the timezone from the original event or fallback to local timezone
        event_timezone = event.get('start', {}).get('timeZone', get_localzone_name())
        tz = gettz(event_timezone)

        update_data = {k: v for k, v in kwargs.items() if v is not None}
        
        # Smart duration handling
        if 'start_time' in update_data and 'end_time' not in update_data:
            start_dt_str = event['start'].get('dateTime')
            end_dt_str = event['end'].get('dateTime')
            
            if start_dt_str and end_dt_str:
                original_start = date_parse(start_dt_str)
                original_end = date_parse(end_dt_str)
                duration = original_end - original_start
                
                new_start = date_parse(update_data['start_time']).astimezone(tz)
                new_end = new_start + duration
                
                event['start']['dateTime'] = new_start.isoformat()
                event['end']['dateTime'] = new_end.isoformat()
                del update_data['start_time']

        if 'summary' in update_data:
            event['summary'] = update_data['summary']
        if 'description' in update_data:
            event['description'] = update_data['description']
        
        if 'start_time' in update_data:
            start_dt = date_parse(update_data['start_time']).astimezone(tz)
            event['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': event_timezone}
        
        if 'end_time' in update_data:
            end_dt = date_parse(update_data['end_time']).astimezone(tz)
            event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': event_timezone}

        if 'attendees_to_add' in update_data:
            if 'attendees' not in event:
                event['attendees'] = []
            existing_emails = {a['email'] for a in event.get('attendees', [])}
            for email in update_data['attendees_to_add']:
                if email not in existing_emails:
                    event['attendees'].append({'email': email})

        if 'attendees_to_remove' in update_data:
            if 'attendees' in event:
                emails_to_remove = set(update_data['attendees_to_remove'])
                event['attendees'] = [a for a in event['attendees'] if a.get('email') not in emails_to_remove]

        updated_event = service.events().update(
            calendarId="primary", 
            eventId=event_id, 
            body=event,
            sendUpdates='all' # Notify attendees of the changes
        ).execute()
        
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

class FindAvailabilityInput(BaseModel):
    start_date: str = Field(description="Start date in ISO format 'YYYY-MM-DD'")
    end_date: Optional[str] = Field(None, description="End date in ISO format 'YYYY-MM-DD'. If not provided, only the start_date is checked.")
    start_hour: int = Field(9, description="Start of working hours (24-hour format, default 9 for 9 AM)")
    end_hour: int = Field(17, description="End of working hours (24-hour format, default 17 for 5 PM)")
    duration_minutes: int = Field(30, description="Duration of the meeting in minutes")

@tool("find_available_time_slots", args_schema=FindAvailabilityInput)
def find_available_time_slots(start_date: str, end_date: Optional[str] = None, start_hour: int = 9, end_hour: int = 17, duration_minutes: int = 30) -> str:
    """
    Finds available time slots in the user's calendar within a given date range and working hours.
    
    Args:
        start_date: Date in ISO format 'YYYY-MM-DD'
        end_date: Optional. Date in ISO format 'YYYY-MM-DD'
        start_hour: Start of working hours (24-hour format, default 9 for 9 AM)
        end_hour: End of working hours (24-hour format, default 17 for 5 PM)
        duration_minutes: Duration of the meeting in minutes (default 30)
    """
    try:
        service = get_calendar_service()
        local_tz_name = get_localzone_name()
        local_tz = gettz(local_tz_name)
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # Parse dates
        try:
            parsed_start_date = date_parse(start_date).date()
            parsed_end_date = date_parse(end_date).date() if end_date else parsed_start_date
        except ValueError:
            return "Error: Dates must be in YYYY-MM-DD format."

        # Validate dates
        if parsed_start_date < now_utc.astimezone(local_tz).date():
            parsed_start_date = now_utc.astimezone(local_tz).date()
            
        if parsed_start_date > parsed_end_date:
            return "Error: The start date must be before or the same as the end date."

        # Validate hours
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            return "Error: Hours must be between 0 and 23."
        if start_hour >= end_hour:
            return "Error: Start hour must be before end hour."
        if duration_minutes <= 0 or duration_minutes > 1440:
            return "Error: Duration must be between 1 and 1440 minutes."

        # Perform core logic in UTC
        time_min_utc = datetime.datetime.combine(parsed_start_date, datetime.time.min, tzinfo=local_tz).astimezone(datetime.timezone.utc)
        time_max_utc = datetime.datetime.combine(parsed_end_date, datetime.time.max, tzinfo=local_tz).astimezone(datetime.timezone.utc)

        freebusy_request = {
            "timeMin": time_min_utc.isoformat(),
            "timeMax": time_max_utc.isoformat(),
            "timeZone": local_tz_name, # Use local TZ for Google to interpret days correctly
            "items": [{"id": "primary"}],
        }

        freebusy_result = service.freebusy().query(body=freebusy_request).execute()
        busy_slots = freebusy_result.get("calendars", {}).get("primary", {}).get("busy", [])
        
        # All busy times are parsed as timezone-aware UTC objects
        busy_times_utc = sorted([(date_parse(slot['start']), date_parse(slot['end'])) for slot in busy_slots])

        available_slots_str = ""
        current_date = parsed_start_date
        duration = datetime.timedelta(minutes=duration_minutes)

        while current_date <= parsed_end_date:
            day_slots = []
            
            # Define work day in local time, then convert to UTC
            work_start_local = datetime.datetime.combine(current_date, datetime.time(start_hour, 0), tzinfo=local_tz)
            work_end_local = datetime.datetime.combine(current_date, datetime.time(end_hour, 0), tzinfo=local_tz)
            work_start_utc = work_start_local.astimezone(datetime.timezone.utc)
            work_end_utc = work_end_local.astimezone(datetime.timezone.utc)

            # Determine search start time in UTC
            search_start_utc = max(now_utc, work_start_utc)

            if search_start_utc >= work_end_utc:
                current_date += datetime.timedelta(days=1)
                continue

            current_time_utc = search_start_utc

            # Filter busy times for the current day's working hours
            day_busy_times_utc = [
                (s, e) for s, e in busy_times_utc 
                if s < work_end_utc and e > work_start_utc
            ]

            merged_busy_times = []
            for busy_start, busy_end in sorted(day_busy_times_utc):
                if not merged_busy_times or busy_start > merged_busy_times[-1][1]:
                    merged_busy_times.append([busy_start, busy_end])
                else:
                    merged_busy_times[-1][1] = max(merged_busy_times[-1][1], busy_end)
            
            for busy_start, busy_end in merged_busy_times:
                free_end_utc = min(busy_start, work_end_utc)
                if current_time_utc < free_end_utc:
                    slot_start_utc = current_time_utc
                    while slot_start_utc + duration <= free_end_utc:
                        slot_end_utc = slot_start_utc + duration
                        # Convert back to local time for display
                        slot_start_local = slot_start_utc.astimezone(local_tz)
                        slot_end_local = slot_end_utc.astimezone(local_tz)
                        day_slots.append(
                            f"{slot_start_local.strftime('%I:%M %p').lstrip('0')} to "
                            f"{slot_end_local.strftime('%I:%M %p').lstrip('0')}"
                        )
                        slot_start_utc += duration
                current_time_utc = max(current_time_utc, busy_end)

            if current_time_utc < work_end_utc:
                slot_start_utc = current_time_utc
                while slot_start_utc + duration <= work_end_utc:
                    slot_end_utc = slot_start_utc + duration
                    slot_start_local = slot_start_utc.astimezone(local_tz)
                    slot_end_local = slot_end_utc.astimezone(local_tz)
                    day_slots.append(
                        f"{slot_start_local.strftime('%I:%M %p').lstrip('0')} to "
                        f"{slot_end_local.strftime('%I:%M %p').lstrip('0')}"
                    )
                    slot_start_utc += duration

            if day_slots:
                try:
                    date_str = current_date.strftime('%A, %B %d')
                    available_slots_str += f"\n🗓️ **{date_str}**:\n" + "\n".join(f"- {s}" for s in day_slots)
                except ValueError:
                    continue
            
            current_date += datetime.timedelta(days=1)

        if not available_slots_str:
            try:
                date_range = (
                    f"{parsed_start_date.strftime('%Y-%m-%d')} to {parsed_end_date.strftime('%Y-%m-%d')}"
                    if parsed_end_date != parsed_start_date
                    else f"{parsed_start_date.strftime('%Y-%m-%d')}"
                )
                return (
                    f"No available slots of {duration_minutes} minutes found for {date_range} "
                    f"between {start_hour:02d}:00 and {end_hour:02d}:00."
                )
            except ValueError:
                return "No available slots found for the specified time range."

        return "✅ Here are the available time slots:\n" + available_slots_str

    except (HttpError, FileNotFoundError) as error:
        return f"An error occurred: {error}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"
