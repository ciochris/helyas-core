from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import os

from backend.orchestrator import round_table

app = Flask(__name__)

# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok"})

# Config check
@app.route("/config", methods=["GET"])
def config():
    return jsonify({"projectName": os.getenv("PROJECT_NAME", "Helyas")})

# Analyze endpoint (usa sempre l’orchestrator)
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    task = data.get("task", "")
    result = round_table(task)
    return jsonify(result)

# Sessions (mock, ultime interazioni)
@app.route("/sessions", methods=["GET"])
def sessions():
    conn = sqlite3.connect("helyas.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY,
            task TEXT,
            summary TEXT,
            artifact_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("SELECT task, summary, created_at FROM decisions ORDER BY created_at DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"task": r[0], "summary": r[1], "created_at": r[2]} for r in rows])

# Approve (mock)
@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    artifact_id = data.get("artifact_id")
    decision = data.get("decision", "approved")
    return jsonify({"artifact_id": artifact_id, "decision": decision, "status": "recorded"})

# Route per servire la dashboard dal frontend
@app.route('/')
def serve_index():
    return send_from_directory(os.path.join(os.path.dirname(__file__), '../frontend'), 'index.html')

# Route per servire i file statici (CSS, JS, immagini)
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(os.path.dirname(__file__), '../frontend'), path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
