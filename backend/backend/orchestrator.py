import os
import random

# Round Table simulato (prima versione stabile)
# In futuro qui collegheremo ChatGPT, Claude e Gemini.
def round_table(task: str):
    """
    Riceve un task in input e restituisce una risposta simulata
    come se fosse passata dal ciclo Round Table.
    """
    # Lista di agenti finti (per ora)
    agents = ["ChatGPT", "Claude", "Gemini"]

    # Risposte simulate (per test funzionale)
    proposals = [
        f"{agent} propone una soluzione per: {task}"
        for agent in agents
    ]

    # Scegliamo una risposta finale “sintetizzata”
    final_choice = random.choice(proposals)

    # Risultato formattato come JSON
    return {
        "task": task,
        "proposals": proposals,
        "decision": final_choice,
        "status": "completed"
    }
