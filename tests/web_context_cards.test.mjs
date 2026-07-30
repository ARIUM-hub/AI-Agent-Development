import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import vm from "node:vm";

const appPath = new URL("../src/dev_agent/web/static/app.js", import.meta.url);
const appSource = readFileSync(appPath, "utf8");
const historyMarker = 'const historyCards = () => document.getElementById("history-cards");';
const contextSource = appSource.slice(0, appSource.indexOf(historyMarker));

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.textContent = "";
    this.attributes = new Map();
    this.listeners = new Map();
    this.isConnected = true;
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

const elementText = (element) => [
  element.textContent,
  ...element.children.map(elementText),
].join(" ");

const loadContextApi = ({ writeText = async () => {} } = {}) => {
  const contextRoot = new FakeElement("div");
  const timers = [];
  const sandbox = {
    document: {
      createElement: (tagName) => new FakeElement(tagName),
      getElementById: (id) => (id === "context-cards" ? contextRoot : new FakeElement("div")),
    },
    fetch: async () => ({ json: async () => ({}) }),
    navigator: { clipboard: { writeText } },
    window: { setTimeout: (callback) => timers.push(callback) },
  };
  vm.runInNewContext(
    `${contextSource}\n` +
      "globalThis.contextTestApi = {" +
      "formatContextCommand, collectContextCommands, copyContextCommand, renderContextCards" +
      "};",
    sandbox,
  );
  return { api: sandbox.contextTestApi, contextRoot, timers };
};

test("formats command arrays as runnable PowerShell text", () => {
  const { api } = loadContextApi();

  assert.equal(
    api.formatContextCommand(["python", "-m", "pytest"]),
    "& 'python' --% -m pytest",
  );
  assert.equal(api.formatContextCommand(["python", ""]), "& 'python' --% \"\"");
  assert.equal(
    api.formatContextCommand([
      "C:\\Program Files\\Python\\python.exe",
      "C:\\work tree\\tests",
      "O'Brien",
      'say "hi"',
      "tab\tvalue",
    ]),
    "& 'C:\\Program Files\\Python\\python.exe' --% " +
      '"C:\\work tree\\tests" O\'Brien "say \\"hi\\"" "tab\tvalue"',
  );
});

test(
  "round-trips command arguments through Windows PowerShell",
  { skip: process.platform !== "win32" },
  () => {
    const { api } = loadContextApi();
    const probeDirectory = mkdtempSync(join(tmpdir(), "dev agent argv "));
    const probePath = join(probeDirectory, "argv probe.mjs");
    const expected = [
      "",
      "space value",
      'say "hi"',
      "ends-with\\",
      "space-end \\",
      "O'Brien",
      "tab\tvalue",
    ];
    writeFileSync(probePath, "console.log(JSON.stringify(process.argv.slice(2)));\n", "utf8");

    try {
      const command = api.formatContextCommand([process.execPath, probePath, ...expected]);
      const completed = spawnSync(
        "powershell.exe",
        ["-NoProfile", "-Command", command],
        { encoding: "utf8", windowsHide: true },
      );
      assert.equal(completed.status, 0, completed.stderr || completed.stdout);
      const output = completed.stdout.trim().split(/\r?\n/).at(-1);
      assert.deepEqual(JSON.parse(output), expected);
    } finally {
      rmSync(probeDirectory, { force: true, recursive: true });
    }
  },
);

test("falls back to suggested commands when verification step names are invalid", () => {
  const { api } = loadContextApi();
  const commands = api.collectContextCommands({
    verification_steps: [{ name: "", command: ["invalid"] }],
    scan: { suggested_commands: { test: "python -m pytest" } },
  });

  assert.deepEqual(
    JSON.parse(JSON.stringify(commands)),
    [{ label: "测试", command: "python -m pytest" }],
  );
});

test("deduplicates valid verification commands", () => {
  const { api } = loadContextApi();
  const commands = api.collectContextCommands({
    verification_steps: [
      { name: "test", command: ["python", "-m", "pytest"] },
      { name: "lint", command: ["python", "-m", "pytest"] },
    ],
  });

  assert.equal(commands.length, 1);
  assert.equal(commands[0].label, "测试");
  assert.equal(commands[0].command, "& 'python' --% -m pytest");
});

test("renders hostile and missing payload values as text", () => {
  const { api, contextRoot } = loadContextApi();
  api.renderContextCards({
    project: { name: '<img src=x onerror="alert(1)">' },
    scan: { languages: "not-an-array" },
    git: null,
    verification_steps: null,
    rules_text: '<script>alert("x")</script>',
  });

  const renderedText = elementText(contextRoot);
  assert.match(renderedText, /<img src=x onerror="alert\(1\)">/);
  assert.match(renderedText, /<script>alert\("x"\)<\/script>/);
  assert.match(renderedText, /暂无 Git 状态/);
  assert.match(renderedText, /暂无验证命令/);
  assert.equal(contextRoot.children.length, 3);
});

test("announces clipboard success and failure through a status node", async () => {
  let writtenCommand = "";
  const success = loadContextApi({
    writeText: async (command) => {
      writtenCommand = command;
    },
  });
  const successButton = new FakeElement("button");
  successButton.textContent = "一键复制";
  const successStatus = new FakeElement("span");

  await success.api.copyContextCommand(successButton, successStatus, "python -m pytest");

  assert.equal(writtenCommand, "python -m pytest");
  assert.equal(successButton.textContent, "已复制");
  assert.equal(successStatus.textContent, "命令已复制");
  success.timers[0]();
  assert.equal(successButton.textContent, "一键复制");
  assert.equal(successStatus.textContent, "");

  const failure = loadContextApi({
    writeText: async () => {
      throw new Error("permission denied");
    },
  });
  const failureButton = new FakeElement("button");
  failureButton.textContent = "一键复制";
  const failureStatus = new FakeElement("span");

  await failure.api.copyContextCommand(failureButton, failureStatus, "python -m pytest");

  assert.equal(failureButton.textContent, "复制失败");
  assert.equal(failureStatus.textContent, "命令复制失败");
});
