# llm_processor.py

import os
import json
# CORREÇÃO 1: Importar 'timedelta' junto com 'datetime'
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("A chave GEMINI_API_KEY não foi encontrada no arquivo .env")
    # Adicionado type: ignore para suprimir o aviso do Pylance
    genai.configure(api_key=api_key) # type: ignore
except (ValueError, Exception) as e:
    print(f"ERRO CRÍTICO ao configurar a API do Gemini: {e}")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions():
    """
    Gera as instruções do sistema com raciocínio aprimorado para múltiplas ações.
    """
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    # CORREÇÃO 2: Usar 'timedelta' diretamente após a importação correta
    tomorrow_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    # Lógica para encontrar a próxima sexta-feira
    friday = today + timedelta(days=(4 - today.weekday() + 7) % 7)
    friday_date = friday.strftime('%Y-%m-%d')


    return f"""
Você é 'Alex', um assistente de agenda para um usuário falante de Português do Brasil.

**SUAS DIRETRIZES CRÍTICAS E INQUEBRÁVEIS:**
1.  **IDIOMA:** TODA a sua saída DEVE ser em Português do Brasil.
2.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda em um único objeto JSON com `intent`, `entities`, e `explanation`.
3.  **PROCESSAMENTO EM LOTE (A MAIS IMPORTANTE):** Para a intenção `create_event`, você DEVE ser capaz de processar múltiplos eventos em um único comando. A entidade `events_to_create` deve ser uma LISTA de objetos de evento.
4.  **REGRAS DE ENTIDADES:**
    -   Use a data atual como referência para termos como "hoje", "amanhã", "sexta-feira".
    -   Para `reschedule_or_modify_event`, as `keywords` devem conter apenas substantivos e adjetivos.
    -   Para `create_event`, assuma 1 hora de duração se não for especificado e NUNCA invente e-mails.

**CONTEXTO ATUAL:** A data de hoje é {today_date}.

**INTENÇÕES E ENTIDADES:**

-   `create_event`: Criar um ou mais novos eventos.
    -   ENTIDADE PRINCIPAL: `events_to_create` (UMA LISTA de dicionários de evento).
    -   EXEMPLO: Para "Marque reunião com a Maria amanhã e sexta, das 9h às 10h", a entidade seria:
        `{{"intent": "create_event", "entities": {{"events_to_create": [{{"summary": "Reunião com Maria", "start_time": "{tomorrow_date}T09:00:00", "end_time": "{tomorrow_date}T10:00:00"}}, {{"summary": "Reunião com Maria", "start_time": "{friday_date}T09:00:00", "end_time": "{friday_date}T10:00:00"}}]}}, "explanation": "Ok, agendando as reuniões com a Maria para amanhã e sexta."}}`

-   `reschedule_or_modify_event`: Inicia o processo de cancelamento ou modificação.
    -   ENTIDADES: `actions` (lista), e opcionalmente `start_date` e `end_date`.
    -   EXEMPLO: Para "Cancele minha reunião de sexta", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"actions": [{{"action": "cancel", "keywords": ["reunião"]}}], "start_date": "{friday_date}", "end_date": "{friday_date}"}}, "explanation": "Ok, buscando a(s) reunião(ões) de sexta para confirmar o cancelamento."}}`

-   `confirm_action`: Confirma uma ação pendente.
-   `cancel_action`: Nega uma ação pendente.
-   `list_events`: Listar eventos por período.
-   `clarify_details`, `unknown`: Para outros casos.
"""

def process_user_prompt(chat_history: list) -> dict:
    """
    Envia o prompt do usuário para a API do Gemini e retorna a resposta JSON.
    """
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna."}

    # CORREÇÃO 3: Adicionados 'type: ignore' para suprimir os avisos do Pylance
    model = genai.GenerativeModel( # type: ignore
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    generation_config = genai.GenerationConfig(response_mime_type="application/json") # type: ignore

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
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma dificuldade em entender sua solicitação. Poderia tentar de outra forma?"}
