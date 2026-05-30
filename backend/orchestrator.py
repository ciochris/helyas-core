import os
import json
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed

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
            max_tokens=1500,
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
            max_tokens=1500,
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


# ── Agente Interprete ────────────────────────────────────────────────────────

def interpret_question(task: str, user_profile: str = "", session_context: list = None) -> dict:
    """
    Analizza la domanda e decide:
    - Se è semplice: risponde direttamente senza Round Table
    - Se è complessa: riscrive la domanda e decide se serve chiarimento
    - Se mancano info: fa domande mirate prima di procedere
    """
    context_text = ""
    if session_context and len(session_context) > 1:
        # Passa tutta la sessione corrente all interprete per non perdere il filo
        lines = []
        for msg in session_context:
            role_label = "Utente" if msg.get("role") == "user" else "Helyas"
            c = (msg.get("content") or "")[:300]
            lines.append(f"{role_label}: {c}")
        context_text = "\nCONVERSAZIONE IN CORSO (leggi tutta per capire il contesto):\n" + "\n".join(lines)

    profile_text = ""
    if user_profile:
        profile_text = "\nCONTESTO UTENTE:\n" + user_profile[:500]

    prompt = (
        "Sei l'Interprete di Helyas. Analizza la domanda dell'utente e rispondi SOLO con un oggetto JSON valido.\n"
        + profile_text
        + context_text
        + "\n\nDOMANDA UTENTE: " + task
        + """\n\nDecidi il tipo di risposta necessaria:

TIPO "direct": domanda semplice che non richiede analisi profonda.
Esempi: saluti, domande fattuali semplici, richieste di informazioni base, conversazione generale, calcoli semplici, "che giorno e domani", "quanto fa 2+2", "come stai".

TIPO "roundtable": domanda che richiede analisi, pianificazione, decisioni strategiche, confronto di opzioni, problemi complessi aziendali.
Esempi: "come miglioro i miei margini", "come gestisco questo cliente", "dammi un piano per X", "analizza questa situazione".

TIPO "clarify": domanda ambigua o incompleta dove servono informazioni essenziali prima di rispondere bene.
Esempi: "aiutami con il cantiere" (quale?), "cosa faccio con questo problema" (quale problema?).

IMPORTANTE: Se il messaggio e chiaramente la continuazione di una conversazione gia avviata (usa pronomi come "questo", "quello", "poterlo fare", "come detto prima", o e una domanda di approfondimento su qualcosa gia discusso), NON classificare come clarify. Usa il contesto della conversazione per capire a cosa si riferisce e classifica come direct o roundtable.

Rispondi SOLO con JSON, nessun testo prima o dopo:
{
  "type": "direct" | "roundtable" | "clarify",
  "rewritten": "versione migliorata e piu precisa della domanda (per roundtable)",
  "direct_answer": "risposta diretta completa (solo per type=direct)",
  "questions": ["domanda 1", "domanda 2"] 
}

Per type=direct: compila direct_answer con la risposta completa, lascia rewritten vuoto.
Per type=roundtable: compila rewritten con domanda migliorata, lascia direct_answer vuoto, questions vuoto.
Per type=clarify: compila questions (max 2), lascia direct_answer vuoto."""
    )

    try:
        raw = call_openai(prompt)
        # Pulisce il JSON da eventuali backtick
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        result = json.loads(raw)
        return result
    except Exception as e:
        # Fallback: vai al round table con la domanda originale
        return {"type": "roundtable", "rewritten": task, "direct_answer": "", "questions": []}


# ── Prompt per ogni ruolo ────────────────────────────────────────────────────

