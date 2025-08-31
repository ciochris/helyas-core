import time
from .provider_clients import GPTClient, ClaudeClient, GeminiClient

GPT = GPTClient()
CLAUDE = ClaudeClient()
GEMINI = GeminiClient()

def _safe_ask(fn, prompt, timeout_s=25):
    start = time.time()
    try:
        return fn(prompt)
    except Exception as e:
        return f"[errore provider] {e}"
    finally:
        if time.time() - start > timeout_s:
            return "[timeout]"

def round_table(task_text: str):
    # Round 1 - proposte indipendenti
    p_gpt = _safe_ask(lambda p: GPT.ask(p), f"[ROUND1][ROLE=Builder] {task_text}")
    p_claude = _safe_ask(lambda p: CLAUDE.ask(p), f"[ROUND1][ROLE=Critic] {task_text}")
    p_gemini = _safe_ask(lambda p: GEMINI.ask(p), f"[ROUND1][ROLE=Analyst] {task_text}")

    # Round 4 - sintesi finale (semplificato per debug)
    synth_input = f"GPT:\n{p_gpt}\n\nCLAUDE:\n{p_claude}\n\nGEMINI:\n{p_gemini}\n"
    if GPT.enabled:
        decision = _safe_ask(lambda p: GPT.ask(p), f"[SYNTHESIZE] Unifica:\n{synth_input}")
    elif CLAUDE.enabled:
        decision = _safe_ask(lambda p: CLAUDE.ask(p), f"[SYNTHESIZE] Unifica:\n{synth_input}")
    elif GEMINI.enabled:
        decision = _safe_ask(lambda p: GEMINI.ask(p), f"[SYNTHESIZE] Unifica:\n{synth_input}")
    else:
        decision = "[Nessun provider disponibile]"

    return {
        "task": task_text,
        "proposals": {"gpt": p_gpt, "claude": p_claude, "gemini": p_gemini},
        "decision": {"proposal": decision},
        "status": "ok"
    }
