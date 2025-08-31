import os
import time
from typing import Dict, Optional

def get_gpt_response(task: str) -> Dict:
    """
    Chiama GPT con gestione timeout e errori
    """
    try:
        # Lazy import per ridurre memoria
        import openai
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return {
                "proposal": "[CONFIG ERROR] OpenAI API key mancante",
                "error": "OPENAI_API_KEY non configurata"
            }
        
        client = openai.OpenAI(api_key=api_key, timeout=15.0)
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user", 
                "content": f"Task: {task}\nFornisci una proposta concreta e pratica."
            }],
            max_tokens=500,
            timeout=15
        )
        
        proposal = response.choices[0].message.content.strip()
        
        return {
            "proposal": proposal,
            "model": "gpt-3.5-turbo",
            "tokens": response.usage.total_tokens if response.usage else 0
        }
        
    except Exception as e:
        return {
            "proposal": f"[GPT ERROR] {str(e)[:100]}",
            "error": str(e)
        }

def get_claude_response(task: str) -> Dict:
    """
    Chiama Claude con gestione timeout e errori
    """
    try:
        # Lazy import per ridurre memoria
        import anthropic
        
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return {
                "proposal": "[CONFIG ERROR] Claude API key mancante", 
                "error": "ANTHROPIC_API_KEY non configurata"
            }
        
        client = anthropic.Anthropic(api_key=api_key, timeout=15.0)
        
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"Task: {task}\nFornisci una risposta pratica e dettagliata."
            }],
            timeout=15
        )
        
        proposal = response.content[0].text.strip()
        
        return {
            "proposal": proposal,
            "model": "claude-3-haiku",
            "tokens": response.usage.input_tokens + response.usage.output_tokens
        }
        
    except Exception as e:
        return {
            "proposal": f"[CLAUDE ERROR] {str(e)[:100]}",
            "error": str(e)
        }

def get_gemini_response(task: str) -> Dict:
    """
    Mock Gemini per ora - da sostituire con API reale quando disponibile
    """
    try:
        time.sleep(1)  # Simula latenza
        
        return {
            "proposal": f"[GEMINI MOCK] Analisi task '{task[:30]}...': suggerisco approccio graduale con focus su ROI immediato",
            "model": "gemini-mock",
            "tokens": 50
        }
        
    except Exception as e:
        return {
            "proposal": f"[GEMINI ERROR] {str(e)[:100]}",
            "error": str(e)
        }
