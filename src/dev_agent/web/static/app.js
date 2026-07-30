const renderJson = (id, value) => {
  document.getElementById(id).textContent = JSON.stringify(value, null, 2);
};

const getJson = async (path) => {
  const response = await fetch(path);
  return response.json();
};

const contextCards = () => document.getElementById("context-cards");

const clearContextCards = () => {
  contextCards().replaceChildren();
};

const contextObject = (value) => {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value;
  }
  return {};
};

const contextText = (value, fallback) => {
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  return fallback;
};

const contextValues = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => typeof item === "string" || typeof item === "number")
    .map((item) => String(item).trim())
    .filter((item) => item !== "");
};

const contextCommandLabel = (name) => {
  const labels = {
    test: "测试",
    lint: "代码检查",
    typecheck: "类型检查",
    build: "构建",
  };
  return labels[name] || contextText(name, "验证命令");
};

const formatContextCommandPart = (part) => {
  const text = String(part);
  if (text === "" || /[\s\"]/.test(text)) {
    return JSON.stringify(text);
  }
  return text;
};

const formatContextCommand = (command) => {
  if (typeof command === "string") {
    return command.trim();
  }
  if (!Array.isArray(command)) {
    return "";
  }
  return command
    .filter((part) => typeof part === "string" || typeof part === "number")
    .map(formatContextCommandPart)
    .join(" ")
    .trim();
};

const collectContextCommands = (payload) => {
  const source = contextObject(payload);
  const steps = Array.isArray(source.verification_steps) ? source.verification_steps : [];
  let candidates = steps
    .map((step) => {
      const item = contextObject(step);
      return {
        label: contextCommandLabel(item.name),
        command: formatContextCommand(item.command),
      };
    })
    .filter((item) => item.command !== "");

  if (candidates.length === 0) {
    const scan = contextObject(source.scan);
    const suggested = contextObject(scan.suggested_commands);
    candidates = ["test", "lint", "typecheck", "build"]
      .map((name) => ({
        label: contextCommandLabel(name),
        command: formatContextCommand(suggested[name]),
      }))
      .filter((item) => item.command !== "");
  }

  const seen = new Set();
  return candidates.filter((item) => {
    if (seen.has(item.command)) {
      return false;
    }
    seen.add(item.command);
    return true;
  });
};

const copyContextCommand = async (button, command) => {
  try {
    await navigator.clipboard.writeText(command);
    button.textContent = "已复制";
  } catch (_error) {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => {
    if (button.isConnected) {
      button.textContent = "一键复制";
    }
  }, 1600);
};

const appendContextText = (parent, className, text) => {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
};

const appendContextTags = (parent, label, values) => {
  const field = document.createElement("section");
  field.className = "context-field";
  appendContextText(field, "context-label", label);

  const tags = document.createElement("div");
  tags.className = "context-tag-list";
  const normalized = contextValues(values);
  if (normalized.length === 0) {
    appendContextText(tags, "context-empty-state", "未检测到");
  } else {
    normalized.forEach((value) => {
      appendContextText(tags, "context-tag", value);
    });
  }
  field.appendChild(tags);
  parent.appendChild(field);
};

const appendContextGitSection = (parent, label, value, emptyText) => {
  const section = document.createElement("section");
  section.className = "context-git-section";
  appendContextText(section, "context-label", label);
  const output = document.createElement("pre");
  output.className = "context-git-output";
  output.textContent = contextText(value, emptyText);
  section.appendChild(output);
  parent.appendChild(section);
};

const buildContextProjectCard = (payload) => {
  const source = contextObject(payload);
  const project = contextObject(source.project);
  const scan = contextObject(source.scan);
  const card = document.createElement("article");
  card.className = "context-card context-project-card";

  appendContextText(card, "context-card-kicker", "项目总览");
  const title = document.createElement("h3");
  title.textContent = contextText(project.name, "未命名项目");
  card.appendChild(title);
  appendContextText(card, "context-path", `扫描目录：${contextText(scan.root, "未检测到")}`);

  const fields = document.createElement("div");
  fields.className = "context-field-grid";
  appendContextTags(fields, "技术栈", project.tech_stack);
  appendContextTags(fields, "识别语言", scan.languages);
  appendContextTags(fields, "项目标记", scan.markers);
  card.appendChild(fields);
  return card;
};

const buildContextGitCard = (payload) => {
  const source = contextObject(payload);
  const git = contextObject(source.git);
  const card = document.createElement("article");
  let stateClass = "context-git-unknown";
  let stateLabel = "暂无 Git 状态";
  let statusText = "暂无 Git 状态";

  if (typeof git.status === "string") {
    if (git.status.trim() === "") {
      stateClass = "context-git-clean";
      stateLabel = "工作区干净";
      statusText = "没有未提交变更。";
    } else {
      stateClass = "context-git-changed";
      stateLabel = "工作区有变更";
      statusText = git.status;
    }
  }

  card.className = `context-card context-git-card ${stateClass}`;
  const header = document.createElement("div");
  header.className = "context-card-header";
  const title = document.createElement("h3");
  title.textContent = "Git 状态";
  const badge = document.createElement("span");
  badge.className = `context-status-badge ${stateClass}`;
  badge.textContent = stateLabel;
  header.append(title, badge);
  card.appendChild(header);

  const fields = document.createElement("div");
  fields.className = "context-git-grid";
  appendContextGitSection(fields, "工作区", statusText, "暂无 Git 状态");
  appendContextGitSection(fields, "变更统计", git.diff_stat, "暂无变更统计");
  appendContextGitSection(fields, "最近提交", git.recent_log, "暂无提交记录");
  card.appendChild(fields);
  return card;
};

const buildContextCommandsCard = (payload) => {
  const card = document.createElement("article");
  card.className = "context-card context-command-card";
  const title = document.createElement("h3");
  title.textContent = "验证命令";
  card.appendChild(title);

  const list = document.createElement("div");
  list.className = "context-command-list";
  const commands = collectContextCommands(payload);
  if (commands.length === 0) {
    appendContextText(list, "context-empty-state", "暂无验证命令");
  } else {
    commands.forEach(({ label, command }) => {
      const row = document.createElement("div");
      row.className = "context-command-row";
      const main = document.createElement("div");
      main.className = "context-command-main";
      appendContextText(main, "context-command-label", label);
      const code = document.createElement("code");
      code.className = "context-command-code";
      code.textContent = command;
      main.appendChild(code);

      const button = document.createElement("button");
      button.type = "button";
      button.className = "context-copy-button";
      button.textContent = "一键复制";
      button.setAttribute("aria-label", `复制${label}命令`);
      button.addEventListener("click", () => copyContextCommand(button, command));
      row.append(main, button);
      list.appendChild(row);
    });
  }
  card.appendChild(list);
  return card;
};

const buildContextSupportCard = (payload) => {
  const source = contextObject(payload);
  const preferences = contextObject(source.preferences);
  const card = document.createElement("article");
  card.className = "context-card context-support-card";
  const title = document.createElement("h3");
  title.textContent = "偏好与规则";
  card.appendChild(title);

  const fields = document.createElement("div");
  fields.className = "context-preferences";
  appendContextText(
    fields,
    "context-preference",
    `语言：${contextText(preferences.language, "未设置")}`,
  );
  appendContextText(
    fields,
    "context-preference",
    `审批模式：${contextText(preferences.approval_mode, "未设置")}`,
  );
  card.appendChild(fields);

  const details = document.createElement("details");
  details.className = "context-rule-detail";
  const summary = document.createElement("summary");
  summary.textContent = "查看项目规则";
  const rules = document.createElement("pre");
  rules.className = "context-rule-text";
  rules.textContent = contextText(source.rules_text, "暂无项目规则");
  details.append(summary, rules);
  card.appendChild(details);
  return card;
};

const renderContextCards = (payload) => {
  clearContextCards();
  const source = contextObject(payload);
  const overview = document.createElement("div");
  overview.className = "context-overview-grid";
  overview.append(buildContextProjectCard(source), buildContextGitCard(source));
  contextCards().append(
    overview,
    buildContextCommandsCard(source),
    buildContextSupportCard(source),
  );
};

const historyCards = () => document.getElementById("history-cards");

const historyStatusLabel = (status) => {
  if (status === "passed") {
    return "通过";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "running") {
    return "运行中";
  }
  if (status === "planned") {
    return "已计划";
  }
  return status || "未知状态";
};

const historyStatusClass = (status) => {
  if (status === "passed") {
    return "history-status-passed";
  }
  if (status === "failed") {
    return "history-status-failed";
  }
  if (status === "running") {
    return "history-status-running";
  }
  if (status === "planned") {
    return "history-status-planned";
  }
  return "history-status-unknown";
};

const clearHistoryCards = () => {
  historyCards().replaceChildren();
};

const appendHistoryList = (parent, title, items, emptyText) => {
  const section = document.createElement("section");
  section.className = "history-detail-section";
  const heading = document.createElement("h5");
  heading.textContent = title;
  section.appendChild(heading);

  const list = document.createElement("ul");
  list.className = "history-list";
  const values = Array.isArray(items) ? items : [];
  if (values.length === 0) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    list.appendChild(item);
  } else {
    values.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = String(value);
      list.appendChild(item);
    });
  }
  section.appendChild(list);
  parent.appendChild(section);
};

