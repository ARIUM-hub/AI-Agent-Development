(() => {
  const STATUS_LABELS = {
    added: "新增",
    modified: "修改",
    unchanged: "无净变更",
  };
  const LINE_ENDING_LABELS = {
    crlf: "CRLF",
    lf: "LF",
    mixed: "混合换行",
    none: "无换行",
  };

  const appendText = (parent, tagName, className, text) => {
    const element = document.createElement(tagName);
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
  };

  const renderExecutionDiffs = (root, payload) => {
    root.replaceChildren();
    const diffs = Array.isArray(payload?.file_diffs) ? payload.file_diffs : [];
    if (diffs.length === 0) {
      appendText(root, "div", "diff-empty-state", "没有可显示的文件 Diff。");
      return;
    }

    let selectedIndex = diffs.findIndex((item) => item?.status !== "unchanged");
    if (selectedIndex < 0) selectedIndex = 0;

    const shell = document.createElement("div");
    shell.className = "diff-browser";
    const navigation = document.createElement("div");
    navigation.className = "diff-file-navigation";
    navigation.setAttribute("role", "tablist");
    navigation.setAttribute("aria-label", "执行 Diff 文件");
    const panel = document.createElement("div");
    panel.className = "diff-current-panel";
    panel.setAttribute("role", "tabpanel");

    const renderCurrent = () => {
      panel.replaceChildren();
      const current = diffs[selectedIndex] || {};
      appendText(panel, "h4", "diff-current-path", current.path || "未命名路径");
      const status = STATUS_LABELS[current.status] || "未知状态";
      const beforeEnding = LINE_ENDING_LABELS[current.before_line_ending] || "未知";
      const afterEnding = LINE_ENDING_LABELS[current.after_line_ending] || "未知";
      appendText(
        panel,
        "div",
        "diff-current-meta",
        `${status} · +${current.additions || 0} -${current.deletions || 0} · ${beforeEnding} → ${afterEnding}`,
      );
      if (current.truncated === true) {
        appendText(
          panel,
          "div",
          "diff-truncation-note",
          `已显示 ${current.displayed_line_count || 0}/${current.diff_line_count || 0} 行，内容已截断`,
        );
      }
      appendText(panel, "pre", "execution-diff", current.diff_text || "没有净变更。");
    };

    const buttons = diffs.map((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "diff-file-button";
      button.setAttribute("role", "tab");
      button.textContent = `${item?.path || "未命名路径"}  +${item?.additions || 0} -${item?.deletions || 0}`;
      button.addEventListener("click", () => {
        selectedIndex = index;
        buttons.forEach((entry, entryIndex) => {
          entry.setAttribute("aria-selected", String(entryIndex === selectedIndex));
        });
        renderCurrent();
      });
      navigation.appendChild(button);
      return button;
    });
    buttons.forEach((button, index) => {
      button.setAttribute("aria-selected", String(index === selectedIndex));
    });
    renderCurrent();
    shell.append(navigation, panel);
    root.appendChild(shell);
  };

  window.DevAgentDiffView = { renderExecutionDiffs };
})();
