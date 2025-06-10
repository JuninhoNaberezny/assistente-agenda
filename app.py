# app.py

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
from dateutil import parser # Importa o parser para lidar com datas

# Carregar módulos do projeto
load_dotenv()
from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service, create_event, list_events_in_range,
    find_events_by_query, delete_event, update_event, TIMEZONE
)
from feedback_manager import save_feedback

# Configuração da Aplicação
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a-very-secret-key-for-dev")
console = Console()
logging.basicConfig(level=logging.INFO)

dias_semana_map = { 'Mon': 'seg', 'Tue': 'ter', 'Wed': 'qua', 'Thu': 'qui', 'Fri': 'sex', 'Sat': 'sáb', 'Sun': 'dom' }

try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

def format_event_list(events: list | None) -> str:
    if not events:
        return "Nenhum compromisso encontrado."
    event_items = []
    for event in events:
        start_info = event.get('start', {})
        start_time_str = start_info.get('dateTime', start_info.get('date'))
        if not start_time_str: continue
        try:
            dt_obj = parser.isoparse(start_time_str)
            day_of_week = dias_semana_map.get(dt_obj.strftime('%a'), '')
            formatted_date = dt_obj.strftime('%d/%m')
            formatted_time = dt_obj.strftime('%H:%M') if start_info.get('dateTime') else "Dia todo"
            event_items.append(f"<li><b>{formatted_date} ({day_of_week})</b>: {formatted_time} - {event.get('summary', 'Sem título')}</li>")
        except Exception as e:
             console.print(f"[yellow]Aviso: Ignorando evento com formato de data inválido: {start_time_str}, Erro: {e}[/yellow]")
    return f"<ul>{''.join(event_items)}</ul>"

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
        if not user_prompt: return jsonify({"response": "Recebi uma mensagem vazia."})

        console.print(f"[yellow]Usuário:[/yellow] {user_prompt}")
        if 'chat_history' not in session: session['chat_history'] = []
        session['chat_history'].append({"role": "user", "parts": [{"text": user_prompt}]})
        
        llm_response = process_user_prompt(session['chat_history'])
        session['last_llm_response'] = llm_response
        
        intent = llm_response.get("intent", "unknown")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation") or "Ok, vamos ver..."
        response_text = ""

        if intent == 'create_event':
            if not all(k in entities for k in ["summary", "start_time", "end_time"]):
                response_text = "Para criar um evento, preciso de um título, data e hora de início e fim."
            else:
                event = create_event(calendar_service, entities["summary"], entities["start_time"], entities["end_time"], description=entities.get("description", ""))
                response_text = f"Evento '{event.get('summary')}' criado com sucesso!" if event and event.get('summary') else "Não consegui criar o evento."
        
        elif intent == 'list_events':
            today_str = datetime.now().strftime('%Y-%m-%d')
            start_date = entities.get("start_date", today_str)
            end_date = entities.get("end_date")
            query_keywords = entities.get("query_keywords")
            
            if query_keywords:
                query = " ".join(query_keywords)
                events_list, error_msg = find_events_by_query(calendar_service, query, start_date, end_date)
            else:
                events_list, error_msg = list_events_in_range(calendar_service, start_date, end_date)
            
            if error_msg:
                response_text = f"Desculpe, tive um problema ao buscar sua agenda: {error_msg}"
            else:
                response_text = f"{explanation}<br>{format_event_list(events_list)}"

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
                    event_to_modify = found_events[0]
                    if action_type == "cancel":
                        delete_event(calendar_service, event_to_modify['id'])
                        response_text = f"O evento '{event_to_modify.get('summary', 'Sem título')}' foi cancelado."
                    
                    elif action_type == "update":
                        update_fields = action_detail.get("update_fields", {})
                        if not update_fields:
                            response_text = "Não entendi o que mudar no evento."
                        else:
                            ## CORREÇÃO CRÍTICA: Lógica para calcular duração e montar o corpo da requisição.
                            try:
                                # 1. Calcular a duração do evento original
                                original_start_str = event_to_modify.get('start', {}).get('dateTime')
                                original_end_str = event_to_modify.get('end', {}).get('dateTime')
                                if not original_start_str or not original_end_str:
                                    raise ValueError("Evento original não tem data/hora de início e fim definidos.")
                                
                                original_start_dt = parser.isoparse(original_start_str)
                                original_end_dt = parser.isoparse(original_end_str)
                                duration = original_end_dt - original_start_dt

                                # 2. Calcular a nova data/hora de fim
                                new_start_str = update_fields.get('start_time')
                                if not new_start_str:
                                    raise ValueError("Nenhum novo horário de início foi fornecido.")
                                
                                new_start_dt = parser.isoparse(new_start_str)
                                new_end_dt = new_start_dt + duration

                                # 3. Montar o corpo da requisição no formato correto da API
                                update_body = {
                                    'start': {'dateTime': new_start_dt.isoformat(), 'timeZone': TIMEZONE},
                                    'end': {'dateTime': new_end_dt.isoformat(), 'timeZone': TIMEZONE}
                                }
                                
                                # 4. Chamar a API
                                updated_event = update_event(calendar_service, event_to_modify['id'], update_body)
                                if updated_event and updated_event.get('summary'):
                                    response_text = f"O evento '{updated_event.get('summary')}' foi atualizado com sucesso."
                                else:
                                    response_text = "Falha ao atualizar o evento no Google Calendar."

                            except Exception as e:
                                console.print(f"[bold red]Erro ao processar atualização de evento:[/bold red] {e}")
                                response_text = "Não consegui processar a alteração do evento. Verifique os dados."
        
        elif intent == 'clarification_needed':
            response_text = explanation
        else:
            response_text = explanation

        if not response_text or not response_text.strip():
             response_text = "Desculpe, não consegui processar sua solicitação. Poderia tentar de outra forma?"

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
        if user_prompts: last_user_prompt = user_prompts[-1]
            
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
