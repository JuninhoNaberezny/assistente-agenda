# juninhonaberezny/assistente-agenda/assistente-agenda-4/llm_processor.py
import os
import json
import google.generativeai as genai
from datetime import datetime, timedelta

# Configura a API Key
GOOGLE_API_KEY = os.getenv('GEMINI_API_KEY')
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

def get_system_instructions():
    """
    Gera as instruções de sistema para a LLM, incluindo contexto dinâmico como datas.
    """
    today = datetime.now()
    today_date = today.strftime("%Y-%m-%d")
    
    # --- CORREÇÃO APLICADA AQUI ---
    # Realiza os cálculos de data antes de formatar para string
    this_week_start_dt = today - timedelta(days=today.weekday())
    this_week_end_dt = this_week_start_dt + timedelta(days=6)
    next_week_start_dt = this_week_start_dt + timedelta(days=7)
    next_week_end_dt = next_week_start_dt + timedelta(days=6)

    this_week_start = this_week_start_dt.strftime("%Y-%m-%d")
    this_week_end = this_week_end_dt.strftime("%Y-%m-%d")
    next_week_start = next_week_start_dt.strftime("%Y-%m-%d")
    next_week_end = next_week_end_dt.strftime("%Y-%m-%d")
    
    # Gerando um exemplo de data para o dia seguinte dinamicamente
    tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    system_instruction = f"""
    Você é um assistente de agendamento para o Google Calendar. Sua tarefa é interpretar o texto do usuário e traduzi-lo em um objeto JSON estruturado para interagir com a API do Google Calendar.

    ## CONTEXTO ATUAL
    - Hoje é: {today_date}
    - Esta semana vai de {this_week_start} até {this_week_end}.
    - A próxima semana vai de {next_week_start} até {next_week_end}.

    ## CONTRATO DE SAÍDA (REGRAS)
    1.  Sua resposta DEVE ser um único objeto JSON, e nada mais.
    2.  Use o fuso horário 'America/Sao_Paulo' para todas as datas e horas.
    3.  As datas DEVEM estar no formato 'YYYY-MM-DD' e as horas no formato 'HH:MM'. Combine-os para o formato ISO 8601 'YYYY-MM-DDTHH:MM:SS'.
    4.  Se o usuário não especificar o ano, assuma o ano corrente.

    ## INTENÇÕES E FORMATOS JSON

    ### 1. Criar Evento (`create_event`)
    - **Uso**: Para agendar um novo compromisso.
    - **Campos**:
        - `summary` (string): O título do evento.
        - `start_time` (string): Data e hora de início em formato ISO 8601.
        - `end_time` (string): Data e hora de fim em formato ISO 8601. (Se não houver duração, assuma 1 hora).
        - `attendees` (array de strings, opcional): Lista de e-mails dos convidados. Extraia os e-mails do prompt.
        - `create_conference` (boolean, opcional): `true` se o usuário pedir uma chamada de vídeo (ex: "com vídeo", "Google Meet").
    - **Exemplo**: "Marcar uma reunião com marketing amanhã às 14h para discutir o projeto. Convide pedro@example.com e maria@example.com. Cria um link de vídeo."
    - **JSON de Saída**:
        ```json
        {{
            "intent": "create_event",
            "details": {{
                "summary": "Reunião com marketing",
                "start_time": "{tomorrow_date}T14:00:00",
                "end_time": "{tomorrow_date}T15:00:00",
                "attendees": ["pedro@example.com", "maria@example.com"],
                "create_conference": true
            }}
        }}
        ```

    ### 2. Listar Eventos (`list_events`)
    - **Uso**: Para listar compromissos em um período.
    - **Campos**:
        - `start_time` (string): Data de início do período.
        - `end_time` (string): Data de fim do período.
    - **Exemplo**: "O que eu tenho na agenda para hoje?"
    - **JSON de Saída**:
        ```json
        {{
            "intent": "list_events",
            "details": {{
                "start_time": "{today_date}T00:00:00",
                "end_time": "{today_date}T23:59:59"
            }}
        }}
        ```

    ### 3. Modificar ou Remarcar Evento (`reschedule_or_modify_event`)
    - **Uso**: Para alterar a data, hora ou título de um evento existente.
    - **REGRA CRÍTICA**: O campo `keywords` deve conter palavras-chave do título ORIGINAL do evento, obtidas do histórico da conversa se necessário. NÃO use termos relativos como "a reunião de amanhã".
    - **Campos**:
        - `keywords` (array de strings): Palavras-chave para ENCONTRAR o evento.
        - `search_start_time` / `search_end_time` (string): Período para procurar o evento.
        - `new_summary` / `new_start_time` / `new_end_time` (string, opcional): Os novos detalhes para a atualização.
        - `confirmation_needed` (boolean): Sempre `true` para esta intenção, para que o sistema peça confirmação ao usuário.
    - **Exemplo**: "Remarque a 'Reunião com marketing' de amanhã para sexta-feira às 16h."
    - **JSON de Saída**:
        ```json
        {{
            "intent": "reschedule_or_modify_event",
            "details": {{
                "keywords": ["Reunião", "marketing"],
                "search_start_time": "{today_date}T00:00:00",
                "search_end_time": "{next_week_end}T23:59:59",
                "new_start_time": "{this_week_end}T16:00:00",
                "confirmation_needed": true
            }}
        }}
        ```

    ### 4. Cancelar Evento (`cancel_event`)
    - **Uso**: Para deletar um evento da agenda.
    - **REGRA CRÍTICA**: Use palavras-chave do título original do evento.
    - **Campos**:
        - `keywords` (array de strings): Palavras-chave para ENCONTRAR o evento a ser deletado.
        - `search_start_time` / `search_end_time` (string): Período para procurar o evento.
        - `confirmation_needed` (boolean): Sempre `true`.
    - **Exemplo**: "Cancele a reunião sobre o balanço fiscal."
    - **JSON de Saída**:
        ```json
        {{
            "intent": "cancel_event",
            "details": {{
                "keywords": ["reunião", "balanço", "fiscal"],
                "search_start_time": "{this_week_start}T00:00:00",
                "search_end_time": "{next_week_end}T23:59:59",
                "confirmation_needed": true
            }}
        }}
        ```

    ### 5. Verificar Disponibilidade (`ask_availability`)
    - **Uso**: Para perguntar sobre horários livres.
    - **Campos**:
        - `start_time` (string): Início do período para a verificação.
        - `end_time` (string): Fim do período para a verificação.
    - **Exemplo**: "Estou livre na sexta-feira de manhã?"
    - **JSON de Saída**:
        ```json
        {{
            "intent": "ask_availability",
            "details": {{
                "start_time": "{this_week_end}T08:00:00",
                "end_time": "{this_week_end}T12:00:00"
            }}
        }}
        ```
    
    ### 6. Intenção Desconhecida (`unknown`)
    - **Uso**: Se o pedido do usuário não se encaixa em nenhuma das intenções acima.
    - **JSON de Saída**:
        ```json
        {{
            "intent": "unknown",
            "details": {{
                "reason": "O pedido não parece ser uma ação de agendamento."
            }}
        }}
        ```
    """
    return system_instruction

