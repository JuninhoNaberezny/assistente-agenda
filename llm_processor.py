# llm_processor.py

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
from rich.console import Console

# Configuração
load_dotenv()
console = Console()
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada no arquivo .env")
    genai.configure(api_key=api_key) # type: ignore
except (ValueError, Exception) as e:
    console.print(f"[bold red]ERRO CRÍTICO ao configurar a API do Gemini: {e}[/bold red]")
    genai = None

def get_system_instructions() -> str:
    """Gera as instruções do sistema com contrato de datas, regras explícitas e exemplos."""
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    start_of_week_dt = today - timedelta(days=today.weekday())
    end_of_week_dt = start_of_week_dt + timedelta(days=6)
    start_of_week_date = start_of_week_dt.strftime('%Y-%m-%d')
    end_of_week_date = end_of_week_dt.strftime('%Y-%m-%d')
    start_of_month_date = today.replace(day=1).strftime('%Y-%m-%d')
    
    # Exemplo de JSON de atualização, corrigido para ser um formato de string válido dentro da f-string
    update_json_example = '{"start_time": "2025-06-12T14:00:00"}'

    return f"""
Você é um assistente de agendamento inteligente e contextual. Sua resposta DEVE ser um único objeto JSON válido.

**CONTRATO DE DATAS E FUSO HORÁRIO (Hoje é {today_date}):**
- "hoje": {today_date}
- "amanhã": {(today + timedelta(days=1)).strftime('%Y-%m-%d')}
- "esta semana": Use o intervalo de {start_of_week_date} a {end_of_week_date}.
- "próxima semana": Use o intervalo de {(start_of_week_dt + timedelta(days=7)).strftime('%Y-%m-%d')} a {(end_of_week_dt + timedelta(days=7)).strftime('%Y-%m-%d')}.
- "este mês": Use o intervalo a partir de {start_of_month_date}.
- FUSO HORÁRIO PADRÃO: `America/Sao_Paulo`. Datas devem ser no formato 'YYYY-MM-DD' e horas em 'YYYY-MM-DDTHH:MM:SS'.

**INTENÇÕES E ENTIDADES:**
- `create_event`: Para criar um novo evento. Entidades: `summary`, `start_time`, `end_time`.
- `list_events`: Para listar eventos. Entidades: `start_date`, `end_date`. `query_keywords` (OPCIONAL) para filtrar.
- `reschedule_or_modify_event`: Para alterar ou cancelar um evento.
    - `actions`: Lista com um objeto contendo:
        - `action`: "update" ou "cancel".
        - `keywords`: Termos do **NOME REAL** do evento para encontrá-lo (ex: ["Reunião", "Claudia"]).
        - `update_fields`: (Apenas para "update") Dicionário com as alterações. Ex: {update_json_example}.
    - **REGRA CRÍTICA:** Se o usuário disser "mude a reunião de amanhã", use o histórico da conversa para descobrir o nome real do evento (ex: "Reunião com Claudia") e usar esse nome nas `keywords`. **NUNCA use termos relativos como "amanhã", "hoje" nas `keywords` de busca.**
- `clarification_needed`: Se o pedido for ambíguo.
- `unknown`: Para qualquer outra coisa.

**EXEMPLO CRÍTICO DE ATUALIZAÇÃO:**
- Histórico: [..., Assistant: "Amanhã você tem: 14:00 - Reunião com Claudia."]
- Usuário: "Mude essa reunião para quinta no mesmo horário."
- JSON: {{ "intent": "reschedule_or_modify_event", "entities": {{ "actions": [{{ "action": "update", "keywords": ["Reunião", "Claudia"], "update_fields": {update_json_example} }}] }}, "explanation": "OK. Movendo a Reunião com Claudia para quinta-feira." }}
"""

def process_user_prompt(chat_history: list) -> dict:
    """Processa o prompt do usuário e retorna um dicionário JSON."""
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, a conexão com a IA não está disponível."}

    try:
        model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest', system_instruction=get_system_instructions()) # type: ignore
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json") # type: ignore
        
        response = model.generate_content(chat_history, generation_config=generation_config)
        
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        console.print(f"[cyan]LLM Raw Response:[/cyan] {cleaned_json}")
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        console.print(f"[bold red]ERRO de Decodificação JSON:[/bold red] {e} | Resposta Bruta: {response.text}")
        return {"intent": "unknown", "entities": {}, "explanation": "Não consegui processar a resposta do meu cérebro digital."}
    except Exception as e:
        console.print(f"[bold red]ERRO INESPERADO na API da LLM:[/bold red] {e}")
        return {"intent": "unknown", "entities": {}, "explanation": "Ocorreu um erro de comunicação com a inteligência artificial."}

