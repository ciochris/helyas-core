import os
from openai import OpenAI
import anthropic
import google.generativeai as genai

def _bool(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1","true","yes","on")

class GPTClient:
    def __init__(self):
        self.enabled = _bool("ENABLE_GPT", "true")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.enabled = False
        self.client = OpenAI(api_key=api_key)

    def ask(self, prompt, model=None):
        if not self.enabled:
            return None
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=512
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Errore GPT] {e}"

class ClaudeClient:
    def __init__(self):
        self.enabled = _bool("ENABLE_CLAUDE", "true")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            self.enabled = False
        self.client = anthropic.Anthropic(api_key=api_key)

    def ask(self, prompt, model=None):
        if not self.enabled:
            return None
        model = model or os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
        try:
            resp = self.client.messages.create(
                model=model,
                max_tokens=512,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            if resp.content and len(resp.content) > 0 and hasattr(resp.content[0], "text"):
                return resp.content[0].text
            return str(resp)
        except Exception as e:
            return f"[Errore Claude] {e}"

class GeminiClient:
    def __init__(self):
        self.enabled = _bool("ENABLE_GEMINI", "false")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            self.enabled = False
            return
        genai.configure(api_key=api_key)
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.model = genai.GenerativeModel(self.model_name)

    def ask(self, prompt):
        if not self.enabled:
            return None
        try:
            resp = self.model.generate_content(prompt)
            return getattr(resp, "text", str(resp))
        except Exception as e:
            return f"[Errore Gemini] {e}"
