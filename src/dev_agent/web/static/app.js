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

let lastProviderPreview = null;

const providerForm = () => document.getElementById("provider-plan-form");
const providerPreviewButton = () => document.getElementById("preview-provider-plan");
const providerApplyButton = () => document.getElementById("confirm-provider-apply");
const providerStatus = () => document.getElementById("provider-status");
const providerError = () => document.getElementById("provider-error");

const setProviderBusy = (busy) => {
  providerPreviewButton().disabled = busy;
  providerApplyButton().disabled = busy || lastProviderPreview === null;
};

const showProviderError = (message) => {
  providerError().hidden = false;
  providerError().textContent = message;
};

const clearProviderError = () => {
  providerError().hidden = true;
  providerError().textContent = "";
};

const postJson = async (path, payload) => {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "请求失败，请检查本地服务是否仍在运行。");
  }
  return body;
};

async function submitProviderPreview(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearProviderError();
  lastProviderPreview = null;
  providerStatus().textContent = "正在生成预览";
  renderJson("provider-apply-result", "确认执行后显示结果。");
  setProviderBusy(true);
  try {
    const payload = await postJson("/api/provider-plan/preview", {
      request: form.elements.request.value,
      fake_response: form.elements.fake_response.value,
    });
    lastProviderPreview = payload;
    renderJson("provider-preview-result", payload);
    providerStatus().textContent = "预览通过，可以确认执行";
  } catch (error) {
    renderJson("provider-preview-result", "预览失败。");
    providerStatus().textContent = "预览失败";
    showProviderError(error.message);
  } finally {
    setProviderBusy(false);
  }
}

async function submitProviderApply() {
  const form = providerForm();
  clearProviderError();
  providerStatus().textContent = "正在执行";
  setProviderBusy(true);
  try {
    const payload = await postJson("/api/provider-plan/apply", {
      request: form.elements.request.value,
      fake_response: form.elements.fake_response.value,
    });
    renderJson("provider-apply-result", payload);
    providerStatus().textContent = payload.execution_error ? "执行失败" : "执行完成";
    await loadHistory();
  } catch (error) {
    renderJson("provider-apply-result", "执行失败。");
    providerStatus().textContent = "执行失败";
    showProviderError(error.message);
  } finally {
    setProviderBusy(false);
  }
}

document.getElementById("run-form").addEventListener("submit", submitRun);
providerForm().addEventListener("submit", submitProviderPreview);
providerApplyButton().addEventListener("click", submitProviderApply);
loadHealth();
loadContext();
loadHistory();
