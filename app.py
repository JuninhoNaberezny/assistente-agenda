# juninhonaberezny/assistente-agenda/assistente-agenda-4/app.py
import os
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil import parser
from pprint import pformat # Importa a função para formatar o JSON

# Carregar variáveis de ambiente
load_dotenv()

# Módulos do projeto
import google_calendar_service as calendar_service
import llm_processor
import feedback_manager

# Importações para logging
import logging
from rich.logging import RichHandler
from rich.console import Console

# Configuração do logging
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console, markup=True)]
)
log = logging.getLogger("rich")

# Validação da chave secreta do Flask
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    raise ValueError("A variável de ambiente FLASK_SECRET_KEY não foi definida.")

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Inicializa o serviço do Google Calendar
try:
    gcal_service = calendar_service.get_calendar_service()
    log.info("Serviço do Google Calendar iniciado com sucesso.")
except Exception as e:
    log.error(f"Falha ao iniciar o serviço do Google Calendar: {e}")
    gcal_service = None

# --- FUNÇÕES HANDLER (AGORA RETORNAM UM DICIONÁRIO) ---

def _format_response(text, link=None):
    """Padroniza o formato de resposta das funções handler."""
    return {'text': text, 'link': link}

def handle_create_event(details):
    if not details:
        return _format_response("Não recebi os detalhes para criar o evento.")
        
    start_time = details.get('start_time')
    end_time = details.get('end_time')

    if not all([start_time, end_time]):
        return _format_response("Não consegui identificar a data e hora para criar o evento.")

    conflicting_events, error = calendar_service.list_events_in_range(gcal_service, start_time, end_time)
    if error:
        return _format_response(f"Houve um problema ao verificar sua agenda: {error}")
    
    if conflicting_events:
        session['pending_action'] = {'intent': 'confirm_conflicting_creation', 'details': details}
        event_titles = ", ".join([f"'{event.get('summary', 'Evento sem título')}'" for event in conflicting_events])
        text = f"Percebi que você já tem outro(s) evento(s) nesse horário: {event_titles}.\nDeseja marcar mesmo assim?"
        return _format_response(text)

    return execute_create_event(details)

def execute_create_event(details):
    if not details:
        return _format_response("Detalhes para criação do evento estão faltando.")

    event, error = calendar_service.create_event(
        gcal_service,
        summary=details.get('summary', 'Compromisso'),
        start_time_str=details['start_time'],
        end_time_str=details['end_time'],
        attendees=details.get('attendees'),
        create_conference=details.get('create_conference', False)
    )
    if error or not event:
        return _format_response(f"Não consegui criar o evento: {error}")
    
    conference_link = event.get('hangoutLink')
    event_summary = event.get('summary')
    text = f"Evento '{event_summary}' criado com sucesso!"
    if conference_link:
        text += f"\n\n🔗 **Link da videochamada:** {conference_link}"
        
    return _format_response(text, event.get('htmlLink'))

def handle_list_events(details):
    events, error = calendar_service.list_events_in_range(
        gcal_service, details.get('start_time'), details.get('end_time'))
    if error:
        return _format_response(f"Não consegui listar seus eventos: {error}")
    if not events:
        return _format_response("Você não tem nenhum evento nesse período.")
    
    response_lines = ["Aqui estão seus próximos eventos:"]
    for event in events:
        start_str = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
        if start_str:
            start = parser.isoparse(start_str).strftime('%d/%m às %H:%M')
            summary = event.get('summary', 'Evento sem título')
            response_lines.append(f"• **{summary}** em {start}")
    return _format_response("\n".join(response_lines))

def handle_cancel_event(details):
    keywords = details.get('keywords', [])
    if not keywords:
        return _format_response("Por favor, especifique qual evento você deseja cancelar.")
    session['pending_action'] = {'intent': 'confirm_cancel', 'details': details}
    return _format_response(f"Você tem certeza que deseja cancelar o evento relacionado a '{' '.join(keywords)}'?")

def execute_cancel_event(details):
    keywords = details.get('keywords', [])
    start_time = details.get('search_start_time')
    end_time = details.get('search_end_time')

    found_events, error = calendar_service.find_events_by_query(gcal_service, keywords, start_time, end_time)
    if error:
        return _format_response(f"Erro ao procurar o evento para cancelar: {error}")
    if not found_events:
        return _format_response("Não encontrei nenhum evento com esses detalhes para cancelar.")
    if len(found_events) > 1:
        return _format_response("Encontrei múltiplos eventos com essa descrição. Por favor, seja mais específico.")

    event_to_delete = found_events[0]
    success, error = calendar_service.delete_event(gcal_service, event_to_delete.get('id'))
    if not success:
        return _format_response(f"Não foi possível cancelar o evento: {error}")
    return _format_response(f"Evento '{event_to_delete.get('summary')}' cancelado com sucesso.")

def handle_reschedule_event(details):
    keywords = details.get('keywords', [])
    if not keywords:
        return _format_response("Por favor, especifique qual evento você deseja alterar.")
    session['pending_action'] = {'intent': 'confirm_reschedule', 'details': details}
    return _format_response(f"Você tem certeza que deseja alterar o evento relacionado a '{' '.join(keywords)}'?")

