# llm_processor.py

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("A chave GEMINI_API_KEY não foi encontrada no arquivo .env")
    genai.configure(api_key=api_key)
except (ValueError, Exception) as e:
    print(f"ERRO CRÍTICO ao configurar a API do Gemini: {e}")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions():
    """
    Gera as instruções do sistema com regras reforçadas para extração de entidades.
    """
    # Carregar exemplos de feedback pode ser reativado aqui se necessário
    learning_examples = ""
    today_date = datetime.now().strftime('%Y-%m-%d')

    return f"""
Você é 'Alex', um assistente de agenda para um usuário falante de Português do Brasil.

**SUAS DIRETRIZES CRÍTICAS E INQUEBRÁVEIS:**
1.  **IDIOMA:** TODA a sua saída, especialmente o campo `explanation`, DEVE ser em Português do Brasil.
2.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda em um único objeto JSON com `intent`, `entities`, e `explanation`. Não adicione nenhum texto fora do JSON.
3.  **FLUXO DE AÇÕES COM CONFIRMAÇÃO:** O cancelamento é um processo de duas etapas. Primeiro, use a intenção `reschedule_or_modify_event` para encontrar o evento. Depois, o backend pedirá confirmação, que você deve processar com `confirm_action` ou `cancel_action`.
4.  **REGRA DE ATUALIZAÇÃO:** Use `update_event_details` somente para adicionar informações (como e-mails) a um evento que acabou de ser criado.
5.  **REGRAS DE ENTIDADES (A MAIS IMPORTANTE):**
    -   **Para `list_events` e `reschedule_or_modify_event`:** Você DEVE extrair as entidades `start_date` e `end_date` se o usuário mencionar qualquer referência temporal (como "hoje", "amanhã", "sexta-feira", "semana que vem"). Use a data atual como referência.
    -   **Para `reschedule_or_modify_event`:** As `keywords` na lista de ações devem conter APENAS substantivos e adjetivos que descrevem o evento (ex: "dentista", "trimestral", "reunião", "Cláudio"). NUNCA inclua verbos como "cancelar" ou "desmarcar" nas `keywords`.
    -   **Para `create_event`:** Assuma 1 hora de duração se não for especificado e NUNCA invente e-mails de convidados.

**CONTEXTO ATUAL:** A data de hoje é {today_date}.
{learning_examples}

**INTENÇÕES E ENTIDADES:**

-   `create_event`: Criar um novo evento. Entidades: `summary`, `start_time`, `end_time`, etc.
-   `update_event_details`: Atualizar um evento recém-criado. Entidades: `attendees_to_add`, etc.

-   `reschedule_or_modify_event`: **Inicia** o processo de cancelamento ou modificação.
    -   ENTIDADES: `actions` (lista), e opcionalmente `start_date` e `end_date`.
    -   EXEMPLO 1 (com data): Para "Cancele minha reunião de sexta", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"actions": [{{"action": "cancel", "keywords": ["reunião"]}}], "start_date": "{today_date[:4]}-06-13", "end_date": "{today_date[:4]}-06-13"}}, "explanation": "Ok, buscando a(s) reunião(ões) de sexta para confirmar o cancelamento."}}`
    -   EXEMPLO 2 (sem data): Para "Desmarcar o planejamento trimestral", a entidade seria:
        `{{"intent": "reschedule_or_modify_event", "entities": {{"actions": [{{"action": "cancel", "keywords": ["planejamento", "trimestral"]}}]}}, "explanation": "Ok, buscando o planejamento trimestral para confirmar o cancelamento."}}`

-   `confirm_action`: **Confirma** uma ação pendente (como um cancelamento).
-   `cancel_action`: **Nega** uma ação pendente.
-   `list_events`: Listar eventos por período.
    -   ENTIDADES: `start_date` e `end_date` (OBRIGATÓRIAS).
    -   EXPLANATION: "Verificando sua agenda para o período solicitado."

-   `clarify_details`, `unknown`: Para outros casos.
"""

def process_user_prompt(chat_history: list) -> dict:
    """
    Envia o prompt do usuário para a API do Gemini e retorna a resposta JSON.
    """
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna."}

    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    generation_config = genai.GenerationConfig(response_mime_type="application/json")

    try:
        response = model.generate_content(chat_history, generation_config=generation_config)
        # Limpa qualquer formatação de markdown que a API possa adicionar
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_json)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Erro ao processar resposta da LLM: {e}")
        print(f"Resposta bruta recebida: {response.text if 'response' in locals() else 'N/A'}")
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma dificuldade em entender sua solicitação. Poderia tentar de outra forma?"}
