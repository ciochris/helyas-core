// URL base del backend (Render lo serve sullo stesso dominio)
const BASE_URL = "";

// Invio task
async function sendTask() {
  const input = document.getElementById("task-input");
  const task = input.value.trim();

  if (!task) {
    alert("Inserisci un task prima di inviare!");
    return;
  }

  try {
    const response = await fetch(`${BASE_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: task })
    });

    const data = await response.json();

    // Mostra la decisione finale dell'orchestrator
    const resultDiv = document.getElementById("response");
    resultDiv.innerText =
      data.decision?.proposal || JSON.stringify(data, null, 2);

    // Aggiorna le sessioni recenti
    loadSessions();
  } catch (err) {
    console.error("Errore durante l'invio del task:", err);
    document.getElementById("response").innerText =
      "Errore di connessione al backend.";
  }

  input.value = "";
}

// Controllo health del backend
async function checkHealth() {
  try {
    const response = await fetch(`${BASE_URL}/health`);
    const data = await response.json();
    console.log("Health check:", data.status);
  } catch (err) {
    console.error("Errore health check:", err);
  }
}

// Caricamento sessioni recenti
async function loadSessions() {
  try {
    const response = await fetch(`${BASE_URL}/sessions`);
    const data = await response.json();
    const sessionsList = document.getElementById("sessions");
    sessionsList.innerHTML = "";
    data.forEach((s, i) => {
      const li = document.createElement("li");
      li.textContent = `#${i + 1}: ${s.task} → ${s.summary || "N/A"}`;
      sessionsList.appendChild(li);
    });
  } catch (err) {
    console.error("Errore caricamento sessioni:", err);
  }
}

// Avvio automatico quando la pagina è pronta
window.onload = () => {
  checkHealth();
  loadSessions();
};
