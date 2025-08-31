import os
from flask import Flask, request, jsonify
from backend.orchestrator import round_table
from backend.autodev import autodev_bp

app = Flask(__name__)

# Registra il blueprint autodev
app.register_blueprint(autodev_bp)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "Helyas", "status": "ok"})

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        task = data.get("task", "")
        print(f"[DEBUG] Ricevuto task: {task}", flush=True)
        result = round_table(task)
        print(f"[DEBUG] Risultato round_table: {result}", flush=True)
        return jsonify(result)
    except Exception as e:
        print(f"[ERRORE analyze] {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
