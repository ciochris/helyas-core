from flask import Flask, request, jsonify
import sqlite3
import os
from backend.utils.logging_utils import setup_logging, log
from backend.utils.provider_manager import get_providers

app = Flask(__name__)

setup_logging()

DB_PATH = "synapse_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT,
            response TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "Helyas"})

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    task = data.get("task", "")
    if not task:
        return jsonify({"error": "No task provided"}), 400

    response = f"Helyas ha ricevuto il task: {task}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO memory (task, response) VALUES (?, ?)", (task, response))
    conn.commit()
    conn.close()

    log(f"Task analizzato: {task}")
    return jsonify({"response": response})

@app.route("/sessions", methods=["GET"])
def sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, task, response FROM memory ORDER BY id DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return jsonify([
        {"id": r[0], "task": r[1], "response": r[2]} for r in rows
    ])

@app.route("/approve", methods=["POST"])
def approve():
    data = request.get_json()
    task_id = data.get("id")
    decision = data.get("decision", "pending")
    log(f"Approvazione task {task_id}: {decision}")
    return jsonify({"status": "approved", "id": task_id, "decision": decision})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
