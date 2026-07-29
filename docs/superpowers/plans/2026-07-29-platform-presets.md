# Platform Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add common overseas e-commerce platform presets to the existing platform inputs while preserving free-form platform entry.

**Architecture:** Use a shared HTML `datalist` in the existing Jinja template and point the three existing `platform` text inputs at it. Keep all backend APIs, storage, filtering, export, and summary behavior unchanged because the submitted field remains the same string field.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, pytest, httpx/TestClient.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-platform-presets-design.md`

## Scope Check

This plan implements only platform input presets with HTML `datalist`. It does not add platform account binding, platform API sync, platform-specific parsers, platform enum migration, alias normalization, storage changes, JavaScript, or model calls.

## File Structure

- Modify: `tests/test_app.py`
  - Add homepage tests for the shared platform preset datalist and the three input bindings.
- Modify: `src/customer_issue_agent/templates/index.html`
  - Add `list="platform-presets"` to `paste-platform`, `upload-platform`, and `batch-platform`.
  - Add one shared `<datalist id="platform-presets">` with common overseas e-commerce platform options.
- Modify: `README.md`
  - Document that users can choose a preset or type another overseas e-commerce platform.

## Task 1: Platform Preset Markup

**Files:**
- Modify: `tests/test_app.py`
- Modify: `src/customer_issue_agent/templates/index.html`

- [ ] **Step 1: Write failing platform preset markup test**

Append to `tests/test_app.py`:

```python
def test_index_contains_platform_presets_for_all_platform_inputs(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="platform-presets"' in html
    assert 'id="paste-platform" name="platform" list="platform-presets"' in html
    assert 'id="upload-platform" name="platform" list="platform-presets"' in html
    assert 'id="batch-platform" name="platform" list="platform-presets"' in html
    assert 'value="Amazon"' in html
    assert 'value="TikTok Shop"' in html
    assert 'value="Shopee"' in html
    assert 'value="Walmart Marketplace"' in html
    assert 'value="eBay"' in html
    assert 'value="Shopify"' in html
    assert 'value="AliExpress"' in html
    assert 'value="Lazada"' in html
    assert 'value="Temu"' in html
    assert 'value="Shein"' in html
    assert 'value="Other overseas platform"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_platform_presets_for_all_platform_inputs -q
```

Expected: FAIL because `platform-presets` and `list="platform-presets"` do not exist.

- [ ] **Step 3: Add datalist bindings and options**

Modify the three platform inputs in `src/customer_issue_agent/templates/index.html`:

```html
<input id="paste-platform" name="platform" list="platform-presets" value="Other overseas platform">
<input id="upload-platform" name="platform" list="platform-presets" value="Other overseas platform">
<input id="batch-platform" name="platform" list="platform-presets" value="Other overseas platform">
```

Add the shared datalist once before the closing `</main>` or before the feedback template:

```html
    <datalist id="platform-presets">
      <option value="Amazon"></option>
      <option value="TikTok Shop"></option>
      <option value="Shopee"></option>
      <option value="Walmart Marketplace"></option>
      <option value="eBay"></option>
      <option value="Shopify"></option>
      <option value="AliExpress"></option>
      <option value="Lazada"></option>
      <option value="Temu"></option>
      <option value="Shein"></option>
      <option value="Other overseas platform"></option>
    </datalist>
```

- [ ] **Step 4: Run markup test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py::test_index_contains_platform_presets_for_all_platform_inputs -q
```

Expected: selected test passes.

- [ ] **Step 5: Run app tests**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/test_app.py -q
```

Expected: all app tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html tests/test_app.py
git commit -m "feat: add platform presets"
```

## Task 2: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README platform usage**

Modify the “工作台使用方式” section in `README.md` so the platform source guidance says:

```markdown
平台来源输入框提供 Amazon、TikTok Shop、Shopee、Walmart Marketplace、eBay、Shopify、AliExpress、Lazada、Temu、Shein 等常用海外电商平台预设；也可以直接输入其他海外电商平台名称。
```

Keep the manual acceptance sample with `Other overseas platform`.

- [ ] **Step 2: Run full automated verification**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Check worktree status**

Run:

```powershell
git status --short --branch
```

Expected: only README is modified before commit.

- [ ] **Step 4: Commit**

Run:

```powershell
git add README.md
git commit -m "docs: document platform presets"
```

## Final Verification

- [ ] Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest -q
```

Expected: all tests pass.

- [ ] Run:

```powershell
git status --short --branch
```

Expected: clean worktree on `codex/customer-issue-agent-mvp`.

- [ ] Push to target repository:

```powershell
git push https://github.com/ARIUM-hub/Agent-Operations-Workflow.git codex/customer-issue-agent-mvp:codex/customer-issue-agent-mvp
```

Expected: push succeeds and updates the existing open PR in `ARIUM-hub/Agent-Operations-Workflow`.

## Self-Review Checklist

- Spec coverage: shared datalist, three platform inputs, all requested platform presets, free-form entry preservation, README docs, and regression verification are covered.
- Deferred items: platform account binding, platform API sync, platform-specific parsers, enum migration, alias normalization, storage changes, JavaScript, and model calls are intentionally excluded.
- Placeholder scan: this plan contains no unfinished placeholder markers.
- Type consistency: `platform-presets`, `paste-platform`, `upload-platform`, and `batch-platform` are named consistently across tasks.
