# feedback_manager.py

import json
import os
from rich.console import Console

console = Console()
FEEDBACK_FILE = "feedback_log.json"

def save_feedback(feedback_data: dict):
    """
    Salva um novo feedback no arquivo de log.

    Args:
        feedback_data (dict): Um dicionário contendo o contexto,
                              a resposta incorreta e a correção.
    """
    feedback_list = load_feedback()
    feedback_list.append(feedback_data)
    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=4)
        console.print(f"[bold green]Feedback salvo com sucesso em {FEEDBACK_FILE}[/bold green]")
    except IOError as e:
        console.print(f"[bold red]ERRO: Não foi possível escrever em {FEEDBACK_FILE}: {e}[/bold red]")


def load_feedback() -> list:
    """
    Carrega todos os feedbacks do arquivo de log.

    Returns:
        list: Uma lista de dicionários de feedback. Retorna uma lista vazia se o arquivo não existir.
    """
    if not os.path.exists(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            # Se o arquivo estiver vazio, retorna uma lista vazia
            content = f.read()
            if not content:
                return []
            return json.loads(content)
    except (IOError, json.JSONDecodeError) as e:
        console.print(f"[bold red]ERRO: Não foi possível ler ou decodificar {FEEDBACK_FILE}: {e}[/bold red]")
        return []