# app.py

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
import json
from dotenv import load_dotenv

# CORREÇÃO: Garante que todas as importações necessárias estão aqui
from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service,
    create_event,
    list_events_in_range,
    find_events_by_query,
    find_event_by_keywords,
    delete_event
)
from feedback_manager import save_feedback

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key-for-dev")
console = Console()

dias_semana_map = {
    'Mon': 'seg', 'Tue': 'ter', 'Wed': 'qua',
    'Thu': 'qui', 'Fri': 'sex', 'Sat': 'sáb', 'Sun': 'dom'
}

try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

# ... (funções index e format_event_list continuam as mesmas)
@app.route('/')
def index():
    session.clear()
    return render_template('index.html')

def format_event_list(events):
    if not events: return ""
    def get_event_date(event):
        return datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00')).astimezone()
    sorted_events = sorted(events, key=get_event_date)
    event_items = []
    for e in sorted_events:
        start_dt = get_event_date(e)
        dia_en = start_dt.strftime('%a')
        dia_pt = dias_semana_map.get(dia_en, dia_en)
        formatted_date = start_dt.strftime(f'%d/%m ({dia_pt})')
        formatted_time = start_dt.strftime('%H:%M')
        event_items.append(f"<li><b>{formatted_date}</b>: {formatted_time} - {e['summary']}</li>")
    return f"<ul>{''.join(event_items)}</ul>"

@app.route('/chat', methods=['POST'])
def chat():
    # CORREÇÃO: Adicionada verificação para garantir que request.json não é None
    if not request.json:
        return jsonify({"response": "Erro: a requisição não contém dados JSON."}), 400

    if not calendar_service:
        return jsonify({"response": "Desculpe, estou com um problema interno e não consigo acessar a agenda."}), 500
    
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"response": "Erro: a chave 'message' não foi encontrada no JSON."}), 400

    if 'chat_history' not in session:
        session['chat_history'] = []
    session['chat_history'].append({"role": "user", "parts": [{"text": user_message}]})
    session.modified = True
    console.print(f"\n[cyan]Usuário:[/cyan] {user_message}")
    
    try:
        llm_response = process_user_prompt(session['chat_history'])
        console.print(f"[magenta]LLM Response JSON:[/magenta] {json.dumps(llm_response, indent=2, ensure_ascii=False)}")
        session['last_llm_response'] = llm_response
        session.modified = True
        intent = llm_response.get("intent")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation", "Ok, entendi.")
    except Exception as e:
        console.print(f"[bold red]Erro ao processar com a LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema ao entender seu pedido."}), 500

    response_text = explanation
    
    try:
        if intent == "find_event":
            keywords = entities.get("keywords")
            if not keywords:
                response_text = "Por favor, diga o nome do evento que você está procurando."
            else:
                query_string = " ".join(keywords)
                events = find_events_by_query(calendar_service, query_string)
                if not events:
                    response_text = f"Não encontrei nenhum evento relacionado a '{query_string}' na sua agenda."
                elif len(events) == 1:
                    response_text = f"Encontrei este evento correspondente:<br>{format_event_list(events)}"
                else:
                    response_text = f"Encontrei múltiplos eventos para '{query_string}':<br>{format_event_list(events)}"
        elif intent == "list_events":
            if "start_date" in entities and "end_date" in entities:
                events, formatted_range = list_events_in_range(calendar_service, entities["start_date"], entities["end_date"])
                if not events:
                    response_text = f"Verifiquei sua agenda e parece que você não tem nenhum evento para {formatted_range}."
                else:
                    response_text = f"Com certeza! Para {formatted_range}, seus compromissos são:<br>{format_event_list(events)}"
            else:
                response_text = explanation

    except Exception as e:
        console.print(f"[bold red]ERRO ao executar a ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda. Pode tentar novamente?"

    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', ' ').replace('<ul>', '', 1).replace('</ul>', '').replace('<li>', ' - ')}")
    return jsonify({"response": response_text})

@app.route('/feedback', methods=['POST'])
def feedback():
    # CORREÇÃO: Adicionada verificação para garantir que request.json não é None
    if not request.json:
        return jsonify({"status": "error", "message": "Requisição sem JSON."}), 400

    data = request.json
    feedback_data = {
        "timestamp": datetime.now().isoformat(),
        "chat_history": session.get('chat_history', []),
        "incorrect_assistant_response": session.get('last_llm_response', {}),
        "user_correction": data.get("correction")
    }
    save_feedback(feedback_data)
    console.print(f"[bold yellow]Feedback recebido e salvo:[/bold yellow] {feedback_data}")
    return jsonify({"status": "success", "message": "Obrigado pelo seu feedback! Estou sempre aprendendo."})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
