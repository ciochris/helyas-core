import random

# Orchestrator Round Table (versione base)
# In futuro qui collegheremo ChatGPT, Claude e Gemini via API.
def round_table(task: str):
    """
    Riceve un task in input e restituisce una risposta unificata
    simulando un ciclo Round Table tra 3 agenti.
    """

    agents = ["ChatGPT", "Claude", "Gemini"]

    # Ogni agente propone qualcosa
    proposals = [
        {"agent": agent, "proposal": f"{agent} propone una soluzione per: {task}"}
        for agent in agents
    ]

    # Scegliamo una risposta finale
    final_choice = random.choice(proposals)

    return {
        "task": task,
        "proposals": proposals,
        "decision": final_choice,
        "status": "completed"
    }
