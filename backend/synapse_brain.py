from flask import Flask, request, jsonify, render_template_string
from backend.orchestrator import round_table
import json
import os
import time
import uuid
import threading
import psycopg2
import psycopg2.extras
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Database ─────────────────────────────────────────────────────────────────

def clean_markdown(text):
    """Rimuove simboli markdown dal testo."""
    if not text:
        return text
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        while line.startswith('#'):
            line = line[1:]
        line = line.lstrip()
        while '**' in line:
            line = line.replace('**', '', 2)
        if line.strip().startswith('---'):
            line = ''
        cleaned.append(line)
    result = '\n'.join(cleaned)
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    return result.strip()

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

INITIAL_PROFILE = """PROFILO UTENTE:
Nome: Christian Ciofi
Azienda: Soluzione Casa Srls (in trasformazione in Srl)
Ruolo: Amministratore Unico
Sede: Via San Lazzaro 16, 34122 Trieste
Telefono: 3336263840
Email: info@soluzionecasatrieste.it
P.IVA: 01352380321
Settore: Edilizia e ristrutturazioni, specializzazione bagni e impianti di climatizzazione
"""

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                project_id TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                synthesis TEXT,
                log JSONB DEFAULT '[]',
                execution_time FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY DEFAULT 1,
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_memory (
                id INTEGER PRIMARY KEY DEFAULT 1,
                project_id TEXT,
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS global_memory (
                id INTEGER PRIMARY KEY DEFAULT 1,
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS group_chat_debates (
                debate_id         UUID PRIMARY KEY,
                session_id        TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                status            VARCHAR NOT NULL DEFAULT 'running',
                current_agent     VARCHAR,
                next_agent        VARCHAR,
                round_index       INTEGER DEFAULT 0,
                decision_question TEXT,
                created_at        TIMESTAMP DEFAULT NOW(),
                updated_at        TIMESTAMP DEFAULT NOW(),
                metadata          JSONB DEFAULT '{}'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS group_chat_messages (
                id           SERIAL PRIMARY KEY,
                session_id   TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                debate_id    UUID NOT NULL REFERENCES group_chat_debates(debate_id),
                speaker      VARCHAR NOT NULL,
                target_agent VARCHAR,
                message_type VARCHAR NOT NULL,
                content      TEXT NOT NULL,
                status       VARCHAR,
                round_index  INTEGER DEFAULT 0,
                created_at   TIMESTAMP DEFAULT NOW(),
                metadata     JSONB DEFAULT '{}'
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gcm_debate_id
                ON group_chat_messages(debate_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gcd_session_id
                ON group_chat_debates(session_id)
        """)
        cur.execute("ALTER TABLE group_chat_debates ADD COLUMN IF NOT EXISTS deciding_agent VARCHAR")
        cur.execute("ALTER TABLE group_chat_debates ADD COLUMN IF NOT EXISTS revision_cycle INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE group_chat_messages ADD COLUMN IF NOT EXISTS revision_cycle INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS project_id TEXT")
        cur.execute("SELECT content FROM user_profile WHERE id = 1")
        existing = cur.fetchone()
        old_profile_has_dynamic = existing and any(
            x in existing["content"] for x in ["Team:", "Partner:", "Collaboratore:", "Problemi prioritari:", "Condizioni preventivi"]
        )
        if not existing or old_profile_has_dynamic:
            cur.execute("""
                INSERT INTO user_profile (id, content, updated_at)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET content = %s, updated_at = NOW()
            """, (INITIAL_PROFILE, INITIAL_PROFILE))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")

def get_user_profile():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT content FROM user_profile WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row["content"] if row else INITIAL_PROFILE
    except Exception as e:
        print(f"[PROFILE ERROR] {e}")
        return INITIAL_PROFILE

def get_project_memory(project_id):
    if not project_id:
        return ""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT content FROM project_memory WHERE project_id = %s", (project_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row["content"] if row else ""
    except Exception as e:
        print(f"[PROJECT MEMORY ERROR] {e}")
        return ""

def get_global_memory():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT content FROM global_memory WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row["content"] if row else ""
    except Exception as e:
        print(f"[GLOBAL MEMORY ERROR] {e}")
        return ""

def update_global_memory_auto(session_synthesis, user_message):
    try:
        from backend.orchestrator import call_openai
        from datetime import datetime
        current = get_global_memory()
        prompt = (
            "Estrai le decisioni concrete da questo debate in massimo 5 righe, formato:\n"
            "- [DECISIONE] testo\n"
            "Solo le decisioni, niente altro.\n\n"
            + session_synthesis[:1000]
        )
        delta = call_openai(prompt)
        if not delta or "ERROR" in delta:
            print("[GLOBAL MEMORY] Delta non generato, skip aggiornamento")
            return
        data_ora = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_content = (current or "") + f"\n\n--- AGGIORNAMENTO {data_ora} ---\n" + delta.strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO global_memory (id, content, updated_at)
            VALUES (1, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET content = %s, updated_at = NOW()
        """, (new_content, new_content))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[GLOBAL MEMORY] Delta appeso ({len(delta)} char)")
    except Exception as e:
        print(f"[GLOBAL MEMORY UPDATE ERROR] {e}")

def update_project_memory_auto(project_id, session_synthesis):
    if not project_id or not session_synthesis:
        return
    try:
        from backend.orchestrator import call_openai
        current = get_project_memory(project_id)
        prompt = (
            "Sei un assistente che mantiene la memoria di un progetto.\n\n"
            "MEMORIA ATTUALE:\n" + (current if current else "(vuota)") + "\n\n"
            "NUOVA SESSIONE:\n" + session_synthesis[:800] + "\n\n"
            "Aggiorna la memoria integrando le novita. Mantieni info importanti, "
            "aggiungi novita, rimuovi obsolete. Max 400 parole. Solo testo, niente altro."
        )
        updated = call_openai(prompt)
        if updated and "ERROR" not in updated:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO project_memory (id, project_id, content, updated_at)
                VALUES (1, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET content = %s, project_id = %s, updated_at = NOW()
            """, (project_id, updated, updated, project_id))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"[PROJECT MEMORY UPDATE ERROR] {e}")

# ── Backlog ───────────────────────────────────────────────────────────────────

BACKLOG_FILE = os.path.join("backend", "backlog.json")

def load_backlog():
    if not os.path.exists(BACKLOG_FILE):
        return []
    try:
        with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_backlog(backlog):
    try:
        with open(BACKLOG_FILE, "w", encoding="utf-8") as f:
            json.dump(backlog, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Errore salvataggio backlog: {e}")

def clean_result(result):
    try:
        if isinstance(result, dict):
            decision = result.get("decision", {})
            synthesis = decision.get("synthesis", "")
            summary = decision.get("summary", "")
            return synthesis if synthesis else summary
        return str(result)
    except Exception:
        return str(result)

# ── API Sessioni ──────────────────────────────────────────────────────────────

@app.route("/sessions", methods=["GET"])
def list_sessions():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 50")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"sessions": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sessions", methods=["POST"])
def create_session():
    try:
        data = request.get_json(force=True)
        session_id = str(uuid.uuid4())[:8]
        title = data.get("title", "Nuova sessione")
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (id, title) VALUES (%s, %s) RETURNING *",
            (session_id, title)
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sessions/<session_id>", methods=["PATCH"])
def rename_session(session_id):
    try:
        data = request.get_json(force=True)
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Titolo vuoto"}), 400
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE sessions SET title = %s WHERE id = %s", (title, session_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "renamed", "title": title})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sessions/<session_id>/messages", methods=["GET"])
def get_messages(session_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"messages": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sessions/<session_id>/chat", methods=["POST"])
def chat(session_id):
    try:
        data = request.get_json(force=True)
        user_message = data.get("message", "").strip()
        max_rounds = int(data.get("max_rounds", 2))

        if not user_message:
            return jsonify({"error": "Messaggio vuoto"}), 400

        conn = get_db()
        cur = conn.cursor()

        # Salva messaggio utente
        cur.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, "user", user_message)
        )

        # Recupera history della sessione per il contesto
        cur.execute(
            "SELECT role, content, synthesis FROM messages WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )
        history_rows = cur.fetchall()

        # Costruisce contesto per gli agenti
        session_context = []
        for row in history_rows:
            session_context.append({
                "role": row["role"],
                "content": row["synthesis"] or row["content"]
            })

        # Titolo intelligente al primo messaggio
        cur.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = %s AND role = 'user'", (session_id,))
        count = cur.fetchone()["cnt"]
        if count == 1:
            try:
                from backend.orchestrator import call_openai
                smart_title = call_openai(
                    f"Genera un titolo breve (massimo 5 parole, in italiano) per una conversazione che inizia con: '{user_message[:200]}'. "
                    f"Rispondi SOLO con il titolo, senza virgolette o punteggiatura finale."
                )
                title = smart_title.strip()[:60] if smart_title and "ERROR" not in smart_title else user_message[:50]
            except Exception:
                title = user_message[:50]
            cur.execute("UPDATE sessions SET title = %s WHERE id = %s", (title, session_id))

        conn.commit()

        # Recupera profilo utente, memoria globale e memoria progetto
        user_profile = get_user_profile()
        global_memory = get_global_memory()
        cur.execute("SELECT project_id FROM sessions WHERE id = %s", (session_id,))
        session_row = cur.fetchone()
        project_id = session_row["project_id"] if session_row else None
        project_memory = get_project_memory(project_id) if project_id else ""

        # Combina profilo + memoria globale + memoria progetto
        full_context = user_profile
        if global_memory:
            full_context += "\n\nCOSA HO IMPARATO SU QUESTO UTENTE:\n" + global_memory
        if project_memory:
            full_context += "\n\nCONTESTO PROGETTO CORRENTE:\n" + project_memory

        # Agente Interprete
        from backend.orchestrator import interpret_question
        start_time = time.time()

        interpretation = interpret_question(user_message, full_context, session_context)
        response_type = interpretation.get("type", "roundtable")

        if response_type == "direct":
            import openai as openai_lib
            RESPONSE_STYLE = "concise"
            client = openai_lib.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
            system_prompt = (
                "Sei Helyas, l'assistente personale di Christian Ciofi. "
                "Conosci la sua azienda, i suoi collaboratori, i suoi progetti. "
                "Rispondi in modo diretto e umano. "
                "Non salutare, non presentarti, vai dritto al punto. "
                "Se e una conversazione in corso, mantieni il filo senza ricominciare da capo. "
                + ("Massimo 3-4 frasi. Approfondisci solo se esplicitamente richiesto." if RESPONSE_STYLE == "concise" else "")
            )
            messages_for_gpt = [{"role": "system", "content": system_prompt}]
            if full_context:
                messages_for_gpt.append({"role": "assistant", "content": f"Memoria della conversazione:\n{full_context}"})
            for msg in session_context:
                role = "user" if msg.get("role") == "user" else "assistant"
                content = msg.get("content") or ""
                if content:
                    messages_for_gpt.append({"role": role, "content": content})
            gpt_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_for_gpt,
                max_tokens=300,
                temperature=0.4
            )
            synthesis = gpt_response.choices[0].message.content.strip()
            synthesis_clean = clean_markdown(synthesis)
            log = []
            execution_time = round(time.time() - start_time, 3)

        elif response_type == "clarify":
            questions = interpretation.get("questions", [])
            synthesis = "Ho bisogno di qualche informazione in piu prima di rispondere al meglio:\n\n"
            for i, q in enumerate(questions, 1):
                synthesis += f"{i}. {q}\n"
            synthesis_clean = synthesis
            log = []
            execution_time = round(time.time() - start_time, 3)

        else:
            rewritten = interpretation.get("rewritten", user_message)
            if not rewritten or rewritten == user_message:
                rewritten = user_message

            result = round_table(
                rewritten,
                max_rounds=max_rounds,
                session_context=session_context,
                user_profile=full_context,
                project_memory=""
            )
            execution_time = round(time.time() - start_time, 3)
            decision = result.get("decision", {})
            synthesis = decision.get("synthesis", "")
            log = decision.get("log", [])
            synthesis_clean = clean_markdown(synthesis)

        msg_content = synthesis_clean if response_type in ("direct", "clarify") else clean_result(result)
        cur.execute(
            """INSERT INTO messages (session_id, role, content, synthesis, log, execution_time)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (session_id, "assistant", msg_content, synthesis_clean, json.dumps(log), execution_time)
        )
        msg = dict(cur.fetchone())

        cur.execute("UPDATE sessions SET updated_at = NOW() WHERE id = %s", (session_id,))
        conn.commit()
        cur.close()
        conn.close()

        import threading
        if synthesis_clean:
            threading.Thread(
                target=update_global_memory_auto,
                args=(synthesis_clean, user_message),
                daemon=True
            ).start()
        if project_id and synthesis_clean:
            threading.Thread(
                target=update_project_memory_auto,
                args=(project_id, synthesis_clean),
                daemon=True
            ).start()

        return jsonify(msg)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Group Chat Mode ──────────────────────────────────────────────────────────

@app.route("/sessions/<session_id>/group-chat", methods=["POST"])
def group_chat(session_id):
    try:
        from backend.group_chat import (
            save_debate_message, update_debate_status,
            get_debate_messages, run_group_chat_loop
        )
        from backend.orchestrator import call_openai

        data = request.get_json(force=True)
        action = data.get("action", "").strip()

        if not action:
            return jsonify({"error": "Campo 'action' obbligatorio"}), 400

        conn = get_db()
        cur = conn.cursor()

        # ── START ──────────────────────────────────────────────────────────────
        if action == "start":
            message = data.get("message", "").strip()
            first_speaker = data.get("first_speaker", "").strip().lower()

            if not message:
                return jsonify({"error": "Campo 'message' obbligatorio per action=start"}), 400
            if first_speaker not in ("gpt", "claude"):
                return jsonify({"error": "first_speaker deve essere 'gpt' o 'claude'"}), 400

            # Controlla debate già attivo
            cur.execute(
                """SELECT debate_id::text FROM group_chat_debates
                   WHERE session_id = %s AND status = 'running'
                   LIMIT 1""",
                (session_id,)
            )
            existing = cur.fetchone()
            if existing:
                cur.close()
                conn.close()
                return jsonify({
                    "error": "Esiste già un debate running per questa sessione",
                    "debate_id": existing["debate_id"]
                }), 409

            debate_id = str(uuid.uuid4())
            other_speaker = "claude" if first_speaker == "gpt" else "gpt"

            # Crea record debate
            cur.execute(
                """INSERT INTO group_chat_debates
                   (debate_id, session_id, status, current_agent, next_agent, round_index)
                   VALUES (%s, %s, 'running', %s, %s, 0)""",
                (debate_id, session_id, first_speaker, other_speaker)
            )
            conn.commit()

            # Salva input Christian
            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker="christian",
                target_agent=first_speaker,
                message_type="user_input",
                content=message,
                status=None,
                round_index=0
            )

            cur.close()
            conn.close()

            threading.Thread(
                target=run_group_chat_loop,
                args=(session_id, debate_id, first_speaker, 8, DATABASE_URL),
                daemon=True
            ).start()

            return jsonify({
                "debate_id": debate_id,
                "status": "running",
                "round_index": 0,
                "next_agent": first_speaker,
                "messages": []
            })

        # ── STOP ──────────────────────────────────────────────────────────────
        elif action == "stop":
            debate_id = data.get("debate_id", "").strip()
            if not debate_id:
                return jsonify({"error": "Campo 'debate_id' obbligatorio"}), 400

            update_debate_status(conn, debate_id, status="stopped")

            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker="system",
                target_agent=None,
                message_type="final_output",
                content="Dibattito fermato da Christian.",
                status="stopped",
                round_index=0
            )

            messages = get_debate_messages(conn, debate_id)
            cur.close()
            conn.close()
            return jsonify({
                "debate_id": debate_id,
                "status": "stopped",
                "messages": messages
            })

        # ── CONTINUE ──────────────────────────────────────────────────────────
        elif action == "continue":
            debate_id = data.get("debate_id", "").strip()
            message = data.get("message", "").strip()
            if not debate_id:
                return jsonify({"error": "Campo 'debate_id' obbligatorio"}), 400

            cur.execute(
                "SELECT * FROM group_chat_debates WHERE debate_id = %s",
                (debate_id,)
            )
            debate_row = cur.fetchone()
            if not debate_row:
                return jsonify({"error": "Debate non trovato"}), 404

            if debate_row["status"] == "running":
                cur.close()
                conn.close()
                return jsonify({"error": "Debate già in esecuzione"}), 409

            deciding_agent = debate_row.get("deciding_agent")
            start_agent = deciding_agent if deciding_agent else (debate_row["next_agent"] or "gpt")
            round_index = debate_row["round_index"] or 0

            # Salva eventuale messaggio di Christian
            if message:
                save_debate_message(
                    conn=conn,
                    session_id=session_id,
                    debate_id=debate_id,
                    speaker="christian",
                    target_agent=start_agent,
                    message_type="user_input",
                    content=message,
                    status=None,
                    round_index=round_index
                )

            # Riporta a running, azzera decision_question e deciding_agent
            cur.execute(
                """UPDATE group_chat_debates
                   SET status='running', decision_question=NULL, deciding_agent=NULL,
                       updated_at=NOW()
                   WHERE debate_id=%s""",
                (debate_id,)
            )
            conn.commit()
            cur.close()
            conn.close()

            threading.Thread(
                target=run_group_chat_loop,
                args=(session_id, debate_id, start_agent, 12, DATABASE_URL),
                daemon=True
            ).start()

            return jsonify({
                "debate_id": debate_id,
                "status": "running",
                "round_index": round_index,
                "next_agent": start_agent,
                "messages": []
            })

        # ── SUMMARIZE ─────────────────────────────────────────────────────────
        elif action == "summarize":
            debate_id = data.get("debate_id", "").strip()
            if not debate_id:
                return jsonify({"error": "Campo 'debate_id' obbligatorio"}), 400

            messages = get_debate_messages(conn, debate_id)
            if not messages:
                cur.close()
                conn.close()
                return jsonify({"error": "Nessun messaggio nel debate"}), 404

            history_text = "\n\n".join(
                f"[{m['speaker'].upper()}] {m['content']}"
                for m in messages
                if m["message_type"] not in ("final_output", "cycle_summary")
            )

            summary_prompt = (
                "Sei Helyas. Produci un decision log operativo da questo dibattito. "
                "Non un riassunto generico.\n\n"
                f"DIBATTITO:\n{history_text[:3000]}\n\n"
                "Elenca solo le decisioni concrete prese, formato:\n"
                "- [DECISIONE] testo della decisione\n"
                "Massimo 8 decisioni. Solo ciò che è stato deciso, "
                "non opinioni o considerazioni generali. "
                "Niente introduzioni o conclusioni."
            )

            synthesis = call_openai(summary_prompt)

            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker="system",
                target_agent=None,
                message_type="final_output",
                content=synthesis,
                status="ready",
                round_index=0
            )

            cur.close()
            conn.close()
            return jsonify({
                "debate_id": debate_id,
                "status": "ready",
                "synthesis": synthesis
            })

        # ── APPROVE ───────────────────────────────────────────────────────────
        elif action == "approve":
            debate_id = data.get("debate_id", "").strip()
            if not debate_id:
                return jsonify({"error": "Campo 'debate_id' obbligatorio"}), 400

            update_debate_status(conn, debate_id, status="ready")

            messages = get_debate_messages(conn, debate_id)
            # Includi tutti i messaggi non-system + i final_output di system (decision log)
            full_content = " ".join(
                m["content"] for m in messages
                if m["speaker"] != "system" or m["message_type"] == "final_output"
            )

            cur.close()
            conn.close()

            # Aggiorna memoria globale in background
            if full_content:
                threading.Thread(
                    target=update_global_memory_auto,
                    args=(full_content[:1000], "Group Chat debate approvato"),
                    daemon=True
                ).start()

            return jsonify({
                "debate_id": debate_id,
                "status": "approved"
            })

        # ── REJECT ────────────────────────────────────────────────────────────
        elif action == "reject":
            debate_id = data.get("debate_id", "").strip()
            correction = data.get("correction", "").strip()
            if not debate_id:
                return jsonify({"error": "Campo 'debate_id' obbligatorio"}), 400

            cur.execute(
                "SELECT next_agent, revision_cycle FROM group_chat_debates WHERE debate_id = %s",
                (debate_id,)
            )
            debate_row = cur.fetchone()
            if not debate_row:
                return jsonify({"error": "Debate non trovato"}), 404

            next_agent = (debate_row["next_agent"] or "gpt")
            current_cycle = debate_row["revision_cycle"] or 0

            # Sintesi provvisoria del ciclo corrente
            all_messages = get_debate_messages(conn, debate_id)
            cycle_msgs = [
                m for m in all_messages
                if m.get("revision_cycle") == current_cycle
                and m["speaker"] in ("gpt", "claude")
            ]
            cycle_history_text = "\n\n".join(
                f"[{m['speaker'].upper()}] {m['content']}"
                for m in cycle_msgs[-8:]
            ) if cycle_msgs else ""

            synthesis_content = ""
            if cycle_history_text:
                try:
                    from backend.orchestrator import call_openai
                    summary_prompt = (
                        "Produci una sintesi breve (max 5 righe) delle proposte principali "
                        "emerse in questo ciclo di dibattito. Formato:\n"
                        "- [PROPOSTA] testo\n"
                        f"Solo le proposte concrete. Niente altro.\n\nDIBATTITO:\n{cycle_history_text[:2000]}"
                    )
                    result = call_openai(summary_prompt)
                    if result and "ERROR" not in result:
                        synthesis_content = result
                except Exception as e:
                    print(f"[REJECT] Sintesi ciclo fallita: {e}")

            if not synthesis_content:
                synthesis_content = cycle_history_text[:500] if cycle_history_text else "Ciclo senza proposte registrate."

            # Salva cycle_summary per il ciclo corrente
            save_debate_message(
                conn=conn,
                session_id=session_id,
                debate_id=debate_id,
                speaker="system",
                target_agent=None,
                message_type="cycle_summary",
                content=synthesis_content,
                status=None,
                round_index=0,
                revision_cycle=current_cycle
            )

            new_cycle = current_cycle + 1

            # Incrementa ciclo, resetta round_index, riporta a running
            cur.execute(
                """UPDATE group_chat_debates
                   SET revision_cycle = %s, round_index = 0, status = 'running',
                       decision_question = NULL, deciding_agent = NULL, updated_at = NOW()
                   WHERE debate_id = %s""",
                (new_cycle, debate_id)
            )
            conn.commit()

            # Salva motivazione reject di Christian nel nuovo ciclo
            if correction:
                save_debate_message(
                    conn=conn,
                    session_id=session_id,
                    debate_id=debate_id,
                    speaker="christian",
                    target_agent=next_agent,
                    message_type="user_input",
                    content=f"Non approvo. Correzione: {correction}",
                    status=None,
                    round_index=0,
                    revision_cycle=new_cycle
                )

            cur.close()
            conn.close()

            threading.Thread(
                target=run_group_chat_loop,
                args=(session_id, debate_id, next_agent, 10, DATABASE_URL),
                daemon=True
            ).start()

            return jsonify({
                "debate_id": debate_id,
                "status": "running",
                "next_agent": next_agent,
                "revision_cycle": new_cycle
            })

        else:
            cur.close()
            conn.close()
            return jsonify({"error": f"Action '{action}' non riconosciuta"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sessions/<session_id>/group-chat/<debate_id>/status", methods=["GET"])
def group_chat_status(session_id, debate_id):
    try:
        from backend.group_chat import get_debate_messages

        after_id = request.args.get("after_id", None)
        if after_id is not None:
            try:
                after_id = int(after_id)
            except ValueError:
                after_id = None

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """SELECT debate_id::text, session_id, status, current_agent,
                      next_agent, round_index, decision_question,
                      created_at, updated_at
               FROM group_chat_debates
               WHERE debate_id = %s AND session_id = %s""",
            (debate_id, session_id)
        )
        debate_row = cur.fetchone()
        cur.close()
        conn.close()

        if not debate_row:
            return jsonify({"error": "Debate non trovato"}), 404

        conn2 = get_db()
        messages = get_debate_messages(conn2, debate_id, after_id=after_id)
        conn2.close()

        result = dict(debate_row)
        if result.get("created_at"):
            result["created_at"] = result["created_at"].isoformat()
        if result.get("updated_at"):
            result["updated_at"] = result["updated_at"].isoformat()
        result["messages"] = messages

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API Progetti ──────────────────────────────────────────────────────────────

@app.route("/projects", methods=["GET"])
def list_projects():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects ORDER BY updated_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"projects": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/projects", methods=["POST"])
def create_project():
    try:
        data = request.get_json(force=True)
        project_id = str(uuid.uuid4())[:8]
        name = data.get("name", "Nuovo progetto")
        description = data.get("description", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO projects (id, name, description) VALUES (%s, %s, %s) RETURNING *",
            (project_id, name, description)
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE sessions SET project_id = NULL WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM project_memory WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/projects/<project_id>/memory", methods=["GET"])
def get_project_memory_api(project_id):
    memory = get_project_memory(project_id)
    return jsonify({"memory": memory})

@app.route("/profile", methods=["GET"])
def get_profile():
    return jsonify({"profile": get_user_profile()})

@app.route("/profile", methods=["POST"])
def update_profile():
    try:
        data = request.get_json(force=True)
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Contenuto vuoto"}), 400
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_profile (id, content, updated_at)
            VALUES (1, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET content = %s, updated_at = NOW()
        """, (content, content))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/global_memory", methods=["GET"])
def get_global_memory_api():
    memory = get_global_memory()
    return jsonify({"global_memory": memory, "empty": not bool(memory)})

# ── API Legacy ────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok", "version": "3.2"})

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        task = data.get("task", "")
        result = round_table(task)
        return jsonify({"task": task, "result": clean_result(result)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/backlog/add", methods=["POST"])
def backlog_add():
    try:
        data = request.get_json(force=True)
        task = data.get("task", "")
        max_rounds = int(data.get("max_rounds", 2))
        if not task:
            return jsonify({"status": "error", "message": "No task provided"}), 400

        backlog = load_backlog()
        start_time = time.time()

        try:
            result = round_table(task, max_rounds=max_rounds)
            execution_time = round(time.time() - start_time, 3)
            decision = result.get("decision", {})
            entry = {
                "task": task,
                "status": "done",
                "result": clean_result(result),
                "synthesis": decision.get("synthesis", ""),
                "summary": decision.get("summary", ""),
                "log": decision.get("log", []),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "execution_time": execution_time
            }
            backlog.append(entry)
            save_backlog(backlog)
            return jsonify(entry)
        except Exception as e:
            execution_time = round(time.time() - start_time, 3)
            entry = {
                "task": task,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "execution_time": execution_time
            }
            backlog.append(entry)
            save_backlog(backlog)
            return jsonify(entry), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/backlog/list", methods=["GET"])
def backlog_list():
    try:
        backlog = load_backlog()
        simplified = [
            {
                "task": t.get("task", ""),
                "status": t.get("status", ""),
                "result": t.get("result", ""),
                "synthesis": t.get("synthesis", ""),
                "summary": t.get("summary", ""),
                "timestamp": t.get("timestamp", ""),
                "execution_time": t.get("execution_time", ""),
                "log": t.get("log", [])
            }
            for t in backlog
        ]
        return jsonify({"status": "success", "backlog": simplified})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard", methods=["GET"])
def dashboard():
    html_template = r"""
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Helyas</title>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0a0f;
            --surface: #12121a;
            --surface2: #1a1a26;
            --border: #2a2a3a;
            --accent: #7c6fff;
            --accent2: #ff6b9d;
            --green: #4ade80;
            --amber: #fbbf24;
            --red: #f87171;
            --text: #e8e8f0;
            --muted: #6b6b85;
            --font: 'Syne', sans-serif;
            --mono: 'JetBrains Mono', monospace;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; display: flex; overflow: hidden; }
        .sidebar { width: 260px; min-width: 260px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
        .logo { padding: 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
        .logo-icon { font-size: 1.4rem; }
        .logo-text { font-size: 1.1rem; font-weight: 800; letter-spacing: -0.5px; }
        .logo-text span { color: var(--accent); }
        .new-session-btn { margin: 14px; padding: 10px 16px; background: var(--accent); color: white; border: none; border-radius: 8px; font-family: var(--font); font-size: 13px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: opacity 0.2s; }
        .new-session-btn:hover { opacity: 0.85; }
        .sessions-label { padding: 8px 16px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted); }
        .sessions-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
        .session-item { padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; color: var(--muted); transition: all 0.15s; border: 1px solid transparent; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .session-item:hover { background: var(--surface2); color: var(--text); }
        .session-item.active { background: var(--surface2); color: var(--text); border-color: var(--border); }
        .session-date { font-size: 10px; color: var(--muted); margin-top: 2px; font-family: var(--mono); }
        .session-row { cursor: pointer; flex: 1; }
        .session-name { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .session-actions { display: none; gap: 4px; margin-top: 4px; }
        .session-item:hover .session-actions { display: flex; }
        .action-btn { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--muted); font-size: 11px; padding: 2px 6px; cursor: pointer; }
        .action-btn:hover { background: var(--surface2); color: var(--text); }
        .action-btn.danger:hover { border-color: var(--red); color: var(--red); }
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; background: var(--surface); }
        .session-title { font-size: 15px; font-weight: 700; color: var(--text); }
        .session-title.placeholder { color: var(--muted); font-weight: 400; }
        .rounds-select { padding: 6px 12px; background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; font-family: var(--font); font-size: 12px; cursor: pointer; }
        .chat-area { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
        .empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--muted); }
        .empty-state .big-icon { font-size: 3rem; opacity: 0.4; }
        .empty-state p { font-size: 14px; text-align: center; max-width: 280px; line-height: 1.6; }
        .msg { display: flex; gap: 12px; max-width: 820px; }
        .msg.user { flex-direction: row-reverse; margin-left: auto; }
        .msg-avatar { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; font-weight: 700; }
        .msg.user .msg-avatar { background: var(--accent); color: white; }
        .msg.assistant .msg-avatar { background: var(--surface2); border: 1px solid var(--border); }
        .msg-body { flex: 1; }
        .msg.user .msg-bubble { background: var(--accent); color: white; border-radius: 12px 4px 12px 12px; padding: 12px 16px; font-size: 14px; line-height: 1.6; }
        .msg.assistant .msg-bubble { background: var(--surface2); border: 1px solid var(--border); border-radius: 4px 12px 12px 12px; padding: 14px 18px; font-size: 14px; line-height: 1.7; }
        .msg-meta { font-size: 11px; color: var(--muted); margin-top: 5px; font-family: var(--mono); }
        .msg.user .msg-meta { text-align: right; }
        .synthesis-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: var(--green); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
        .synthesis-label::before { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: var(--green); }
        .debate-toggle { margin-top: 12px; padding: 6px 12px; background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--muted); font-family: var(--font); font-size: 12px; cursor: pointer; transition: all 0.15s; }
        .debate-toggle:hover { border-color: var(--accent); color: var(--accent); }
        .debate-box { display: none; margin-top: 12px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
        .debate-box table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: var(--mono); }
        .debate-box th { background: var(--surface); padding: 8px 10px; text-align: left; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }
        .debate-box td { padding: 8px 10px; border-top: 1px solid var(--border); vertical-align: top; color: var(--text); }
        .role-Analyst { color: #60a5fa; }
        .role-Planner { color: var(--green); }
        .role-Builder { color: var(--amber); }
        .role-Critic { color: var(--red); }
        .agent-gpt { color: #10a37f; }
        .agent-claude { color: var(--amber); }
        .agent-gemini { color: #60a5fa; }
        .thinking { display: none; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; padding: 4px 0; }
        .thinking.visible { display: flex; }
        .dots { display: flex; gap: 4px; }
        .dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: bounce 1.2s infinite; }
        .dots span:nth-child(2) { animation-delay: 0.2s; }
        .dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }
        .input-area { padding: 16px 24px; border-top: 1px solid var(--border); background: var(--surface); display: flex; gap: 10px; align-items: flex-end; }
        .input-wrapper { flex: 1; position: relative; }
        .chat-input { width: 100%; padding: 12px 16px; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-family: var(--font); font-size: 14px; resize: none; min-height: 48px; max-height: 140px; line-height: 1.5; transition: border-color 0.2s; outline: none; }
        .chat-input:focus { border-color: var(--accent); }
        .chat-input::placeholder { color: var(--muted); }
        .send-btn { padding: 12px 20px; background: var(--accent); border: none; border-radius: 10px; color: white; font-family: var(--font); font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; white-space: nowrap; }
        .send-btn:hover:not(:disabled) { opacity: 0.85; }
        .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
        /* ── Group Chat Mode ── */
        :root { --gpt-color: #10a37f; --claude-color: #d97706; }
        .mode-toggle { display: flex; gap: 4px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 3px; }
        .mode-btn { padding: 5px 14px; border: none; border-radius: 6px; font-family: var(--font); font-size: 12px; font-weight: 600; cursor: pointer; background: transparent; color: var(--muted); transition: all 0.15s; }
        .mode-btn.active { background: var(--accent); color: white; }
        .gc-area { flex: 1; display: none; flex-direction: column; overflow: hidden; }
        .gc-messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 14px; }
        .gc-msg { border-radius: 10px; padding: 14px 18px; font-size: 14px; line-height: 1.7; border-left: 3px solid transparent; background: var(--surface2); }
        .gc-msg.christian { border-left-color: var(--text); }
        .gc-msg.gpt { border-left-color: var(--gpt-color); }
        .gc-msg.claude { border-left-color: var(--claude-color); }
        .gc-msg.system { border-left-color: var(--muted); opacity: 0.7; font-style: italic; font-size: 13px; }
        .gc-cycle-separator { padding: 12px 24px; text-align: center; }
        .gc-cycle-label { display: inline-block; padding: 4px 16px; font-size: 12px; color: var(--muted); border: 1px solid var(--border); border-radius: 20px; background: var(--surface); }
        .gc-speaker-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 6px; }
        .gc-speaker-label.christian { color: var(--text); }
        .gc-speaker-label.gpt { color: var(--gpt-color); }
        .gc-speaker-label.claude { color: var(--claude-color); }
        .gc-speaker-label.system { color: var(--muted); }
        .gc-round-badge { font-size: 10px; color: var(--muted); font-family: var(--mono); margin-left: 8px; font-weight: 400; }
        .gc-status-bar { display: none; align-items: center; gap: 10px; padding: 10px 24px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--border); background: var(--surface); }
        .gc-status-bar.visible { display: flex; }
        .gc-controls { display: none; flex-wrap: wrap; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--border); background: var(--surface); }
        .gc-controls.visible { display: flex; }
        .gc-btn { padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface2); color: var(--text); font-family: var(--font); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
        .gc-btn:hover { border-color: var(--accent); color: var(--accent); }
        .gc-btn.primary { background: var(--accent); color: white; border-color: var(--accent); }
        .gc-btn.primary:hover { opacity: 0.85; }
        .gc-btn.danger { border-color: var(--red); color: var(--red); }
        .gc-btn.danger:hover { background: var(--red); color: white; }
        .gc-start { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 16px; padding: 32px; }
        .gc-start-label { font-size: 13px; color: var(--muted); }
        .gc-start-buttons { display: flex; gap: 12px; }
        .gc-start-btn { padding: 12px 28px; border-radius: 10px; border: 1px solid var(--border); font-family: var(--font); font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
        .gc-start-btn.gpt { background: var(--gpt-color); color: white; border-color: var(--gpt-color); }
        .gc-start-btn.gpt:hover { opacity: 0.85; }
        .gc-start-btn.claude { background: var(--claude-color); color: white; border-color: var(--claude-color); }
        .gc-start-btn.claude:hover { opacity: 0.85; }
        .gc-decision-box { background: var(--surface2); border: 1px solid var(--amber); border-radius: 10px; padding: 14px 18px; margin: 0 24px 12px; font-size: 13px; }
        .gc-decision-box .gc-decision-q { color: var(--amber); font-weight: 700; margin-bottom: 8px; }
        .gc-decision-input { display: flex; gap: 8px; margin-top: 10px; }
        .gc-decision-input textarea { flex: 1; padding: 8px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-family: var(--font); font-size: 13px; resize: none; outline: none; }
        .gc-decision-input textarea:focus { border-color: var(--accent); }
    </style>
</head>
<body>
<div class="sidebar">
    <div class="logo">
        <span class="logo-icon">🧠</span>
        <span class="logo-text">He<span>lyas</span></span>
    </div>
    <button class="new-session-btn" onclick="newSession()">＋ Nuova sessione</button>
    <div class="sessions-label">Sessioni recenti</div>
    <div class="sessions-list" id="sessionsList"></div>
</div>
<div class="main">
    <div class="topbar">
        <div class="session-title placeholder" id="sessionTitle">Seleziona o crea una sessione</div>
        <div style="display:flex; gap:12px; align-items:center;">
            <div class="mode-toggle" style="display:none">
                <button class="mode-btn active" id="modeChatBtn" onclick="setMode('chat')">Chat</button>
                <button class="mode-btn" id="modeGCBtn" onclick="setMode('groupchat')">Group Chat</button>
            </div>
            <select class="rounds-select" id="roundsSelect">
                <option value="1">Rapida – 1 round</option>
                <option value="2" selected>Standard – 2 round</option>
                <option value="3">Approfondita – 3 round</option>
                <option value="5">Completa – 5 round</option>
            </select>
        </div>
    </div>
    <div class="chat-area" id="chatArea">
        <div class="empty-state" id="emptyState">
            <div class="big-icon">🧠</div>
            <p>Crea una nuova sessione e scrivi il tuo primo task.<br>Helyas analizzerà con più AI in parallelo.</p>
        </div>
    </div>
    <div class="thinking" id="thinking">
        <div class="dots"><span></span><span></span><span></span></div>
        <span>Helyas sta elaborando...</span>
    </div>
    <div class="input-area" id="chatInputArea">
        <div class="input-wrapper">
            <textarea class="chat-input" id="chatInput" placeholder="Scrivi un task o una domanda..." rows="1"></textarea>
        </div>
        <button class="send-btn" id="sendBtn" onclick="sendMessage()" disabled>Avvia ▶</button>
    </div>
    <!-- Group Chat Area -->
    <div class="gc-area" id="gcArea">
        <div class="gc-messages" id="gcMessages">
            <div class="gc-start" id="gcStart" style="display:none">
                <div class="gc-start-label">Scegli chi inizia il dibattito</div>
                <div class="gc-start-buttons">
                    <button class="gc-start-btn gpt" onclick="startGroupChat('gpt')">Parti con GPT</button>
                    <button class="gc-start-btn claude" onclick="startGroupChat('claude')">Parti con Claude</button>
                </div>
            </div>
        </div>
        <div class="gc-decision-box" id="gcDecisionBox" style="display:none">
            <div class="gc-decision-q" id="gcDecisionQuestion"></div>
            <div class="gc-decision-input">
                <textarea id="gcDecisionAnswer" placeholder="La tua risposta..." rows="2"></textarea>
                <button class="gc-btn primary" onclick="continueWithDecision()">Continua</button>
            </div>
        </div>
        <div class="gc-status-bar" id="gcStatusBar">
            <div class="dots"><span></span><span></span><span></span></div>
            <span id="gcStatusText">In elaborazione...</span>
        </div>
        <div id="gcStopWrap" style="display:none; padding:8px 24px; border-top:1px solid var(--border); background:var(--surface);">
            <button class="gc-btn danger" onclick="stopDebate()">Stop</button>
        </div>
        <div class="gc-controls" id="gcControls">
            <button class="gc-btn" onclick="summarizeDebate()">Sintesi</button>
            <button class="gc-btn primary" onclick="approveDebate()">Approvo</button>
            <button class="gc-btn" onclick="rejectDebate()">Non approvo</button>
        </div>
        <div class="input-area" id="gcInputArea" style="display:none">
            <div class="input-wrapper">
                <textarea class="chat-input" id="gcInput" placeholder="Scrivi per Group Chat..." rows="1"></textarea>
            </div>
            <div style="display:flex; gap:8px;">
                <button class="gc-start-btn gpt" style="padding:10px 16px; font-size:12px;" onclick="startGroupChat('gpt')">GPT</button>
                <button class="gc-start-btn claude" style="padding:10px 16px; font-size:12px;" onclick="startGroupChat('claude')">Claude</button>
            </div>
        </div>
    </div>
</div>
<script>
let currentSessionId = null;
let debateCounter = 0;
function markdownToHtml(text) {
    if (!text) return '';
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
}
function formatDate(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short' }) + ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}
async function loadSessions() {
    try {
        const res = await fetch('/sessions');
        const data = await res.json();
        const list = document.getElementById('sessionsList');
        list.innerHTML = '';
        (data.sessions || []).forEach(s => {
            const div = document.createElement('div');
            div.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
            div.innerHTML = `<div class="session-row" onclick="openSession('${s.id}', '${(s.title||'Sessione').replace(/'/g,"\\'")}')"><div class="session-name">${s.title || 'Sessione'}</div><div class="session-date">${formatDate(s.updated_at)}</div></div><div class="session-actions"><button class="action-btn" title="Rinomina" onclick="event.stopPropagation(); renameSession('${s.id}', '${(s.title||'Sessione').replace(/'/g,"\\'")}')">✏️</button><button class="action-btn danger" title="Elimina" onclick="event.stopPropagation(); deleteSession('${s.id}')">🗑️</button></div>`;
            list.appendChild(div);
        });
    } catch(e) { console.error(e); }
}
async function renameSession(sessionId, currentTitle) {
    const newTitle = prompt('Nuovo nome sessione:', currentTitle);
    if (!newTitle || newTitle === currentTitle) return;
    try {
        await fetch(`/sessions/${sessionId}`, { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: newTitle }) });
        if (currentSessionId === sessionId) document.getElementById('sessionTitle').textContent = newTitle;
        loadSessions();
    } catch(e) { console.error(e); }
}
async function deleteSession(sessionId) {
    if (!confirm('Eliminare questa sessione?')) return;
    try {
        await fetch(`/sessions/${sessionId}`, { method: 'DELETE' });
        if (currentSessionId === sessionId) {
            currentSessionId = null;
            document.getElementById('sessionTitle').textContent = 'Seleziona o crea una sessione';
            document.getElementById('sessionTitle').classList.add('placeholder');
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('chatArea').innerHTML = '';
        }
        loadSessions();
    } catch(e) { console.error(e); }
}
async function newSession() {
    try {
        const res = await fetch('/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: 'Nuova sessione' }) });
        const s = await res.json();
        openSession(s.id, s.title);
        loadSessions();
    } catch(e) { console.error(e); }
}
async function openSession(sessionId, title) {
    currentSessionId = sessionId;
    resetGCState();
    document.getElementById('sessionTitle').textContent = title || 'Sessione';
    document.getElementById('sessionTitle').classList.remove('placeholder');
    document.getElementById('sendBtn').disabled = false;
    document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
    const chatArea = document.getElementById('chatArea');
    chatArea.innerHTML = '';
    try {
        const res = await fetch(`/sessions/${sessionId}/messages`);
        const data = await res.json();
        const msgs = data.messages || [];
        if (msgs.length === 0) {
            chatArea.innerHTML = `<div class="empty-state"><div class="big-icon">💬</div><p>Sessione vuota. Scrivi il tuo primo messaggio!</p></div>`;
        } else {
            msgs.forEach(m => renderMessage(m));
        }
    } catch(e) { console.error(e); }
    chatArea.scrollTop = chatArea.scrollHeight;
}
function renderMessage(msg) {
    const chatArea = document.getElementById('chatArea');
    const isUser = msg.role === 'user';
    const div = document.createElement('div');
    div.className = `msg ${msg.role}`;
    const content = msg.synthesis || msg.content || '';
    const log = msg.log || [];
    let debateHTML = '';
    if (!isUser && log.length > 0) {
        const id = 'db-' + (debateCounter++);
        let rows = '';
        log.forEach(e => {
            const ac = 'agent-' + (e.agent === 'ChatGPT' ? 'gpt' : e.agent === 'Claude' ? 'claude' : 'gemini');
            const rc = 'role-' + (e.role || '');
            rows += `<tr><td class="${ac}">${e.agent}</td><td class="${rc}">${e.role}</td><td>${markdownToHtml(e.proposal || '')}</td><td>${(e.risks||[]).join('<br>')}</td></tr>`;
        });
        debateHTML = `<button class="debate-toggle" onclick="toggleDebate('${id}')">📋 Dibattito completo (${log.length} contributi)</button><div class="debate-box" id="${id}"><table><tr><th>Agente</th><th>Ruolo</th><th>Proposta</th><th>Rischi</th></tr>${rows}</table></div>`;
    }
    const timeStr = msg.execution_time ? ` · ${msg.execution_time}s` : '';
    const dateStr = formatDate(msg.created_at);
    if (isUser) {
        div.innerHTML = `<div class="msg-avatar">C</div><div class="msg-body"><div class="msg-bubble">${markdownToHtml(msg.content)}</div><div class="msg-meta">${dateStr}</div></div>`;
    } else {
        div.innerHTML = `<div class="msg-avatar">🧠</div><div class="msg-body"><div class="msg-bubble"><div class="synthesis-label">Sintesi Helyas</div>${markdownToHtml(content)}${debateHTML}</div><div class="msg-meta">${dateStr}${timeStr}</div></div>`;
    }
    chatArea.appendChild(div);
}
function toggleDebate(id) {
    const box = document.getElementById(id);
    box.style.display = box.style.display === 'block' ? 'none' : 'block';
}
async function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;
    if (!currentSessionId) {
        const res = await fetch('/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: 'Nuova sessione' }) });
        const s = await res.json();
        currentSessionId = s.id;
        document.getElementById('sessionTitle').textContent = s.title;
        document.getElementById('sessionTitle').classList.remove('placeholder');
        loadSessions();
    }
    const rounds = parseInt(document.getElementById('roundsSelect').value);
    renderMessage({ role: 'user', content: message, created_at: new Date().toISOString() });
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('thinking').classList.add('visible');
    document.getElementById('sendBtn').disabled = true;
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;
    try {
        const res = await fetch(`/sessions/${currentSessionId}/chat`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ message, max_rounds: rounds }) });
        const msg = await res.json();
        renderMessage(msg);
        loadSessions();
    } catch(e) {
        renderMessage({ role: 'assistant', content: '⚠️ Errore: ' + e.message, created_at: new Date().toISOString() });
    } finally {
        document.getElementById('thinking').classList.remove('visible');
        document.getElementById('sendBtn').disabled = false;
        chatArea.scrollTop = chatArea.scrollHeight;
    }
}
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('chatInput');
    input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    const gcInput = document.getElementById('gcInput');
    if (gcInput) {
        gcInput.addEventListener('input', () => { gcInput.style.height = 'auto'; gcInput.style.height = Math.min(gcInput.scrollHeight, 140) + 'px'; });
    }
    loadSessions();
    setMode('groupchat');
});

