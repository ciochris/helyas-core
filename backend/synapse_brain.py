from flask import Flask, request, jsonify
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

# Analyze endpoint (collegato a orchestrator)
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    task = data.get("task", "")

    if os.getenv("RT_ENABLED", "0") == "1":
        result = round_table(task)
        return jsonify(result)
    else:
        return jsonify({"result": f"Analyzed (mock): {task}"})

# Sessions (mock, ultime interazioni)
@app.route("/sessions", methods=["GET"])
def sessions():
    conn = sqlite3.connect("helyas.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, task TEXT, summary TEXT, artifact_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
