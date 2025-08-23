async function sendTask() {
  const input = document.getElementById("task-input");
  const task = input.value.trim();

  if (!task) {
    alert("Inserisci un task prima di inviare!");
    return;
  }

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: task })
    });

    const data = await response.json();
    document.getElementById("response").innerText =
      data.response || "Nessuna risposta dal backend.";

    loadSessions();
  } catch (err) {
    console.error("Errore durante l'invio del task:", err);
    document.getElementById("response").innerText =
      "Errore di connessione al backend.";
  }

  input.value = "";
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const data = await response.json();
    console.log("Health check:", data.status);
  } catch (err) {
    console.error("Errore health check:", err);
  }
}

async function loadSessions() {
  try {
    const response = await fetch("/sessions");
    const data = await response.json();
    const sessionsList = document.getElementById("sessions");
    sessionsList.innerHTML = "";
    data.forEach((s) => {
      const li = document.createElement("li");
      li.textContent = `#${s.id}: ${s.task} → ${s.response}`;
      sessionsList.appendChild(li);
    });
  } catch (err) {
    console.error("Errore caricamento sessioni:", err);
  }
}

window.onload = () => {
  checkHealth();
  loadSessions();
};
