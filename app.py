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
    find_events_by_query, delete_event, update_event, TIMEZONE
)

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
    if not events: return ""
    def get_event_date(event):
        start = event.get('start', {})
        date_str = start.get('dateTime', start.get('date'))
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    sorted_events = sorted(events, key=get_event_date)
    event_items = []
    for e in sorted_events:
        start_dt = get_event_date(e).astimezone()
        event_summary = e.get('summary', 'Evento sem título')
        dia_en = start_dt.strftime('%a')
        dia_pt = dias_semana_map.get(dia_en, dia_en)
        event_items.append(f"<li><b>{start_dt.strftime(f'%d/%m ({dia_pt})')}</b>: {start_dt.strftime('%H:%M')} - {event_summary}</li>")
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
        if intent == "list_events":
            start_date = entities.get("start_date")
            end_date = entities.get("end_date")
            if start_date and end_date:
                events, formatted_range = list_events_in_range(calendar_service, start_date, end_date)
                if not events: response_text = f"Você não tem nenhum evento agendado para {formatted_range}."
                else: response_text = f"Para {formatted_range}, seus compromissos são:<br>{format_event_list(events)}"
            else: response_text = "Não consegui identificar o período de tempo que você pediu."

        elif intent == "create_event":
            # ... (código existente, já validado)
            pass

        elif intent == "reschedule_or_modify_event":
            search_keywords = entities.get("search_keywords")
            update_fields = entities.get("update_fields")
            
            if search_keywords and update_fields:
                query = " ".join(search_keywords)
                found_events = find_events_by_query(calendar_service, query)
                
                if not found_events:
                    response_text = f"Não encontrei o evento '{query}' para editar."
                elif len(found_events) > 1:
                    response_text = "Encontrei mais de um evento com essa descrição. Por favor, seja mais específico."
                else:
                    event_id_to_update = found_events[0]['id']
                    
                    # --- LÓGICA DE TRADUÇÃO PARA A API DO GOOGLE ---
                    formatted_update_body = {}
                    if "location" in update_fields:
                        formatted_update_body['location'] = update_fields['location']
                    if "start_time" in update_fields:
                        formatted_update_body['start'] = {'dateTime': update_fields['start_time'], 'timeZone': TIMEZONE}
                    if "end_time" in update_fields:
                        formatted_update_body['end'] = {'dateTime': update_fields['end_time'], 'timeZone': TIMEZONE}
                    
                    if not formatted_update_body:
                        response_text = "Não entendi o que você quer alterar no evento."
                    else:
                        updated_event = update_event(calendar_service, event_id_to_update, formatted_update_body)
                        if updated_event: response_text = explanation
                        else: response_text = "Desculpe, não consegui atualizar o evento na agenda."
            else: # Lógica de Cancelamento
                # ... (código existente, já validado)
                pass

        # (Outras intenções permanecem as mesmas)

    except Exception as e:
        console.print(f"[bold red]ERRO na ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda."

    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '')}")
    return jsonify({"response": response_text})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5001)
