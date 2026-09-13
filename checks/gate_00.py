"""Stage 0 gate, environment bootstrap."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REQUIRED_DIRS = [
    "data/raw", "data/interim", "data/processed", "data/dashboard",
    "db", "sql", "src", "checks", "notebooks", "dashboard", "app",
    "app/.streamlit", "reports/figures", "reports/gate_reports",
    "reports/metrics", "docs", "docs/screenshots", "plan",
]

REQUIRED_FILES = ["config.yaml", "CLAUDE.md", ".gitignore", "requirements.txt"]


def _redact(path_str: str) -> str:
    """Replace the local repo-root prefix with a placeholder before writing to a
    committed report. A gate report is published, and the absolute filesystem
    path it would otherwise contain leaks the local username (DECISIONS.md D-0006)."""
    return path_str.replace(str(REPO_ROOT), "<repo-root>")


def main() -> int:
    failures: list[str] = []
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        lines.append(f"[{status}] {label} {_redact(detail)}")
        if not cond:
            failures.append(label)

    check("Python >= 3.10", sys.version_info >= (3, 10), str(sys.version_info))
    check("Interpreter is the project .venv", ".venv" in sys.executable.replace("\\", "/"),
          sys.executable)

    for mod in ["pandas", "numpy", "scipy", "sklearn", "matplotlib", "seaborn",
                "pyarrow", "openpyxl", "yaml"]:
        try:
            __import__(mod)
            check(f"import {mod}", True)
        except ImportError as exc:
            check(f"import {mod}", False, str(exc))

    for d in REQUIRED_DIRS:
        check(f"dir exists: {d}", (REPO_ROOT / d).is_dir())

    for f in REQUIRED_FILES:
        p = REPO_ROOT / f
        check(f"file non-empty: {f}", p.exists() and p.stat().st_size > 0)

    try:
        from src.config import cfg
        check("cfg.project.seed == 42", cfg.project.seed == 42, str(cfg.project.seed))
    except Exception as exc:  # noqa: BLE001
        check("from src.config import cfg", False, str(exc))

    raw_xlsx = REPO_ROOT / "data/raw/online_retail_II.xlsx"
    size_ok = raw_xlsx.exists() and 35_000_000 <= raw_xlsx.stat().st_size <= 60_000_000
    check("raw xlsx exists, size in [35MB,60MB]", size_ok,
          f"size={raw_xlsx.stat().st_size if raw_xlsx.exists() else 'MISSING'}")

    sheet_names: list[str] = []
    if raw_xlsx.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(raw_xlsx, read_only=True)
            sheet_names = wb.sheetnames
            from src.config import cfg
            expected_sheets = set(cfg.ingest.sheets)
            check("both configured sheets present", expected_sheets.issubset(set(sheet_names)),
                  str(sheet_names))
        except Exception as exc:  # noqa: BLE001
            check("openpyxl can open raw xlsx", False, str(exc))

    try:
        out = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                              cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        check("git rev-parse --is-inside-work-tree", out.stdout.strip() == "true", out.stdout.strip())
    except Exception as exc:  # noqa: BLE001
        check("git available", False, str(exc))

    pip_freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                 capture_output=True, text=True, check=False).stdout

    report_path = REPO_ROOT / "reports/gate_reports/gate_00.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("# Stage 0 Gate Report: Environment Bootstrap\n\n")
        fh.write(f"Python version: `{sys.version}`\n\n")
        fh.write(f"Interpreter: `{_redact(sys.executable)}`\n\n")
        fh.write(f"Raw xlsx size (MB): {raw_xlsx.stat().st_size / 1e6:.2f}\n\n" if raw_xlsx.exists() else "Raw xlsx: MISSING\n\n")
        fh.write(f"Sheet names found: {sheet_names}\n\n")
        fh.write("## Checks\n\n```\n" + "\n".join(lines) + "\n```\n\n")
        fh.write("## pip freeze\n\n```\n" + pip_freeze + "\n```\n\n")
        fh.write(f"## GATE: {'PASS' if not failures else 'FAIL'}\n")

    print("\n".join(lines))
    print(f"\nGATE: {'PASS' if not failures else 'FAIL'}")
    if failures:
        print(f"\nFailed checks: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
