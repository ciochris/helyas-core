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
    # Round 1 – proposte indipendenti
    p_gpt = _safe_ask(lambda p: GPT.ask(p), f"[ROUND1][ROLE=Builder] {task_text}")
    p_claude = _safe_ask(lambda p: CLAUDE.ask(p), f"[ROUND1][ROLE=Critic] {task_text}")
    p_gemini = _safe_ask(lambda p: GEMINI.ask(p), f"[ROUND1][ROLE=Analyst] {task_text}")

    # Round 2 – critica incrociata
    critic_prompt = lambda other: f"[ROUND2][CRITIQUE] Analizza e segnala debolezze/migliorie:\n{other[:4000]}"
    c_gpt = _safe_ask(lambda p: GPT.ask(p), critic_prompt((p_claude or '') + '\n' + (p_gemini or '')))
    c_claude = _safe_ask(lambda p: CLAUDE.ask(p), critic_prompt((p_gpt or '') + '\n' + (p_gemini or '')))
    c_gemini = _safe_ask(lambda p: GEMINI.ask(p), critic_prompt((p_gpt or '') + '\n' + (p_claude or '')))

    # Round 3 – raffinamento
    refine_prompt = lambda base, crit: f"[ROUND3][REFINE]\nBASE:\n{base}\nCRITIQUE:\n{crit}\nMigliora e restituisci versione finale."
    r_gpt = _safe_ask(lambda p: GPT.ask(p), refine_prompt(p_gpt, c_claude or c_gemini or ''))
    r_claude = _safe_ask(lambda p: CLAUDE.ask(p), refine_prompt(p_claude, c_gpt or c_gemini or ''))
    r_gemini = _safe_ask(lambda p: GEMINI.ask(p), refine_prompt(p_gemini, c_gpt or c_claude or ''))

    # Round 4 – sintesi finale
    synth_input = f"GPT:\n{r_gpt}\n\nCLAUDE:\n{r_claude}\n\nGEMINI:\n{r_gemini}\n"
    if GPT.enabled:
        decision = _safe_ask(lambda p: GPT.ask(p), f"[ROUND4][SYNTHESIZE] Unifica in una sola risposta chiara e operativa:\n{synth_input}")
    else:
        decision = _safe_ask(lambda p: CLAUDE.ask(p), f"[ROUND4][SYNTHESIZE] Unifica in una sola risposta chiara e operativa:\n{synth_input}")

    return {
        "task": task_text,
        "proposals": {"gpt": p_gpt, "claude": p_claude, "gemini": p_gemini},
        "critiques": {"gpt": c_gpt, "claude": c_claude, "gemini": c_gemini},
        "refined": {"gpt": r_gpt, "claude": r_claude, "gemini": r_gemini},
        "decision": {"proposal": decision},
        "status": "ok"
    }
