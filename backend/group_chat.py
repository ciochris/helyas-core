import os
import json
import uuid
import time
import psycopg2
import psycopg2.extras


# ── Status parsing ────────────────────────────────────────────────────────────

def parse_status(raw_text: str) -> tuple:
    """
    Cerca riga STATUS: nelle ultime 3 righe (robustezza vs formatting irregolare).
    Ritorna (clean_text, status, decision_question).
    status: "continue" | "needs_decision" | "ready"
    """
    if not raw_text:
        return ("", "continue", None)

    lines = raw_text.strip().splitlines()
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return (raw_text.strip(), "continue", None)

    # Cerca STATUS: nelle ultime 3 righe non vuote
    tail = non_empty[-3:] if len(non_empty) >= 3 else non_empty
    status_line_idx = None
    status_line = None
    for i, line in enumerate(reversed(tail)):
        stripped = line.strip()
        if stripped.upper().startswith("STATUS:"):
            status_line = stripped
            # indice nel tail (dalla fine)
            status_line_idx = len(tail) - 1 - i
            break

    if status_line is None:
        print(f"[GROUP CHAT] WARNING: STATUS mancante, fallback CONTINUA. Tail: {tail}")
        return (raw_text.strip(), "continue", None)

    # Rimuovi la riga STATUS dal testo
    # Trova la riga nel testo originale e rimuovila
    clean_lines = []
    status_removed = False
    for line in reversed(lines):
        if not status_removed and line.strip() == status_line:
            status_removed = True
            continue
        clean_lines.insert(0, line)
    clean_text = "\n".join(clean_lines).strip()

    # Classifica status
    status_raw = status_line[7:].strip()  # tutto dopo "STATUS:"

    if status_raw.upper() == "CONTINUA":
        return (clean_text, "continue", None)

    if status_raw.upper() == "PRONTO":
        return (clean_text, "ready", None)

    if status_raw.upper().startswith("DECIDI:"):
        question = status_raw[7:].strip()
        return (clean_text, "needs_decision", question)

    # STATUS presente ma valore non riconosciuto
    print(f"[GROUP CHAT] WARNING: STATUS valore sconosciuto '{status_raw}', fallback CONTINUA")
    return (clean_text, "continue", None)


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_group_chat_prompt(
    agent_name: str,
    history: list,
    global_memory: str,
    project_memory: str,
    user_profile: str,
    pending_ready_note: str = None,
    revision_note: str = None
) -> str:
    other_agent = "Claude" if agent_name == "ChatGPT" else "ChatGPT"

    # SEZIONE 0 — Contesto vincolante (global_memory in cima, priorità massima)
    section0 = ""
    if global_memory:
        section0 = (
            "=== CONTESTO VINCOLANTE HELYAS / SOLUZIONE CASA ===\n"
            "Leggi questo contesto PRIMA di rispondere.\n"
            "Se una persona, un cantiere o una decisione è definita qui, "
            "non trattarla come sconosciuta e non chiederla a Christian.\n"
            f"{global_memory.strip()}\n"
            "=== FINE CONTESTO VINCOLANTE ===\n\n"
        )

    # SEZIONE 1 — Identità
    section1 = (
        f"Sei {agent_name} in una Group Chat sequenziale con {other_agent} e Christian Ciofi.\n"
        f"Il tuo interlocutore principale in questo turno è {other_agent}, non Christian.\n"
        "Christian sta leggendo la conversazione ma interviene solo quando serve una sua decisione.\n\n"
        f"Devi rispondere direttamente a {other_agent}: contesta, integra, correggi, sviluppa o approva "
        "ciò che ha appena detto.\n\n"
        "Non iniziare rivolgendoti a Christian, salvo che tu debba chiedergli una decisione.\n\n"
        f"Inizia la risposta rivolgendoti all'altro agente per nome: '{other_agent}, ...'\n\n"
        "Non trasformare ogni risposta in una consulenza diretta a Christian. "
        "Il tuo compito è migliorare il ragionamento dell'altro agente.\n\n"
        "Usa STATUS: DECIDI solo quando il dibattito non può proseguire senza una scelta reale di Christian.\n"
        "Parti sempre dal contesto reale di Christian — non rispondere in astratto.\n\n"
        "Prima di fare una domanda a Christian su persone, ruoli, cantieri o decisioni, controlla se "
        "l'informazione è già nel CONTESTO VINCOLANTE. "
        "Se Tommaso, Moki, Oleg o altri operatori sono definiti nel contesto, usali direttamente.\n\n"
        "REGOLE DI CONVERGENZA (obbligatorie):\n"
        "- IMPORTANTE: nei primi 2 round del debate NON usare mai STATUS: PRONTO. "
        "Usa sempre STATUS: CONTINUA per i primi 2 round, indipendentemente da quanto ti sembra completa "
        "la tua risposta. Solo dal round 3 in poi puoi valutare se usare STATUS: PRONTO.\n"
        "- Se Christian ha scritto frasi come 'concludete voi', 'decidete voi', 'fate una proposta finale', "
        "'scegliete voi', 'andate avanti voi' o simili: non fare altre domande. "
        "Produci una proposta finale concreta e usa STATUS: PRONTO.\n"
        "- Se nel dibattito sono già stati usati 2 o più STATUS: DECIDI: al prossimo turno NON usare "
        "un altro STATUS: DECIDI. Produci invece una proposta finale ragionata con ciò che sai e usa STATUS: PRONTO.\n"
    )
    if agent_name == "ChatGPT":
        section1 += (
            "- Non limitarti ad approvare le proposte di Claude. Identifica rischi, "
            "debolezze o alternative che Claude non ha considerato.\n"
        )
    elif agent_name == "Claude":
        section1 += (
            "- Non fare troppe domande a Christian. Prima di usare STATUS: DECIDI, prova a risolvere "
            "l'incertezza dialogando con ChatGPT e ragionando insieme.\n"
        )

    # SEZIONE 2 — Contesto
    section2_parts = []
    if user_profile:
        section2_parts.append("PROFILO UTENTE:\n" + user_profile.strip())
    if global_memory:
        section2_parts.append("COSA HO IMPARATO SU QUESTO UTENTE:\n" + global_memory.strip())
    if project_memory:
        section2_parts.append("CONTESTO PROGETTO:\n" + project_memory.strip())
    section2 = "\n\n".join(section2_parts) if section2_parts else ""

    # SEZIONE 3 — History debate
    history_lines = []
    for msg in history:
        speaker = msg.get("speaker", "?")
        content = (msg.get("content") or "").strip()
        round_idx = msg.get("round_index", 0)
        label_map = {
            "christian": "Christian",
            "gpt": "ChatGPT",
            "claude": "Claude",
            "system": "Sistema"
        }
        label = label_map.get(speaker, speaker.capitalize())
        history_lines.append(f"[Round {round_idx}] {label}: {content}")
    if history_lines:
        section3 = "STORIA DEL DIBATTITO:\n" + "\n\n".join(history_lines)
        if pending_ready_note:
            section3 += "\n\n" + pending_ready_note
    else:
        section3 = pending_ready_note or ""

    # SEZIONE 4 — Istruzioni formato (rigide)
    section4 = (
        "FORMATO RISPOSTA OBBLIGATORIO:\n"
        "- Scrivi in testo libero naturale, senza sezioni o intestazioni\n"
        "- Rispondi in italiano\n"
        "- Sii diretto e concreto — massimo 3-4 paragrafi\n"
        "- Alla fine scrivi ESATTAMENTE UNA RIGA con uno di questi tre formati:\n\n"
        "  STATUS: CONTINUA\n"
        "  (se il dibattito deve proseguire — l'altro agente risponderà)\n\n"
        "  STATUS: DECIDI: [scrivi qui la domanda specifica per Christian]\n"
        "  (se serve una decisione di Christian prima di procedere)\n\n"
        "  STATUS: PRONTO\n"
        "  (se hai raggiunto una conclusione chiara e il dibattito può chiudersi)\n\n"
        "IMPORTANTE: non scrivere NULLA dopo la riga STATUS. "
        "La riga STATUS deve essere l'ultima riga assoluta della tua risposta."
    )

    parts = []
    if revision_note:
        parts.append(revision_note)
    if section0:
        parts.append(section0)
    parts.append(section1)
    if section2:
        parts.append(section2)
    if section3:
        parts.append(section3)
    parts.append(section4)

    return "\n\n".join(parts)


