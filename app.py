# app.py

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
from dotenv import load_dotenv
import logging

# Carregar módulos do projeto
load_dotenv()
from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service, create_event, list_events_in_range,
    find_events_by_query, delete_event, update_event
)
from feedback_manager import save_feedback

# Configuração da Aplicação
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a-very-secret-key-for-dev")
console = Console()
logging.basicConfig(level=logging.INFO)

# Mapa para traduzir dias da semana
dias_semana_map = { 'Mon': 'seg', 'Tue': 'ter', 'Wed': 'qua', 'Thu': 'qui', 'Fri': 'sex', 'Sat': 'sáb', 'Sun': 'dom' }

# Inicialização do Serviço de Calendário
try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

# --- Funções Utilitárias ---

def format_event_list(events: list | None) -> str:
    """Formata uma lista de eventos do Google Calendar em uma string HTML."""
    if not events:
        return "Nenhum compromisso encontrado."
        
    def get_day_of_week(date_str: str) -> str:
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dias_semana_map.get(date_obj.strftime('%a'), '')
        except:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                return dias_semana_map.get(date_obj.strftime('%a'), '')
            except:
                return ""

    event_items = []
    for event in events:
        start_info = event.get('start', {})
        start_time_str = start_info.get('dateTime', start_info.get('date'))
        
        if not start_time_str:
            continue
            
        try:
            dt_obj = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            formatted_date = dt_obj.strftime('%d/%m')
            day_of_week = get_day_of_week(start_time_str)
            formatted_time = dt_obj.strftime('%H:%M') if start_info.get('dateTime') else "Dia todo"
            event_items.append(f"<li><b>{formatted_date} ({day_of_week})</b>: {formatted_time} - {event.get('summary', 'Sem título')}</li>")
        except Exception as e:
             console.print(f"[yellow]Aviso: Ignorando evento com formato de data inválido: {start_time_str}, Erro: {e}[/yellow]")
             continue
        
    return f"<ul>{''.join(event_items)}</ul>"

# --- ROTAS DA APLICAÇÃO ---

@app.route('/')
def index():
    session.clear()
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not calendar_service:
        return jsonify({"response": "Desculpe, o serviço de agenda não está disponível no momento."}), 503

    try:
        data = request.get_json()
        user_prompt = data.get("message")
        
        if not user_prompt:
            return jsonify({"response": "Recebi uma mensagem vazia."})

        console.print(f"[yellow]Usuário:[/yellow] {user_prompt}")

        if 'chat_history' not in session:
            session['chat_history'] = []
        
        session['chat_history'].append({"role": "user", "parts": [{"text": user_prompt}]})
        
        llm_response = process_user_prompt(session['chat_history'])
        session['last_llm_response'] = llm_response
        
        intent = llm_response.get("intent", "unknown")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation", "Ok, processando...")
        response_text = ""

        if intent == 'create_event':
            if not all(k in entities for k in ["summary", "start_time", "end_time"]):
                response_text = "Para criar um evento, preciso de um título, data e hora de início e fim."
            else:
                event = create_event(calendar_service, entities["summary"], entities["start_time"], entities["end_time"], description=entities.get("description", ""))
                if event and event.get('summary'):
                    response_text = f"Evento '{event.get('summary')}' criado com sucesso!"
                else:
                    response_text = "Não consegui criar o evento."
        
        elif intent == 'list_events':
            today_str = datetime.now().strftime('%Y-%m-%d')
            start_date = entities.get("start_date", today_str)
            end_date = entities.get("end_date") # Pode ser None
            
            ## CORREÇÃO: Lógica que decide entre busca por período ou por palavra-chave.
            query_keywords = entities.get("query_keywords")
            
            if query_keywords:
                # Se houver palavras-chave, usa a função de busca por query.
                query = " ".join(query_keywords)
                events_list, error_msg = find_events_by_query(calendar_service, query, start_date, end_date)
            else:
                # Senão, usa a função de busca por intervalo de datas.
                events_list, error_msg = list_events_in_range(calendar_service, start_date, end_date)
            
            if error_msg:
                response_text = f"Desculpe, tive um problema ao buscar sua agenda: {error_msg}"
            else:
                formatted_list = format_event_list(events_list)
                response_text = f"{explanation}<br>{formatted_list}"

        elif intent == 'reschedule_or_modify_event':
            action_detail = entities.get("actions", [{}])[0]
            action_type = action_detail.get("action")
            query = " ".join(action_detail.get("keywords", []))

            if not query:
                response_text = "Preciso de palavras-chave para encontrar o evento a ser modificado."
            else:
                found_events, error_msg = find_events_by_query(calendar_service, query)
                if error_msg:
                     response_text = f"Desculpe, tive um problema ao pesquisar: {error_msg}"
                elif not found_events:
                    response_text = f"Não encontrei eventos com os termos '{query}'."
                else:
                    # Lógica para modificar o evento encontrado
                    event_to_modify = found_events[0]
                    if action_type == "cancel":
                        delete_event(calendar_service, event_to_modify['id'])
                        response_text = f"O evento '{event_to_modify.get('summary', 'Sem título')}' foi cancelado."
                    elif action_type == "update":
                        update_fields = action_detail.get("update_fields", {})
                        if not update_fields:
                            response_text = "Não entendi o que mudar no evento."
                        else:
                            updated_event = update_event(calendar_service, event_to_modify['id'], update_fields)
                            if updated_event and updated_event.get('summary'):
                                response_text = f"O evento '{updated_event.get('summary')}' foi atualizado com sucesso."
                            else:
                                response_text = "Não foi possível atualizar o evento."
        
        elif intent == 'clarification_needed':
            response_text = explanation
            
        else: # intent == 'unknown'
            response_text = explanation if explanation else "Não entendi. Pode tentar de outra forma?"

        session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
        session.modified = True
        
        console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', ' ').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ')}")
        return jsonify({"response": response_text})

    except Exception as e:
        logging.exception("ERRO INESPERADO NA ROTA /chat:")
        console.print(f"[bold red]ERRO INESPERADO NA ROTA /chat:[/bold red] {e}")
        return jsonify({"response": "Ocorreu um erro inesperado no servidor."}), 500

@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    if not data or "correction" not in data:
        return jsonify({"status": "error", "message": "Requisição inválida."}), 400

    last_user_prompt = "Nenhum prompt de usuário na sessão."
    if session.get('chat_history'):
        user_prompts = [msg['parts'][0]['text'] for msg in session['chat_history'] if msg['role'] == 'user']
        if user_prompts:
            last_user_prompt = user_prompts[-1]
            
    feedback_data = {
        "timestamp": datetime.now().isoformat(),
        "last_user_prompt": last_user_prompt,
        "chat_history": session.get('chat_history', []),
        "incorrect_assistant_response_json": session.get('last_llm_response', {}),
        "user_correction": data.get("correction")
    }
    save_feedback(feedback_data)
    
    return jsonify({"status": "success", "message": "Obrigado pelo seu feedback! Ele me ajuda a aprender."})

if __name__ == '__main__':
    app.run(port=5001, debug=True)
