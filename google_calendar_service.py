# google_calendar_service.py (versão com busca e deleção)

import datetime
import os.path
import locale
from unidecode import unidecode

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    print("AVISO: Locale pt_BR.UTF-8 não encontrado.")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = 'America/Sao_Paulo'

def get_calendar_service():
    # Esta função não muda
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
    # Esta função não muda
    event_body = {
        "summary": summary, "description": description,
        "start": {"dateTime": start_time, "timeZone": TIMEZONE},
        "end": {"dateTime": end_time, "timeZone": TIMEZONE},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }
    return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all").execute()

def list_events_in_range(service, start_date_str=None, end_date_str=None):
    # Esta função não muda
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

# --- NOVA FUNÇÃO: Encontra um evento específico ---
def find_event_by_keywords(service, keywords):
    """Encontra o primeiro evento nos próximos 30 dias que corresponde a todas as palavras-chave."""
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    thirty_days_later = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=thirty_days_later,
        singleEvents=True, orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    if not events:
        return None

    # Normaliza as palavras-chave (remove acentos, minúsculas)
    normalized_keywords = [unidecode(k.lower()) for k in keywords]

    for event in events:
        summary = event.get('summary', '')
        normalized_summary = unidecode(summary.lower())
        
        # Verifica se todas as palavras-chave estão no título do evento
        if all(keyword in normalized_summary for keyword in normalized_keywords):
            return event  # Retorna o primeiro evento que corresponder

    return None

# --- NOVA FUNÇÃO: Deleta um evento pelo seu ID ---
def delete_event(service, event_id):
    """Deleta um evento da agenda usando seu ID."""
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except HttpError as e:
        print(f"Erro ao deletar evento: {e}")
        return False

# A função find_and_delete_event não é mais necessária, pois separamos as responsabilidades