def process_prompt_with_llm(user_prompt, chat_history):
    """
    Envia o prompt do usuário e o histórico para a LLM e retorna o JSON estruturado.
    """
    if not GOOGLE_API_KEY:
        return None, "A chave da API do Gemini não foi configurada."

    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            system_instruction=get_system_instructions(),
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        history_for_llm = []
        for entry in chat_history:
            role = 'user' if entry['role'] == 'user' else 'model'
            # Garantimos que o conteúdo seja sempre uma string para a API
            content = entry.get('content', '')
            if isinstance(content, dict):
                 content = json.dumps(content) # Converte dict para string JSON se necessário
            
            if role == 'user':
                 history_for_llm.append({'role': 'user', 'parts': [content]})
            # Apenas respostas do assistente que sejam string são adicionadas ao histórico do modelo
            elif role == 'model' and isinstance(content, str):
                 history_for_llm.append({'role': 'model', 'parts': [content]})

        response = model.generate_content(
            history_for_llm + [{'role': 'user', 'parts': [user_prompt]}]
        )
        
        response_json = json.loads(response.text)
        return response_json, None

    except json.JSONDecodeError:
        error_msg = f"Erro: A LLM retornou um formato inválido. Resposta recebida: {getattr(response, 'text', 'N/A')}"
        return None, error_msg
    except Exception as e:
        error_msg = f"Ocorreu um erro ao processar seu pedido com a IA: {e}"
        return None, error_msg