/* ── Group Chat JavaScript ── */
let currentDebateId = null;
let gcPollingInterval = null;
let lastMessageId = 0;
let currentGCMode = false;

function setMode(mode) {
    currentGCMode = (mode === 'groupchat');
    document.getElementById('modeChatBtn').classList.toggle('active', !currentGCMode);
    document.getElementById('modeGCBtn').classList.toggle('active', currentGCMode);

    const chatArea = document.getElementById('chatArea');
    const chatThinking = document.getElementById('thinking');
    const chatInputArea = document.getElementById('chatInputArea');
    const gcArea = document.getElementById('gcArea');

    if (currentGCMode) {
        chatArea.style.display = 'none';
        chatThinking.style.display = 'none';
        chatInputArea.style.display = 'none';
        gcArea.style.display = 'flex';
        gcArea.style.flexDirection = 'column';
        document.getElementById('roundsSelect').style.display = 'none';
        if (currentSessionId) {
            document.getElementById('gcInputArea').style.display = 'flex';
            document.getElementById('gcStart').style.display = 'none';
        } else {
            document.getElementById('gcInputArea').style.display = 'none';
            document.getElementById('gcStart').style.display = 'none';
        }
    } else {
        chatArea.style.display = 'flex';
        chatArea.style.flexDirection = 'column';
        chatThinking.style.display = '';
        chatInputArea.style.display = 'flex';
        gcArea.style.display = 'none';
        document.getElementById('roundsSelect').style.display = '';
    }
}

