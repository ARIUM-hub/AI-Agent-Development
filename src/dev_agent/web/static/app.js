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
const providerPreviewCards = () => document.getElementById("provider-preview-cards");

const providerRiskLabel = (risk) => {
  if (risk === "create") {
    return "新建";
  }
  if (risk === "overwrite") {
    return "覆盖";
  }
  if (risk === "append") {
    return "追加";
  }
  if (risk === "append_create") {
    return "追加并创建";
  }
  return risk || "未知风险";
};

const providerRiskClass = (risk) => {
  if (risk === "create") {
    return "risk-create";
  }
  if (risk === "overwrite") {
    return "risk-overwrite";
  }
  if (risk === "append") {
    return "risk-append";
  }
  if (risk === "append_create") {
    return "risk-append-create";
  }
  return "risk-unknown";
};

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

const clearProviderPreviewCards = () => {
  providerPreviewCards().replaceChildren();
};

const appendText = (parent, className, text) => {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
};

const renderProviderPreviewCards = (payload) => {
  clearProviderPreviewCards();
  const changes = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  if (changes.length === 0) {
    appendText(providerPreviewCards(), "preview-empty-state", "没有可显示的预览变更。");
    return;
  }

  changes.forEach((change) => {
    const riskClass = providerRiskClass(change.risk);
    const card = document.createElement("article");
    card.className = `preview-card ${riskClass}`;

    const header = document.createElement("div");
    header.className = "preview-card-header";
    const path = document.createElement("h4");
    path.textContent = change.path || "未命名路径";
    const badge = document.createElement("span");
    badge.className = `risk-badge ${riskClass}`;
    badge.textContent = providerRiskLabel(change.risk);
    header.append(path, badge);

    const meta = document.createElement("p");
    meta.className = "preview-meta";
    const targetState = change.exists ? "目标已存在" : "目标不存在";
    const bytes = Number.isFinite(change.content_bytes) ? `${change.content_bytes} bytes` : "未知 bytes";
    const lines = Number.isFinite(change.content_preview_line_count)
      ? `原始内容 ${change.content_preview_line_count} 行`
      : "行数未知";
    meta.textContent = `${targetState} · 将写入 ${bytes} · ${lines}`;

    const previewLabel = document.createElement("div");
    previewLabel.className = "preview-content-label";
    previewLabel.textContent = "内容预览";

    const preview = document.createElement("pre");
    preview.className = "content-preview";
    if (typeof change.content_preview === "string") {
      preview.textContent = change.content_preview === "" ? "内容为空" : change.content_preview;
    } else {
      preview.textContent = "此预览没有内容片段字段，请重新生成预览或检查服务版本。";
    }

    card.append(header, meta, previewLabel, preview);
    if (change.content_preview_truncated === true) {
      appendText(card, "truncation-note", "内容已截断，请查看原始 JSON 或缩小计划内容后重新预览。");
    }
    providerPreviewCards().appendChild(card);
  });
};

const resetProviderPreview = () => {
  if (lastProviderPreview === null) {
    return;
  }
  clearProviderPreviewCards();
  lastProviderPreview = null;
  providerStatus().textContent = "内容已变化，需要重新预览";
  providerApplyButton().disabled = true;
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
  clearProviderPreviewCards();
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
    renderProviderPreviewCards(payload);
    renderJson("provider-preview-result", payload);
    providerStatus().textContent = "预览通过，可以确认执行";
  } catch (error) {
    clearProviderPreviewCards();
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
    clearProviderPreviewCards();
    lastProviderPreview = null;
    await loadHistory();
  } catch (error) {
    renderJson("provider-apply-result", "执行失败。");
    providerStatus().textContent = "执行失败";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    showProviderError(error.message);
  } finally {
    setProviderBusy(false);
  }
}

document.getElementById("run-form").addEventListener("submit", submitRun);
providerForm().addEventListener("submit", submitProviderPreview);
providerForm().addEventListener("input", resetProviderPreview);
providerApplyButton().addEventListener("click", submitProviderApply);
loadHealth();
loadContext();
loadHistory();
