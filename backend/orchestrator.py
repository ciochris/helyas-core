import os
import openai
from anthropic import Anthropic
import random
import json
from datetime import datetime

# Configura le chiavi dalle variabili di ambiente
openai.api_key = os.getenv("OPENAI_API_KEY")
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# --- Funzione principale Round Table ---

def round_table(task: str, user: str = "Utente"):
    """
    Esegue un Round Table di 4 round fissi con ChatGPT, Claude e Gemini (mock).
    Ritorna solo la sintesi finale all'utente ma salva tutti i round come artifact.
    """

    artifacts = []  # archivio round-by-round

    # Round 0: chiarificazione domanda
    clarified_task = prepare_task(task)
    artifacts.append({
        "round": 0,
        "mode": "prepare",
        "task_original": task,
        "task_clarified": clarified_task,
        "timestamp": str(datetime.utcnow())
    })

    # Round 1: proposte indipendenti
    proposals_r1 = run_round(clarified_task, mode="proposal", round_number=1)
    artifacts.append({"round": 1, "mode": "proposal", "data": proposals_r1})

    # Round 2: critiche
    proposals_r2 = run_round(proposals_r1, mode="critique", round_number=2)
    artifacts.append({"round": 2, "mode": "critique", "data": proposals_r2})

    # Round 3: raffinamento
    proposals_r3 = run_round(proposals_r2, mode="refine", round_number=3)
    artifacts.append({"round": 3, "mode": "refine", "data": proposals_r3})

    # Round 4: convergenza finale
    proposals_r4 = run_round(proposals_r3, mode="converge", round_number=4)
    artifacts.append({"round": 4, "mode": "converge", "data": proposals_r4})

    # Orchestrator sceglie la decisione finale (qui semplificato: random tra le convergenze)
    final_decision = random.choice(proposals_r4)

    # Costruisce il risultato
    result = {
        "task_original": task,
        "task_clarified": clarified_task,
        "final_decision": final_decision,
        "status": "completed",
        "artifact_log": artifacts  # utile per debug/audit
    }

    return result


# --- Funzioni di supporto ---

def prepare_task(task: str) -> str:
    """Chiarifica la richiesta utente usando GPT"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Riformula il seguente task in modo chiaro e preciso."},
                {"role": "user", "content": task}
            ]
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        return task  # fallback: restituisce la frase originale


def run_round(input_data, mode: str, round_number: int):
    """Esegue un round del dibattito tra GPT, Claude e Gemini"""

    results = []

    # GPT
    gpt_response = call_gpt(input_data, mode, round_number)
    results.append({
        "agent": "ChatGPT",
        "round": round_number,
        "mode": mode,
        "proposal": gpt_response
    })

    # Claude
    claude_response = call_claude(input_data, mode, round_number)
    results.append({
        "agent": "Claude",
        "round": round_number,
        "mode": mode,
        "proposal": claude_response
    })

    # Gemini (placeholder per ora)
    gemini_response = f"[Placeholder Gemini] Risposta simulata round {round_number}, mode={mode}"
    results.append({
        "agent": "Gemini",
        "round": round_number,
        "mode": mode,
        "proposal": gemini_response
    })

    return results


def call_gpt(prompt: str, mode: str, round_number: int) -> str:
    """Chiamata a OpenAI GPT"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Sei ChatGPT. Modalità: {mode}, Round: {round_number}."},
                {"role": "user", "content": str(prompt)}
            ]
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        return f"[Errore GPT] {str(e)}"


def call_claude(prompt: str, mode: str, round_number: int) -> str:
    """Chiamata a Claude"""
    try:
        response = anthropic_client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=500,
            messages=[
                {"role": "user", "content": f"Modalità: {mode}, Round: {round_number}. Input: {prompt}"}
            ]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"[Errore Claude] {str(e)}"


# --- Routing messaggi ---

def route_message(user: str, text: str) -> str:
    """
    Smista i messaggi in base al prefisso.
    Default: a ORCHESTRATOR
    GPT:/ChatGPT: → ChatGPT
    Claude: → Claude
    Gemini: → Gemini
    """
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
