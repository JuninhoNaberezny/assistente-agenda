# app.py (versão com lógica de listagem corrigida e sistema de feedback)

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
import json
from dotenv import load_dotenv

from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service,
    create_event,
    list_events_in_range,
    find_event_by_keywords,
    delete_event
)
from feedback_manager import save_feedback

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key-for-dev")

console = Console()

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

@app.route('/chat', methods=['POST'])
def chat():
    if not calendar_service:
        return jsonify({"response": "Desculpe, estou com um problema interno e não consigo acessar a agenda."}), 500
        
    user_message = request.json.get("message")
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

        # --- LÓGICA CORRIGIDA ---
        # Em vez de esperar uma chave "entities", coletamos todas as outras chaves.
        # Isso torna a aplicação robusta ao formato "plano" que a LLM está enviando.
        intent = llm_response.get("intent")
        explanation = llm_response.get("explanation", "Ok, entendi.")
        entities = {k: v for k, v in llm_response.items() if k not in ["intent", "explanation"]}

    except Exception as e:
        console.print(f"[bold red]Erro ao processar com a LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema ao entender seu pedido."}), 500

    response_text = explanation

    try:
        if intent == "create_event":
            if "summary" in entities and "start_time" in entities and "end_time" in entities:
                event = create_event(service=calendar_service, **entities)
                response_text = f"{explanation} <a href='{event.get('htmlLink')}' target='_blank'>Pode confirmar o evento aqui.</a>"
            else:
                response_text = explanation

        elif intent == "list_events":
            if "start_date" in entities and "end_date" in entities:
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
            else:
                response_text = explanation

        elif intent == "reschedule_or_modify_event":
            keywords = entities.get("source_event_keywords")
            modification = entities.get("modification", {})
            if not keywords or not modification:
                 response_text = explanation
            else:
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
                        action = modification.get("action")
                        if action == "cancel":
                            response_text = f"Pronto! O evento '{event_summary}' foi cancelado com sucesso."
                        elif action == "reschedule":
                            new_event_details = {
                                "summary": modification.get("new_summary", event_summary),
                                "start_time": modification.get("new_start_time", source_event['start'].get('dateTime')),
                                "end_time": modification.get("new_end_time", source_event['end'].get('dateTime'))
                            }
                            new_event = create_event(service=calendar_service, **new_event_details)
                            response_text = f"Ok! Cancelei '{event_summary}' e agendei '{new_event_details['summary']}'. <a href='{new_event.get('htmlLink')}' target='_blank'>Confirme aqui.</a>"
        
    except Exception as e:
        console.print(f"[bold red]ERRO ao executar a ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda. Pode tentar novamente?"

    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    session.modified = True
    
    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', ' ').replace('<ul>', '', 1).replace('</ul>', '').replace('<li>', ' - ')}")
    return jsonify({"response": response_text})

@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    
    feedback_data = {
        "timestamp": datetime.now().isoformat(),
        "chat_history": session.get('chat_history', []),
        "incorrect_assistant_response": session.get('last_llm_response', {}),
        "user_correction": data.get("correction")
    }
    
    save_feedback(feedback_data)
    
    console.print(f"[bold yellow]Feedback recebido e salvo:[/bold yellow] {feedback_data}")
    
    # Mantendo a correção anterior de não limpar a sessão
    # session.pop('chat_history', None)
    # session.pop('last_llm_response', None)
    
    return jsonify({"status": "success", "message": "Obrigado pelo seu feedback! Estou sempre aprendendo."})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
