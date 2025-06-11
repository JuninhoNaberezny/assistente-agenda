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
    start_of_week_date = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    end_of_week_date = (today + timedelta(days=6-today.weekday())).strftime('%Y-%m-%d')
    next_week_start = (today + timedelta(days=7-today.weekday())).strftime('%Y-%m-%d')
    next_week_end = (today + timedelta(days=13-today.weekday())).strftime('%Y-%m-%d')
    
    return f"""
Você é um assistente de agendamento que se comunica EXCLUSIVAMENTE através de um único objeto JSON.

**REGRAS DE ESTRUTURA (OBRIGATÓRIO):**
1.  Sua resposta DEVE ser um objeto JSON único e válido.
2.  O JSON DEVE ter SEMPRE as chaves de nível superior: "intent", "entities" e "explanation".
3.  A chave "entities" DEVE ser um objeto, mesmo que esteja vazio.

**DATAS E FUSO HORÁRIO (Hoje é {today_date}):**
-   Fuso Horário Padrão: `America/Sao_Paulo`.
-   "hoje": use `{today_date}`
-   "amanhã": use `{(today + timedelta(days=1)).strftime('%Y-%m-%d')}`
-   "esta semana": use start_date `{start_of_week_date}` e end_date `{end_of_week_date}`.
-   "próxima semana" ou "outra semana": use start_date `{next_week_start}` e end_date `{next_week_end}`.

**INTENÇÕES E SUAS ENTIDADES:**
-   `create_event`: entidades necessárias: `summary`, `start_time`, `end_time`.
-   `list_events`: entidades: `start_date`, `end_date`. `query_keywords` (OPCIONAL) para filtrar.
-   `reschedule_or_modify_event`: entidade `actions` (uma lista) contendo um objeto com `action`, `keywords`, e `update_fields`.
    -   **REGRA DE KEYWORDS:** O campo `keywords` DEVE ser uma **LISTA de strings** contendo o NOME REAL do evento. Ex: `["Reunião", "Claudia"]`.
-   `clarification_needed`: entidade `entities` vazia.
-   `unknown`: entidade `entities` vazia.

**EXEMPLO COMPLETO DE ESTRUTURA PERFEITA:**
-   Usuário: "Modifique o evento Discussão sobre valores para o dia 15"
-   Sua Resposta JSON:
    {{
        "intent": "reschedule_or_modify_event",
        "entities": {{
            "actions": [
                {{
                    "action": "update",
                    "keywords": ["Discussão", "sobre", "valores"],
                    "update_fields": {{
                        "start_time": "2025-06-15T14:00:00"
                    }}
                }}
            ]
        }},
        "explanation": "Ok, o evento 'Discussão sobre valores' foi atualizado."
    }}
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
