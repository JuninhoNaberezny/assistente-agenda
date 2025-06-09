# app.py (versão com orquestração de Google Meet)

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
import json

from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service,
    create_event,
    list_events_in_range,
    find_event_by_keywords,
    delete_event
)

app = Flask(__name__)
app.secret_key = os.urandom(24) 

console = Console()

try:
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar: {e}[/bold red]")
    calendar_service = None

@app.route('/')
def index():
    session.pop('chat_history', None)
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not calendar_service:
        return jsonify({"response": "Desculpe, estou com um problema interno e não consigo acessar a agenda."}), 500
        
    user_message = request.json.get("message")
    if 'chat_history' not in session:
        session['chat_history'] = []
    
    # Adiciona a mensagem atual ao histórico ANTES de enviar para a LLM
    session['chat_history'].append({"role": "user", "parts": [{"text": user_message}]})
    session['chat_history'] = session['chat_history'][-10:] # Mantém o histórico com um tamanho razoável

    console.print(f"\n[cyan]Usuário:[/cyan] {user_message}")
    
    try:
        # Passa o histórico da sessão para a LLM
        llm_response = process_user_prompt(session['chat_history'])
        console.print(f"[magenta]LLM Response:[/magenta] {json.dumps(llm_response, indent=2, ensure_ascii=False)}")
        
        intent = llm_response.get("intent")
        entities = llm_response.get("entities", {})
        # Garante que a explanation sempre tenha um valor
        explanation = llm_response.get("explanation", "Ok, entendi.")

    except Exception as e:
        console.print(f"[bold red]Erro ao processar com a LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema ao entender seu pedido."}), 500

    response_text = explanation
    action_taken = False

    try:
        if intent == "create_event":
            # Passa as entidades diretamente para a função de criação
            if "summary" in entities and "start_time" in entities and "end_time" in entities:
                event = create_event(calendar_service, **entities)
                response_text = f"{explanation} <a href='{event.get('htmlLink')}' target='_blank'>Pode confirmar o evento aqui.</a>"
                action_taken = True
            else:
                # Se faltar algo, a própria LLM deve ter pedido para esclarecer
                response_text = explanation


        elif intent == "list_events":
            start_date = entities.get("start_date")
            end_date = entities.get("end_date")
            
            events, formatted_range = list_events_in_range(calendar_service, start_date, end_date)
            
            if not events:
                response_text = f"Verifiquei sua agenda e parece que você não tem nenhum evento para {formatted_range}."
            else:
                event_list_html = "".join([
                    f"<li><b>{datetime.fromisoformat(e['start'].get('dateTime', e['start'].get('date')).replace('Z', '+00:00')).astimezone().strftime('%d/%m (%a)')}</b>: {datetime.fromisoformat(e['start'].get('dateTime', e['start'].get('date')).replace('Z', '+00:00')).astimezone().strftime('%H:%M')} - {e['summary']}</li>"
                    for e in events
                ])
                response_text = f"Com certeza! Para {formatted_range}, seus compromissos são:<br><ul>{event_list_html}</ul>"
            # Não consideramos 'listar' uma ação que limpa o histórico, para manter o contexto
            action_taken = False

        elif intent == "reschedule_or_modify_event":
            keywords = entities.get("source_event_keywords")
            modification = entities.get("modification", {})
            action = modification.get("action")
            
            source_event = find_event_by_keywords(calendar_service, keywords)
            
            if not source_event:
                response_text = f"Desculpe, não consegui encontrar um evento com os detalhes '{' '.join(keywords)}' na sua agenda para modificar."
            else:
                event_id = source_event['id']
                event_summary = source_event['summary']
                
                delete_success = delete_event(calendar_service, event_id)
                
                if not delete_success:
                    response_text = "Encontrei o evento, mas tive um problema ao tentar cancelá-lo."
                else:
                    if action == "cancel":
                        response_text = f"Pronto! O evento '{event_summary}' foi cancelado com sucesso."
                    elif action == "reschedule":
                        # Usa os detalhes do evento antigo como base
                        new_summary = modification.get("new_summary", event_summary)
                        start_time = modification.get("new_start_time", source_event['start'].get('dateTime'))
                        end_time = modification.get("new_end_time", source_event['end'].get('dateTime'))

                        new_event = create_event(calendar_service, new_summary, start_time, end_time)
                        response_text = f"Ok! Cancelei '{event_summary}' e agendei '{new_summary}'. <a href='{new_event.get('htmlLink')}' target='_blank'>Confirme aqui.</a>"
            action_taken = True
        
    except Exception as e:
        console.print(f"[bold red]ERRO ao executar a ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda. Pode tentar novamente?"

    # Adiciona a resposta do assistente ao histórico
    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    
    # Limpa o histórico apenas se uma ação definitiva (criar/cancelar) foi tomada
    if action_taken:
        session.pop('chat_history', None)

    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', ' ').replace('<ul>', '', 1).replace('</ul>', '').replace('<li>', ' - ')}")
    return jsonify({"response": response_text})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
