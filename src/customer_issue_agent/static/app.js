const labels = {
  issue_category: {
    installation: "安装、开箱或组装问题",
    function_use: "功能不会用或设置失败",
    expectation_gap: "功能表现未达到预期",
    product_fault: "产品异常、失灵或疑似质量问题",
    compatibility: "兼容性问题",
    accessory: "配件缺失或条件不满足",
    non_usage: "非产品使用问题",
    unclear: "信息不足",
  },
  responsibility: {
    operations: "运营",
    customer_service_training: "客服培训",
    product: "产品",
    supply_chain_quality: "供应链或质量",
    need_more_information: "需要补充信息",
  },
  evidence: {
    clear: "较明确",
    likely: "倾向于",
    insufficient: "信息不足",
  },
  feedback: {
    unreviewed: "未复核",
    accepted: "已认可",
    corrected: "已修正",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindAnalysisForm("paste-form", "paste-error");
  bindAnalysisForm("upload-form", "upload-error");
  bindBatchForm();
  bindFeedbackForms(document);
  bindSummaryRange();
  loadRecordsSummary();
  bindFilteredExport();
  bindRecordFilters();
});

function bindTabs() {
  const tabs = Array.from(document.querySelectorAll("[data-tab-target]"));
  const forms = {
    "paste-panel": document.getElementById("paste-form"),
    "upload-panel": document.getElementById("upload-form"),
    "batch-panel": document.getElementById("batch-form"),
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tabTarget;
      tabs.forEach((item) => {
        const selected = item === tab;
        item.classList.toggle("is-active", selected);
        item.setAttribute("aria-selected", String(selected));
      });

      Object.entries(forms).forEach(([panelId, form]) => {
        const panel = document.getElementById(panelId);
        const active = panelId === target;
        if (!form || !panel) {
          return;
        }
        form.classList.toggle("is-hidden", !active);
        panel.hidden = !active;
      });
    });
  });
}

function bindAnalysisForm(formId, errorId) {
  const form = document.getElementById(formId);
  if (!form) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAnalysisForm(form, document.getElementById(errorId));
  });
}

function bindBatchForm() {
  const form = document.getElementById("batch-form");
  if (!form) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitBatchForm(form, document.getElementById("batch-error"));
  });
}

