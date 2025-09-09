from flask import Flask, request, jsonify
from backend.orchestrator import round_table
import json
import os

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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok"})

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        task = data.get("task", "")
        result = round_table(task)
        return jsonify(result)
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
        backlog.append({"task": task, "status": "pending"})
        save_backlog(backlog)

        return jsonify({"status": "success", "message": f"Task added: {task}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/backlog/list", methods=["GET"])
def backlog_list():
    try:
        backlog = load_backlog()
        return jsonify({"status": "success", "backlog": backlog})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 🔹 NUOVO ENDPOINT: esegue i task pending
@app.route("/scheduler/run", methods=["POST"])
def scheduler_run():
    try:
        backlog = load_backlog()
        results = []

        for task in backlog:
            if task.get("status") == "pending":
                try:
                    result = round_table(task["task"])
                    task["status"] = "done"
                    task["result"] = result
                    results.append({"task": task["task"], "result": result})
                except Exception as e:
                    task["status"] = "error"
                    task["error"] = str(e)
                    results.append({"task": task["task"], "error": str(e)})

        save_backlog(backlog)

        return jsonify({"status": "success", "processed": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
