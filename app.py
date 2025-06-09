# app.py (versão com Memória de Conversa)
# Servidor principal da aplicação com Flask

import os
from flask import Flask, request, jsonify, render_template, session
from rich.console import Console
from datetime import datetime
import json

from llm_processor import process_user_prompt
from google_calendar_service import (
    get_calendar_service,
    create_event,
    list_upcoming_events,
    find_and_delete_event
)

app = Flask(__name__)
# SESSIONS REQUIRE A SECRET KEY
app.secret_key = os.urandom(24) 

console = Console()

try:
    console.print("[yellow]Inicializando serviço do Google Calendar...[/yellow]")
    calendar_service = get_calendar_service()
    console.print("[bold green]Serviço do Google Calendar conectado com sucesso![/bold green]")
except Exception as e:
    console.print(f"[bold red]ERRO CRÍTICO: Não foi possível conectar ao Google Calendar.[/bold red]")
    console.print(f"Detalhes: {e}")
    calendar_service = None

@app.route('/')
def index():
    # Limpa o histórico de chat ao recarregar a página
    session.pop('chat_history', None)
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not calendar_service:
        return jsonify({
            "response": "Desculpe, estou com um problema interno e não consigo acessar a agenda no momento."
        }), 500
        
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "Mensagem não encontrada."}), 400

    # --- MELHORIA: GERENCIAMENTO DO HISTÓRICO DA CONVERSA ---
    if 'chat_history' not in session:
        session['chat_history'] = []
    
    # Adiciona a mensagem do usuário ao histórico
    session['chat_history'].append({"role": "user", "parts": [{"text": user_message}]})
    # Garante que o histórico não fique muito longo
    session['chat_history'] = session['chat_history'][-10:] 

    console.print(f"\n[cyan]Usuário:[/cyan] {user_message}")
    
    try:
        # Passa todo o histórico para a LLM
        llm_response = process_user_prompt(session['chat_history'])
        console.print(f"[magenta]LLM Response:[/magenta] {json.dumps(llm_response, indent=2, ensure_ascii=False)}")
        
        intent = llm_response.get("intent")
        entities = llm_response.get("entities", {})
        explanation = llm_response.get("explanation", "Não foi possível processar o pedido.")

    except Exception as e:
        console.print(f"[bold red]Erro ao processar com a LLM:[/bold red] {e}")
        return jsonify({"response": "Desculpe, tive um problema ao entender seu pedido."}), 500

    # Por padrão, a resposta é a explicação da LLM (parte conversacional)
    response_text = explanation
    action_taken = False

    try:
        if intent == "create_event":
            if all(k in entities for k in ["summary", "start_time", "end_time"]):
                event = create_event(
                    calendar_service,
                    summary=entities["summary"],
                    start_time_str=entities["start_time"],
                    end_time_str=entities["end_time"],
                    attendees=entities.get("attendees", []),
                    description=f"Criado a partir de um pedido do assistente."
                )
                response_text = f"{explanation} <a href='{event.get('htmlLink')}' target='_blank'>Pode confirmar o evento aqui.</a>"
                action_taken = True

        elif intent == "list_events":
            events, formatted_date = list_upcoming_events(calendar_service, entities.get("date"))
            if not events:
                response_text = f"Verifiquei sua agenda e parece que você não tem nenhum evento para {formatted_date}."
            else:
                event_list_html = "".join([f"<li>{datetime.fromisoformat(e['start'].get('dateTime', e['start'].get('date')).replace('Z', '+00:00')).astimezone().strftime('%H:%M')} - {e['summary']}</li>" for e in events])
                response_text = f"Com certeza! Para {formatted_date}, seus compromissos são:<br><ul>{event_list_html}</ul>"
            action_taken = True
        
        # ... outras intenções como delete_event podem ser adicionadas aqui

    except Exception as e:
        console.print(f"[bold red]ERRO ao executar a ação do calendário:[/bold red] {e}")
        response_text = "Peço desculpas, mas encontrei um erro ao tentar acessar sua agenda. Pode tentar novamente?"

    # Adiciona a resposta do assistente ao histórico
    session['chat_history'].append({"role": "model", "parts": [{"text": response_text}]})
    
    # Se uma ação concreta foi realizada (criar/listar evento), limpamos o histórico 
    # para iniciar uma nova conversa.
    if action_taken:
        session.pop('chat_history', None)

    console.print(f"[green]Assistente:[/green] {response_text.replace('<br>', ' ').replace('<ul>', '').replace('</ul>', '').replace('<li>', ' - ')}")
    return jsonify({"response": response_text})


if __name__ == '__main__':
    app.run(debug=True, port=5001)