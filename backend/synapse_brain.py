from flask import Flask, request, jsonify, render_template_string
from backend.orchestrator import round_table
import json
import os
import time
import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Database ─────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    """Crea le tabelle se non esistono."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
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
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")

# ── Backlog (compatibilità con versioni precedenti) ───────────────────────────

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

        # Costruisce contesto testuale per gli agenti
        session_context = []
        for row in history_rows:
            session_context.append({
                "role": row["role"],
                "content": row["synthesis"] or row["content"]
            })

        # Aggiorna titolo sessione al primo messaggio utente
        cur.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = %s AND role = 'user'", (session_id,))
        count = cur.fetchone()["cnt"]
        if count == 1:
            title = user_message[:50] + ("..." if len(user_message) > 50 else "")
            cur.execute("UPDATE sessions SET title = %s WHERE id = %s", (title, session_id))

        conn.commit()

        # Esegui round table con contesto sessione
        start_time = time.time()
        result = round_table(user_message, max_rounds=max_rounds, session_context=session_context)
        execution_time = round(time.time() - start_time, 3)

        decision = result.get("decision", {})
        synthesis = decision.get("synthesis", "")
        log = decision.get("log", [])

        # Salva risposta assistant
        cur.execute(
            """INSERT INTO messages (session_id, role, content, synthesis, log, execution_time)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (session_id, "assistant", clean_result(result), synthesis, json.dumps(log), execution_time)
        )
        msg = dict(cur.fetchone())

        # Aggiorna updated_at sessione
        cur.execute("UPDATE sessions SET updated_at = NOW() WHERE id = %s", (session_id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify(msg)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── API Legacy ────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok", "version": "3.1"})

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

        /* Sidebar */
        .sidebar {
            width: 260px; min-width: 260px; background: var(--surface);
            border-right: 1px solid var(--border); display: flex; flex-direction: column;
        }
        .logo {
            padding: 20px; border-bottom: 1px solid var(--border);
            display: flex; align-items: center; gap: 10px;
        }
        .logo-icon { font-size: 1.4rem; }
        .logo-text { font-size: 1.1rem; font-weight: 800; letter-spacing: -0.5px; }
        .logo-text span { color: var(--accent); }
        .new-session-btn {
            margin: 14px; padding: 10px 16px;
            background: var(--accent); color: white; border: none;
            border-radius: 8px; font-family: var(--font); font-size: 13px;
            font-weight: 600; cursor: pointer; display: flex; align-items: center;
            gap: 8px; transition: opacity 0.2s;
        }
        .new-session-btn:hover { opacity: 0.85; }
        .sessions-label {
            padding: 8px 16px; font-size: 10px; font-weight: 700;
            text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted);
        }
        .sessions-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
        .session-item {
            padding: 10px 12px; border-radius: 8px; cursor: pointer;
            font-size: 13px; color: var(--muted); transition: all 0.15s;
            border: 1px solid transparent; margin-bottom: 2px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .session-item:hover { background: var(--surface2); color: var(--text); }
        .session-item.active { background: var(--surface2); color: var(--text); border-color: var(--border); }
        .session-date { font-size: 10px; color: var(--muted); margin-top: 2px; font-family: var(--mono); }

        /* Main */
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar {
            padding: 16px 24px; border-bottom: 1px solid var(--border);
            display: flex; align-items: center; justify-content: space-between;
            background: var(--surface);
        }
        .session-title { font-size: 15px; font-weight: 700; color: var(--text); }
        .session-title.placeholder { color: var(--muted); font-weight: 400; }
        .rounds-select {
            padding: 6px 12px; background: var(--surface2); border: 1px solid var(--border);
            color: var(--text); border-radius: 6px; font-family: var(--font);
            font-size: 12px; cursor: pointer;
        }

        /* Chat area */
        .chat-area { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
        .empty-state {
            flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 12px; color: var(--muted);
        }
        .empty-state .big-icon { font-size: 3rem; opacity: 0.4; }
        .empty-state p { font-size: 14px; text-align: center; max-width: 280px; line-height: 1.6; }

        /* Messages */
        .msg { display: flex; gap: 12px; max-width: 820px; }
        .msg.user { flex-direction: row-reverse; margin-left: auto; }
        .msg-avatar {
            width: 32px; height: 32px; border-radius: 8px; display: flex;
            align-items: center; justify-content: center; font-size: 14px;
            flex-shrink: 0; font-weight: 700;
        }
        .msg.user .msg-avatar { background: var(--accent); color: white; }
        .msg.assistant .msg-avatar { background: var(--surface2); border: 1px solid var(--border); }
        .msg-body { flex: 1; }
        .msg.user .msg-bubble {
            background: var(--accent); color: white; border-radius: 12px 4px 12px 12px;
            padding: 12px 16px; font-size: 14px; line-height: 1.6;
        }
        .msg.assistant .msg-bubble {
            background: var(--surface2); border: 1px solid var(--border);
            border-radius: 4px 12px 12px 12px; padding: 14px 18px;
            font-size: 14px; line-height: 1.7;
        }
        .msg-meta { font-size: 11px; color: var(--muted); margin-top: 5px; font-family: var(--mono); }
        .msg.user .msg-meta { text-align: right; }

        /* Synthesis box */
        .synthesis-label {
            font-size: 10px; font-weight: 700; text-transform: uppercase;
            letter-spacing: 1.2px; color: var(--green); margin-bottom: 8px;
            display: flex; align-items: center; gap: 6px;
        }
        .synthesis-label::before { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: var(--green); }

        /* Debate toggle */
        .debate-toggle {
            margin-top: 12px; padding: 6px 12px;
            background: transparent; border: 1px solid var(--border);
            border-radius: 6px; color: var(--muted); font-family: var(--font);
            font-size: 12px; cursor: pointer; transition: all 0.15s;
        }
        .debate-toggle:hover { border-color: var(--accent); color: var(--accent); }
        .debate-box { display: none; margin-top: 12px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
        .debate-box table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: var(--mono); }
        .debate-box th { background: var(--surface); padding: 8px 10px; text-align: left; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }
        .debate-box td { padding: 8px 10px; border-top: 1px solid var(--border); vertical-align: top; color: var(--text); }
        .role-Analyst { color: #60a5fa; }
        .role-Planner { color: var(--green); }
        .role-Builder { color: var(--amber); }
        .role-Critic  { color: var(--red); }
        .agent-gpt { color: #10a37f; }
        .agent-claude { color: var(--amber); }
        .agent-gemini { color: #60a5fa; }

        /* Thinking indicator */
        .thinking {
            display: none; align-items: center; gap: 10px;
            color: var(--muted); font-size: 13px; padding: 4px 0;
        }
        .thinking.visible { display: flex; }
        .dots { display: flex; gap: 4px; }
        .dots span {
            width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
            animation: bounce 1.2s infinite;
        }
        .dots span:nth-child(2) { animation-delay: 0.2s; }
        .dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

        /* Input area */
        .input-area {
            padding: 16px 24px; border-top: 1px solid var(--border);
            background: var(--surface); display: flex; gap: 10px; align-items: flex-end;
        }
        .input-wrapper { flex: 1; position: relative; }
        .chat-input {
            width: 100%; padding: 12px 16px; background: var(--surface2);
            border: 1px solid var(--border); border-radius: 10px;
            color: var(--text); font-family: var(--font); font-size: 14px;
            resize: none; min-height: 48px; max-height: 140px; line-height: 1.5;
            transition: border-color 0.2s; outline: none;
        }
        .chat-input:focus { border-color: var(--accent); }
        .chat-input::placeholder { color: var(--muted); }
        .send-btn {
            padding: 12px 20px; background: var(--accent); border: none;
            border-radius: 10px; color: white; font-family: var(--font);
            font-size: 14px; font-weight: 600; cursor: pointer;
            transition: opacity 0.2s; white-space: nowrap;
        }
        .send-btn:hover:not(:disabled) { opacity: 0.85; }
        .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
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
        <select class="rounds-select" id="roundsSelect">
            <option value="1">Rapida – 1 round</option>
            <option value="2" selected>Standard – 2 round</option>
            <option value="3">Approfondita – 3 round</option>
            <option value="5">Completa – 5 round</option>
        </select>
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

    <div class="input-area">
        <div class="input-wrapper">
            <textarea class="chat-input" id="chatInput" placeholder="Scrivi un task o una domanda..." rows="1"></textarea>
        </div>
        <button class="send-btn" id="sendBtn" onclick="sendMessage()" disabled>Avvia ▶</button>
    </div>
</div>

<script>
let currentSessionId = null;
let debateCounter = 0;

function markdownToHtml(text) {
    if (!text) return '';
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

function formatDate(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short' }) + ' ' +
           d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
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
            div.innerHTML = `<div>${s.title || 'Sessione'}</div><div class="session-date">${formatDate(s.updated_at)}</div>`;
            div.onclick = () => openSession(s.id, s.title);
            list.appendChild(div);
        });
    } catch(e) { console.error(e); }
}

async function newSession() {
    try {
        const res = await fetch('/sessions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title: 'Nuova sessione' })
        });
        const s = await res.json();
        openSession(s.id, s.title);
        loadSessions();
    } catch(e) { console.error(e); }
}

async function openSession(sessionId, title) {
    currentSessionId = sessionId;
    document.getElementById('sessionTitle').textContent = title || 'Sessione';
    document.getElementById('sessionTitle').classList.remove('placeholder');
    document.getElementById('sendBtn').disabled = false;

    // Evidenzia sessione attiva
    document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.session-item').forEach(el => {
        if (el.querySelector('div')?.textContent === (title || 'Sessione')) el.classList.add('active');
    });

    // Carica messaggi
    const chatArea = document.getElementById('chatArea');
    chatArea.innerHTML = '';
    document.getElementById('emptyState') && (document.getElementById('emptyState').style.display = 'none');

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
            rows += `<tr>
                <td class="${ac}">${e.agent}</td>
                <td class="${rc}">${e.role}</td>
                <td>${markdownToHtml(e.proposal || '')}</td>
                <td>${(e.risks||[]).join('<br>')}</td>
            </tr>`;
        });
        debateHTML = `
            <button class="debate-toggle" onclick="toggleDebate('${id}')">📋 Dibattito completo (${log.length} contributi)</button>
            <div class="debate-box" id="${id}">
                <table>
                    <tr><th>Agente</th><th>Ruolo</th><th>Proposta</th><th>Rischi</th></tr>
                    ${rows}
                </table>
            </div>`;
    }

    const timeStr = msg.execution_time ? ` · ${msg.execution_time}s` : '';
    const dateStr = formatDate(msg.created_at);

    if (isUser) {
        div.innerHTML = `
            <div class="msg-avatar">C</div>
            <div class="msg-body">
                <div class="msg-bubble">${markdownToHtml(msg.content)}</div>
                <div class="msg-meta">${dateStr}</div>
            </div>`;
    } else {
        div.innerHTML = `
            <div class="msg-avatar">🧠</div>
            <div class="msg-body">
                <div class="msg-bubble">
                    <div class="synthesis-label">Sintesi Helyas</div>
                    ${markdownToHtml(content)}
                    ${debateHTML}
                </div>
                <div class="msg-meta">${dateStr}${timeStr}</div>
            </div>`;
    }

    chatArea.appendChild(div);
}

