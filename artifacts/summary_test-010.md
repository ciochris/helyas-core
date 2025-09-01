# Task Summary

Objective: Verifica hardcoded blocco import vietati
Decision: **Sintesi della Verifica di Importazioni Hardcoded Vietate nel Codice**

Per controllare la presenza di importazioni vietate nel codice sorgente, segui questi passaggi:

1. **Identificazione delle Importazioni Vietate**: Definisci una lista di librerie o moduli che non devono essere utilizzati.

2. **Analisi del Codice Sorgente**: Raccogli i file di codice sorgente da analizzare. Specifica il linguaggio di programmazione e la struttura del progetto.

3. **Utilizzo di Strumenti di Analisi**: Impiega strumenti di analisi statica come SonarQube, ESLint, o Pylint per automatizzare la ricerca di importazioni vietate. Questi strumenti possono essere configurati per segnalare le importazioni non autorizzate.

4. **Espressioni Regolari**: Se la lista di importazioni vietate è breve, puoi utilizzare espressioni regolari per cercare le stringhe corrispondenti nei file di codice.

5. **Script Personalizzati**: Scrivi uno script (ad esempio in Python) per leggere i file di codice e confrontare le istruzioni di importazione con la lista di importazioni vietate.

6. **Revisione Manuale**: Esegui una revisione manuale del codice per garantire che non ci siano importazioni vietate, soprattutto in file recentemente modificati.

7. **Documentazione**: Registra le importazioni vietate e le motivazioni per cui sono escluse, per facilitare la comprensione delle restrizioni da parte di altri sviluppatori.

**Esempio di Script in Python**:
```python
import re

forbidden_imports = ["os", "sys"]
forbidden_pattern = re.compile(r'^\s*import\s+(' + '|'.join(forbidden_imports) + r')|^\s*from\s+(' + '|'.join(forbidden_imports) + r')\s+import')

with open('your_code_file.py', 'r') as file:
    for line in file:
        if forbidden_pattern.search(line):
            print("Importazione vietata trovata:", line.strip())
```

Questi passaggi e strumenti ti aiuteranno a identificare e gestire le importazioni hardcoded vietate nel tuo codice. Se hai bisogno di assistenza specifica, fornisci dettagli sul codice o sulla lista di importazioni vietate.
