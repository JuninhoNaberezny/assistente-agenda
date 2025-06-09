# google_calendar_service.py (versão corrigida e robusta)
# Funções expandidas para interagir com a API do Google Calendar.

import datetime
import os.path
import locale # <<--- NOVO: Importado para corrigir o idioma das datas

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- MELHORIA: Garantir que as datas sejam formatadas em Português do Brasil ---
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    print("Locale pt_BR.UTF-8 não encontrado. Usando o locale padrão do sistema.")


SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = 'America/Sao_Paulo' # Você pode ajustar para o seu fuso horário

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
    return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all").execute()

def list_upcoming_events(service, date_str=None):
    # --- CORREÇÃO: Lógica de data/hora para buscar eventos corretamente ---
    try:
        if date_str:
            # Se uma data for fornecida pela IA, use-a.
            target_date = datetime.datetime.fromisoformat(date_str).date()
        else:
            # Se não, use a data local de hoje.
            target_date = datetime.date.today()

        # Define o início do dia (meia-noite) e o fim do dia (23:59:59) no fuso horário correto.
        time_min_dt = datetime.datetime.combine(target_date, datetime.time.min).astimezone(datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(target_date, datetime.time.max).astimezone(datetime.timezone.utc)
        
        # Formata para o padrão RFC3339 que a API do Google espera.
        time_min = time_min_dt.isoformat()
        time_max = time_max_dt.isoformat()

        # Formata a data para uma resposta amigável em português.
        formatted_date = target_date.strftime("%d de %B de %Y")
        
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", []), formatted_date
    except Exception as e:
        print(f"Erro ao listar eventos: {e}")
        return [], "data não especificada"


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
