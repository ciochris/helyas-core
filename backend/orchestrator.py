import os
import random
from datetime import datetime

# --- Funzione principale Round Table ---

def round_table(task: str, user: str = "Utente"):
    """Esegue un Round Table di 4 round fissi con ChatGPT, Claude e Gemini (mock)."""

    artifacts = []

    clarified_task = prepare_task(task)
    artifacts.append({
        "round": 0,
        "mode": "prepare",
        "task_original": task,
        "task_clarified": clarified_task,
        "timestamp": str(datetime.utcnow())
    })

    proposals_r1 = run_round(clarified_task, "proposal", 1)
    artifacts.append({"round": 1, "mode": "proposal", "data": proposals_r1})

    proposals_r2 = run_round(proposals_r1, "critique", 2)
    artifacts.append({"round": 2, "mode": "critique", "data": proposals_r2})

    proposals_r3 = run_round(proposals_r2, "refine", 3)
    artifacts.append({"round": 3, "mode": "refine", "data": proposals_r3})

    proposals_r4 = run_round(proposals_r3, "converge", 4)
    artifacts.append({"round": 4, "mode": "converge", "data": proposals_r4})

    final_decision = random.choice(proposals_r4)

    return {
        "task_original": task,
        "task_clarified": clarified_task,
        "final_decision": final_decision,
        "status": "completed",
        "artifact_log": artifacts
    }


# --- Funzioni di supporto ---

def prepare_task(task: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Riformula il seguente task in modo chiaro e preciso."},
                {"role": "user", "content": task}
            ]
        )
        return response.choices[0].message.content[0].text.strip()
    except Exception as e:
        return task


def run_round(input_data, mode: str, round_number: int):
    results = []
    results.append({"agent": "ChatGPT", "round": round_number, "mode": mode, "proposal": call_gpt(input_data, mode, round_number)})
    results.append({"agent": "Claude", "round": round_number, "mode": mode, "proposal": call_claude(input_data, mode, round_number)})
    results.append({"agent": "Gemini", "round": round_number, "mode": mode, "proposal": f"[Placeholder Gemini] Risposta simulata round {round_number}, mode={mode}"})
    return results


def call_gpt(prompt: str, mode: str, round_number: int) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Sei ChatGPT. Modalità: {mode}, Round: {round_number}."},
                {"role": "user", "content": str(prompt)}
            ]
        )
        return response.choices[0].message.content[0].text.strip()
    except Exception as e:
        return f"[Errore GPT] {str(e)}"


def call_claude(prompt: str, mode: str, round_number: int) -> str:
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=500,
            messages=[{"role": "user", "content": f"Modalità: {mode}, Round: {round_number}. Input: {prompt}"}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"[Errore Claude] {str(e)}"


# --- Routing messaggi ---

def route_message(user: str, text: str) -> str:
    text = text.strip()
    low = text.lower()
    if low.startswith(("gpt:", "chatgpt:")):
        return f"[MESSAGGIO DI UTENTE ({user}) A CHATGPT]\n{text.split(':',1)[1].strip()}"
    elif low.startswith("claude:"):
        return f"[MESSAGGIO DI UTENTE ({user}) A CLAUDE]\n{text.split(':',1)[1].strip()}"
    elif low.startswith("gemini:"):
        return f"[MESSAGGIO DI UTENTE ({user}) A GEMINI]\n{text.split(':',1)[1].strip()}"
    else:
        return f"[MESSAGGIO DI UTENTE ({user}) A ORCHESTRATOR]\n{text}"
