from flask import Flask, request, jsonify, render_template_string
from backend.orchestrator import round_table
import json
import os
import time
from datetime import datetime

app = Flask(__name__)

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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok"})

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
        if not task:
            return jsonify({"status": "error", "message": "No task provided"}), 400

        backlog = load_backlog()
        start_time = time.time()

        try:
            result = round_table(task)
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

@app.route("/scheduler/run", methods=["POST"])
def scheduler_run():
    try:
        backlog = load_backlog()
        results = []
        for task in backlog:
            if task.get("status") == "pending":
                start_time = time.time()
                try:
                    result = round_table(task["task"])
                    execution_time = round(time.time() - start_time, 3)
                    decision = result.get("decision", {})
                    task["status"] = "done"
                    task["result"] = clean_result(result)
                    task["synthesis"] = decision.get("synthesis", "")
                    task["log"] = decision.get("log", [])
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["execution_time"] = execution_time
                    results.append(task)
                except Exception as e:
                    task["status"] = "error"
                    task["error"] = str(e)
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    results.append(task)
        save_backlog(backlog)
        return jsonify({"status": "success", "processed": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/dashboard", methods=["GET"])
def dashboard():
    html_template = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Helyas Dashboard</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #222; }
            header { background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 20px 30px; display: flex; align-items: center; gap: 12px; }
            header h1 { font-size: 1.6rem; font-weight: 600; }
            header span { font-size: 1.8rem; }
            .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; }
            .input-box { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 24px; display: flex; gap: 10px; align-items: center; }
            .input-box input { flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 15px; }
            .input-box select { padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; background: white; }
            .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
            .btn-primary { background: #4f46e5; color: white; }
            .btn-primary:hover { background: #4338ca; }
            .btn-secondary { background: #e5e7eb; color: #374151; }
            .btn-secondary:hover { background: #d1d5db; }
            .loading { display: none; text-align: center; padding: 20px; color: #6b7280; font-style: italic; }
            .task-card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #4f46e5; }
            .task-card.error { border-left-color: #ef4444; }
            .task-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
            .task-title { font-weight: 700; font-size: 1rem; color: #1f2937; flex: 1; }
            .task-meta { font-size: 12px; color: #9ca3af; text-align: right; margin-left: 10px; }
            .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 8px; }
            .badge-done { background: #d1fae5; color: #065f46; }
            .badge-error { background: #fee2e2; color: #991b1b; }
            .synthesis-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px; margin-bottom: 12px; font-size: 14px; line-height: 1.6; }
            .synthesis-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #059669; margin-bottom: 6px; }
            .toggle-btn { background: none; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer; color: #6b7280; }
            .toggle-btn:hover { background: #f9fafb; }
            .debate-box { display: none; margin-top: 14px; }
            .debate-box table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .debate-box th { background: #f3f4f6; padding: 8px 10px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; }
            .debate-box td { padding: 8px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
            .debate-box tr:last-child td { border-bottom: none; }
            .role-Analyst { color: #2563eb; font-weight: 700; }
            .role-Planner { color: #16a34a; font-weight: 700; }
            .role-Builder { color: #d97706; font-weight: 700; }
            .role-Critic  { color: #dc2626; font-weight: 700; }
            .agent-gpt { color: #10a37f; font-weight: 600; }
            .agent-claude { color: #c17f24; font-weight: 600; }
            .agent-gemini { color: #4285f4; font-weight: 600; }
            .empty { text-align: center; color: #9ca3af; padding: 40px; font-size: 15px; }
        </style>
    </head>
    <body>
        <header>
            <span>🧠</span>
            <h1>Helyas – Round Table AI</h1>
        </header>
        <div class="container">
            <div class="input-box">
                <input type="text" id="taskInput" placeholder="Scrivi un task per Helyas..." />
                <select id="roundsSelect">
                    <option value="1">Rapida (1 round)</option>
                    <option value="2" selected>Standard (2 round)</option>
                    <option value="3">Approfondita (3 round)</option>
                    <option value="5">Completa (5 round)</option>
                    <option value="8">Massima (8 round)</option>
                </select>
                <button class="btn btn-primary" onclick="addTask()">▶ Avvia</button>
                <button class="btn btn-secondary" onclick="loadTasks()">↻ Aggiorna</button>
            </div>
            <div class="loading" id="loading">⏳ Helyas sta elaborando... potrebbe richiedere 1-3 minuti.</div>
            <div id="taskList"></div>
        </div>
        <script>
            function markdownToHtml(text) {
                if (!text) return '';
                return text
                    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                    .replace(/\\n/g, '<br>');
            }

            async function addTask() {
                const task = document.getElementById('taskInput').value.trim();
                const rounds = document.getElementById('roundsSelect').value;
                if (!task) { alert("Inserisci un task!"); return; }
                document.getElementById('loading').style.display = 'block';
                document.querySelector('.btn-primary').disabled = true;
                try {
                    const response = await fetch('/backlog/add', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task: task, max_rounds: parseInt(rounds) })
                    });
                    await response.json();
                    document.getElementById('taskInput').value = '';
                    loadTasks();
                } catch(e) {
                    alert("Errore: " + e.message);
                } finally {
                    document.getElementById('loading').style.display = 'none';
                    document.querySelector('.btn-primary').disabled = false;
                }
            }

            async function loadTasks() {
                const response = await fetch('/backlog/list');
                const data = await response.json();
                const list = document.getElementById('taskList');
                if (!data.backlog || data.backlog.length === 0) {
                    list.innerHTML = '<div class="empty">Nessun task ancora. Scrivi qualcosa sopra per iniziare.</div>';
                    return;
                }
                list.innerHTML = '';
                [...data.backlog].reverse().forEach((t, i) => {
                    const index = data.backlog.length - 1 - i;
                    const isError = t.status === 'error';
                    const synthesis = t.synthesis || t.result || '';
                    let debateHTML = '';
                    if (t.log && t.log.length > 0) {
                        debateHTML = '<table><tr><th>Agente</th><th>Ruolo</th><th>Proposta</th><th>Rischi</th><th>Lacune</th></tr>';
                        t.log.forEach(entry => {
                            const agentClass = 'agent-' + (entry.agent === 'ChatGPT' ? 'gpt' : entry.agent === 'Claude' ? 'claude' : 'gemini');
                            const roleClass = 'role-' + (entry.role || 'Other');
                            debateHTML += '<tr>' +
                                '<td class="' + agentClass + '">' + entry.agent + '</td>' +
                                '<td class="' + roleClass + '">' + entry.role + '</td>' +
                                '<td>' + markdownToHtml(entry.proposal || '') + '</td>' +
                                '<td>' + (entry.risks || []).join('<br>') + '</td>' +
                                '<td>' + (entry.gaps || []).join('<br>') + '</td>' +
                                '</tr>';
                        });
                        debateHTML += '</table>';
                    }
                    list.innerHTML += '<div class="task-card ' + (isError ? 'error' : '') + '">' +
                        '<div class="task-header">' +
                            '<div class="task-title">' + t.task + '</div>' +
                            '<div class="task-meta">' + t.timestamp + '<br>' + t.execution_time + 's</div>' +
                        '</div>' +
                        '<span class="badge ' + (isError ? 'badge-error' : 'badge-done') + '">' + (isError ? '✗ Errore' : '✓ Completato') + '</span>' +
                        (synthesis ? '<div class="synthesis-box"><div class="synthesis-label">💡 Sintesi Helyas</div>' + markdownToHtml(synthesis) + '</div>' : '') +
                        (debateHTML ? '<button class="toggle-btn" onclick="toggleDebate(' + index + ')">📋 Vedi dibattito completo</button><div class="debate-box" id="debate-' + index + '">' + debateHTML + '</div>' : '') +
                        '</div>';
                });
            }

            function toggleDebate(index) {
                const box = document.getElementById('debate-' + index);
                box.style.display = box.style.display === 'block' ? 'none' : 'block';
            }

            document.addEventListener('DOMContentLoaded', () => {
                document.getElementById('taskInput').addEventListener('keypress', e => {
                    if (e.key === 'Enter') addTask();
                });
                loadTasks();
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
