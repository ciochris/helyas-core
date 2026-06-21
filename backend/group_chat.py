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
    user_profile: str
) -> str:
    other_agent = "Claude" if agent_name == "ChatGPT" else "ChatGPT"

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
        "Parti sempre dal contesto reale di Christian — non rispondere in astratto.\n"
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
    section3 = "STORIA DEL DIBATTITO:\n" + "\n\n".join(history_lines) if history_lines else ""

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

    parts = [section1]
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
    metadata: dict = None
) -> int:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO group_chat_messages
           (session_id, debate_id, speaker, target_agent, message_type,
            content, status, round_index, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            json.dumps(metadata or {})
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
                      created_at, metadata
               FROM group_chat_messages
               WHERE debate_id = %s AND id > %s
               ORDER BY round_index ASC, created_at ASC""",
            (debate_id, after_id)
        )
    else:
        cur.execute(
            """SELECT id, session_id, debate_id::text, speaker, target_agent,
                      message_type, content, status, round_index,
                      created_at, metadata
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
        round_index = 1  # round 0 = input Christian

        agent_name_map = {"gpt": "ChatGPT", "claude": "Claude"}

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
            prompt = build_group_chat_prompt(
                agent_display, history, global_memory, project_memory, user_profile
            )

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
                metadata={"execution_time": exec_time}
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
                update_debate_status(
                    conn, debate_id,
                    status="ready",
                    next_agent=None,
                    round_index=round_index
                )
                print(f"[GROUP CHAT] Debate {debate_id} completato al round {round_index}")
                break

            # Continua: aggiorna round e switch agente
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
                metadata={}
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
