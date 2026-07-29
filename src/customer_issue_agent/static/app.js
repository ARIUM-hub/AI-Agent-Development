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
};

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindAnalysisForm("paste-form", "paste-error");
  bindAnalysisForm("upload-form", "upload-error");
  bindBatchForm();
  bindFeedbackForms(document);
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
