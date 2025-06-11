# juninhonaberezny/assistente-agenda/assistente-agenda-4/google_calendar_service.py
import os.path
import datetime
from dateutil import parser, tz

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopos da API do Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
TIMEZONE = 'America/Sao_Paulo'

def get_calendar_service():
    """Autentica e retorna um objeto de serviço para interagir com a API do Google Calendar."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    service = build('calendar', 'v3', credentials=creds)
    return service

def _prepare_time_range(start_date_str=None, end_date_str=None):
    """
    Função auxiliar para preparar os horários de início e fim em formato RFC3339.
    Se nenhuma data for fornecida, retorna um intervalo de hoje até o final do dia.
    """
    local_tz = tz.gettz(TIMEZONE)
    
    if start_date_str:
        start_time = parser.isoparse(start_date_str).astimezone(local_tz)
    else:
        start_time = datetime.datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
    if end_date_str:
        end_time = parser.isoparse(end_date_str).astimezone(local_tz)
    else:
        # Por padrão, se não houver data final, pega até o fim do dia do início
        end_time = start_time.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_time.isoformat(), end_time.isoformat()


def list_events_in_range(service, start_date_str=None, end_date_str=None):
    """Lista eventos em um determinado intervalo de datas."""
    try:
        time_min, time_max = _prepare_time_range(start_date_str, end_date_str)
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', []), None
    except Exception as e:
        return None, f"Erro ao listar eventos: {e}"

def create_event(service, summary, start_time_str, end_time_str, attendees=None, create_conference=False):
    """Cria um novo evento na agenda."""
    try:
        local_tz = tz.gettz(TIMEZONE)
        start_time = parser.isoparse(start_time_str).astimezone(local_tz)
        end_time = parser.isoparse(end_time_str).astimezone(local_tz)

        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': TIMEZONE,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': TIMEZONE,
            },
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        if create_conference:
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': f"sample-request-{datetime.datetime.utcnow().timestamp()}",
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet'
                    }
                }
            }
        
        created_event = service.events().insert(
            calendarId='primary', 
            body=event,
            sendUpdates='all' if attendees else 'none',
            conferenceDataVersion=1
        ).execute()
        
        return created_event, None
    except Exception as e:
        return None, f"Erro ao criar o evento: {e}"


def find_events_by_query(service, query_keywords, start_date_str=None, end_date_str=None):
    """Encontra eventos que correspondem a palavras-chave em um intervalo de tempo."""
    try:
        time_min, time_max = _prepare_time_range(start_date_str, end_date_str)
        
        # O 'q' parameter faz uma busca textual nos eventos.
        # Juntamos as keywords para uma busca mais eficaz.
        full_query = " ".join(query_keywords)

        events_result = service.events().list(
            calendarId='primary',
            q=full_query,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True
        ).execute()
        
        return events_result.get('items', []), None
    except Exception as e:
        return None, f"Erro ao buscar eventos: {e}"

def update_event(service, event_id, updated_fields):
    """Atualiza um evento existente."""
    try:
        event = service.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=updated_fields,
            sendUpdates='all'
        ).execute()
        return event, None
    except HttpError as e:
        return None, f"Erro ao atualizar o evento: {e.content.decode()}"
    except Exception as e:
        return None, f"Um erro inesperado ocorreu ao atualizar o evento: {e}"


def delete_event(service, event_id):
    """Deleta um evento."""
    try:
        service.events().delete(
            calendarId='primary', 
            eventId=event_id,
            sendUpdates='all'
        ).execute()
        return True, None
    except HttpError as e:
        return False, f"Erro ao deletar o evento: {e.content.decode()}"
    except Exception as e:
        return False, f"Um erro inesperado ocorreu ao deletar o evento: {e}"