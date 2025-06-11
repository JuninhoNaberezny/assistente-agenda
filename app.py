# juninhonaberezny/assistente-agenda/assistente-agenda-4/app.py
import os
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil import parser

# Carregar variáveis de ambiente
load_dotenv()

# Módulos do projeto
import google_calendar_service as calendar_service
import llm_processor
import feedback_manager

# Importações para logging
import logging
from rich.logging import RichHandler

# Configuração do logging
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
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

# --- ROTEADOR DE INTENÇÕES E FUNÇÕES HANDLER ---

def handle_create_event(details):
    """Lida com a intenção de criar um evento, verificando conflitos."""
    if not details:
        return "Não recebi os detalhes para criar o evento."
        
    start_time = details.get('start_time')
    end_time = details.get('end_time')

    if not all([start_time, end_time]):
        return "Não consegui identificar a data e hora para criar o evento."

    conflicting_events, error = calendar_service.list_events_in_range(gcal_service, start_time, end_time)
    if error:
        return f"Houve um problema ao verificar sua agenda: {error}"
    
    if conflicting_events:
        session['pending_action'] = {'intent': 'confirm_conflicting_creation', 'details': details}
        event_titles = ", ".join([f"'{event.get('summary', 'Evento sem título')}'" for event in conflicting_events])
        return f"Percebi que você já tem outro(s) evento(s) nesse horário: {event_titles}. Deseja marcar mesmo assim?"

    return execute_create_event(details)

def execute_create_event(details):
    """Executa a criação do evento."""
    if not details:
        return "Detalhes para criação do evento estão faltando."

    event, error = calendar_service.create_event(
        gcal_service,
        summary=details.get('summary', 'Compromisso'),
        start_time_str=details['start_time'],
        end_time_str=details['end_time'],
        attendees=details.get('attendees'),
        create_conference=details.get('create_conference', False)
    )
    if error or not event:
        return f"Não consegui criar o evento: {error}"
    
    link = event.get('hangoutLink', '')
    response_msg = f"Evento '{event.get('summary')}' criado com sucesso!"
    if link:
        response_msg += f" Link da videochamada: {link}"
    return response_msg

def handle_list_events(details):
    """Lida com a intenção de listar eventos."""
    events, error = calendar_service.list_events_in_range(
        gcal_service, details.get('start_time'), details.get('end_time'))
    if error:
        return f"Não consegui listar seus eventos: {error}"
    if not events:
        return "Você não tem nenhum evento nesse período."
    
    response_lines = ["Aqui estão seus próximos eventos:"]
    for event in events:
        start_str = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
        if start_str:
            start = parser.isoparse(start_str).strftime('%d/%m às %H:%M')
            response_lines.append(f"- {event.get('summary', 'Evento sem título')} em {start}")
    return "\n".join(response_lines)

def handle_cancel_event(details):
    """Lida com a intenção de cancelar um evento, pedindo confirmação."""
    keywords = details.get('keywords', [])
    if not keywords:
        return "Por favor, especifique qual evento você deseja cancelar."
    session['pending_action'] = {'intent': 'confirm_cancel', 'details': details}
    return f"Você tem certeza que deseja cancelar o evento relacionado a '{' '.join(keywords)}'?"

def execute_cancel_event(details):
    """Executa o cancelamento após a confirmação."""
    keywords = details.get('keywords', [])
    start_time = details.get('search_start_time')
    end_time = details.get('search_end_time')

    found_events, error = calendar_service.find_events_by_query(gcal_service, keywords, start_time, end_time)
    if error:
        return f"Erro ao procurar o evento para cancelar: {error}"
    if not found_events:
        return "Não encontrei nenhum evento com esses detalhes para cancelar."
    if len(found_events) > 1:
        return "Encontrei múltiplos eventos com essa descrição. Por favor, seja mais específico."

    event_to_delete = found_events[0]
    success, error = calendar_service.delete_event(gcal_service, event_to_delete.get('id'))
    if not success:
        return f"Não foi possível cancelar o evento: {error}"
    return f"Evento '{event_to_delete.get('summary')}' cancelado com sucesso."