function toggleDebate(id) {
    const box = document.getElementById(id);
    box.style.display = box.style.display === 'block' ? 'none' : 'block';
}

async function sendMessage() {
    if (!currentSessionId) return;
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    const rounds = parseInt(document.getElementById('roundsSelect').value);

    // Render messaggio utente subito
    renderMessage({ role: 'user', content: message, created_at: new Date().toISOString() });
    input.value = '';
    input.style.height = 'auto';

    document.getElementById('thinking').classList.add('visible');
    document.getElementById('sendBtn').disabled = true;

    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;

    try {
        const res = await fetch(`/sessions/${currentSessionId}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message, max_rounds: rounds })
        });
        const msg = await res.json();
        renderMessage(msg);
        loadSessions(); // aggiorna titolo nella sidebar
    } catch(e) {
        renderMessage({ role: 'assistant', content: '⚠️ Errore: ' + e.message, created_at: new Date().toISOString() });
    } finally {
        document.getElementById('thinking').classList.remove('visible');
        document.getElementById('sendBtn').disabled = false;
        chatArea.scrollTop = chatArea.scrollHeight;
    }
}

// Auto-resize textarea
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('chatInput');
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 140) + 'px';
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    loadSessions();
});
</script>
</body>
</html>
    """
    return render_template_string(html_template)

# ── Avvio ─────────────────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
