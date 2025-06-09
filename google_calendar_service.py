# google_calendar_service.py
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = 'America/Sao_Paulo'

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def create_event(service, summary, start_time_str, end_time_str, attendees=None, description=""):
    event_body = {
        "summary": summary, "description": description,
        "start": {"dateTime": start_time_str, "timeZone": TIMEZONE},
        "end": {"dateTime": end_time_str, "timeZone": TIMEZONE},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }
    return service.events().insert(calendarId="primary", body=event_body).execute()

def list_upcoming_events(service, date_str=None):
    if not date_str:
        start_dt = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_dt = datetime.datetime.fromisoformat(date_str)

    time_min = start_dt.isoformat() + "Z"
    time_max = (start_dt + datetime.timedelta(days=1)).isoformat() + "Z"

    formatted_date = start_dt.strftime("%d de %B de %Y")

    events_result = service.events().list(
        calendarId="primary", timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy="startTime"
    ).execute()
    return events_result.get("items", []), formatted_date

def check_availability(service, start_time_str, end_time_str):
    body = {
        "timeMin": start_time_str, "timeMax": end_time_str, "timeZone": TIMEZONE,
        "items": [{"id": "primary"}]
    }
    freebusy_result = service.freebusy().query(body=body).execute()
    return len(freebusy_result.get('calendars', {}).get('primary', {}).get('busy', [])) > 0

def find_and_delete_event(service, event_summary, event_date=None):
    events, _ = list_upcoming_events(service, event_date)
    deleted_count = 0
    if not events: return 0
    for event in events:
        if event_summary.lower() in event.get('summary', '').lower():
            try:
                service.events().delete(calendarId='primary', eventId=event['id']).execute()
                print(f"Evento '{event['summary']}' ({event['id']}) deletado.")
                deleted_count += 1
            except HttpError as e:
                print(f"Erro ao deletar evento {event['id']}: {e}")
    return deleted_count