def build_prompt(agent_name: str, role: str, task: str, context: list = None, session_context: list = None, user_profile: str = None, project_memory: str = None) -> str:
    role_instructions = {
        "Analyst":  "Analizza il problema in modo critico. Identifica i punti chiave, rischi principali e lacune informative.",
        "Planner":  "Proponi un piano d'azione strutturato per risolvere il problema. Elenca i passi principali.",
        "Builder":  "Proponi una soluzione concreta e implementabile. Concentrati su cosa fare praticamente.",
        "Critic":   "Critica costruttivamente le soluzioni proposte. Identifica debolezze, rischi non considerati e suggerisci miglioramenti."
    }

    # Profilo utente
    profile_text = ""
    if user_profile:
        profile_text = (
            f"\n\nCONTESTO UTENTE:\n{user_profile.strip()}\n\n"
            "ISTRUZIONE IMPORTANTE: Usa questo contesto per ragionare, non per citare. "
            "Non menzionare nomi di persone o situazioni specifiche a meno che siano direttamente rilevanti per questa domanda. "
            "Parti dal contesto per arrivare a conclusioni specifiche che un consulente generico non potrebbe dare. "
            "Esempio sbagliato: 'Oleg e Moki dovrebbero fare X'. "
            "Esempio giusto: 'Dato che il tuo team e piccolo, concentra le risorse su Y invece di Z'.\n"
        )

    # Memoria del progetto
    project_text = ""
    if project_memory:
        project_text = f"\n\nCONTESTO PROGETTO:\n{project_memory.strip()}\n"

    # Contesto della sessione (storico conversazione)
    session_text = ""
    if session_context and len(session_context) > 1:
        # Per gli agenti: ultimi 6 messaggi compressi (controllo costi)
        # La sessione completa va solo all Interprete
        recent = session_context[-6:]
        lines = []
        for msg in recent:
            role_label = "Utente" if msg.get("role") == "user" else "Helyas"
            c = (msg.get("content") or "")[:200]
            lines.append(f"{role_label}: {c}")
        session_text = "\n\nCONTESTO RECENTE:\n" + "\n".join(lines) + "\n"

    # Contesto del round precedente
    context_text = ""
    if context:
        last = context[-1]
        context_text = f"\n\nROUND PRECEDENTE:\nAgente: {last.get('agent')}, Ruolo: {last.get('role')}\nProposta: {last.get('proposal')}\n"

    return f"""Sei {agent_name} nel ruolo di {role} in una sessione di analisi collaborativa multi-AI.

{role_instructions.get(role, 'Contribuisci con la tua perspettiva.')}
{profile_text}
{project_text}
{session_text}
{context_text}
Task da analizzare: {task}

COME RISPONDERE:
Prima di scrivere qualsiasi cosa, chiediti: questa informazione cambia qualcosa per questa persona in questa situazione specifica? Se la risposta e no, non includerla.

Ogni punto che scrivi deve essere presente perche senza di esso la risposta sarebbe peggiore, non perche completa un elenco. Non essere completo - sii utile. La lunghezza giusta e quella necessaria, ne piu ne meno.

Ragiona dal contesto dell utente per arrivare a conclusioni specifiche. Non citare nomi o situazioni meccanicamente - usali solo se cambiano concretamente la risposta.

Rispondi in italiano. Struttura liberamente in base a cosa serve per questa risposta specifica.
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

def ask_ai(agent_name: str, role: str, task: str, context: list = None, session_context: list = None, user_profile: str = None, project_memory: str = None) -> dict:
    prompt = build_prompt(agent_name, role, task, context, session_context, user_profile, project_memory)

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

def round_table(task: str, max_rounds: int = 2, session_context: list = None, user_profile: str = None, project_memory: str = None) -> dict:
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
        context = history[-len(agents):] if history else None

        # Chiamate parallele: tutti gli agenti e ruoli contemporaneamente
        tasks = [(agent, role) for agent in agents for role in roles]
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {
                executor.submit(ask_ai, agent, role, task, context, session_context, user_profile, project_memory): (agent, role)
                for agent, role in tasks
            }
            for future in as_completed(futures):
                try:
                    entry = future.result(timeout=30)
                    round_logs.append(entry)
                except Exception as e:
                    agent, role = futures[future]
                    round_logs.append({
                        "agent": agent, "role": role,
                        "proposal": f"[Timeout] {agent} non ha risposto in tempo.",
                        "risks": [], "gaps": [], "raw": "", "artifacts": []
                    })

        history.extend(round_logs)

        # Controlla consenso sull'ultimo ruolo (Critic) di ogni agente
        latest = [next((l for l in reversed(round_logs) if l["agent"] == a), None) for a in agents]
        latest = [l for l in latest if l]
        if latest and is_consensus(latest):
            consensus_reached = True

    # Sintesi finale — GPT sintetizza tutti i contributi in una risposta coerente
    all_proposals = []
    for log in history:
        if log.get("proposal"):
            all_proposals.append(f"[{log['agent']} - {log['role']}]: {log['proposal'][:300]}")

    proposals_text = "\n".join(all_proposals)

    # Contesto conversazione per la sintesi
    session_text = ""
    if session_context and len(session_context) > 1:
        lines = []
        for msg in session_context[-6:]:
            role_label = "Utente" if msg.get("role") == "user" else "Helyas"
            lines.append(f"{role_label}: {(msg.get('content') or '')[:300]}")
        session_text = "\nCONVERSAZIONE PRECEDENTE:\n" + "\n".join(lines) + "\n"

        profile_text = f"\nCONTESTO UTENTE:\n{user_profile[:400]}\n" if user_profile else ""

    synthesis_prompt = (
        ""Sei Helyas, un assistente AI personale e diretto. Non salutare e non presentarti - sei già in conversazione. Vai dritto alla risposta.\n"
        + profile_text
        + session_text
        + "\nHai appena ricevuto questi contributi da un team di analisi:\n"
        + proposals_text
        + "\n\nDOMANDA ORIGINALE: " + task
        + "\n\nOra rispondi tu direttamente all'utente in prima persona, come se fossi il suo consulente di fiducia. "
        "Sintetizza i contributi migliori in una risposta unica, coerente e utile. "
        "Non citare gli agenti, non fare liste meccaniche. "
        "Prima di scrivere ogni frase chiediti: questa informazione cambia qualcosa per questa persona? "
        "Se no, non scriverla. Rispondi in italiano, tono diretto e umano. Massimo 3-4 frasi. Se la risposta richiede più dettagli, scrivi le 3 frasi più utili e offri di approfondire."
    )

    synthesis = call_openai(synthesis_prompt)
    if not synthesis or "ERROR" in synthesis:
        synthesis = all_proposals[0] if all_proposals else "Nessuna proposta raccolta."

    final_summary = {
        "summary": f"Sintesi dopo {round_count} round - consenso={'sì' if consensus_reached else 'no'}",
        "synthesis": synthesis,
        "decisions": [log["proposal"] for log in history[-len(agents):]],
        "final_artifacts": [a["name"] for log in history[-len(agents):] for a in log.get("artifacts", [])],
        "approval_requested": True,
        "log": history
    }

    return {"decision": final_summary}
 
