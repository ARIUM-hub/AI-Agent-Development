from pathlib import Path
import tomllib

from dev_agent import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"


def test_web_static_assets_are_declared_as_package_data() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    package_data = data["tool"]["setuptools"]["package-data"]

    assert "web/static/*" in package_data["dev_agent"]
