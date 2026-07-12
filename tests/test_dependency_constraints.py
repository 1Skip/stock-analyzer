import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _package_name(line: str) -> str:
    return re.split(r"[<>=!~]", line, maxsplit=1)[0].strip().lower().replace("_", "-")


def _requirement_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_all_direct_requirements_have_exact_constraints():
    requirements = {_package_name(line) for line in _requirement_lines(ROOT / "requirements.txt")}
    constraint_lines = _requirement_lines(ROOT / "constraints.txt")
    constraints = {_package_name(line) for line in constraint_lines}

    assert requirements <= constraints
    assert all("==" in line for line in constraint_lines)


def test_install_entrypoints_use_constraints_file():
    expected = {
        "start.bat": "-c constraints.txt",
        "start.sh": "-c constraints.txt",
        ".devcontainer/devcontainer.json": "-c constraints.txt",
        ".github/workflows/test.yml": "-c constraints.txt",
        ".github/workflows/real-data-contracts.yml": "-c constraints.txt",
    }

    for relative_path, marker in expected.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert marker in source, relative_path


def test_local_install_entrypoints_require_python_311():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    windows_launcher = (ROOT / "start.bat").read_text(encoding="utf-8")
    posix_launcher = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "Python 3.11 或更高版本" in readme
    assert "Python 3.10 或更高版本" not in readme
    for source in (windows_launcher, posix_launcher):
        assert "Python 3.11 or newer" in source
        assert "sys.version_info >= (3, 11)" in source
        assert "Python 3.10 or newer" not in source
