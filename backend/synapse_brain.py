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

        # Esegui subito il task con timing
        start_time = time.time()
        try:
            result = round_table(task)
            execution_time = round(time.time() - start_time, 3)
            entry = {
                "task": task,
                "status": "done",
                "result": result,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "execution_time": execution_time
            }
            backlog.append(entry)
            save_backlog(backlog)
            return jsonify({"status": "success", "message": f"Task executed: {task}", "result": result, "execution_time": execution_time})
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
            return jsonify({"status": "error", "message": str(e), "execution_time": execution_time}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/backlog/list", methods=["GET"])
def backlog_list():
    try:
        backlog = load_backlog()
        return jsonify({"status": "success", "backlog": backlog})
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
                    task["result"] = result
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["execution_time"] = execution_time
                    results.append({"task": task["task"], "result": result, "execution_time": execution_time})
                except Exception as e:
                    execution_time = round(time.time() - start_time, 3)
                    task["status"] = "error"
                    task["error"] = str(e)
                    task["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["execution_time"] = execution_time
                    results.append({"task": task["task"], "error": str(e), "execution_time": execution_time})

        save_backlog(backlog)

        return jsonify({"status": "success", "processed": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
