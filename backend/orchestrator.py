import time
import json
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import signal

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Function call timed out")

def safe_provider_call(provider_name: str, provider_func, task: str, timeout: int = 25) -> Dict:
    """
    Chiama un provider con timeout e fallback automatico
    """
    try:
        # Imposta timeout con signal (funziona solo su Unix, per Windows usiamo ThreadPoolExecutor)
        result = None
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(provider_func, task)
            try:
                result = future.result(timeout=timeout)
            except TimeoutError:
                return {
                    "provider": provider_name,
                    "status": "timeout",
                    "proposal": f"[TIMEOUT] {provider_name} non ha risposto entro {timeout}s",
                    "error": f"Timeout dopo {timeout} secondi"
                }
        
        if not result or 'proposal' not in result:
            return {
                "provider": provider_name,
                "status": "error",
                "proposal": f"[ERROR] {provider_name} ha restituito formato non valido",
                "error": "Formato risposta non valido"
            }
            
        result["provider"] = provider_name
        result["status"] = "success"
        return result
        
    except Exception as e:
        return {
            "provider": provider_name,
            "status": "error", 
            "proposal": f"[ERROR] {provider_name}: {str(e)[:100]}",
            "error": str(e)
        }

def round_table(task: str) -> Dict:
    """
    Round Table con timeout robusto e fallback garantito
    """
    start_time = time.time()
    
    try:
        # Import lazy per evitare caricamento inutile
        from backend.provider_clients import get_gpt_response, get_claude_response, get_gemini_response
        
        # Definizione provider attivi
        providers = [
            ("gpt", get_gpt_response),
            ("claude", get_claude_response),
            ("gemini", get_gemini_response)
        ]
        
        # Round 1: Proposte parallele con timeout individuale
        round1_responses = []
        
        print(f"[ORCHESTRATOR] Avvio Round 1 per task: {task[:50]}...")
        
        # Chiamate parallele con timeout
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_provider = {
                executor.submit(safe_provider_call, name, func, task, 20): name 
                for name, func in providers
            }
            
            for future in as_completed(future_to_provider, timeout=25):
                provider_name = future_to_provider[future]
                try:
                    response = future.result()
                    round1_responses.append(response)
                    print(f"[ORCHESTRATOR] {provider_name} completato: {response['status']}")
                except Exception as e:
                    print(f"[ORCHESTRATOR] {provider_name} fallito: {e}")
                    round1_responses.append({
                        "provider": provider_name,
                        "status": "error",
                        "proposal": f"[ERROR] Fallimento esecuzione: {str(e)[:50]}",
                        "error": str(e)
                    })
        
        # Fallback se nessun provider risponde
        if not round1_responses:
            return {
                "task": task,
                "status": "complete_failure",
                "decision": {
                    "proposal": "[SYSTEM ERROR] Tutti i provider hanno fallito",
                    "reasoning": "Impossibile contattare GPT, Claude o Gemini",
                    "confidence": 0
                },
                "round1_responses": [],
                "execution_time": time.time() - start_time
            }
        
        # Filtra risposte valide
        valid_responses = [r for r in round1_responses if r.get('status') == 'success']
        
        # Scelta della migliore risposta (logica semplificata)
        if valid_responses:
            # Prendi la prima risposta valida come decisione finale
            best_response = valid_responses[0]
            decision = {
                "proposal": best_response.get('proposal', 'Risposta generata'),
                "reasoning": f"Selezionata risposta di {best_response['provider']} (prima disponibile)",
                "confidence": 85 if len(valid_responses) >= 2 else 70
            }
        else:
            # Fallback con risposte di errore
            error_response = round1_responses[0]  # Prima risposta anche se errore
            decision = {
                "proposal": f"[FALLBACK] Task ricevuto: {task}. Tutti i provider hanno avuto problemi.",
                "reasoning": "Utilizzato fallback di sistema per garantire risposta",
                "confidence": 10
            }
        
        return {
            "task": task,
            "status": "completed",
            "decision": decision,
            "round1_responses": round1_responses,
            "valid_providers": len(valid_responses),
            "execution_time": time.time() - start_time
        }
        
    except Exception as e:
        # Fallback finale assoluto
        return {
            "task": task,
            "status": "system_error",
            "decision": {
                "proposal": f"[SYSTEM FALLBACK] Errore critico nell'orchestrator: {str(e)[:100]}",
                "reasoning": "Fallback di emergenza attivato",
                "confidence": 5
            },
            "error": str(e),
            "execution_time": time.time() - start_time
        }

def validate_response_format(response: Dict) -> bool:
    """
    Valida che la risposta abbia il formato corretto
    """
    required_fields = ['task', 'status', 'decision']
    return all(field in response for field in required_fields)
