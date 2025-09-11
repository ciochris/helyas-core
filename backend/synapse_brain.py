from flask import Flask, request, jsonify
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
    with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_backlog(backlog):
    with open(BACKLOG_FILE, "w", encoding="utf-8") as f:
        json.dump(backlog, f, indent=2)

# Funzione per semplificare e pulire i risultati
def clean_result(result):
    try:
        if isinstance(result, dict):
            if "decision" in result:
                decision = result["decision"]
                # Se la decisione è un dizionario con 'proposal'
                if isinstance(decision, dict) and "proposal" in decision:
                    return f"Decisione: {decision['proposal']}"
                # Se la decisione è testo
                return f"Decisione: {decision}"
            return str(result)
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
            entry = {
                "task": task,
                "status": "done",
                "result": clean_result(result),
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
                "timestamp": t.get("timestamp", ""),
                "execution_time": t.get("execution_time", "")
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
                    task["status"] = "done"
                    task["result"] = clean_result(result)
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["execution_time"] = execution_time
                    results.append(task)
                except Exception as e:
                    execution_time = round(time.time() - start_time, 3)
                    task["status"] = "error"
                    task["error"] = str(e)
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["execution_time"] = execution_time
                    results.append(task)

        save_backlog(backlog)

        return jsonify({"status": "success", "processed": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
