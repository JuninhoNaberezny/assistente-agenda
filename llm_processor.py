# llm_processor.py

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Carrega as variáveis de ambiente PRIMEIRO.
load_dotenv()

# Tenta configurar a API do Gemini imediatamente após carregar o .env
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada no arquivo .env")
    genai.configure(api_key=api_key) # type: ignore
except (ValueError, Exception) as e:
    print(f"ERRO CRÍTICO ao configurar a API do Gemini: {e}")
    genai = None

from feedback_manager import load_feedback

def get_system_instructions():
    """
    Gera as instruções do sistema com regras reforçadas para a 'explanation'.
    """
    learning_examples = ""
    # ... (a lógica de carregar exemplos de feedback não muda)
    feedback_items = load_feedback()
    if feedback_items:
        # (código de exemplos de aprendizado existente)
        pass

    # --- PROMPT FINAL E MAIS PRECISO ---
    return f"""
Você é 'Alex', um assistente executivo virtual proativo e eficiente.

**SUAS DIRETRIZES CRÍTICAS:**
1.  **ESTRUTURA JSON OBRIGATÓRIA:** Responda em um único objeto JSON com `intent`, `entities` (aninhado) e `explanation`.
2.  **REGRA DA 'EXPLANATION' (A MAIS IMPORTANTE):** O texto no campo `explanation` DEVE ser uma afirmação direta e confiante que corresponda EXATAMENTE à `intent` e às `entities` que você identificou.
    -   **NUNCA** faça uma pergunta na `explanation` se você já tem as informações necessárias para agir (como em `find_event` ou `create_event`).
    -   **Exemplo CORRETO para find_event:** "Ok, estou buscando por 'Arraiá' na sua agenda."
    -   **Exemplo ERRADO:** "Para te ajudar a encontrar o evento 'Arraiá', preciso de mais informações."
    -   **Exemplo CORRETO para create_event:** "Entendido. Agendando a reunião com a equipe para as 10h."
    -   **Exemplo ERRADO:** "Ok, vou agendar. Para quando?" (Esta pergunta só deve ser feita se a data não foi fornecida).
3.  **REGRA DE E-MAIL:** Para `attendees`, inclua APENAS e-mails válidos. Se o usuário mencionar um nome, NÃO o adicione.
4.  **REGRA DE DURAÇÃO:** Para `create_event`, se a duração não for especificada, assuma 1 hora e calcule o `end_time`.

**CONTEXTO ATUAL:** A data de hoje é {datetime.now().strftime('%Y-%m-%d')}.
{learning_examples}

**INTENÇÕES E ENTIDADES:**
-   `create_event`: Criar evento. ENTIDADES: `summary`, `start_time`, `end_time`, `attendees` (apenas e-mails válidos).
-   `find_event`: Encontrar um evento por nome. ENTIDADES: `keywords` (deve ser uma lista de strings).
-   `list_events`: Listar por período. ENTIDADES: `start_date`, `end_date`.
-   `reschedule_or_modify_event`: Cancelar ou reagendar.
-   `clarify_details`: Use esta intenção **APENAS** se for absolutamente impossível determinar a intenção ou as entidades a partir da mensagem do usuário.
-   `unknown`: Para saudações ou pedidos fora do escopo.
"""

def process_user_prompt(chat_history: list) -> dict:
    if not genai:
        return {"intent": "unknown", "entities": {}, "explanation": "Desculpe, estou com um problema de configuração interna e não posso processar seu pedido agora."}

    model = genai.GenerativeModel( # type: ignore
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    generation_config = genai.GenerationConfig(response_mime_type="application/json") # type: ignore
    
    try:
        response = model.generate_content(chat_history, generation_config=generation_config)
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_json)
    except Exception as e:
        print(f"Erro ao decodificar JSON da LLM: {e}")
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma pequena dificuldade em entender. Poderia reformular?"}

