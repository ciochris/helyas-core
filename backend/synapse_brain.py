from flask import Flask, request, jsonify
from backend.orchestrator import round_table

app = Flask(__name__)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
