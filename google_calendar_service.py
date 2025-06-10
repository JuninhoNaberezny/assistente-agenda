# google_calendar_service.py

import datetime
import os.path
import uuid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dateutil.parser import parse, ParserError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = 'America/Sao_Paulo'

def get_calendar_service():
    """
    Autentica e retorna o serviço do Google Calendar.
    Esta função permanece inalterada.
    """
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
    """Cria um novo evento no calendário."""
    event_body = { "summary": summary, "description": description, "location": location, "start": {"dateTime": start_time, "timeZone": TIMEZONE}, "end": {"dateTime": end_time, "timeZone": TIMEZONE}, "attendees": [{"email": email} for email in attendees] if attendees else [] }
    if conference_solution == "Google Meet": event_body["conferenceData"] = { "createRequest": { "requestId": f"{uuid.uuid4().hex}", "conferenceSolutionKey": {"type": "hangoutsMeet"} } }
    return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all", conferenceDataVersion=1).execute()

def list_events_in_range(service, start_date_str=None, end_date_str=None):
    """Lista eventos em um determinado período."""
    try:
        start_date_obj = datetime.date.today() if not start_date_str else datetime.datetime.fromisoformat(start_date_str).date()
        end_date_obj = datetime.datetime.fromisoformat(end_date_str).date() if end_date_str else start_date_obj
        time_min_dt = datetime.datetime.combine(start_date_obj, datetime.time.min).astimezone()
        time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone()
        if start_date_obj == end_date_obj: formatted_range = f"o dia {start_date_obj.strftime('%d de %B')}"
        else: formatted_range = f"o período de {start_date_obj.strftime('%d/%m')} a {end_date_obj.strftime('%d/%m')}"
        events_result = service.events().list(calendarId="primary", timeMin=time_min_dt.isoformat(), timeMax=time_max_dt.isoformat(), singleEvents=True, orderBy="startTime").execute()
        return events_result.get("items", []), formatted_range
    except Exception as e:
        print(f"Erro ao listar eventos: {e}")
        return [], "o período solicitado"

def find_events_by_query(service, query_text, start_date_str=None, end_date_str=None):
    """
    Busca eventos de forma inteligente.
    1. Se datas são fornecidas, busca eventos NESSE PERÍODO.
    2. Usa o query_text para FILTRAR os resultados por palavras-chave.
    """
    try:
        # Se não houver datas, usa um período padrão (próximos 365 dias)
        if not start_date_str:
            time_min_dt = datetime.datetime.utcnow()
            time_max_dt = time_min_dt + datetime.timedelta(days=365)
        else:
            # Converte as strings de data para objetos datetime com fuso horário
            time_min_dt = datetime.datetime.fromisoformat(start_date_str).astimezone()
            # Se a data final não for fornecida, usa o mesmo dia da data inicial
            if end_date_str:
                end_date_obj = datetime.datetime.fromisoformat(end_date_str).date()
            else:
                end_date_obj = time_min_dt.date()
            time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone()

        events_result = service.events().list(
            calendarId='primary',
            q=query_text, # A API usará a query para uma filtragem inicial no título/descrição
            timeMin=time_min_dt.isoformat(),
            timeMax=time_max_dt.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        return events_result.get('items', [])
    except (HttpError, ParserError, Exception) as e:
        print(f"Erro ao buscar eventos com a query '{query_text}': {e}")
        return []


def delete_event(service, event_id):
    """Deleta um evento pelo seu ID."""
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except HttpError as e:
        print(f"Erro ao deletar evento {event_id}: {e}")
        return False

def update_event_attendees(service, event_id, new_attendees_emails):
    """Adiciona novos convidados a um evento."""
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        current_attendees = event.get('attendees', [])
        current_emails = {attendee['email'] for attendee in current_attendees}
        for email in new_attendees_emails:
            if email not in current_emails:
                current_attendees.append({'email': email})
        updated_body = {'attendees': current_attendees}
        updated_event = service.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=updated_body,
            sendUpdates='all'
        ).execute()
        return updated_event
    except HttpError as e:
        print(f"Erro ao atualizar o evento {event_id}: {e}")
        return None
