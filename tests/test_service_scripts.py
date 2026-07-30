from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_powershell_script(script_name: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    script = PROJECT_ROOT / "scripts" / script_name
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_start_service_script_dry_run_reports_fixed_project_paths():
    completed = _run_powershell_script("start-local-service.ps1", "-DryRun")

    assert completed.returncode == 0
    assert str(PROJECT_ROOT) in completed.stdout
    assert str(PROJECT_ROOT / "src") in completed.stdout
    assert "127.0.0.1:58623" in completed.stdout


def test_start_service_script_dry_run_reports_bootstrap_actions():
    completed = _run_powershell_script("start-local-service.ps1", "-DryRun", "-ForceReinstall")

    assert completed.returncode == 0
    assert "TASK_ACTION=repair_editable_install" in completed.stdout
    assert "TASK_ACTION=stop_existing_customer_issue_agent_processes" in completed.stdout
    assert "TASK_ACTION=start_uvicorn" in completed.stdout
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in completed.stdout


def test_register_task_script_dry_run_reports_task_configuration():
    completed = _run_powershell_script("register-local-service-task.ps1", "-DryRun")

    assert completed.returncode == 0
    assert "TASK_NAME=CustomerIssueAgentLocalService" in completed.stdout
    assert "TRIGGER=AtLogOn" in completed.stdout
    assert "start-local-service.ps1" in completed.stdout


def test_readme_documents_local_service_workflow():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "register-local-service-task.ps1" in readme
    assert "unregister-local-service-task.ps1" in readme
    assert "http://localhost:58623" in readme
