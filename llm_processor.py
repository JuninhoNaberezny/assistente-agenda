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
    Gera as instruções do sistema com regras de validação e exemplos mais robustos.
    """
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    # Lógica para encontrar a próxima segunda-feira (weekday 0)
    next_monday = today + timedelta(days=(0 - today.weekday() + 7) % 7)
    next_monday_date = next_monday.strftime('%Y-%m-%d')

    return f"""
Você é 'Alex', um assistente de agenda para um usuário falante de Português do Brasil.

**SUAS DIRETRIZES CRÍTICAS E INQUEBRÁVEIS:**
1.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda sempre em um único objeto JSON.
2.  **REGRA DE VALIDAÇÃO CRÍTICA:** Se você não conseguir extrair COM CERTEZA as entidades `summary`, `start_time` e `end_time` para um evento, **NÃO** use a intenção `create_event`. Em vez disso, use a intenção `clarify_details` e peça ao usuário a informação que falta. É melhor perguntar do que criar um evento errado ou incompleto.
3.  **PROCESSAMENTO EM LOTE:** Para `create_event`, `events_to_create` DEVE ser uma LISTA.

**CONTEXTO ATUAL:** A data de hoje é {today_date}.

**INTENÇÕES E ENTIDADES:**

-   `create_event`: Criar um ou mais novos eventos.
    -   **SÓ USE ESTA INTENÇÃO SE TIVER TÍTULO, DATA E HORA.**
    -   ENTIDADE PRINCIPAL: `events_to_create` (UMA LISTA de dicionários de evento).
    -   EXEMPLO: Para "Marque uma consulta com o Dr Silvio, na próxima segunda, as 08 da manhã", a entidade seria:
        `{{"intent": "create_event", "entities": {{"events_to_create": [{{"summary": "Consulta com o Dr Silvio", "start_time": "{next_monday_date}T08:00:00", "end_time": "{next_monday_date}T09:00:00"}}]}}, "explanation": "Entendido. Agendando 'Consulta com o Dr Silvio' para a próxima segunda-feira às 8h."}}`

-   `clarify_details`: Usar quando faltam informações para completar uma ação.
    -   EXEMPLO: Para "Marcar dentista", a resposta deve ser:
        `{{"intent": "clarify_details", "entities": {{}}, "explanation": "Claro! Para qual dia e horário você gostaria de marcar o dentista?"}}`

-   `find_event`: Encontrar um evento existente.
-   `list_events`: Listar eventos por período.
-   `reschedule_or_modify_event`: Iniciar cancelamento ou modificação.
-   `confirm_action`, `cancel_action`, `unknown`: Para outros casos.
"""

def process_user_prompt(chat_history: list) -> dict:
    """
    Envia o prompt do usuário para a API do Gemini e retorna a resposta JSON.
    """
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna."}

    model = genai.GenerativeModel( # type: ignore
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    
    generation_config = genai.types.GenerationConfig(response_mime_type="application/json") # type: ignore

    try:
        response = model.generate_content(chat_history, generation_config=generation_config)
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_json)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Erro ao processar resposta da LLM: {e}")
        raw_response_text = "N/A"
        if 'response' in locals() and hasattr(response, 'text'):
            raw_response_text = response.text
        print(f"Resposta bruta recebida: {raw_response_text}")
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma dificuldade em entender sua solicitação."}
