# llm_processor.py

import os
import json
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

from feedback_manager import load_feedback

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key) # type: ignore
except Exception as e:
    print(f"Erro ao configurar a API do Gemini: {e}")

def get_system_instructions():
    # Esta função não precisa de alterações
    learning_examples = ""
    feedback_items = load_feedback()
    if feedback_items:
        # A lógica de aprendizado existente é mantida
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
Você é 'Alex', um assistente executivo virtual proativo e eficiente.

**SUAS DIRETRIZES:**
1.  **USE O CONTEXTO AGRESSIVAMENTE:** Analise o histórico da conversa para evitar perguntas redundantes.
2.  **ESTRUTURA JSON OBRIGATÓRIA:** Sua resposta DEVE ser um único objeto JSON com `intent`, `entities` (um objeto aninhado) e `explanation`.
3.  **SEJA DIRETO:** Se o usuário pergunta sobre um evento por nome (ex: "Quando é a reunião de projeto?"), use a intenção `find_event` imediatamente. Não peça datas se o nome do evento for suficiente para uma busca.

**EXEMPLO DE FORMATO DE SAÍDA OBRIGATÓRIO:**
```json
{{
  "intent": "find_event",
  "entities": {{
    "keywords": ["reunião", "projeto"]
  }},
  "explanation": "Estou procurando pela 'reunião de projeto' na sua agenda."
}}
```

**CONTEXTO ATUAL:** A data de hoje é {datetime.now().strftime('%Y-%m-%d')}.
{learning_examples}

**INTENÇÕES E SUAS ENTIDADES (para preencher o campo `entities`):**
-   `find_event`: Para encontrar um evento por nome ou palavras-chave. ENTIDADES: `keywords`.
-   `list_events`: Apenas para listar eventos por um período de tempo claro. ENTIDADES: `start_date`, `end_date`.
-   `create_event`: Criar novo evento. ENTIDADES: `summary`, `start_time`, etc.
-   `reschedule_or_modify_event`: Cancelar ou reagendar. ENTIDADES: `source_event_keywords`, `modification`.
-   `clarify_details`: Para pedir mais informações.
-   `unknown`: Para saudações ou pedidos fora do escopo.
"""

def process_user_prompt(chat_history: list) -> dict:
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
        try:
            start = cleaned_json.find('{')
            end = cleaned_json.rfind('}') + 1
            if start != -1 and end != 0:
                return json.loads(cleaned_json[start:end])
        except Exception as inner_e:
            print(f"Falha na tentativa de extração de JSON: {inner_e}")

        return {"intent": "unknown", "entities": {}, "explanation": "Peço desculpas, tive uma pequena dificuldade. Poderia reformular?"}
