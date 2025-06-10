# app.py

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

load_dotenv()

from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service, create_event, list_events_in_range,
    find_events_by_query, update_event_attendees, delete_event
)
# O feedback_manager não é usado diretamente nesta versão, mas mantemos a importação
from feedback_manager import save_feedback

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key-for-dev")
console = Console()

# Mapa para traduzir dias da semana
dias_semana_map = { 'Mon': 'seg', 'Tue': 'ter', 'Wed': 'qua', 'Thu': 'qui', 'Fri': 'sex', 'Sat': 'sáb', 'Sun': 'dom' }

try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

@app.route('/')
def index():
    session.clear() # Limpa a sessão para um novo começo
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
        start_dt = get_event_date(e).astimezone() # Converte para o fuso horário local
        dia_en = start_dt.strftime('%a')
        dia_pt = dias_semana_map.get(dia_en, dia_en)
        formatted_date = start_dt.strftime(f'%d/%m ({dia_pt})')
        formatted_time = start_dt.strftime('%H:%M')
        event_items.append(f"<li><b>{formatted_date}</b>: {formatted_time} - {e.get('summary', 'Evento sem título')}</li>")
    return f"<ul>{''.join(event_items)}</ul>"

@app.route('/chat', methods=['POST'])
def chat():
    # Validações iniciais
    if not request.json: return jsonify({"response": "Erro: requisição sem JSON."}), 400
    if not calendar_service: return jsonify({"response": "Desculpe, estou com um problema de conexão com a agenda."}), 500
    user_message = request.json.get("message")
    if not user_message: return jsonify({"response": "Erro: 'message' não encontrada na requisição."}), 400
    
    # Gerencia o histórico da conversa na sessão
    if 'chat_history' not in session: session['chat_history'] = []
    session['chat_history'].append({"role": "user", "parts": [{"text": user_message}]})
    session.modified = True
    console.print(f"\n[cyan]Usuário:[/cyan] {user_message}")
    
    try:
        # Processa a mensagem do usuário com o LLM
        llm_response = process_user_prompt(session['chat_history'])
        console.print(f"[magenta]LLM Response JSON:[/magenta] {json.dumps(llm_response, indent=2, ensure_ascii=False)}")
        intent = llm_response.get("intent")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation", "Ok, entendi.")
        
        # Limpa ações pendentes se a nova intenção não for de confirmação/cancelamento
        if intent not in ['confirm_action', 'cancel_action', 'update_event_details', 'clarify_details']:
            session.pop('pending_action', None)

    except Exception as e:
        console.print(f"[bold red]Erro na chamada ou processamento do LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema para entender sua solicitação."}), 500

    response_text = explanation
    
    try:
        # --- LÓGICA DE INTENÇÕES APRIMORADA ---

        if intent == "reschedule_or_modify_event":
            actions = entities.get("actions", [])
            if not actions:
                response_text = "Não entendi qual ação você deseja realizar. Poderia especificar?"
            else:
                action_item = actions[0] # Simplificando para uma ação por vez
                if action_item.get("action") == "cancel":
                    keywords = action_item.get("keywords", [])
                    query = " ".join(keywords)
                    
                    # Usa as datas extraídas pelo LLM para uma busca mais precisa
                    start_date = entities.get("start_date")
                    end_date = entities.get("end_date")

                    found_events = find_events_by_query(calendar_service, query, start_date, end_date)

                    if not found_events:
                        response_text = "Não encontrei nenhum evento que corresponda à sua descrição para cancelar."
                    elif len(found_events) == 1:
                        # Caso único: Pede confirmação direta
                        event = found_events[0]
                        session['pending_action'] = [{'action': 'delete', 'event_id': event['id'], 'summary': event['summary']}]
                        event_list_html = format_event_list(found_events)
                        response_text = f"Encontrei o seguinte evento:<br>{event_list_html}Posso prosseguir com o cancelamento?"
                    else:
                        # Caso de ambiguidade: Lista os eventos e pede para o usuário escolher
                        session['pending_action'] = [{'action': 'delete', 'event_id': evt['id'], 'summary': evt['summary']} for evt in found_events]
                        event_list_html = format_event_list(found_events)
                        response_text = f"Encontrei mais de um evento que corresponde à sua descrição. Qual deles você gostaria de cancelar?<br>{event_list_html}Você pode dizer, por exemplo, 'cancele o das 15h' ou 'o com Cláudio'."
                    session.modified = True

        elif intent == "confirm_action":
            pending_actions = session.get('pending_action')
            if not pending_actions:
                response_text = "Não há nenhuma ação pendente para confirmar."
            else:
                # Por enquanto, cancela todas as ações pendentes.
                # Melhoria futura: permitir que o usuário especifique qual cancelar.
                results = []
                for action in pending_actions:
                    if action.get('action') == 'delete':
                        success = delete_event(calendar_service, action['event_id'])
                        if success: results.append(f"Evento '{action['summary']}' cancelado com sucesso.")
                        else: results.append(f"Falha ao cancelar o evento '{action['summary']}'.")
                response_text = "<br>".join(results)
                session.pop('pending_action', None)

        elif intent == "cancel_action":
            session.pop('pending_action', None)
            response_text = "Ok, a ação foi cancelada."

        elif intent == "list_events":
            if "start_date" in entities and "end_date" in entities:
                events, formatted_range = list_events_in_range(calendar_service, entities["start_date"], entities["end_date"])
                if not events:
                    response_text = f"Você não tem nenhum evento agendado para {formatted_range}."
                else:
                    response_text = f"Para {formatted_range}, seus compromissos são:<br>{format_event_list(events)}"
            else:
                response_text = explanation # Fallback caso a LLM falhe em extrair datas

        # Outras intenções (create_event, etc.) podem ser adicionadas aqui

    except Exception as e:
        console.print(f"[bold red]ERRO na execução da ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda."

    # Adiciona a resposta do assistente ao histórico e retorna para o front-end
    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '')}")
    return jsonify({"response": response_text})

# Rota de feedback (opcional, mas bom ter)
@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    save_feedback({
        "timestamp": datetime.now().isoformat(),
        "chat_history": session.get('chat_history', []),
        "user_correction": data.get('correction')
    })
    return jsonify({"message": "Obrigado pelo seu feedback! Isso me ajuda a aprender."})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
