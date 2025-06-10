# google_calendar_service.py

import datetime
import os.path
import uuid
from unidecode import unidecode

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

def create_event(service, summary, start_time, end_time, attendees=None, description="", location=None, conference_solution=None):
    event_body = {
        "summary": summary, "description": description, "location": location,
        "start": {"dateTime": start_time, "timeZone": TIMEZONE},
        "end": {"dateTime": end_time, "timeZone": TIMEZONE},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }
    if conference_solution == "Google Meet":
        event_body["conferenceData"] = { "createRequest": { "requestId": f"{uuid.uuid4().hex}", "conferenceSolutionKey": {"type": "hangoutsMeet"} } }
    return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all", conferenceDataVersion=1).execute()

def list_events_in_range(service, start_date_str=None, end_date_str=None):
    try:
        start_date_obj = datetime.date.today() if not start_date_str else datetime.datetime.fromisoformat(start_date_str).date()
        end_date_obj = datetime.datetime.fromisoformat(end_date_str).date() if end_date_str else start_date_obj
        time_min_dt = datetime.datetime.combine(start_date_obj, datetime.time.min).astimezone(datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone(datetime.timezone.utc)
        if start_date_obj == end_date_obj:
            formatted_range = f"o dia {start_date_obj.strftime('%d de %B')}"
        else:
            formatted_range = f"o período de {start_date_obj.strftime('%d/%m')} a {end_date_obj.strftime('%d/%m')}"
        events_result = service.events().list(calendarId="primary", timeMin=time_min_dt.isoformat(), timeMax=time_max_dt.isoformat(), singleEvents=True, orderBy="startTime").execute()
        return events_result.get("items", []), formatted_range
    except Exception as e:
        print(f"Erro ao listar eventos: {e}")
        return [], "o período solicitado"

def find_events_by_query(service, query_text):
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    one_year_later = (datetime.datetime.utcnow() + datetime.timedelta(days=365)).isoformat() + 'Z'
    try:
        events_result = service.events().list(
            calendarId='primary', q=query_text, timeMin=now,
            timeMax=one_year_later, singleEvents=True, orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except Exception as e:
        print(f"Erro ao buscar eventos com a query '{query_text}': {e}")
        return []

def find_event_by_keywords(service, keywords):
    # Esta função pode ser mantida para usos futuros ou removida se não for mais necessária
    pass

def delete_event(service, event_id):
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except HttpError as e:
        print(f"Erro ao deletar evento: {e}")
        return False