def execute_reschedule_event(details):
    keywords = details.get('keywords', [])
    start_time = details.get('search_start_time')
    end_time = details.get('search_end_time')

    found_events, error = calendar_service.find_events_by_query(gcal_service, keywords, start_time, end_time)
    if error:
        return _format_response(f"Erro ao procurar o evento para alterar: {error}")
    if not found_events:
        return _format_response("Não encontrei nenhum evento com esses detalhes para alterar.")
    if len(found_events) > 1:
        return _format_response("Encontrei múltiplos eventos. Por favor, seja mais específico.")

    event_to_update = found_events[0]
    
    if details.get('new_start_time') and not details.get('new_end_time'):
        original_start_str = event_to_update.get('start', {}).get('dateTime')
        original_end_str = event_to_update.get('end', {}).get('dateTime')
        if original_start_str and original_end_str:
            original_start = parser.isoparse(original_start_str)
            original_end = parser.isoparse(original_end_str)
            duration = original_end - original_start
            new_start = parser.isoparse(details['new_start_time'])
            details['new_end_time'] = (new_start + duration).isoformat()
    
    update_payload = {}
    if 'new_summary' in details:
        update_payload['summary'] = details['new_summary']
    if 'new_start_time' in details:
        update_payload['start'] = {'dateTime': details['new_start_time']}
    if 'new_end_time' in details:
        update_payload['end'] = {'dateTime': details['new_end_time']}

    if not update_payload:
        return _format_response("Não identifiquei nenhuma alteração a ser feita.")

    updated_event, error = calendar_service.update_event(gcal_service, event_to_update.get('id'), update_payload)
    if error or not updated_event:
        return _format_response(f"Não foi possível alterar o evento: {error}")
    return _format_response(f"Evento '{updated_event.get('summary')}' alterado com sucesso.", updated_event.get('htmlLink'))

def handle_ask_availability(details):
    start_time_str = details.get('start_time')
    end_time_str = details.get('end_time')

    events, error = calendar_service.list_events_in_range(gcal_service, start_time_str, end_time_str)
    if error:
        return _format_response(f"Não consegui verificar sua disponibilidade: {error}")

    if not events:
        return _format_response("Parece que você está livre nesse período!")
    
    response = "Nesse período, sua agenda tem os seguintes compromissos:\n"
    for event in events:
        start = parser.isoparse(event.get('start', {}).get('dateTime')).strftime('%H:%M')
        end = parser.isoparse(event.get('end', {}).get('dateTime')).strftime('%H:%M')
        response += f"• **{event.get('summary')}** das {start} às {end}\n"
    response += "\nFora desses horários, você está livre."
    return _format_response(response)

def handle_unknown_intent(_):
    return _format_response("Desculpe, não entendi o que você quis dizer. Posso te ajudar a criar, listar, alterar ou cancelar eventos.")

INTENT_HANDLERS = {
    'create_event': handle_create_event,
    'list_events': handle_list_events,
    'cancel_event': handle_cancel_event,
    'reschedule_or_modify_event': handle_reschedule_event,
    'ask_availability': handle_ask_availability,
    'unknown': handle_unknown_intent
}

@app.route("/")
def index():
    session.clear()
    session['chat_history'] = []
    return render_template('index.html')

@app.route("/chat", methods=['POST'])
def chat():
    if not gcal_service:
        return jsonify({'response': "O serviço do Google Calendar não está disponível."})

    request_data = request.json
    if not request_data or 'message' not in request_data:
        return jsonify({'response': "Pedido inválido."}), 400
    user_input = request_data['message']
    
    # --- LOG ADICIONADO ---
    console.rule("[bold green]Nova Requisição[/bold green]")
    log.info(f"[bold]Entrada do Usuário:[/] {user_input}")
    
    if 'chat_history' not in session:
        session['chat_history'] = []
    session['chat_history'].append({'role': 'user', 'content': user_input})
    session.modified = True

    response_data = {}
    pending_action = session.get('pending_action')
    if pending_action:
        log.info(f"[bold]Ação Pendente Detectada:[/] {pending_action.get('intent')}")
        if user_input.lower() in ['sim', 's', 'pode', 'confirmo', 'isso', 'ok']:
            log.info("[bold yellow]Usuário confirmou a ação.[/]")
            intent = pending_action.get('intent')
            details = pending_action.get('details')
            action_executors = {
                'confirm_cancel': execute_cancel_event,
                'confirm_reschedule': execute_reschedule_event,
                'confirm_conflicting_creation': execute_create_event,
            }
            handler = action_executors.get(intent)
            response_data = handler(details) if handler else _format_response("Houve um erro no fluxo de confirmação.")
        else:
            log.info("[bold red]Usuário negou a ação.[/]")
            response_data = _format_response("Ok, ação cancelada.")
        session.pop('pending_action', None)
    else:
        llm_response, error = llm_processor.process_prompt_with_llm(user_input, session['chat_history'])
        if error:
            log.error(f"Erro da LLM: {error}")
            return jsonify({'response': error})

        # --- LOG ADICIONADO ---
        log.info(f"[bold]JSON da LLM:[/]\n[cyan]{pformat(llm_response)}[/]")

        session['last_llm_response'] = llm_response
        intent = llm_response.get('intent', 'unknown')
        details = llm_response.get('details', {})

        # --- LOG ADICIONADO ---
        log.info(f"[bold]Intenção Processada:[/] '{intent}'")

        handler = INTENT_HANDLERS.get(intent, handle_unknown_intent)
        response_data = handler(details)
    
    response_text = response_data.get('text', 'Ocorreu um erro inesperado.')
    event_link = response_data.get('link')

    # --- LOG ADICIONADO ---
    log.info(f"[bold]Resposta para o Frontend:[/] {response_text.replace('[bold]', '').replace('[/]', '').replace('•', '-')}")
    if event_link:
        log.info(f"[bold]Link do Evento:[/] {event_link}")

    session['chat_history'].append({'role': 'assistant', 'content': response_text})
    session.modified = True
    
    return jsonify({
        'response': response_text, 
        'event_link': event_link,
        'llm_response': session.get('last_llm_response', {})
    })

@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'Corpo da requisição está vazio.'}), 400
    
    try:
        feedback_manager.save_feedback(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        log.error(f"Erro ao salvar feedback: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=False)