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
            if "decision" in result:
                decision = result["decision"]
                if isinstance(decision, dict) and "proposal" in decision:
                    return decision["proposal"]
                return str(decision)
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

# 🔹 Dashboard HTML
@app.route("/dashboard", methods=["GET"])
def dashboard():
    backlog = load_backlog()
    html_template = """
    <html>
    <head>
        <title>Helyas Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background-color: #f4f4f4; }
            tr:nth-child(even) { background-color: #f9f9f9; }
        </style>
    </head>
    <body>
        <h2>📊 Helyas – Lista Task</h2>
        <table>
            <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Result</th>
                <th>Timestamp</th>
                <th>Execution Time (s)</th>
            </tr>
            {% for t in backlog %}
            <tr>
                <td>{{ t.task }}</td>
                <td>{{ t.status }}</td>
                <td>{{ t.result }}</td>
                <td>{{ t.timestamp }}</td>
                <td>{{ t.execution_time }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html_template, backlog=backlog)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
