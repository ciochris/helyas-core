from typing import Dict

def get_providers():
    providers: Dict[str, str] = {
        "openai": "OpenAI GPT-5",
        "claude": "Anthropic Claude",
        "gemini": "Google Gemini"
    }
    return providers
