import json
import difflib

# Simulazione provider AI (da sostituire con chiamate API reali)
def ask_ai(agent_name, role, task, context=None):
    response = {
        "task_id": f"rt-task",
        "agent": agent_name,
        "role": role,
        "proposal": f"[{agent_name}] ({role}) proposta sul task: {task}",
        "risks": [f"rischio generico individuato da {agent_name}"],
        "gaps": [f"lacuna individuata da {agent_name}"],
        "artifacts": [
            {"name": f"{agent_name}_artifact.txt", "type": "text", "content": f"output simulato da {agent_name}"}
        ]
    }
    if context:
        response["context_used"] = context
    return response

def is_consensus(logs, threshold=0.8):
    """Controlla se le proposte degli agenti sono sufficientemente simili"""
    proposals = [log["proposal"] for log in logs]
    if len(proposals) < 2:
        return False
    base = proposals[0]
    matches = [difflib.SequenceMatcher(None, base, p).ratio() for p in proposals[1:]]
    return all(m > threshold for m in matches)

def round_table(task: str, max_rounds: int = 5):
    agents = ["ChatGPT", "Claude", "Gemini"]
    roles = ["Analyst", "Planner", "Builder", "Critic"]

    history = []
    round_count = 0
    consensus_reached = False

    while round_count < max_rounds and not consensus_reached:
        round_count += 1
        round_logs = []

        # Ogni agente contribuisce con tutti i ruoli dinamici
        for agent in agents:
            context = [entry for entry in history[-len(agents):]] if history else None
            for role in roles:
                entry = ask_ai(agent, role, task, context)
                round_logs.append(entry)

        history.extend(round_logs)

        # Controllo consenso sulle ultime proposte da ogni agente
        latest_by_agent = []
        for agent in agents:
            proposals = [log for log in round_logs if log["agent"] == agent]
            if proposals:
                latest_by_agent.append(proposals[-1])

        if latest_by_agent and is_consensus(latest_by_agent):
            consensus_reached = True

    # Sintesi finale (Synthesizer/Moderator)
    final_summary = {
        "summary": f"Sintesi dopo {round_count} round - consenso={'sì' if consensus_reached else 'no'}",
        "decisions": [log["proposal"] for log in history[-len(agents):]],
        "final_artifacts": [a["name"] for log in history[-len(agents):] for a in log.get("artifacts", [])],
        "approval_requested": True,
        "log": history
    }

    return {"decision": final_summary}
