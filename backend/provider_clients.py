import os
import re
import time
import google.generativeai as genai
from openai import OpenAI
import anthropic

class GPTClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.enabled = True if api_key else False
        self.client = OpenAI(api_key=api_key) if api_key else None

    def ask(self, prompt, model=None):
        if not self.enabled:
            return "[GPT disabled]"
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
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.enabled = True if api_key else False
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

    def ask(self, prompt, model=None):
        if not self.enabled:
            return "[Claude disabled]"
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
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        
        if not api_key:
            print("[GEMINI] API key missing")
            self.enabled = False
            return
        
        # Validazione formato API key
        if not re.match(r'^[A-Za-z0-9_\-]+$', api_key):
            print(f"[GEMINI] Invalid API key format: contains illegal characters")
            self.enabled = False
            return
        
        if len(api_key) < 20:
            print(f"[GEMINI] API key too short: {len(api_key)} chars")
            self.enabled = False
            return
        
        try:
            genai.configure(api_key=api_key)
            self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            self.model = genai.GenerativeModel(self.model_name)
            self.enabled = True
            print(f"[GEMINI] Configured successfully with key: {api_key[:8]}...{api_key[-4:]}")
        except Exception as e:
            print(f"[GEMINI] Configuration failed: {e}")
            self.enabled = False

    def ask(self, prompt):
        if not self.enabled:
            return "[Gemini disabled]"
        
        try:
            print(f"[GEMINI] Sending request...")
            start_time = time.time()
            
            resp = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=512,
                    temperature=0.3,
                ),
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            )
            
            elapsed = time.time() - start_time
            print(f"[GEMINI] Response received in {elapsed:.2f}s")
            
            if hasattr(resp, "text") and resp.text:
                return resp.text.strip()
            else:
                return f"[Gemini] Risposta vuota o bloccata dai filtri di sicurezza"
                
        except Exception as e:
            print(f"[GEMINI] API call failed: {e}")
            
            # Categorizza l'errore per debugging
            error_str = str(e).lower()
            if "quota" in error_str or "limit" in error_str:
                return "[Gemini] Quota API esaurita"
            elif "permission" in error_str or "forbidden" in error_str:
                return "[Gemini] Permessi insufficienti"
            elif "timeout" in error_str:
                return "[Gemini] Timeout connessione"
            elif "illegal header" in error_str:
                return "[Gemini] API key contiene caratteri non validi"
            else:
                return f"[Errore Gemini] {str(e)[:100]}"