function renderGCMessage(msg) {
    const container = document.getElementById('gcMessages');
    const startEl = document.getElementById('gcStart');
    if (startEl) startEl.style.display = 'none';

    const div = document.createElement('div');

    if (msg.message_type === 'cycle_summary') {
        div.className = 'gc-cycle-separator';
        div.innerHTML = '<div class="gc-cycle-label">↻ Revisione dopo feedback di Christian</div>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return;
    }

    const speaker = msg.speaker || 'system';
    div.className = `gc-msg ${speaker}`;
    const labelMap = { christian: 'Christian', gpt: 'ChatGPT', claude: 'Claude', system: 'Sistema' };
    const label = labelMap[speaker] || speaker;
    const content = (msg.content || '').replace(/\n/g, '<br>');
    div.innerHTML = `<div class="gc-speaker-label ${speaker}">${label}</div><div>${content}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function startPolling() {
    if (gcPollingInterval) clearInterval(gcPollingInterval);
    gcPollingInterval = setInterval(pollStatus, 2500);
}

function stopPolling() {
    if (gcPollingInterval) { clearInterval(gcPollingInterval); gcPollingInterval = null; }
}

function updateStopVisibility() {
    const stopWrap = document.getElementById('gcStopWrap');
    if (stopWrap) stopWrap.style.display = currentDebateId ? 'flex' : 'none';
}

function resetGCState() {
    stopPolling();
    currentDebateId = null;
    lastMessageId = 0;
    document.getElementById('gcMessages').innerHTML = '';
    document.getElementById('gcDecisionBox').style.display = 'none';
    const gcDecisionAnswer = document.getElementById('gcDecisionAnswer');
    if (gcDecisionAnswer) gcDecisionAnswer.value = '';
    document.getElementById('gcDecisionQuestion').textContent = '';
    document.getElementById('gcControls').classList.remove('visible');
    document.getElementById('gcStatusBar').classList.remove('visible');
    updateStopVisibility();
    if (currentSessionId) {
        document.getElementById('gcInputArea').style.display = 'flex';
        document.getElementById('gcStart').style.display = 'none';
    }
}

async function pollStatus() {
    if (!currentSessionId || !currentDebateId) return;
    try {
        const url = `/sessions/${currentSessionId}/group-chat/${currentDebateId}/status?after_id=${lastMessageId}`;
        const res = await fetch(url);
        const data = await res.json();
        if (data.error) { stopPolling(); return; }

        const msgs = data.messages || [];
        msgs.forEach(msg => { if (msg.id > lastMessageId) lastMessageId = msg.id; });
        msgs.forEach(msg => renderGCMessage(msg));

        handleDebateStatus(data.status, data.decision_question);
    } catch(e) {
        console.error('[GC Poll]', e);
    }
}

function handleDebateStatus(status, decisionQuestion) {
    const statusBar = document.getElementById('gcStatusBar');
    const statusText = document.getElementById('gcStatusText');
    const controls = document.getElementById('gcControls');
    const decisionBox = document.getElementById('gcDecisionBox');
    const gcInputArea = document.getElementById('gcInputArea');

    if (status === 'running') {
        statusBar.classList.add('visible');
        statusText.textContent = 'Agenti in elaborazione...';
        controls.classList.remove('visible');
        if (decisionBox.style.display !== 'none') decisionBox.style.display = 'none';
    } else {
        stopPolling();
        statusBar.classList.remove('visible');

        if (status === 'needs_decision') {
            decisionBox.style.display = 'block';
            document.getElementById('gcDecisionQuestion').textContent = decisionQuestion || 'Serve una tua decisione per continuare.';
            controls.classList.remove('visible');
        } else if (status === 'ready') {
            controls.classList.add('visible');
            decisionBox.style.display = 'none';
        } else if (status === 'stopped' || status === 'safety_limit') {
            controls.classList.add('visible');
            gcInputArea.style.display = 'flex';
        } else if (status === 'error') {
            statusBar.classList.add('visible');
            statusText.textContent = 'Errore durante il dibattito. Consulta il log.';
        }
    }
    updateStopVisibility();
}

async function startGroupChat(firstSpeaker) {
    if (!currentSessionId) {
        alert('Seleziona o crea una sessione prima di avviare Group Chat.');
        return;
    }
    const gcInputEl = document.getElementById('gcInput');
    const message = gcInputEl.value.trim();
    if (!message) { alert('Scrivi un messaggio prima di avviare il dibattito.'); return; }

    // Reset UI
    lastMessageId = 0;
    currentDebateId = null;
    document.getElementById('gcMessages').innerHTML = '';
    document.getElementById('gcDecisionBox').style.display = 'none';
    document.getElementById('gcControls').classList.remove('visible');
    document.getElementById('gcInputArea').style.display = 'none';

    // Mostra stato
    const statusBar = document.getElementById('gcStatusBar');
    const statusText = document.getElementById('gcStatusText');
    statusBar.classList.add('visible');
    statusText.textContent = 'Dibattito avviato, attendo risposte...';
    gcInputEl.value = '';

    try {
        const res = await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'start', message, first_speaker: firstSpeaker })
        });
        const data = await res.json();
        if (data.error) {
            statusText.textContent = 'Errore: ' + data.error;
            return;
        }
        currentDebateId = data.debate_id;
        updateStopVisibility();
        startPolling();
    } catch(e) {
        statusText.textContent = 'Errore di rete: ' + e.message;
    }
}

async function stopDebate() {
    if (!currentDebateId) return;
    stopPolling();
    try {
        await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'stop', debate_id: currentDebateId })
        });
    } catch(e) { console.error(e); }
    handleDebateStatus('stopped', null);
    renderGCMessage({ speaker: 'system', content: 'Dibattito fermato.', round_index: 0 });
}

async function summarizeDebate() {
    if (!currentDebateId) return;
    document.getElementById('gcStatusBar').classList.add('visible');
    document.getElementById('gcStatusText').textContent = 'Generazione sintesi...';
    document.getElementById('gcControls').classList.remove('visible');
    try {
        const res = await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'summarize', debate_id: currentDebateId })
        });
        const data = await res.json();
        document.getElementById('gcStatusBar').classList.remove('visible');
        if (data.synthesis) {
            renderGCMessage({ speaker: 'system', content: data.synthesis, round_index: 0 });
        }
        document.getElementById('gcControls').classList.add('visible');
    } catch(e) {
        document.getElementById('gcStatusText').textContent = 'Errore sintesi: ' + e.message;
    }
}

async function approveDebate() {
    if (!currentDebateId) return;
    try {
        await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'approve', debate_id: currentDebateId })
        });
    } catch(e) { console.error(e); }
    renderGCMessage({ speaker: 'system', content: 'Output approvato da Christian.', round_index: 0 });
    document.getElementById('gcControls').classList.remove('visible');
    currentDebateId = null;
    updateStopVisibility();
    document.getElementById('gcInputArea').style.display = 'flex';
}

async function rejectDebate() {
    if (!currentDebateId) return;
    const correction = prompt('Cosa vuoi correggere o aggiungere?', '');
    if (correction === null) return;
    document.getElementById('gcStatusBar').classList.add('visible');
    document.getElementById('gcStatusText').textContent = 'Riprendendo il dibattito...';
    document.getElementById('gcControls').classList.remove('visible');
    if (correction.trim()) {
        renderGCMessage({ speaker: 'christian', content: 'Non approvo. ' + correction, round_index: 0 });
    }
    lastMessageId = 0;
    try {
        const res = await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'reject', debate_id: currentDebateId, correction })
        });
        const data = await res.json();
        if (!data.error) startPolling();
        else document.getElementById('gcStatusText').textContent = 'Errore: ' + data.error;
    } catch(e) {
        document.getElementById('gcStatusText').textContent = 'Errore: ' + e.message;
    }
}

async function continueWithDecision() {
    if (!currentDebateId) return;
    const answer = document.getElementById('gcDecisionAnswer').value.trim();
    document.getElementById('gcDecisionBox').style.display = 'none';
    document.getElementById('gcStatusBar').classList.add('visible');
    document.getElementById('gcStatusText').textContent = 'Riprendendo il dibattito...';
    try {
        const res = await fetch(`/sessions/${currentSessionId}/group-chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'continue', debate_id: currentDebateId, message: answer })
        });
        const data = await res.json();
        if (!data.error) {
            document.getElementById('gcDecisionAnswer').value = '';
            document.getElementById('gcDecisionQuestion').textContent = '';
            startPolling();
        }
    } catch(e) {
        document.getElementById('gcStatusText').textContent = 'Errore: ' + e.message;
    }
}
</script>
</body>
</html>
    """
    return render_template_string(html_template)

# ── Avvio ─────────────────────────────────────────────────────────────────────

_db_initialized = False

@app.before_request
def lazy_init_db():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            print(f"[DB INIT WARNING] {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
