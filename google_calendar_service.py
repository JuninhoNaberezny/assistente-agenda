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
    """Autentica e retorna o serviço do Google Calendar."""
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
    try:
        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time, "timeZone": TIMEZONE},
            "end": {"dateTime": end_time, "timeZone": TIMEZONE},
            "attendees": [{"email": email} for email in attendees] if attendees else []
        }
        if conference_solution == "Google Meet":
            event_body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"{uuid.uuid4().hex}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}
                }
            }
        return service.events().insert(calendarId="primary", body=event_body, sendUpdates="all", conferenceDataVersion=1).execute()
    except HttpError as e:
        print(f"Erro ao criar evento: {e}")
        return None


def list_events_in_range(service, start_date_str=None, end_date_str=None):
    """
    ## CORREÇÃO: Função refatorada para retornar (dados, erro).
    Lista eventos em um intervalo de datas.
    Retorna:
        tuple: Uma tupla (lista_de_eventos, None) em sucesso,
               ou (None, mensagem_de_erro) em falha.
    """
    try:
        start_date_obj = datetime.date.today() if not start_date_str else datetime.datetime.fromisoformat(start_date_str).date()
        end_date_obj = datetime.datetime.fromisoformat(end_date_str).date() if end_date_str else start_date_obj

        # Converte as datas para o fuso horário UTC para a API
        time_min_dt = datetime.datetime.combine(start_date_obj, datetime.time.min).astimezone(datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone(datetime.timezone.utc)

        # Formato RFC3339 correto
        time_min = time_min_dt.isoformat()
        time_max = time_max_dt.isoformat()

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        return events_result.get("items", []), None  # Sucesso: (lista, None)
    except HttpError as e:
        print(f"Erro de API ao listar eventos: {e}")
        return None, "Ocorreu um erro ao me conectar com a agenda do Google."
    except (ParserError, ValueError) as e:
        print(f"Erro de parsing de data: {e}")
        return None, "Não consegui entender as datas que você pediu."
    except Exception as e:
        print(f"Erro inesperado ao listar eventos: {e}")
        return None, "Ocorreu um erro inesperado ao processar seu pedido."


def find_events_by_query(service, query_text, start_date_str=None, end_date_str=None):
    """
    ## CORREÇÃO: Função refatorada para retornar (dados, erro).
    Encontra eventos por uma query de texto.
    """
    try:
        if not start_date_str:
            time_min_dt = datetime.datetime.now(datetime.timezone.utc)
            time_max_dt = time_min_dt + datetime.timedelta(days=365)
        else:
            time_min_dt = datetime.datetime.fromisoformat(start_date_str).astimezone(datetime.timezone.utc)
            end_date_obj = datetime.datetime.fromisoformat(end_date_str).date() if end_date_str else time_min_dt.date()
            time_max_dt = datetime.datetime.combine(end_date_obj, datetime.time.max).astimezone(datetime.timezone.utc)
        
        time_min = time_min_dt.isoformat()
        time_max = time_max_dt.isoformat()
        
        events_result = service.events().list(
            calendarId='primary',
            q=query_text,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', []), None # Sucesso: (lista, None)
    except (HttpError, ParserError, Exception) as e:
        print(f"Erro ao buscar eventos com a query '{query_text}': {e}")
        return None, "Ocorreu um erro ao pesquisar na sua agenda."


def update_event(service, event_id, update_body):
    """Atualiza um evento existente."""
    try:
        return service.events().patch(calendarId='primary', eventId=event_id, body=update_body, sendUpdates='all').execute()
    except HttpError as e:
        print(f"Erro ao atualizar o evento {event_id}: {e}")
        return None

def delete_event(service, event_id):
    """Deleta um evento pelo seu ID."""
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except HttpError as e:
        print(f"Erro ao deletar evento {event_id}: {e}")
        return False
