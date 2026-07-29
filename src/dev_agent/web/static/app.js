const renderJson = (id, value) => {
  document.getElementById(id).textContent = JSON.stringify(value, null, 2);
};

const getJson = async (path) => {
  const response = await fetch(path);
  return response.json();
};

async function loadHealth() {
  renderJson("health", await getJson("/api/health"));
}

async function loadContext() {
  renderJson("context", await getJson("/api/context"));
}

async function loadHistory() {
  renderJson("history", await getJson("/api/history"));
}

async function submitRun(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request: form.elements.request.value,
      fake_response: form.elements.fake_response.value,
    }),
  });
  renderJson("run-result", await response.json());
  await loadHistory();
}

document.getElementById("run-form").addEventListener("submit", submitRun);
loadHealth();
loadContext();
loadHistory();
