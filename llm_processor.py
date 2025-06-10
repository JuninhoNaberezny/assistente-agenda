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
    genai.configure(api_key=api_key)
except (ValueError, Exception) as e:
    console.print(f"[bold red]ERRO CRÍTICO ao configurar a API do Gemini: {e}[/bold red]")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions() -> str:
    """Gera as instruções do sistema com contrato de datas, regras explícitas e exemplos."""
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    start_of_week_dt = today - timedelta(days=today.weekday())
    end_of_week_dt = start_of_week_dt + timedelta(days=6)
    start_of_week_date = start_of_week_dt.strftime('%Y-%m-%d')
    end_of_week_date = end_of_week_dt.strftime('%Y-%m-%d')
    start_of_month_date = today.replace(day=1).strftime('%Y-%m-%d')
    
    feedback_rules = "\n--- REGRAS OBRIGATÓRIAS BASEADAS EM FEEDBACKS ---\n"
    feedback_rules += "1. FUSO HORÁRIO: Sempre assuma o fuso horário 'America/Sao_Paulo' para todas as operações. NUNCA pergunte ao usuário o fuso horário.\n"
    feedback_rules += "2. LISTAR EVENTOS EM PERÍODO: Se o usuário pedir para listar eventos de 'esta semana' ou qualquer outro intervalo de tempo, sua resposta JSON DEVE conter as entidades 'start_date' e 'end_date' com o intervalo completo.\n"
    
    return f"""
Você é um assistente de agendamento inteligente e prestativo. Sua resposta DEVE ser um único objeto JSON válido, sem exceções.

**CONTRATO DE DATAS E FUSO HORÁRIO (Hoje é {today_date}):**
- "hoje": {today_date}
- "amanhã": {(today + timedelta(days=1)).strftime('%Y-%m-%d')}
- "esta semana": Use o intervalo de {start_of_week_date} a {end_of_week_date}.
- "próxima semana": Use o intervalo de {(start_of_week_dt + timedelta(days=7)).strftime('%Y-%m-%d')} a {(end_of_week_dt + timedelta(days=7)).strftime('%Y-%m-%d')}.
- "este mês": Use o intervalo a partir de {start_of_month_date}.
- FUSO HORÁRIO PADRÃO: `America/Sao_Paulo`. Todas as datas e horas devem considerar este fuso.
- Para outros casos, sempre extraia a data no formato `YYYY-MM-DD`.
- Para horários, sempre extraia no formato `HH:MM:SS`.

**INTENÇÕES E ENTIDADES OBRIGATÓRIAS:**
- `create_event`: Para criar um novo evento. Entidades necessárias: `summary`, `start_time`, `end_time`. Opcional: `description`.
- `list_events`: Para listar eventos existentes. Entidades: `start_date`, `end_date`.
    ## MELHORIA: Adicionada entidade opcional para busca por palavras-chave.
    - `query_keywords`: (OPCIONAL) Uma lista de palavras-chave para filtrar a busca de eventos. Use isso quando o usuário perguntar por um evento específico (ex: "reunião com claudia", "arraiá").
- `reschedule_or_modify_event`: Para alterar, reagendar ou cancelar. A entidade `actions` deve ser uma lista contendo um objeto com `action` ("update" ou "cancel"), `keywords` (para encontrar o evento) e `update_fields` (dicionário com as atualizações).
- `clarification_needed`: Use esta intenção se o pedido do usuário for ambíguo ou se faltarem informações cruciais.
- `unknown`: Para qualquer outra coisa.

{feedback_rules}

**EXEMPLOS DE RESPOSTA JSON:**
- Usuário: "Ver meus compromissos da semana."
- JSON: `{{"intent": "list_events", "entities": {{"start_date": "{start_of_week_date}", "end_date": "{end_of_week_date}"}}, "explanation": "Claro, verificando sua agenda para esta semana."}}`
## MELHORIA: Adicionado exemplo de busca por palavra-chave.
- Usuário: "Quando é a reunião com a Claudia?"
- JSON: `{{"intent": "list_events", "entities": {{"query_keywords": ["reunião", "Claudia"], "start_date": "{start_of_month_date}"}}, "explanation": "Deixa eu ver na sua agenda quando é a reunião com a Claudia..."}}`
- Usuário: "Cancele a consulta com Dr. Silvio."
- JSON: `{{"intent": "reschedule_or_modify_event", "entities": {{"actions": [{{"action": "cancel", "keywords": ["Consulta", "Dr Silvio"]}}]}}, "explanation": "Ok, buscando a consulta para cancelar."}}`
"""

def process_user_prompt(chat_history: list) -> dict:
    """Processa o prompt do usuário e retorna um dicionário JSON."""
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, a conexão com a IA não está disponível."}

    try:
        model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest', system_instruction=get_system_instructions())
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
        
        response = model.generate_content(chat_history, generation_config=generation_config)
        
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        console.print(f"[cyan]LLM Raw Response:[/cyan] {cleaned_json}")
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        console.print(f"[bold red]ERRO de Decodificação JSON:[/bold red] {e} | Resposta Bruta: {response.text}")
        return {"intent": "unknown", "entities": {}, "explanation": "Não consegui processar a resposta do meu cérebro digital. Pode tentar de novo?"}
    except Exception as e:
        console.print(f"[bold red]ERRO INESPERADO na API da LLM:[/bold red] {e}")
        return {"intent": "unknown", "entities": {}, "explanation": "Ocorreu um erro de comunicação com a inteligência artificial."}

if __name__ == "__main__":
    # Teste rápido para verificar se o sistema está funcionando
    test_prompt = [{"role": "user", "parts": [{"text": "Quais são meus compromissos esta semana?"}]}]
    response = process_user_prompt(test_prompt)
    console.print(f"[green]Resposta do LLM:[/green] {response}")
    
    # Carrega feedbacks para testes
    feedbacks = load_feedback()
    console.print(f"[blue]Feedbacks carregados:[/blue] {feedbacks}")