# ── DB helpers ────────────────────────────────────────────────────────────────

def save_debate_message(
    conn,
    session_id: str,
    debate_id: str,
    speaker: str,
    target_agent,
    message_type: str,
    content: str,
    status,
    round_index: int,
    metadata: dict = None,
    revision_cycle: int = 0
) -> int:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO group_chat_messages
           (session_id, debate_id, speaker, target_agent, message_type,
            content, status, round_index, metadata, revision_cycle)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (
            session_id,
            debate_id,
            speaker,
            target_agent,
            message_type,
            content,
            status,
            round_index,
            json.dumps(metadata or {}),
            revision_cycle
        )
    )
    msg_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    return msg_id


def update_debate_status(
    conn,
    debate_id: str,
    status: str,
    next_agent=None,
    round_index=None,
    decision_question=None,
    deciding_agent=None,
    metadata=None
):
    fields = ["status = %s", "updated_at = NOW()"]
    values = [status]

    if next_agent is not None:
        fields.append("next_agent = %s")
        values.append(next_agent)
    if round_index is not None:
        fields.append("round_index = %s")
        values.append(round_index)
    if decision_question is not None:
        fields.append("decision_question = %s")
        values.append(decision_question)
    if deciding_agent is not None:
        fields.append("deciding_agent = %s")
        values.append(deciding_agent)

    values.append(debate_id)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE group_chat_debates SET {', '.join(fields)} WHERE debate_id = %s",
        values
    )
    conn.commit()
    cur.close()


