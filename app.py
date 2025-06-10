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
        dia_en = start_dt.strftime('%a')
        dia_pt = dias_semana_map.get(dia_en, dia_en)
        formatted_date = start_dt.strftime(f'%d/%m ({dia_pt})')
        formatted_time = start_dt.strftime('%H:%M')
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
        if intent == "create_event":
            events_to_create = entities.get("events_to_create", [])
            if not events_to_create or not isinstance(events_to_create, list):
                response_text = "Não consegui entender os detalhes do evento que você quer criar."
            else:
                created_events, failed_events = [], []
                for event_data in events_to_create:
                    # --- CAMADA DE DEFESA: VALIDAÇÃO DOS DADOS DO LLM ---
                    if not all(k in event_data for k in ("summary", "start_time", "end_time")):
                        console.print(f"[yellow]Validação falhou: LLM não enviou todos os campos necessários. Dados: {event_data}[/yellow]")
                        failed_events.append(event_data)
                        continue # Pula para o próximo evento da lista
                    
                    try:
                        new_event = create_event(service=calendar_service, **event_data)
                        created_events.append(new_event)
                    except Exception as e:
                        failed_events.append(event_data)
                        console.print(f"[bold red]Falha ao criar evento na API do Google: {e}[/bold red]")

                # Constrói a resposta final com base no que deu certo ou errado
                if created_events:
                    response_text = "Tudo certo! Agendei o(s) seguinte(s) compromisso(s):<br>" + format_event_list(created_events)
                else:
                    response_text = "Desculpe, não consegui agendar os compromissos. Faltaram informações essenciais como o título ou a data/hora."
                
                if failed_events and created_events: # Se alguns falharam e outros não
                    response_text += "<br>Alguns itens não puderam ser agendados por falta de informação."

        # (A lógica de outras intenções permanece a mesma)
        elif intent == "find_event":
            keywords = entities.get("keywords", [])
            if not keywords:
                response_text = "Não entendi sobre qual evento você está perguntando."
            else:
                query = " ".join(keywords)
                found_events = find_events_by_query(calendar_service, query)
                if not found_events and len(keywords) > 1:
                    common_verbs = ['falar', 'ver', 'ter', 'levar', 'encontrar', 'conversar', 'arrumar', 'pegar']
                    filtered_keywords = [k for k in keywords if k.lower() not in common_verbs]
                    if filtered_keywords:
                        query = " ".join(filtered_keywords)
                        found_events = find_events_by_query(calendar_service, query)
                if not found_events:
                    response_text = f"Não encontrei nenhum evento na sua agenda sobre '{query}'."
                else:
                    response_text = "Encontrei o(s) seguinte(s) compromisso(s) para você:<br>" + format_event_list(found_events)

    except Exception as e:
        console.print(f"[bold red]ERRO na ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda."

    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '')}")
    return jsonify({"response": response_text})

if __name__ == '__main__':
    # CORREÇÃO DE AMBIENTE: use_reloader=False previne o erro de soquete no Windows.
    # Você precisará parar e reiniciar o servidor manualmente para ver as alterações no código.
    app.run(debug=True, use_reloader=False, port=5001)
