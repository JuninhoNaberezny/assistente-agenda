# llm_processor.py

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("A chave GEMINI_API_KEY não foi encontrada no arquivo .env")
    genai.configure(api_key=api_key) # type: ignore
except (ValueError, Exception) as e:
    print(f"ERRO CRÍTICO ao configurar a API do Gemini: {e}")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions():
    """
    Gera as instruções do sistema com contrato de datas e exemplo de alteração de horário.
    """
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    next_monday_dt = today + timedelta(days=(0 - today.weekday() + 7) % 7)
    next_monday_date = next_monday_dt.strftime('%Y-%m-%d')
    start_of_week_dt = today - timedelta(days=today.weekday())
    end_of_week_dt = start_of_week_dt + timedelta(days=6)
    start_of_week_date = start_of_week_dt.strftime('%Y-%m-%d')
    end_of_week_date = end_of_week_dt.strftime('%Y-%m-%d')

    return f"""
Você é 'Alex', um assistente de agenda para um usuário falante de Português do Brasil.

**SUAS DIRETRIZES CRÍTICAS E INQUEBRÁVEIS:**
1.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda sempre em um único objeto JSON.
2.  **CONTRATO DA INTENÇÃO `list_events`:** Para esta intenção, você DEVE OBRIGATORIAMENTE retornar as entidades `start_date` e `end_date`.
3.  **REGRA DE VALIDAÇÃO:** Para `create_event`, se não tiver certeza sobre `summary`, `start_time` e `end_time`, use `clarify_details`.
4.  **EDIÇÃO VS. CANCELAMENTO:** A intenção `reschedule_or_modify_event` lida tanto com edição quanto com cancelamento. Diferencie pela presença de `update_fields` (edição) ou `actions` (cancelamento).

**CONTEXTO ATUAL:** A data de hoje é {today_date}.

**INTENÇÕES E ENTIDADES:**

-   `list_events`: Listar eventos por período.
-   `create_event`: Criar um ou mais novos eventos.
-   `find_event`: Encontrar um evento existente.

-   `reschedule_or_modify_event`: Modificar ou cancelar um evento.
    -   **Para Edição de Horário:** Para "Altere o horário da consulta com Dr. Silvio para as 9h", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"search_keywords": ["Consulta", "Dr Silvio"], "update_fields": {{"start_time": "{next_monday_date}T09:00:00", "end_time": "{next_monday_date}T10:00:00"}}}}, "explanation": "Ok. Movendo a consulta com o Dr. Silvio para as 9:00."}}`
    -   **Para Edição de Local:** Para "Adicione o endereço à consulta com Dr. Silvio: Rua X, 123", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"search_keywords": ["Consulta", "Dr Silvio"], "update_fields": {{"location": "Rua X, 123"}}}}, "explanation": "OK. Adicionei o endereço à consulta."}}`
    -   **Para Cancelamento:** Para "Cancele a consulta com Dr. Silvio", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"actions": [{{"action": "cancel", "keywords": ["Consulta", "Dr Silvio"]}}]}}, "explanation": "Ok, buscando a consulta para confirmar o cancelamento."}}`

-   `confirm_action`, `cancel_action`, `clarify_details`, `unknown`: Para outros casos.
"""

def process_user_prompt(chat_history: list) -> dict:
    if not genai: return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna."}
    model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest', system_instruction=get_system_instructions()) # type: ignore
    generation_config = genai.types.GenerationConfig(response_mime_type="application/json") # type: ignore
    try:
        response = model.generate_content(chat_history, generation_config=generation_config)
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_json)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Erro ao processar resposta da LLM: {e}")
        raw_response_text = "N/A"
        if 'response' in locals() and hasattr(response, 'text'): raw_response_text = response.text
        print(f"Resposta bruta recebida: {raw_response_text}")
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma dificuldade em entender sua solicitação."}