def handle_reschedule_event(details):
    """Lida com a intenção de remarcar um evento, pedindo confirmação."""
    keywords = details.get('keywords', [])
    if not keywords:
        return "Por favor, especifique qual evento você deseja alterar."
    session['pending_action'] = {'intent': 'confirm_reschedule', 'details': details}
    return f"Você tem certeza que deseja alterar o evento relacionado a '{' '.join(keywords)}'?"

def execute_reschedule_event(details):
    """Executa a remarcação após a confirmação."""
    keywords = details.get('keywords', [])
    start_time = details.get('search_start_time')
    end_time = details.get('search_end_time')

    found_events, error = calendar_service.find_events_by_query(gcal_service, keywords, start_time, end_time)
    if error:
        return f"Erro ao procurar o evento para alterar: {error}"
    if not found_events:
        return "Não encontrei nenhum evento com esses detalhes para alterar."
    if len(found_events) > 1:
        return "Encontrei múltiplos eventos. Por favor, seja mais específico."

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
        return "Não identifiquei nenhuma alteração a ser feita."

    updated_event, error = calendar_service.update_event(gcal_service, event_to_update.get('id'), update_payload)
    if error or not updated_event:
        return f"Não foi possível alterar o evento: {error}"
    return f"Evento '{updated_event.get('summary')}' alterado com sucesso."

def handle_ask_availability(details):
    """Lida com a intenção de verificar disponibilidade."""
    start_time_str = details.get('start_time')
    end_time_str = details.get('end_time')

    events, error = calendar_service.list_events_in_range(gcal_service, start_time_str, end_time_str)
    if error:
        return f"Não consegui verificar sua disponibilidade: {error}"

    if not events:
        return "Parece que você está livre nesse período!"
    
    response = "Nesse período, sua agenda tem os seguintes compromissos:\n"
    for event in events:
        start = parser.isoparse(event.get('start', {}).get('dateTime')).strftime('%H:%M')
        end = parser.isoparse(event.get('end', {}).get('dateTime')).strftime('%H:%M')
        response += f"- '{event.get('summary')}' das {start} às {end}\n"
    response += "Fora desses horários, você está livre."
    return response

def handle_unknown_intent(_):
    return "Desculpe, não entendi o que você quis dizer. Posso te ajudar a criar, listar, alterar ou cancelar eventos."

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
    
    if 'chat_history' not in session:
        session['chat_history'] = []
    session['chat_history'].append({'role': 'user', 'content': user_input})
    session.modified = True

    pending_action = session.get('pending_action')
    if pending_action:
        if user_input.lower() in ['sim', 's', 'pode', 'confirmo', 'isso', 'ok']:
            intent = pending_action.get('intent')
            details = pending_action.get('details')
            action_executors = {
                'confirm_cancel': execute_cancel_event,
                'confirm_reschedule': execute_reschedule_event,
                'confirm_conflicting_creation': execute_create_event,
            }
            handler = action_executors.get(intent)
            response_text = handler(details) if handler else "Houve um erro no fluxo de confirmação."
        else:
            response_text = "Ok, ação cancelada."
        session.pop('pending_action', None)
    else:
        llm_response, error = llm_processor.process_prompt_with_llm(user_input, session['chat_history'])
        if error:
            log.error(f"Erro da LLM: {error}", extra={"markup": True})
            return jsonify({'response': error})

        session['last_llm_response'] = llm_response
        intent = llm_response.get('intent', 'unknown')
        details = llm_response.get('details', {})
        handler = INTENT_HANDLERS.get(intent, handle_unknown_intent)
        response_text = handler(details)
    
    session['chat_history'].append({'role': 'assistant', 'content': response_text})
    session.modified = True
    
    return jsonify({'response': response_text, 'llm_response': session.get('last_llm_response', {})})

@app.route('/feedback', methods=['POST'])
def feedback():
    """Salva o feedback do usuário em um arquivo."""
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'Corpo da requisição está vazio.'}), 400
    
    # --- CORREÇÃO APLICADA AQUI ---
    # Passa o dicionário 'data' inteiro para a função, como esperado.
    try:
        feedback_manager.save_feedback(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        log.error(f"Erro ao salvar feedback: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    # O comando 'flask run' usa essa configuração por padrão
    # Para rodar com 'python app.py', o debug=True é útil.
    app.run(host='0.0.0.0', port=5001, debug=True)