# app.py

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
import json
from dotenv import load_dotenv

load_dotenv()

from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service, create_event, list_events_in_range,
    find_events_by_query, delete_event
)
from feedback_manager import save_feedback

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key-for-dev")
console = Console()

dias_semana_map = { 'Mon': 'seg', 'Tue': 'ter', 'Wed': 'qua', 'Thu': 'qui', 'Fri': 'sex', 'Sat': 'sáb', 'Sun': 'dom' }

try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

@app.route('/')
def index():
    session.clear()
    return render_template('index.html')

def format_event_list(events):
    """Formata uma lista de eventos em HTML para exibição no chat."""
    if not events: return ""
    
    def get_event_date(event):
        start = event.get('start', {})
        date_str = start.get('dateTime', start.get('date'))
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

    sorted_events = sorted(events, key=get_event_date)
    event_items = []
    for e in sorted_events:
        start_dt = get_event_date(e).astimezone()
        dia_en = start_dt.strftime('%a')
        dia_pt = dias_semana_map.get(dia_en, dia_en)
        formatted_date = start_dt.strftime(f'%d/%m ({dia_pt})')
        formatted_time = start_dt.strftime('%H:%M')
        # Adiciona o ID do evento para futura referência, se necessário
        event_summary = e.get('summary', 'Evento sem título')
        event_items.append(f"<li><b>{formatted_date}</b>: {formatted_time} - {event_summary}</li>")
    return f"<ul>{''.join(event_items)}</ul>"

@app.route('/chat', methods=['POST'])
def chat():
    if not request.json or "message" not in request.json: return jsonify({"response": "Requisição inválida."}), 400
    if not calendar_service: return jsonify({"response": "Problema interno de conexão com a agenda."}), 500
    
    user_message = request.json.get("message")
    if 'chat_history' not in session: session['chat_history'] = []
    session['chat_history'].append({"role": "user", "parts": [{"text": user_message}]})
    session.modified = True
    console.print(f"\n[cyan]Usuário:[/cyan] {user_message}")
    
    try:
        llm_response = process_user_prompt(session['chat_history'])
        console.print(f"[magenta]LLM Response JSON:[/magenta] {json.dumps(llm_response, indent=2, ensure_ascii=False)}")
        intent = llm_response.get("intent")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation", "Ok, entendi.")
        
        if intent not in ['confirm_action', 'cancel_action', 'clarify_details']:
            session.pop('pending_action', None)

    except Exception as e:
        console.print(f"[bold red]Erro no LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema para entender."}), 500

    response_text = explanation
    
    try:
        # --- LÓGICA DE INTENÇÕES COM SUPORTE A MÚLTIPLOS EVENTOS ---
        
        if intent == "create_event":
            events_to_create = entities.get("events_to_create", [])
            if not events_to_create or not isinstance(events_to_create, list):
                response_text = "Não consegui entender os detalhes do evento que você quer criar. Poderia tentar novamente?"
            else:
                created_events = []
                failed_events = []
                for event_data in events_to_create:
                    try:
                        new_event = create_event(
                            service=calendar_service,
                            summary=event_data.get("summary", "Evento"),
                            start_time=event_data.get("start_time"),
                            end_time=event_data.get("end_time"),
                            attendees=event_data.get("attendees", [])
                        )
                        created_events.append(new_event)
                    except Exception as e:
                        console.print(f"[bold red]Falha ao criar um evento: {event_data}[/bold red]\nError: {e}")
                        failed_events.append(event_data)
                
                # Constrói a resposta final
                if created_events:
                    response_text = "Tudo certo! Agendei o(s) seguinte(s) compromisso(s) para você:<br>" + format_event_list(created_events)
                else:
                    response_text = "Desculpe, não consegui agendar os compromissos solicitados."
                if failed_events:
                    response_text += "<br>Não foi possível agendar alguns itens. Por favor, verifique os detalhes."


        elif intent == "reschedule_or_modify_event":
            # (Esta lógica permanece a mesma da versão anterior, já está robusta)
            actions = entities.get("actions", [])
            action_item = actions[0] if actions else {}
            if action_item.get("action") == "cancel":
                keywords = action_item.get("keywords", [])
                query = " ".join(keywords)
                start_date = entities.get("start_date")
                end_date = entities.get("end_date")
                found_events = find_events_by_query(calendar_service, query, start_date, end_date)

                if not found_events:
                    response_text = "Não encontrei nenhum evento que corresponda à sua descrição para cancelar."
                elif len(found_events) == 1:
                    event = found_events[0]
                    session['pending_action'] = [{'action': 'delete', 'event_id': event['id'], 'summary': event['summary']}]
                    response_text = f"Encontrei o seguinte evento:<br>{format_event_list(found_events)}Posso prosseguir com o cancelamento?"
                else:
                    session['pending_action'] = [{'action': 'delete', 'event_id': evt['id'], 'summary': evt['summary']} for evt in found_events]
                    response_text = f"Encontrei mais de um evento. Qual deles você gostaria de cancelar?<br>{format_event_list(found_events)}"
                session.modified = True

        elif intent == "confirm_action":
            pending_actions = session.get('pending_action')
            if not pending_actions:
                response_text = "Não há nenhuma ação pendente para confirmar."
            else:
                results = []
                for action in pending_actions:
                    if action.get('action') == 'delete':
                        success = delete_event(calendar_service, action['event_id'])
                        if success: results.append(f"Evento '{action['summary']}' cancelado.")
                        else: results.append(f"Falha ao cancelar '{action['summary']}'.")
                response_text = "<br>".join(results)
                session.pop('pending_action', None)

        elif intent == "cancel_action":
            session.pop('pending_action', None)
            response_text = "Ok, a ação foi cancelada."

        elif intent == "list_events":
            events, formatted_range = list_events_in_range(calendar_service, entities.get("start_date"), entities.get("end_date"))
            if not events:
                response_text = f"Você não tem nenhum evento agendado para {formatted_range}."
            else:
                response_text = f"Para {formatted_range}, seus compromissos são:<br>{format_event_list(events)}"

    except Exception as e:
        console.print(f"[bold red]ERRO na ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda."

    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '')}")
    return jsonify({"response": response_text})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
