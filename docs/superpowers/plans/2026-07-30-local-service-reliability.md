# Local Service Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce local service downtime by adding bounded Scheduled Task retries and a one-shot repair script for `http://localhost:58623`.

**Architecture:** Extend the existing PowerShell startup flow rather than creating a parallel path. The Scheduled Task registration script will advertise and apply bounded retry settings, while a new repair script will inspect the task, port ownership, editable install target, and service health before delegating any real recovery to `start-local-service.ps1`.

**Tech Stack:** PowerShell 5.1, Windows Scheduled Tasks, Python 3.13, pytest

---

### Task 1: Add regression coverage for reliability outputs

**Files:**
- Modify: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_register_task_script_dry_run_reports_retry_configuration():
    completed = _run_powershell_script("register-local-service-task.ps1", "-DryRun")

    assert completed.returncode == 0
    assert "RESTART_COUNT=3" in completed.stdout
    assert "RESTART_INTERVAL=00:01:00" in completed.stdout


def test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent():
    completed = _run_powershell_script("repair-local-service.ps1", "-DryRun")

    assert completed.returncode == 0
    assert "TASK_NAME=CustomerIssueAgentLocalService" in completed.stdout
    assert "HEALTHCHECK_URL=http://127.0.0.1:58623/api/records/summary" in completed.stdout
    assert "TASK_ACTION=verify_scheduled_task" in completed.stdout
    assert "TASK_ACTION=verify_service_health" in completed.stdout
    assert "TASK_ACTION=repair_via_start_script" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_retry_configuration tests/test_service_scripts.py::test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent -q`
Expected: FAIL because the registration script does not yet report retry settings and `scripts/repair-local-service.ps1` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def test_register_task_script_dry_run_reports_retry_configuration():
    ...


def test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent():
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_retry_configuration tests/test_service_scripts.py::test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_service_scripts.py
git commit -m "test: cover local service reliability scripts"
```

### Task 2: Add bounded retry settings to task registration

**Files:**
- Modify: `scripts/register-local-service-task.ps1`
- Test: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_register_task_script_dry_run_reports_retry_configuration():
    completed = _run_powershell_script("register-local-service-task.ps1", "-DryRun")

    assert completed.returncode == 0
    assert "RESTART_COUNT=3" in completed.stdout
    assert "RESTART_INTERVAL=00:01:00" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_retry_configuration -q`
Expected: FAIL because the script does not emit retry metadata yet.

- [ ] **Step 3: Write minimal implementation**

```powershell
$RestartCount = 3
$RestartInterval = New-TimeSpan -Minutes 1

Write-Output "RESTART_COUNT=$RestartCount"
Write-Output "RESTART_INTERVAL=00:01:00"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount $RestartCount `
    -RestartInterval $RestartInterval
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_retry_configuration -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/register-local-service-task.ps1 tests/test_service_scripts.py
git commit -m "feat: add bounded scheduled task retries"
```

### Task 3: Add one-shot repair script

**Files:**
- Create: `scripts/repair-local-service.ps1`
- Modify: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent():
    completed = _run_powershell_script("repair-local-service.ps1", "-DryRun")

    assert completed.returncode == 0
    assert "TASK_NAME=CustomerIssueAgentLocalService" in completed.stdout
    assert "HEALTHCHECK_URL=http://127.0.0.1:58623/api/records/summary" in completed.stdout
    assert "TASK_ACTION=verify_scheduled_task" in completed.stdout
    assert "TASK_ACTION=verify_service_health" in completed.stdout
    assert "TASK_ACTION=repair_via_start_script" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent -q`
Expected: FAIL because `scripts/repair-local-service.ps1` does not exist.

- [ ] **Step 3: Write minimal implementation**

```powershell
param([switch]$DryRun)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start-local-service.ps1"
$HealthcheckUrl = "http://127.0.0.1:58623/api/records/summary"
$TaskName = "CustomerIssueAgentLocalService"

Write-Output "TASK_NAME=$TaskName"
Write-Output "HEALTHCHECK_URL=$HealthcheckUrl"
Write-Output "TASK_ACTION=verify_scheduled_task"
Write-Output "TASK_ACTION=verify_service_health"
Write-Output "TASK_ACTION=repair_via_start_script"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_repair_service_script_dry_run_reports_diagnostics_and_repair_intent -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/repair-local-service.ps1 tests/test_service_scripts.py
git commit -m "feat: add local service repair entrypoint"
```

### Task 4: Document recovery workflow

**Files:**
- Modify: `README.md`
- Modify: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_readme_documents_local_service_workflow():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "register-local-service-task.ps1" in readme
    assert "unregister-local-service-task.ps1" in readme
    assert "repair-local-service.ps1" in readme
    assert "失败后自动重试" in readme
    assert "http://localhost:58623" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_readme_documents_local_service_workflow -q`
Expected: FAIL because the README does not mention the repair script or bounded retry behavior.

- [ ] **Step 3: Write minimal implementation**

```markdown
计划任务在登录启动失败后会按有限次数自动重试。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair-local-service.ps1
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_readme_documents_local_service_workflow -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_service_scripts.py
git commit -m "docs: add local service recovery workflow"
```
