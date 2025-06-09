# google_calendar_service.py (VERSÃO FINAL E CORRETA)

import datetime
import os.path
import locale

try:
    # Define o locale para português do Brasil para formatar datas corretamente
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    print("AVISO: Locale pt_BR.UTF-8 não encontrado. As datas podem não ser formatadas corretamente.")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo de permissão para o Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar"]
# Fuso horário para os eventos
TIMEZONE = 'America/Sao_Paulo'

def get_calendar_service():
    """Autentica com a API do Google Calendar e retorna um objeto de serviço."""
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

def create_event(service, summary, start_time, end_time, attendees=None, description=""):
    """Cria um novo evento na agenda principal."""
    event_body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": TIMEZONE},
        "end": {"dateTime": end_time, "timeZone": TIMEZONE},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }
    return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all").execute()

def list_events_in_range(service, start_date_str=None, end_date_str=None):
    """Lista eventos em um intervalo de datas específico."""
    try:
        start_date_obj = datetime.date.today() if not start_date_str else datetime.datetime.fromisoformat(start_date_str).date()
        
        if end_date_str:
            end_date_obj = datetime.datetime.fromisoformat(end_date_str).date()
        else:
            end_date_obj = start_date_obj

        time_min_dt = datetime.datetime.combine(start_date_obj, datetime.time.min).astimezone(datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone(datetime.timezone.utc)
        
        time_min_iso = time_min_dt.isoformat()
        time_max_iso = time_max_dt.isoformat()

        if start_date_obj == end_date_obj:
            formatted_range = start_date_obj.strftime("o dia %d de %B")
        else:
            formatted_range = f"o período de {start_date_obj.strftime('%d/%m')} a {end_date_obj.strftime('%d/%m')}"
        
        events_result = service.events().list(
            calendarId="primary", timeMin=time_min_iso, timeMax=time_max_iso,
            singleEvents=True, orderBy="startTime"
        ).execute()
        
        return events_result.get("items", []), formatted_range
        
    except Exception as e:
        print(f"Erro ao listar eventos: {e}")
        return [], "o período solicitado"

def find_and_delete_event(service, event_summary):
    """Função de placeholder para encontrar e deletar um evento. (Não implementada ainda)"""
    print(f"AVISO: A função 'find_and_delete_event' para '{event_summary}' não está implementada.")
    return None