async function submitAnalysisForm(form, errorBox) {
  const button = form.querySelector("button[type='submit']");
  const originalLabel = button.textContent;
  clearError(errorBox);
  setLoading(button, true);

  try {
    const response = await fetch(form.dataset.endpoint, {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderAnalysisResult(payload);
    bindFeedbackForms(document.getElementById("analysis-result"));
    prependRecentRecord(payload);
    form.reset();
  } catch (error) {
    showError(errorBox, error.message || "分析失败，请检查输入后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}

function renderAnalysisResult(payload) {
  const result = document.getElementById("analysis-result");
  const analysis = payload.analysis;
  const attribution = analysis.attribution;
  result.innerHTML = `
    <div class="result-header">
      <div>
        <p class="eyebrow">分析完成</p>
        <h2>${escapeHtml(analysis.request.platform)}</h2>
      </div>
      <span class="record-id">#${escapeHtml(payload.record_id.slice(0, 8))}</span>
    </div>
    <div class="summary-strip">
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <div class="result-grid">
      ${resultCard("客户问题", attribution.customer_problem)}
      ${resultCard("业务原因", attribution.root_causes.map((item) => labelFor("rootCause", item)).join(" + ") || analysis.report)}
      ${resultCard("优先责任方", labelFor("responsibility", attribution.primary_responsibility))}
      ${resultCard("下一步建议", attribution.recommended_actions.join("；"))}
      ${resultCard("需要补充", attribution.missing_information.join("；") || "暂无必须补充的信息。")}
    </div>
  `;
  result.appendChild(createFeedbackForm(payload.record_id));
}

async function submitBatchForm(form, errorBox) {
  const button = form.querySelector("button[type='submit']");
  const originalLabel = button.textContent;
  clearError(errorBox);
  setLoading(button, true);

  try {
    const response = await fetch(form.dataset.endpoint, {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderBatchResults(payload);
    payload.records.forEach((record) => prependRecentRecord(record));
    form.reset();
  } catch (error) {
    showError(errorBox, error.message || "批量分析失败，请检查文件后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}

function renderBatchResults(payload) {
  const container = document.getElementById("batch-results");
  container.innerHTML = `
    <div class="result-header">
      <div>
        <p class="eyebrow">批量分析完成</p>
        <h2>${payload.count} 条会话已生成分析</h2>
      </div>
      <span class="record-id">批次 #${escapeHtml(payload.batch_id.slice(0, 8))}</span>
    </div>
    <div class="batch-list"></div>
  `;
  const list = container.querySelector(".batch-list");
  payload.records.forEach((record) => {
    list.appendChild(buildRecordCard(record));
  });
  bindFeedbackForms(container);
}

function buildRecordCard(payload) {
  const analysis = payload.analysis;
  const attribution = analysis.attribution;
  const article = document.createElement("article");
  article.className = "record result-record";
  article.dataset.recordId = payload.record_id;
  article.innerHTML = `
    <div class="record-meta">
      <strong>${escapeHtml(analysis.request.platform)}</strong>
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <p>${escapeHtml(analysis.report)}</p>
  `;
  article.appendChild(createFeedbackForm(payload.record_id));
  return article;
}

function createFeedbackForm(recordId) {
  const template = document.querySelector("[data-feedback-template]");
  const fragment = template.content.cloneNode(true);
  const form = fragment.querySelector("form");
  form.dataset.endpoint = `/api/records/${recordId}/feedback`;
  return fragment;
}

function bindFeedbackForms(root) {
  root.querySelectorAll(".feedback-form").forEach((form) => {
    if (form.dataset.bound === "true") {
      return;
    }
    form.dataset.bound = "true";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitFeedbackForm(form);
    });
  });
}

async function submitFeedbackForm(form) {
  const button = form.querySelector("button[type='submit']");
  const message = form.querySelector(".form-message");
  const originalLabel = button.textContent;
  clearError(message);
  setLoading(button, true);

  try {
    const response = await fetch(form.dataset.endpoint, {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    message.textContent = payload.feedback.accepted ? "已保存：认可系统判断。" : "已保存：人工修正已记录。";
    message.classList.add("is-visible", "is-success");
  } catch (error) {
    showError(message, error.message || "反馈保存失败，请稍后重试。");
  } finally {
    button.textContent = originalLabel;
    setLoading(button, false);
  }
}

function prependRecentRecord(payload) {
  const list = document.getElementById("recent-records");
  const analysis = payload.analysis;
  const attribution = analysis.attribution;
  const empty = list.querySelector(".empty");
  if (empty) {
    empty.remove();
  }

  const article = document.createElement("article");
  article.className = "record";
  article.dataset.recordId = payload.record_id;
  article.dataset.platform = analysis.request.platform;
  article.dataset.issueCategory = attribution.issue_category;
  article.dataset.responsibility = attribution.primary_responsibility;
  article.dataset.feedbackStatus = "unreviewed";
  article.dataset.searchText = `${payload.record_id} ${analysis.request.platform} ${analysis.report}`;
  article.innerHTML = `
    <div class="record-meta">
      <strong>${escapeHtml(analysis.request.platform)}</strong>
      <span>${labelFor("issue_category", attribution.issue_category)}</span>
      <span>${labelFor("responsibility", attribution.primary_responsibility)}</span>
      <span>${labelFor("evidence", attribution.evidence_strength)}</span>
    </div>
    <p>${escapeHtml(analysis.report)}</p>
  `;
  list.prepend(article);
  applyRecordFilters();
}

function resultCard(title, body) {
  return `
    <article class="result-card">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body || "暂无信息。")}</p>
    </article>
  `;
}

function labelFor(group, value) {
  if (group === "rootCause") {
    return rootCauseLabel(value);
  }
  return labels[group]?.[value] || value || "未知";
}

function rootCauseLabel(value) {
  const rootCauses = {
    unclear_instructions: "说明或引导不清",
    expectation_mismatch: "预期与实际体验有落差",
    customer_service_gap: "客服排障引导不足",
    product_design: "产品设计容易误用",
    quality_signal: "疑似产品质量异常",
    compatibility_limit: "疑似兼容性限制",
    customer_operation: "客户操作或条件不足",
    insufficient_information: "信息不足",
    non_usage_issue: "非产品使用问题",
  };
  return rootCauses[value] || value || "未知";
}

function bindSummaryRange() {
  const select = document.getElementById("summary-range");
  if (!select) {
    return;
  }

  select.addEventListener("change", () => {
    loadRecordsSummary();
  });
}

async function loadRecordsSummary() {
  const container = document.getElementById("summary-content");
  if (!container) {
    return;
  }

  const range = document.getElementById("summary-range")?.value || "all";
  const params = new URLSearchParams();
  params.set("range", range);

  try {
    const response = await fetch(`/api/records/summary?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(readError(payload));
    }
    renderRecordsSummary(payload);
  } catch (error) {
    container.innerHTML = `<p class="summary-error">${escapeHtml(error.message || "概览加载失败，请刷新页面重试。")}</p>`;
  }
}

function renderRecordsSummary(summary) {
  const container = document.getElementById("summary-content");
  if (!container) {
    return;
  }

  container.innerHTML = `
    <div class="summary-metrics">
      ${summaryMetric("总记录数", summary.total_records)}
      ${summaryMetric("已复核", summary.reviewed_records)}
      ${summaryMetric("已修正", summary.corrected_records)}
    </div>
    <div class="summary-grid">
      ${summaryDistribution("问题类型", "issue_category", summary.issue_categories)}
      ${summaryDistribution("责任方", "responsibility", summary.responsibilities)}
      ${summaryDistribution("证据强度", "evidence", summary.evidence_strengths)}
      ${summaryDistribution("复核状态", "feedback", summary.feedback_statuses)}
    </div>
  `;
}

function summaryMetric(label, value) {
  return `
    <article class="summary-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function summaryDistribution(title, labelGroup, items = []) {
  const rows = items.length
    ? items.map((item) => `
        <li>
          <span>${escapeHtml(labelFor(labelGroup, item.value))}</span>
          <strong>${escapeHtml(item.count)}</strong>
        </li>
      `).join("")
    : `<li><span>暂无数据</span><strong>0</strong></li>`;

  return `
    <article class="summary-card distribution-card">
      <h3>${escapeHtml(title)}</h3>
      <ul class="distribution-list">${rows}</ul>
    </article>
  `;
}

function bindFilteredExport() {
  const button = document.querySelector("[data-filter-export]");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => {
    window.location.href = buildFilteredExportUrl();
  });
}

function buildFilteredExportUrl() {
  const params = new URLSearchParams();
  const summaryRange = document.getElementById("summary-range")?.value || "all";
  const query = document.getElementById("record-search")?.value.trim() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";

  if (summaryRange !== "all") {
    params.set("range", summaryRange);
  }
  if (query) {
    params.set("q", query);
  }
  if (issue) {
    params.set("issue_category", issue);
  }
  if (responsibility) {
    params.set("responsibility", responsibility);
  }
  if (feedback) {
    params.set("feedback_status", feedback);
  }

  const queryString = params.toString();
  return queryString ? `/api/records/export.csv?${queryString}` : "/api/records/export.csv";
}

function bindRecordFilters() {
  const form = document.getElementById("record-filter");
  if (!form) {
    return;
  }

  form.addEventListener("input", () => applyRecordFilters());
  form.addEventListener("change", () => applyRecordFilters());

  const reset = form.querySelector("[data-filter-reset]");
  if (reset) {
    reset.addEventListener("click", () => resetRecordFilters(form));
  }

  applyRecordFilters();
}

function applyRecordFilters() {
  const records = Array.from(document.querySelectorAll("#recent-records .record"));
  const query = document.getElementById("record-search")?.value.trim().toLowerCase() || "";
  const issue = document.getElementById("issue-filter")?.value || "";
  const responsibility = document.getElementById("responsibility-filter")?.value || "";
  const feedback = document.getElementById("feedback-filter")?.value || "";
  let visible = 0;

  records.forEach((record) => {
    const matches = recordMatchesFilters(record, { query, issue, responsibility, feedback });
    record.hidden = !matches;
    if (matches) {
      visible += 1;
    }
  });

  updateFilterState(visible, records.length);
}

function resetRecordFilters(form) {
  form.reset();
  applyRecordFilters();
}

function recordMatchesFilters(record, filters) {
  const searchText = (record.dataset.searchText || "").toLowerCase();
  const matchesQuery = !filters.query || searchText.includes(filters.query);
  const matchesIssue = !filters.issue || record.dataset.issueCategory === filters.issue;
  const matchesResponsibility = !filters.responsibility || record.dataset.responsibility === filters.responsibility;
  const matchesFeedback = !filters.feedback || record.dataset.feedbackStatus === filters.feedback;
  return matchesQuery && matchesIssue && matchesResponsibility && matchesFeedback;
}

function updateFilterState(visible, total) {
  const count = document.getElementById("filter-count");
  const empty = document.getElementById("filter-empty");
  if (count) {
    count.textContent = `当前显示 ${visible} / ${total} 条`;
  }
  if (empty) {
    empty.hidden = visible > 0 || total === 0;
  }
}

function readError(payload) {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
    return payload.detail[0].msg;
  }
  return "分析失败，请检查输入后重试。";
}

function showError(errorBox, message) {
  errorBox.textContent = message;
  errorBox.classList.add("is-visible");
}

function clearError(errorBox) {
  errorBox.textContent = "";
  errorBox.classList.remove("is-visible");
}

function setLoading(button, loading) {
  button.disabled = loading;
  if (loading) {
    button.textContent = button.dataset.loadingLabel || "处理中...";
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
