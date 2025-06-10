# llm_processor.py (versão com aprendizado explícito)

import os
import json
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

from feedback_manager import load_feedback

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
except Exception as e:
    print(f"Erro ao configurar a API do Gemini: {e}")

def get_system_instructions():
    """
    Gera as instruções do sistema, injetando a data atual e exemplos de aprendizado
    baseados em feedbacks anteriores de forma mais explícita.
    """
    learning_examples = ""
    feedback_items = load_feedback()

    if feedback_items:
        learning_section = ["\n**APRENDIZADO CONTÍNUO (erros passados e o comportamento esperado):**"]
        for item in feedback_items:
            user_trigger_prompt = "N/A"
            if item.get('chat_history'):
                user_messages = [msg for msg in item['chat_history'] if msg['role'] == 'user']
                if user_messages:
                    user_trigger_prompt = user_messages[-1]['parts'][0]['text']

            incorrect_json = json.dumps(item.get('incorrect_assistant_response', {}))
            user_correction_goal = item.get('user_correction', '')

            example = (
                f"\n- **Exemplo de Erro:**\n"
                f"  - **Quando o usuário disse:** \"{user_trigger_prompt}\"\n"
                f"  - **Você (erradamente) gerou o JSON:** {incorrect_json}\n"
                f"  - **O objetivo correto, descrito pelo usuário, era:** \"{user_correction_goal}\"\n"
                f"  - **Seu Objetivo:** Analise o erro. Da próxima vez que o usuário disser algo parecido com \"{user_trigger_prompt}\", "
                f"gere um JSON que realize a ação \"{user_correction_goal}\"."
            )
            learning_section.append(example)
        learning_examples = "\n".join(learning_section)

    return f"""
Você é 'Alex', um assistente executivo virtual. Sua personalidade é proativa, eficiente e com excelente memória contextual.

**SUAS DIRETRIZES:**
1.  **USE O CONTEXTO AGRESSIVAMENTE:** Sua principal tarefa é entender o pedido do usuário com base no histórico da conversa. Antes de pedir informações, verifique se elas já foram mencionadas.
2.  **SEMPRE RETORNE UMA `explanation`:** Toda resposta JSON DEVE ter uma `explanation` clara e amigável. Se você não tem informação suficiente para preencher as entidades de uma intenção, sua `explanation` DEVE ser uma pergunta para obter os dados que faltam.
3.  **SEMPRE RETORNE UM JSON VÁLIDO.**

**CONTEXTO ATUAL:** A data de hoje é {datetime.now().strftime('%Y-%m-%d')}.
{learning_examples}

**INTENÇÕES E ENTIDADES (formato de saída JSON):**

-   **`create_event`**: Criar novo evento.
    -   ENTIDADES: `summary`, `start_time`, `end_time`, `attendees`, `location`, `conference_solution`.
    -   SE FALTAR ALGO: Pergunte. (Ex: "Ok, para quando devo marcar?")

-   **`list_events`**: Listar compromissos.
    -   ENTIDADES: `start_date`, `end_date`.
    -   SE FALTAR ALGO: Pergunte sobre o período. (Ex: "Claro, para qual período você gostaria de ver os compromissos?").

-   **`reschedule_or_modify_event`**: Cancelar ou reagendar.
    -   ENTIDADES: `source_event_keywords`, `modification` (`action`, `new_summary`, etc.).
    -   SE FALTAR ALGO: Peça detalhes sobre qual evento modificar e para o quê.

-   **`clarify_details`**: Sua intenção quando você precisa fazer uma pergunta para esclarecer um pedido vago.
-   **`unknown`**: Para saudações ou pedidos fora do escopo.
"""

def process_user_prompt(chat_history: list) -> dict:
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash-latest',
        system_instruction=get_system_instructions()
    )
    generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
    try:
        response = model.generate_content(chat_history, generation_config=generation_config)
        cleaned_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(cleaned_json)
    except Exception as e:
        print(f"Erro ao decodificar JSON da LLM: {e}")
        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma pequena dificuldade. Poderia reformular?"}