def get_debate_messages(conn, debate_id: str, after_id: int = None) -> list:
    cur = conn.cursor()
    if after_id is not None:
        cur.execute(
            """SELECT id, session_id, debate_id::text, speaker, target_agent,
                      message_type, content, status, round_index,
                      created_at, metadata, revision_cycle
               FROM group_chat_messages
               WHERE debate_id = %s AND id > %s
               ORDER BY round_index ASC, created_at ASC""",
            (debate_id, after_id)
        )
    else:
        cur.execute(
            """SELECT id, session_id, debate_id::text, speaker, target_agent,
                      message_type, content, status, round_index,
                      created_at, metadata, revision_cycle
               FROM group_chat_messages
               WHERE debate_id = %s
               ORDER BY round_index ASC, created_at ASC""",
            (debate_id,)
        )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    # Serializza created_at e metadata per JSON
    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        if isinstance(row.get("metadata"), str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except Exception:
                row["metadata"] = {}
    return rows


# ── Loop principale ───────────────────────────────────────────────────────────

def run_group_chat_loop(
    session_id: str,
    debate_id: str,
    first_agent: str,
    max_rounds: int,
    db_url: str
):
    """
    Eseguito in thread background. Ogni thread ha la propria connessione DB.
    Loop sequenziale: first_agent → altro agente → first_agent → ...
    Si ferma su: status ready/needs_decision, safety limit, errore esterno.
    """
    conn = None
    try:
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)

        # Importa call_openai e call_claude da orchestrator (già testati)
        from backend.orchestrator import call_openai, call_claude

        # Carica contesto fisso (una volta sola)
        def _query_one(sql, params=()):
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.close()
            return row

        profile_row = _query_one("SELECT content FROM user_profile WHERE id = 1")
        user_profile = profile_row["content"] if profile_row else ""

        global_row = _query_one("SELECT content FROM global_memory WHERE id = 1")
        global_memory = global_row["content"] if global_row else ""

        session_row = _query_one("SELECT project_id FROM sessions WHERE id = %s", (session_id,))
        project_id = session_row["project_id"] if session_row else None

        project_memory = ""
        if project_id:
            pm_row = _query_one(
                "SELECT content FROM project_memory WHERE project_id = %s", (project_id,)
            )
            project_memory = pm_row["content"] if pm_row else ""

        current_agent = first_agent  # "gpt" o "claude"
        other_agent = "claude" if current_agent == "gpt" else "gpt"

        # Legge round_index e revision_cycle dal DB
        debate_meta = _query_one(
            "SELECT round_index, revision_cycle FROM group_chat_debates WHERE debate_id = %s",
            (debate_id,)
        )
        round_index = (debate_meta["round_index"] or 0) + 1
        current_cycle = debate_meta["revision_cycle"] or 0

        agent_name_map = {"gpt": "ChatGPT", "claude": "Claude"}
        pending_ready_agent = None

        while round_index <= max_rounds:
            # Verifica che il debate non sia stato fermato esternamente
            debate_row = _query_one(
                "SELECT status FROM group_chat_debates WHERE debate_id = %s", (debate_id,)
            )
            if not debate_row or debate_row["status"] != "running":
                print(f"[GROUP CHAT] Debate {debate_id} fermato esternamente, uscita loop")
                break

            # Carica history completa
            history = get_debate_messages(conn, debate_id)

            # Costruisce prompt
            agent_display = agent_name_map.get(current_agent, current_agent)
            pending_ready_note = None
            if pending_ready_agent is not None and pending_ready_agent != current_agent:
                proposer_name = agent_name_map.get(pending_ready_agent, pending_ready_agent)
                pending_ready_note = (
                    f"NOTA: {proposer_name} ha proposto la chiusura del debate con una proposta finale. "
                    f"Puoi confermare con STATUS: PRONTO se sei d'accordo, "
                    f"oppure contestare con STATUS: CONTINUA se vedi problemi."
                )
            revision_note = None
            if current_cycle > 0:
                prev_cycle = current_cycle - 1
                cycle_summary_msg = next(
                    (m for m in reversed(history)
                     if m.get("message_type") == "cycle_summary"
                     and m.get("revision_cycle") == prev_cycle),
                    None
                )
                correction_msg = next(
                    (m for m in reversed(history)
                     if m.get("speaker") == "christian"
                     and m.get("revision_cycle") == current_cycle),
                    None
                )
                cycle_summary_text = (
                    cycle_summary_msg["content"].strip() if cycle_summary_msg else "Non disponibile."
                )
                correction_text = (correction_msg["content"] or "").strip() if correction_msg else "Non specificata."
                if correction_text.startswith("Non approvo. Correzione: "):
                    correction_text = correction_text[len("Non approvo. Correzione: "):]
                other_display = agent_name_map.get(other_agent, other_agent)
                revision_note = (
                    "ISTRUZIONE PRIORITARIA ASSOLUTA — CICLO DI REVISIONE\n\n"
                    "Christian ha rifiutato la proposta precedente.\n\n"
                    f"MOTIVO DEL RIFIUTO:\n\"{correction_text}\"\n\n"
                    "La proposta precedente NON è approvata.\n"
                    "Non devi difenderla, ripeterla o riformularla con parole diverse.\n\n"
                    "Devi produrre una proposta sostanzialmente diversa che risolva il motivo del rifiuto.\n\n"
                    "Prima di rispondere, identifica cosa va cambiato.\n"
                    "Nella risposta devi rendere evidente almeno una modifica concreta rispetto al ciclo precedente.\n\n"
                    "Se il motivo è \"voglio una soluzione più semplice\":\n"
                    "- riduci il numero di passaggi\n"
                    "- riduci il carico operativo\n"
                    "- elimina elementi non indispensabili\n"
                    "- proponi una versione più breve e diretta\n\n"
                    "Se ripeti la proposta precedente, la risposta è sbagliata.\n\n"
                    f"PROPOSTA PRECEDENTE RIFIUTATA — NON RIPETERE:\n{cycle_summary_text}\n\n"
                    "NUOVO COMPITO:\n"
                    "Rielabora la proposta. Nel primo messaggio del ciclo devi obbligatoriamente iniziare "
                    "citando il motivo del reject, ad esempio:\n"
                    f"\"{other_display}, Christian ha rifiutato perché [motivo]. Quindi...\""
                )
            prompt = build_group_chat_prompt(
                agent_display, history, global_memory, project_memory, user_profile,
                pending_ready_note=pending_ready_note,
                revision_note=revision_note
            )

            print(f"[GROUP CHAT PROMPT] round={round_index} cycle={current_cycle}")
            print(prompt)
            print("--- END PROMPT ---")

            # Chiama API
            t_start = time.time()
            if current_agent == "gpt":
                import openai as openai_lib
                client = openai_lib.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
                response = client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1200,
                    temperature=0.7
                )
                raw_response = response.choices[0].message.content.strip()
            else:
                import anthropic as anthropic_lib
                client = anthropic_lib.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
                response = client.messages.create(
                    model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
                    max_tokens=1200,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_response = response.content[0].text.strip()
            exec_time = round(time.time() - t_start, 3)

            # Parse STATUS
            clean_text, status, decision_question = parse_status(raw_response)

            # Mappa status → DB status
            status_map = {
                "continue": "continue",
                "needs_decision": "needs_decision",
                "ready": "ready"
            }
            db_status = status_map.get(status, "continue")

            # Salva messaggio
            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker=current_agent,
                target_agent=other_agent,
                message_type="decision_request" if status == "needs_decision" else "agent_message",
                content=clean_text,
                status=db_status,
                round_index=round_index,
                metadata={"execution_time": exec_time},
                revision_cycle=current_cycle
            )

            # Aggiorna stato debate
            if status == "needs_decision":
                update_debate_status(
                    conn, debate_id,
                    status="needs_decision",
                    next_agent=other_agent,
                    round_index=round_index,
                    decision_question=decision_question,
                    deciding_agent=current_agent
                )
                print(f"[GROUP CHAT] Debate {debate_id} in attesa decisione: {decision_question}")
                break

            if status == "ready":
                if pending_ready_agent is None:
                    # Primo PRONTO: aspetta conferma dell'altro agente
                    pending_ready_agent = current_agent
                    print(f"[GROUP CHAT] {current_agent} propone chiusura, attendo conferma di {other_agent}")
                elif pending_ready_agent != current_agent:
                    # Doppia conferma: chiudi il debate
                    update_debate_status(
                        conn, debate_id,
                        status="ready",
                        next_agent=None,
                        round_index=round_index
                    )
                    print(f"[GROUP CHAT] Debate {debate_id} convergenza doppia confermata al round {round_index}")
                    break
            else:
                # STATUS: CONTINUA → reset pending
                pending_ready_agent = None

            # Continua (anche dopo primo PRONTO): switch agente e incrementa round
            update_debate_status(
                conn, debate_id,
                status="running",
                next_agent=other_agent,
                round_index=round_index
            )
            current_agent, other_agent = other_agent, current_agent
            round_index += 1

        else:
            # Safety limit raggiunto (while terminato senza break)
            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker="system",
                target_agent=None,
                message_type="final_output",
                content=f"Safety limit raggiunto dopo {max_rounds} round. Usa 'Sintesi' per un riepilogo.",
                status="safety_limit",
                round_index=round_index,
                metadata={},
                revision_cycle=current_cycle
            )
            update_debate_status(
                conn, debate_id,
                status="safety_limit",
                round_index=round_index
            )
            print(f"[GROUP CHAT] Debate {debate_id} safety limit a {max_rounds} round")

    except Exception as e:
        import traceback
        print(f"[GROUP CHAT ERROR] debate_id={debate_id} error={e}")
        print(traceback.format_exc())
        try:
            if conn:
                update_debate_status(conn, debate_id, status='error',
                    metadata={"error": str(e)})
                conn.commit()
        except:
            pass
    finally:
        try:
            if conn:
                conn.close()
        except:
            pass