const renderHistoryCards = (payload) => {
  clearHistoryCards();
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
  if (tasks.length === 0) {
    appendText(historyCards(), "history-empty-state", "暂无历史任务。完成 dry-run 或确认执行后会出现在这里。");
    return;
  }

  tasks.forEach((task) => {
    const statusClass = historyStatusClass(task.status);
    const events = Array.isArray(task.events) ? task.events : [];
    const verification = Array.isArray(task.verification) ? task.verification : [];
    const lessons = Array.isArray(task.lessons) ? task.lessons : [];

    const card = document.createElement("article");
    card.className = `history-card ${statusClass}`;

    const header = document.createElement("div");
    header.className = "history-card-header";
    const title = document.createElement("h3");
    title.textContent = task.title || "未命名任务";
    const badge = document.createElement("span");
    badge.className = `history-status-badge ${statusClass}`;
    badge.textContent = historyStatusLabel(task.status);
    header.append(title, badge);

    const summary = document.createElement("p");
    summary.className = "history-summary";
    summary.textContent = task.summary || "暂无摘要";

    const latestEvent = events.length > 0 ? events[events.length - 1] : "暂无事件记录";
    const meta = document.createElement("p");
    meta.className = "history-meta";
    meta.textContent = `验证 ${verification.length} 项 · 经验 ${lessons.length} 条 · 最近事件：${latestEvent}`;

    const taskId = document.createElement("p");
    taskId.className = "history-task-id";
    taskId.textContent = `任务 ID：${task.task_id || "未知"}`;

    const details = document.createElement("details");
    details.className = "history-detail";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "查看详情";
    details.appendChild(detailsSummary);
    appendHistoryList(details, "验证命令", verification, "暂无验证命令");
    appendHistoryList(details, "经验", lessons, "暂无经验");
    appendHistoryList(details, "事件", events, "暂无事件");

    card.append(header, summary, meta, taskId, details);
    historyCards().appendChild(card);
  });
};

