# Local Service Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable local startup flow that always launches the customer issue agent from the current worktree on `http://localhost:58623` and can be registered as a Windows logon task.

**Architecture:** Add project-owned PowerShell scripts for bootstrap, task registration, and task removal. The bootstrap script derives the project root from its own path, checks whether the editable install points at the current `src` directory, repairs it when needed, guards the fixed port, and starts a single `uvicorn` instance with file logs.

**Tech Stack:** PowerShell 5+, Windows Scheduled Tasks, Python 3.13, pip editable install, uvicorn, pytest

---

### Task 1: Add script regression coverage

**Files:**
- Create: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import subprocess
import sys


def test_start_service_script_dry_run_reports_fixed_project_paths():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "start-local-service.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-DryRun",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert str(project_root) in completed.stdout
    assert str(project_root / "src") in completed.stdout
    assert "127.0.0.1:58623" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_start_service_script_dry_run_reports_fixed_project_paths -v`
Expected: FAIL because `scripts/start-local-service.ps1` does not exist.

- [ ] **Step 3: Write minimal implementation**

```powershell
param([switch]$DryRun)

$projectRoot = Split-Path -Parent $PSScriptRoot
$expectedSrc = Join-Path $projectRoot "src"
Write-Output "PROJECT_ROOT=$projectRoot"
Write-Output "EXPECTED_SRC=$expectedSrc"
Write-Output "SERVICE_URL=http://127.0.0.1:58623"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_start_service_script_dry_run_reports_fixed_project_paths -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_service_scripts.py scripts/start-local-service.ps1
git commit -m "test: cover local service bootstrap dry run"
```

### Task 2: Build stable bootstrap script

**Files:**
- Modify: `scripts/start-local-service.ps1`
- Test: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_start_service_script_dry_run_reports_bootstrap_actions():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "start-local-service.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-DryRun",
            "-ForceReinstall",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert "TASK_ACTION=repair_editable_install" in completed.stdout
    assert "TASK_ACTION=stop_existing_customer_issue_agent_processes" in completed.stdout
    assert "TASK_ACTION=start_uvicorn" in completed.stdout
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_start_service_script_dry_run_reports_bootstrap_actions -v`
Expected: FAIL because the dry-run output does not yet include bootstrap actions.

- [ ] **Step 3: Write minimal implementation**

```powershell
param(
  [switch]$DryRun,
  [switch]$ForceReinstall
)

$PythonIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple"
Write-Output "TASK_ACTION=repair_editable_install"
Write-Output "TASK_ACTION=stop_existing_customer_issue_agent_processes"
Write-Output "TASK_ACTION=start_uvicorn"
Write-Output "PIP_INDEX_URL=$PythonIndexUrl"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_start_service_script_dry_run_reports_bootstrap_actions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/start-local-service.ps1 tests/test_service_scripts.py
git commit -m "feat: add stable local service bootstrap"
```

### Task 3: Add scheduled task registration scripts

**Files:**
- Create: `scripts/register-local-service-task.ps1`
- Create: `scripts/unregister-local-service-task.ps1`
- Modify: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_register_task_script_dry_run_reports_task_configuration():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "register-local-service-task.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-DryRun",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert "TASK_NAME=CustomerIssueAgentLocalService" in completed.stdout
    assert "TRIGGER=AtLogOn" in completed.stdout
    assert "start-local-service.ps1" in completed.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_task_configuration -v`
Expected: FAIL because `scripts/register-local-service-task.ps1` does not exist.

- [ ] **Step 3: Write minimal implementation**

```powershell
param([switch]$DryRun)

$taskName = "CustomerIssueAgentLocalService"
$bootstrapScript = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\start-local-service.ps1"

Write-Output "TASK_NAME=$taskName"
Write-Output "TRIGGER=AtLogOn"
Write-Output "BOOTSTRAP_SCRIPT=$bootstrapScript"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_register_task_script_dry_run_reports_task_configuration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/register-local-service-task.ps1 scripts/unregister-local-service-task.ps1 tests/test_service_scripts.py
git commit -m "feat: add scheduled task wrappers for local service"
```

### Task 4: Document the supported workflow

**Files:**
- Modify: `README.md`
- Modify: `tests/test_service_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_readme_documents_local_service_workflow():
    project_root = Path(__file__).resolve().parents[1]
    readme = (project_root / "README.md").read_text(encoding="utf-8")

    assert "register-local-service-task.ps1" in readme
    assert "unregister-local-service-task.ps1" in readme
    assert "http://localhost:58623" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_scripts.py::test_readme_documents_local_service_workflow -v`
Expected: FAIL because README still documents the old ad-hoc `uvicorn` startup on port `8000`.

- [ ] **Step 3: Write minimal implementation**

```markdown
## 常驻本机服务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-local-service-task.ps1
```

访问 `http://localhost:58623`。

移除任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\unregister-local-service-task.ps1
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_scripts.py::test_readme_documents_local_service_workflow -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_service_scripts.py
git commit -m "docs: add local service startup workflow"
```
