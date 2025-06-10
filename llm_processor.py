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
    # Este 'configure' pode dar um aviso no Pylance, mas está funcional. Ignoramos.
    genai.configure(api_key=api_key) # type: ignore
except (ValueError, Exception) as e:
    print(f"ERRO CRÍTICO ao configurar a API do Gemini: {e}")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions():
    """
    Gera as instruções do sistema com exemplos refinados para consistência.
    """
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    # Lógica para encontrar a próxima sexta-feira a partir de hoje
    friday = today + timedelta(days=(4 - today.weekday() + 7) % 7)
    friday_date = friday.strftime('%Y-%m-%d')

    return f"""
Você é 'Alex', um assistente de agenda para um usuário falante de Português do Brasil.

**SUAS DIRETRIZES CRÍTICAS E INQUEBRÁVEIS:**
1.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda sempre em um único objeto JSON.
2.  **REGRAS DE ENTIDADES:**
    -   Para `list_events`, SEMPRE use as chaves `start_date` e `end_date`.
    -   Para `create_event`, `events_to_create` DEVE ser uma LISTA.
    -   Para `find_event`, extraia substantivos e verbos para `keywords`.

**CONTEXTO ATUAL:** A data de hoje é {today_date}.

**INTENÇÕES E ENTIDADES:**

-   `find_event`: Encontrar um evento existente.
    -   EXEMPLO: Para "quando eu tenho que levar a moto pra arrumar?", a entidade seria:
        `{{"intent": "find_event", "entities": {{"keywords": ["levar", "moto", "arrumar"]}}, "explanation": "Vou procurar na sua agenda sobre levar a moto para arrumar."}}`

-   `list_events`: Listar eventos por período.
    -   ENTIDADES: `start_date` e `end_date` (OBRIGATÓRIAS).
    -   EXEMPLO: Para "o que tenho na sexta?", a entidade seria:
        `{{"intent": "list_events", "entities": {{"start_date": "{friday_date}", "end_date": "{friday_date}"}}, "explanation": "Verificando sua agenda para sexta-feira."}}`

-   `create_event`, `reschedule_or_modify_event`, `confirm_action`, `cancel_action`, `clarify_details`, `unknown`: Para outros casos.
"""

def process_user_prompt(chat_history: list) -> dict:
    """
    Envia o prompt do usuário para a API do Gemini e retorna a resposta JSON.
    """
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna."}

    # Usamos 'type: ignore' para suprimir o aviso do Pylance que é um falso positivo.
    model = genai.GenerativeModel( # type: ignore
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    
    # CORREÇÃO DEFINITIVA: Usamos o caminho funcional e ignoramos o aviso do linter.
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
def get_feedback_examples() -> list:
    """
    Carrega exemplos de feedback do arquivo de log.
    
    Returns:
        list: Lista de dicionários com feedbacks.
    """
    feedback_list = load_feedback()
    if not feedback_list:
        return []

    examples = []
    for feedback in feedback_list:
        example = {
            "context": feedback.get("context", ""),
            "incorrect_response": feedback.get("incorrect_response", ""),
            "correction": feedback.get("correction", "")
        }
        examples.append(example)
    
    return examples