async function loadHealth() {
  renderJson("health", await getJson("/api/health"));
}

async function loadContext() {
  const payload = await getJson("/api/context");
  renderContextCards(payload);
  renderJson("context", payload);
}

async function loadHistory() {
  const payload = await getJson("/api/history");
  renderHistoryCards(payload);
  renderJson("history", payload);
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
const providerAuditCards = () => document.getElementById("provider-audit-cards");

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

const clearProviderAuditCards = () => {
  providerAuditCards().replaceChildren();
};

const previewChangeAt = (payload, index) => {
  const changes = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  return changes[index] || {};
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

const renderProviderAuditFailure = (message) => {
  clearProviderAuditCards();
  const card = document.createElement("article");
  card.className = "audit-card audit-failed";

  const header = document.createElement("div");
  header.className = "audit-card-header";
  const title = document.createElement("h4");
  title.textContent = "执行失败";
  const badge = document.createElement("span");
  badge.className = "audit-status-badge audit-failed";
  badge.textContent = "失败";
  header.append(title, badge);

  const error = document.createElement("div");
  error.className = "audit-error";
  error.textContent = message || "执行请求失败，请查看错误提示或原始 JSON。";

  card.append(header, error);
  providerAuditCards().appendChild(card);
};

const renderProviderAuditCards = (payload) => {
  clearProviderAuditCards();
  const appliedChanges = Array.isArray(payload.applied_changes) ? payload.applied_changes : [];
  const previewChanges = Array.isArray(payload.preview_changes) ? payload.preview_changes : [];
  const hasExecutionError = typeof payload.execution_error === "string" && payload.execution_error.length > 0;

  const summary = document.createElement("article");
  summary.className = `audit-card ${hasExecutionError ? "audit-failed" : "audit-success"}`;
  const summaryHeader = document.createElement("div");
  summaryHeader.className = "audit-card-header";
  const summaryTitle = document.createElement("h4");
  summaryTitle.textContent = hasExecutionError ? "执行失败" : "执行完成";
  const summaryBadge = document.createElement("span");
  summaryBadge.className = `audit-status-badge ${hasExecutionError ? "audit-failed" : "audit-success"}`;
  summaryBadge.textContent = hasExecutionError ? "失败" : "成功";
  summaryHeader.append(summaryTitle, summaryBadge);

  const summaryMeta = document.createElement("p");
  summaryMeta.className = "audit-meta";
  summaryMeta.textContent = `已应用 ${appliedChanges.length} 项变更 · 计划 ${previewChanges.length} 项预览变更 · 历史已刷新`;
  summary.append(summaryHeader, summaryMeta);
  if (hasExecutionError) {
    appendText(summary, "audit-error", payload.execution_error);
  }
  providerAuditCards().appendChild(summary);

  if (appliedChanges.length === 0) {
    appendText(providerAuditCards(), "preview-empty-state", "没有实际应用变更记录。");
  }

  appliedChanges.forEach((change, index) => {
    const previewChange = previewChangeAt(payload, index);
    const riskClass = providerRiskClass(previewChange.risk);
    const card = document.createElement("article");
    card.className = `audit-card ${riskClass}`;

    const header = document.createElement("div");
    header.className = "audit-card-header";
    const path = document.createElement("h4");
    path.textContent = change.path || previewChange.path || "未命名路径";
    const badge = document.createElement("span");
    badge.className = `risk-badge ${riskClass}`;
    badge.textContent = providerRiskLabel(previewChange.risk || change.action);
    header.append(path, badge);

    const meta = document.createElement("p");
    meta.className = "audit-meta";
    const action = change.action || "未知动作";
    const bytes = Number.isFinite(change.content_bytes) ? `${change.content_bytes} bytes` : "未知 bytes";
    const targetState = typeof previewChange.exists === "boolean"
      ? (previewChange.exists ? "执行前目标已存在" : "执行前目标不存在")
      : "执行前目标状态未知";
    meta.textContent = `${action} · 写入 ${bytes} · ${targetState}`;

    const previewLabel = document.createElement("div");
    previewLabel.className = "preview-content-label";
    previewLabel.textContent = "已审阅内容片段";

    const preview = document.createElement("pre");
    preview.className = "content-preview";
    if (typeof previewChange.content_preview === "string") {
      preview.textContent = previewChange.content_preview === "" ? "内容为空" : previewChange.content_preview;
    } else {
      preview.textContent = "此执行结果没有可读内容片段，请查看原始 JSON。";
    }

    card.append(header, meta, previewLabel, preview);
    if (previewChange.content_preview_truncated === true) {
      appendText(card, "truncation-note", "内容片段已截断，请查看原始 JSON 或缩小计划后重新预览。");
    }
    providerAuditCards().appendChild(card);
  });

  const diff = document.createElement("article");
  diff.className = "audit-card audit-neutral";
  const diffHeader = document.createElement("div");
  diffHeader.className = "audit-card-header";
  const diffTitle = document.createElement("h4");
  diffTitle.textContent = "Git diff 摘要";
  const diffBadge = document.createElement("span");
  diffBadge.className = "audit-status-badge audit-neutral";
  diffBadge.textContent = "diff";
  diffHeader.append(diffTitle, diffBadge);

  const diffBody = document.createElement("pre");
  diffBody.className = "audit-diff";
  if (typeof payload.diff_stat === "string") {
    diffBody.textContent = payload.diff_stat === "" ? "没有 Git diff 摘要。" : payload.diff_stat;
  } else {
    diffBody.textContent = "此执行结果没有 Git diff 摘要字段。";
  }
  diff.append(diffHeader, diffBody);
  providerAuditCards().appendChild(diff);
};

const resetProviderPreview = () => {
  clearProviderAuditCards();
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
  clearProviderAuditCards();
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
    clearProviderAuditCards();
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
    renderProviderAuditCards(payload);
    renderJson("provider-apply-result", payload);
    providerStatus().textContent = payload.execution_error ? "执行失败" : "执行完成";
    clearProviderPreviewCards();
    lastProviderPreview = null;
    await loadHistory();
  } catch (error) {
    renderProviderAuditFailure(error.message);
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
