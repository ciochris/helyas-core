# HELYAS — PIANO STRATEGICO
**Versione:** 1.0 — Maggio 2026  
**Autori:** Christian + Claude  
**Stato:** Documento di lavoro — da discutere e modificare insieme

---

## 1. LA VISIONE

Helyas è un cervello AI universale, modulare, che ragiona meglio di una singola AI perché mette in dialogo più intelligenze artificiali contemporaneamente.

Non è un chatbot. Non è un assistente. È un sistema di ragionamento collettivo che chiunque — un'azienda, un artigiano, una persona a casa — può usare per prendere decisioni migliori, automatizzare processi, e avere accesso a un livello di analisi che prima era riservato solo a chi poteva permettersi consulenti.

Il modello di business è modulare: il cervello è la base, i moduli sono il prodotto vendibile. Ogni cliente compra solo quello che gli serve.

---

## 2. DOVE SIAMO OGGI

### Cosa funziona
- Round Table GPT + Claude operativo in produzione su Railway
- Sessioni conversazionali con memoria persistente su PostgreSQL
- Interfaccia chat moderna e usabile
- Chiamate API parallele (15-45 secondi per risposta)
- Titoli sessione intelligenti, rinomina, cancella
- Deploy automatico da GitHub

### Cosa non funziona ancora
- Gemini disabilitato (libreria deprecata)
- Il cervello non sa chi è l'utente — risponde in modo generico
- Nessuna integrazione con il mondo esterno (WhatsApp, email, calendario, documenti)
- Nessun sistema di autenticazione — chiunque con il link accede
- Nessun sistema di pagamento o abbonamento
- Nessuna API pubblica per i moduli
- Il markdown grezzo appare nella sintesi (###, **)
- Nessun modo per l'utente di correggere o guidare Helyas durante il ragionamento

### Il gap più importante
Helyas oggi è un prototipo intelligente. Non è ancora un prodotto. La differenza è questa: un prototipo dimostra che l'idea funziona, un prodotto risolve un problema specifico abbastanza bene da far sì che qualcuno paghi per usarlo.

---

## 3. COSA MANCA AL CERVELLO PER ESSERE INDISPENSABILE

Questa è la parte più importante. Prima di costruire moduli, il cervello deve essere molto più potente di adesso.

### 3.1 Memoria persistente tra sessioni
Oggi Helyas dimentica tutto quando chiudi una sessione. Un cervello utile ricorda chi sei, cosa hai fatto, cosa hai deciso. Deve esistere un "profilo utente" che si accumula nel tempo — preferenze, contesto aziendale, decisioni passate, progetti in corso.

**Impatto:** trasforma Helyas da "strumento di query" a "collaboratore che ti conosce".

### 3.2 Capacità di fare domande
Oggi Helyas riceve un task e risponde. Un cervello intelligente fa domande di chiarimento prima di rispondere. "Stai parlando di un bagno da ristrutturare completamente o solo gli impianti? Qual è il budget del cliente?" — questo è il comportamento di un consulente vero.

**Impatto:** risposte molto più precise e personalizzate.

### 3.3 Accesso a informazioni esterne in tempo reale
Oggi gli agenti parlano solo di ciò che sanno già. Un cervello potente cerca informazioni — prezzi dei materiali, notizie di settore, normative aggiornate, dati di mercato. GPT ha già web search, Claude anche. Va integrato nel Round Table.

**Impatto:** risposte basate su dati reali, non solo su conoscenza storica.

### 3.4 Capacità di produrre documenti
Oggi Helyas produce solo testo nella chat. Dovrebbe poter produrre: un preventivo in PDF, un contratto, una email pronta da inviare, un piano di progetto scaricabile. Il risultato del ragionamento deve diventare qualcosa di utilizzabile direttamente.

**Impatto:** da "risposta da leggere" a "output da usare".

### 3.5 Sintesi di qualità superiore
Oggi la sintesi è la risposta del Builder migliore. Dovrebbe essere una vera sintesi del dibattito — quello su cui tutti gli agenti concordano, le divergenze segnalate, una raccomandazione finale chiara. Più simile a come lavora un vero team di consulenti.

**Impatto:** output più affidabile e più facile da usare.

### 3.6 Feedback loop
L'utente dovrebbe poter dire "questa risposta non mi convince, approfondisci questo punto" o "ignora questa parte e concentrati su quest'altra". Il cervello deve essere guidabile, non solo interrogabile.

**Impatto:** l'utente diventa co-pilota del ragionamento, non solo spettatore.

---

## 4. I MODULI — LA VISIONE

Una volta che il cervello è solido, i moduli sono interfacce specializzate che lo usano per contesti specifici. Ogni modulo ha il suo sistema di prompt, le sue integrazioni, la sua UX — ma sotto gira sempre il cervello Helyas.

### Moduli prioritari (quelli che generano valore immediato)

**Modulo WhatsApp Business**
Il cervello risponde ai clienti su WhatsApp. Gestisce preventivi, appuntamenti, domande frequenti. Già parzialmente costruito con Make. È il modulo con il ROI più immediato per le PMI.

**Modulo Preventivatore**
L'utente descrive un lavoro, Helyas fa le domande giuste e produce un preventivo strutturato. Per Soluzione Casa significherebbe automatizzare ore di lavoro a settimana. Esiste già un Excel per i bagni — va integrato come base di conoscenza.

**Modulo Gestione Team**
Briefing mattutino automatico, assegnazione task, aggiornamenti di stato. Giorgio riceve istruzioni da Helyas invece che da Christian. Risolve il problema di delega strutturale.

**Modulo Consulente Personale**
Per la persona a casa — pianificazione finanziaria, decisioni di acquisto importanti, ricerche complesse, supporto decisionale. Il Round Table al servizio del singolo individuo.

**Modulo Knowledge Base Aziendale**
L'azienda carica i suoi documenti (contratti, procedure, listini, manuali) e Helyas li usa come base di conoscenza per rispondere. "Come gestiamo i reclami?" → Helyas legge la procedura interna e risponde.

### Moduli futuri (quando il cervello è maturo)

- Modulo Contabilità — analisi di bilancio, previsioni, alert
- Modulo HR — onboarding, valutazione performance, procedure
- Modulo Marketing — analisi campagne, contenuti, strategia
- Modulo Legale — analisi contratti, alert normative, bozze

---

## 5. ROADMAP — PROPOSTA

Questa è la mia proposta. Va discussa e modificata.

### FASE 1 — Cervello maturo (2-3 mesi)
Obiettivo: Helyas diventa abbastanza buono da essere usato quotidianamente da Christian per Soluzione Casa.

Priorità in ordine:

**1. Memoria persistente tra sessioni**
Profilo utente che si accumula nel tempo — chi sei, cosa fai, decisioni passate, progetti in corso. Helyas smette di essere uno sconosciuto ad ogni nuova sessione.

**2. Agente Interprete**
Prima che il Round Table parta, un agente dedicato riscrive la domanda dell'utente in modo preciso, identifica le ambiguità, e fa 1-2 domande mirate. Solo dopo che l'utente ha risposto, il Round Table riceve una domanda pulita e contestualizzata. Questo risolve il problema fondamentale che la maggior parte delle domande degli utenti sono incomplete o ambigue. Il Round Table lavora sempre su input di qualità.

**3. Rendering markdown**
Il testo formattato (titoli, grassetti, liste) viene visualizzato correttamente invece di mostrare ### e **.

**4. Web search integrata nel Round Table**
Gli agenti cercano informazioni reali in tempo reale — prezzi, normative, dati di mercato — invece di rispondere solo dalla loro conoscenza storica.

**5. Output documenti**
Il risultato del ragionamento diventa qualcosa di scaricabile e utilizzabile — un PDF, una email pronta, un preventivo strutturato.

**6. Feedback loop durante il ragionamento**
L'utente può guidare Helyas mentre elabora: "approfondisci questo punto", "ignora quest'altro", "cambia direzione".

**7. Migrazione Gemini**
Aggiornamento alla nuova libreria google.genai per riportare Gemini nel Round Table come terzo agente.

**8. Sistema di autenticazione base**
Accesso protetto con login — prerequisito per aprire Helyas a utenti esterni.

### FASE 2 — Primo modulo reale (1-2 mesi)
Obiettivo: un modulo che risolve un problema reale e misurabile per Soluzione Casa.

- Modulo WhatsApp — integrazione con l'assistente già esistente, migrazione da GPT a Helyas
- Modulo Preventivatore — integrazione del calcolatore Excel bagni
- Test intensivo nel contesto reale di Soluzione Casa
- Misurazione del tempo risparmiato

### FASE 3 — Primo cliente esterno (2-3 mesi)
Obiettivo: vendere Helyas a una PMI esterna al settore edile.

- Sistema di autenticazione multi-utente
- Onboarding guidato
- Pricing e sistema di pagamento
- Dashboard analytics per il cliente
- Documentazione e supporto base

### FASE 4 — Piattaforma (6+ mesi)
Obiettivo: marketplace di moduli, API pubblica, scaling.

- API pubblica per sviluppatori esterni
- Marketplace moduli
- White label per rivenditori
- Integrazioni enterprise

---

## 6. CONTESTO REALE — SOLUZIONE CASA

Risposte di Christian (maggio 2026):

**Problemi principali che rubano più tempo:**
- Comunicazione con clienti e fornitori — messaggi, telefonate, follow-up. Serve un risponditore automatico intelligente che gestisca le domande base e sostituisca Christian nelle interazioni di routine. Obiettivo futuro: risposta telefonica automatica (modello Keplero).
- Preventivi e contabilità — prima nota, gestione amministrativa. Il calcolatore Excel per i bagni esiste ma è incompleto e non viene usato perché non c'è tempo per svilupparlo in parallelo a Helyas.
- Incassi — problema strutturale: difficoltà a richiedere pagamenti. Si perdono soldi reali per mancanza di un processo automatico di follow-up. Questo è il modulo con il ROI più immediato in assoluto.

**Situazione Giorgio:**
In fase di ridefinizione del ruolo. La dipendenza da una singola persona per la delega è un rischio strutturale che Helyas deve contribuire a ridurre.

**Budget:**
Attualmente 200-300€/mese per infrastruttura. Disponibilità ad aumentare l'investimento se il progetto mostra risultati concreti. Obiettivo di lungo termine: Helyas diventa l'entrata principale.

**Tempo disponibile:**
2-3 ore al giorno nei giorni feriali, più tempo nei weekend. Ritmo sostenibile per avanzare di 1 capitolo ogni 2-3 giorni.

---

## 7. COSA PENSO CHE SIA L'ERRORE DA NON FARE

Dirtelo chiaramente è parte del mio lavoro.

L'errore sarebbe continuare a costruire funzionalità tecniche senza mai testare se qualcuno vuole pagare per usarle. Abbiamo un Round Table funzionante — potremmo già far provare Helyas a qualcuno. Un amico, un collega, un'altra piccola impresa. Gratis, in cambio di feedback onesto.

Il feedback reale di un utente reale vale più di 10 capitoli di sviluppo.

La mia proposta: prima di iniziare la Fase 1, identifica 2-3 persone che potrebbero usare Helyas adesso, nella sua forma attuale, e raccogliere i loro feedback. Non per venderlo — per capire cosa manca davvero.

---

*Questo documento è un punto di partenza, non una verità assoluta. Cambia quello che non ti convince.*
