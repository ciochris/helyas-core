import os
import asyncio
from openai import OpenAI
import anthropic

# Inizializza i client usando le chiavi dalle variabili di ambiente
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
client_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Funzione di sicurezza: chiama una funzione con timeout
async def safe_call(func, *args, **kwargs):
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=30)
    except Exception as e:
        return f"[Errore Timeout] {str(e)}"

# Wrapper sincrono per compatibilità col resto del codice
def run_safe(func, *args, **kwargs):
    return asyncio.run(safe_call(func, *args, **kwargs))

# Funzione per interagire con GPT
def ask_gpt(prompt):
    try:
        response = run_safe(
            client_openai.chat.completions.create,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        if isinstance(response, str):  # Se è errore o timeout
            return response
        return response.choices[0].message.content
    except Exception as e:
        return f"[Errore GPT] {str(e)}"

# Funzione per interagire con Claude
def ask_claude(prompt):
    try:
        response = run_safe(
            client_claude.messages.create,
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        if isinstance(response, str):  # Se è errore o timeout
            return response
        return response.content[0].text
    except Exception as e:
        return f"[Errore Claude] {str(e)}"

# Funzione mock per Gemini (verrà integrata più avanti)
def ask_gemini(prompt):
    return f"[Placeholder Gemini] Risposta simulata per: {prompt}"

# Round Table: gestisce i round tra le AI
def round_table(task):
    log = []

    # Round 0 - Preparazione
    log.append({"round": 0, "mode": "prepare", "task_clarified": task})

    # Round 1 - Proposte
    r1 = [
        {"agent": "ChatGPT", "mode": "proposal", "proposal": ask_gpt(task)},
        {"agent": "Claude", "mode": "proposal", "proposal": ask_claude(task)},
        {"agent": "Gemini", "mode": "proposal", "proposal": ask_gemini(task)}
    ]
    log.append({"round": 1, "mode": "proposal", "data": r1})

    # Round 2 - Critiche
    r2 = [
        {"agent": "ChatGPT", "mode": "critique", "proposal": ask_gpt(str(r1))},
        {"agent": "Claude", "mode": "critique", "proposal": ask_claude(str(r1))},
        {"agent": "Gemini", "mode": "critique", "proposal": ask_gemini(str(r1))}
    ]
    log.append({"round": 2, "mode": "critique", "data": r2})

    # Round 3 - Refinement
    r3 = [
        {"agent": "ChatGPT", "mode": "refine", "proposal": ask_gpt(str(r2))},
        {"agent": "Claude", "mode": "refine", "proposal": ask_claude(str(r2))},
        {"agent": "Gemini", "mode": "refine", "proposal": ask_gemini(str(r2))}
    ]
    log.append({"round": 3, "mode": "refine", "data": r3})

    # Round 4 - Convergenza
    r4 = [
        {"agent": "ChatGPT", "mode": "converge", "proposal": ask_gpt(str(r3))},
        {"agent": "Claude", "mode": "converge", "proposal": ask_claude(str(r3))},
        {"agent": "Gemini", "mode": "converge", "proposal": ask_gemini(str(r3))}
    ]
    log.append({"round": 4, "mode": "converge", "data": r4})

    # Decisione finale (puoi farla più complessa)
    final_decision = r4[0]

    return {
        "task_original": task,
        "artifact_log": log,
        "final_decision": final_decision,
        "status": "completed"
    }
