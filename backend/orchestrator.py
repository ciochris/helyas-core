import os
import json
import difflib

# ── Configurazione provider ──────────────────────────────────────────────────
ENABLE_GPT    = os.getenv("ENABLE_GPT",    "true").lower() == "true"
ENABLE_CLAUDE = os.getenv("ENABLE_CLAUDE", "true").lower() == "true"
ENABLE_GEMINI = os.getenv("ENABLE_GEMINI", "true").lower() == "true"

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY", "")

OPENAI_MODEL  = os.getenv("OPENAI_MODEL",  "gpt-4o-mini")
CLAUDE_MODEL  = os.getenv("CLAUDE_MODEL",  "claude-haiku-4-5-20251001")
GEMINI_MODEL  = os.getenv("GEMINI_MODEL",  "gemini-1.5-flash")

# ── Chiamate API reali ───────────────────────────────────────────────────────

def call_openai(prompt: str) -> str:
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[GPT ERROR] {e}"


def call_claude(prompt: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"[CLAUDE ERROR] {e}"


def call_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[GEMINI ERROR] {e}"


# ── Prompt per ogni ruolo ────────────────────────────────────────────────────

def build_prompt(agent_name: str, role: str, task: str, context: list = None, session_context: list = None) -> str:
    role_instructions = {
        "Analyst":  "Analizza il problema in modo critico. Identifica i punti chiave, rischi principali e lacune informative. Sii conciso (max 150 parole).",
        "Planner":  "Proponi un piano d'azione strutturato per risolvere il problema. Elenca i passi principali. Sii conciso (max 150 parole).",
        "Builder":  "Proponi una soluzione concreta e implementabile. Concentrati su cosa fare praticamente. Sii conciso (max 150 parole).",
        "Critic":   "Critica costruttivamente le soluzioni proposte. Identifica debolezze, rischi non considerati e suggerisci miglioramenti. Sii conciso (max 150 parole)."
    }

    # Contesto della sessione (storico conversazione)
    session_text = ""
    if session_context and len(session_context) > 1:
        # Prende ultimi 6 messaggi per non appesantire il prompt
        recent = session_context[-6:]
        lines = []
        for msg in recent:
            role_label = "Utente" if msg.get("role") == "user" else "Helyas"
            content = (msg.get("content") or "")[:200]
            lines.append(f"{role_label}: {content}")
        session_text = "\n\nCONTESTO SESSIONE (messaggi precedenti):\n" + "\n".join(lines) + "\n\nTieni conto di questo contesto nella tua risposta."

    # Contesto del round precedente
    context_text = ""
    if context:
        last = context[-1]
        context_text = f"\n\nContesto dal round precedente:\nAgente: {last.get('agent')}, Ruolo: {last.get('role')}\nProposta: {last.get('proposal')}\n"

    return f"""Sei {agent_name} nel ruolo di {role} in una sessione di analisi collaborativa multi-AI.

{role_instructions.get(role, 'Contribuisci con la tua perspettiva.')}
{session_text}
{context_text}
Task da analizzare: {task}

Rispondi in italiano. Fornisci:
1. PROPOSTA: la tua analisi/soluzione
2. RISCHI: 2-3 rischi principali (formato: "- rischio")
3. LACUNE: 1-2 informazioni mancanti (formato: "- lacuna")
"""


def parse_response(text: str) -> dict:
    """Estrae proposta, rischi e lacune dal testo libero dell'AI."""
    proposal, risks, gaps = "", [], []
    current = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        line_upper = line.upper()

        # Riconosce "1. PROPOSTA:", "PROPOSTA:", "**PROPOSTA:**" ecc.
        if "PROPOSTA" in line_upper and ":" in line:
            current = "proposal"
            after_colon = line.split(":", 1)[-1].strip()
            # Rimuove eventuali ** residui del markdown
            after_colon = after_colon.replace("**", "").strip()
            proposal = after_colon
        elif "RISCHI" in line_upper and ":" in line:
            current = "risks"
        elif "LACUNE" in line_upper and ":" in line:
            current = "gaps"
        elif line.startswith("-"):
            item = line[1:].strip().replace("**", "")
            if current == "risks":
                risks.append(item)
            elif current == "gaps":
                gaps.append(item)
        elif current == "proposal":
            clean = line.replace("**", "").strip()
            # Smette di accumulare se inizia una nuova sezione numerata
            if clean and not clean[0].isdigit():
                proposal += " " + clean

    # Pulizia finale della proposta
    proposal = proposal.strip()

    # Se non ha trovato nulla di strutturato, usa il testo grezzo pulito
    if not proposal:
        # Rimuove righe che sembrano intestazioni di sezione
        lines = [l.strip() for l in text.splitlines() if l.strip()
                 and "PROPOSTA" not in l.upper()
                 and "RISCHI" not in l.upper()
                 and "LACUNE" not in l.upper()]
        proposal = " ".join(lines)[:400].replace("**", "").strip()

    return {"proposal": proposal, "risks": risks, "gaps": gaps}


# ── Agente principale ────────────────────────────────────────────────────────

def ask_ai(agent_name: str, role: str, task: str, context: list = None, session_context: list = None) -> dict:
    prompt = build_prompt(agent_name, role, task, context, session_context)

    if agent_name == "ChatGPT" and ENABLE_GPT:
        raw = call_openai(prompt)
    elif agent_name == "Claude" and ENABLE_CLAUDE:
        raw = call_claude(prompt)
    elif agent_name == "Gemini" and ENABLE_GEMINI:
        raw = call_gemini(prompt)
    else:
        raw = f"[{agent_name}] Provider disabilitato o non configurato."

    parsed = parse_response(raw)

    return {
        "task_id": "rt-task",
        "agent": agent_name,
        "role": role,
        "proposal": parsed["proposal"],
        "risks": parsed["risks"],
        "gaps": parsed["gaps"],
        "raw": raw,
        "artifacts": [
            {"name": f"{agent_name}_{role}.txt", "type": "text", "content": raw}
        ]
    }


# ── Consenso ─────────────────────────────────────────────────────────────────

def is_consensus(logs: list, threshold: float = 0.6) -> bool:
    proposals = [log["proposal"] for log in logs if log["proposal"]]
    if len(proposals) < 2:
        return False
    base = proposals[0]
    matches = [difflib.SequenceMatcher(None, base, p).ratio() for p in proposals[1:]]
    return all(m > threshold for m in matches)


# ── Round Table principale ────────────────────────────────────────────────────

def round_table(task: str, max_rounds: int = 2, session_context: list = None) -> dict:
    agents = []
    if ENABLE_GPT:    agents.append("ChatGPT")
    if ENABLE_CLAUDE: agents.append("Claude")
    if ENABLE_GEMINI: agents.append("Gemini")

    if not agents:
        return {"decision": {"summary": "Nessun provider AI abilitato.", "decisions": [], "log": []}}

    roles = ["Analyst", "Planner", "Builder", "Critic"]
    history = []
    round_count = 0
    consensus_reached = False

    while round_count < max_rounds and not consensus_reached:
        round_count += 1
        round_logs = []

        for agent in agents:
            context = history[-len(agents):] if history else None
            for role in roles:
                entry = ask_ai(agent, role, task, context, session_context)
                round_logs.append(entry)

        history.extend(round_logs)

        # Controlla consenso sull'ultimo ruolo (Critic) di ogni agente
        latest = [next((l for l in reversed(round_logs) if l["agent"] == a), None) for a in agents]
        latest = [l for l in latest if l]
        if latest and is_consensus(latest):
            consensus_reached = True

    # Sintesi finale — usa la proposta Builder più completa
    builder_logs = [log for log in history if log["role"] == "Builder"]
    if builder_logs:
        best = max(builder_logs, key=lambda x: len(x.get("proposal", "")))
        synthesis = best["proposal"]
    else:
        synthesis = "Nessuna proposta raccolta."

    final_summary = {
        "summary": f"Sintesi dopo {round_count} round - consenso={'sì' if consensus_reached else 'no'}",
        "synthesis": synthesis,
        "decisions": [log["proposal"] for log in history[-len(agents):]],
        "final_artifacts": [a["name"] for log in history[-len(agents):] for a in log.get("artifacts", [])],
        "approval_requested": True,
        "log": history
    }

    return {"decision": final_summary}
