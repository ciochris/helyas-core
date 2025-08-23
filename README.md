# Helyas – Round Table Multi-AI Platform for SMEs

Helyas è una piattaforma AI collaborativa che permette a più intelligenze artificiali
(GPT-5, Claude, Gemini, ecc.) di confrontarsi, analizzare problemi e generare soluzioni concrete.

## Funzionalità principali
- Backend Flask con memoria persistente SQLite
- API REST: `/analyze`, `/approve`, `/artifact`, `/sessions`, `/health`
- Supporto multi-AI provider
- Logging avanzato
- Interfaccia web minimale
- Deploy automatico su Railway

## Struttura progetto
Vedi cartella `helyas-core/` nel repo.

## Deploy su Railway
1. Carica il repository su GitHub
2. Collega Railway al repository
3. Railway leggerà `requirements.txt` e `Procfile` per avviare l’app
