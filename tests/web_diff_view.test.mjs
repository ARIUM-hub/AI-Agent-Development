import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/dev_agent/web/static/diff-view.js", import.meta.url),
  "utf8",
);

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.textContent = "";
    this.attributes = new Map();
    this.listeners = new Map();
    this.type = "";
  }

  set innerHTML(_value) {
    throw new Error("动态内容不得通过 innerHTML 渲染");
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }
}

const findAll = (root, tagName) => [
  ...(root.tagName === tagName ? [root] : []),
  ...root.children.flatMap((child) => findAll(child, tagName)),
];

const elementText = (root) => [
  root.textContent,
  ...root.children.map(elementText),
].join(" ");

const sandbox = {
  document: { createElement: (tagName) => new FakeElement(tagName) },
  window: {},
};
vm.runInNewContext(source, sandbox);
const api = sandbox.window.DevAgentDiffView;

const payloadWithTwoChangedFiles = () => ({
  file_diffs: [
    {
      path: "first.md",
      status: "modified",
      diff_text: "-第一版\n+第二版\n",
      additions: 1,
      deletions: 1,
      diff_line_count: 2,
      displayed_line_count: 2,
      truncated: false,
      before_line_ending: "lf",
      after_line_ending: "lf",
    },
    {
      path: "large.md",
      status: "modified",
      diff_text: "+截断内容\n",
      additions: 485,
      deletions: 1,
      diff_line_count: 486,
      displayed_line_count: 200,
      truncated: true,
      before_line_ending: "crlf",
      after_line_ending: "lf",
    },
  ],
});

test("renders safe file navigation and selects the first changed file", () => {
  const root = new FakeElement("div");
  api.renderExecutionDiffs(root, {
    file_diffs: [
      { path: "same.md", status: "unchanged", diff_text: "" },
      {
        path: '<img src=x onerror="alert(1)">',
        status: "modified",
        diff_text: "-旧内容\n+新内容\n",
        additions: 1,
        deletions: 1,
        diff_line_count: 2,
        displayed_line_count: 2,
        truncated: false,
        before_line_ending: "crlf",
        after_line_ending: "lf",
      },
    ],
  });

  assert.match(elementText(root), /<img src=x onerror="alert\(1\)">/);
  assert.match(elementText(root), /-旧内容/);
  assert.match(elementText(root), /CRLF → LF/);
  const buttons = findAll(root, "button");
  assert.equal(buttons[1].getAttribute("aria-selected"), "true");
});

test("switches files and announces truncation", () => {
  const root = new FakeElement("div");
  api.renderExecutionDiffs(root, payloadWithTwoChangedFiles());
  const buttons = findAll(root, "button");

  buttons[1].listeners.get("click")();

  assert.equal(buttons[1].getAttribute("aria-selected"), "true");
  assert.match(elementText(root), /已显示 200\/486 行，内容已截断/);
});

test("renders a readable empty state for malformed payloads", () => {
  const root = new FakeElement("div");

  api.renderExecutionDiffs(root, { file_diffs: "invalid" });

  assert.match(elementText(root), /没有可显示的文件 Diff/);
});
