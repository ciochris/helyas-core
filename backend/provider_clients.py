import os
import json
import requests

# 🔑 Legge chiavi API dalle variabili d’ambiente (da impostare su Railway)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🧩 Prompt standard: ogni modello deve rispondere in JSON
ROUND_TABLE_PROMPT = """
Sei parte del Round Table AI.
Ruolo: {role}
Task: {task}

Rispondi SOLO in JSON con il formato:
{
  "task_id": "{task_id}",
  "agent": "{agent}",
  "role": "{role}",
  "proposal": "testo della proposta",
  "risks": ["rischio1", "rischio2"],
  "gaps": ["lacuna1", "lacuna2"],
  "artifacts": [
    {"name": "nome_file.txt", "type": "text", "content": "contenuto"}
  ]
}
"""

# 🔹 Funzione per chiamare OpenAI GPT
def ask_openai(task_id, role, task, agent="ChatGPT"):
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",  # puoi cambiare modello
            "messages": [{"role": "user", "content": ROUND_TABLE_PROMPT.format(
                role=role, task=task, task_id=task_id, agent=agent
            )}],
            "temperature": 0.7
        }
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=data, timeout=60)
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        return {"task_id": task_id, "agent": agent, "role": role, "error": str(e)}

# 🔹 Funzione per chiamare Claude
def ask_claude(task_id, role, task, agent="Claude"):
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        data = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 800,
            "messages": [
                {"role": "user", "content": ROUND_TABLE_PROMPT.format(
                    role=role, task=task, task_id=task_id, agent=agent
                )}
            ]
        }
        response = requests.post("https://api.anthropic.com/v1/messages",
                                 headers=headers, json=data, timeout=60)
        result = response.json()
        content = result["content"][0]["text"]
        return json.loads(content)
    except Exception as e:
        return {"task_id": task_id, "agent": agent, "role": role, "error": str(e)}

# 🔹 Funzione per chiamare Gemini
def ask_gemini(task_id, role, task, agent="Gemini"):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{
                "parts": [{"text": ROUND_TABLE_PROMPT.format(
                    role=role, task=task, task_id=task_id, agent=agent
                )}]
            }]
        }
        response = requests.post(url, headers=headers, json=data, timeout=60)
        result = response.json()
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(content)
    except Exception as e:
        return {"task_id": task_id, "agent": agent, "role": role, "error": str(e)}
