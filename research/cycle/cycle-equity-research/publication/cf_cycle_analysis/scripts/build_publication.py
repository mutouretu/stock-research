#!/usr/bin/env python3
"""Regenerate publication figures and compile the CF cycle-analysis PDF."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PUBLICATION_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = PUBLICATION_ROOT / "build"
MAIN_TEX = PUBLICATION_ROOT / "cf_cycle_analysis.tex"
FIGURE_SCRIPT = PUBLICATION_ROOT / "scripts/generate_lead_lag_figure.py"


def main() -> int:
    xelatex = shutil.which("xelatex")
    if not xelatex:
        raise RuntimeError("xelatex is required to build the publication")
    subprocess.run([sys.executable, str(FIGURE_SCRIPT)], check=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        xelatex,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={BUILD_DIR}",
        MAIN_TEX.name,
    ]
    for _ in range(2):
        completed = subprocess.run(
            command,
            cwd=PUBLICATION_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            raise subprocess.CalledProcessError(completed.returncode, command)
    print(f"pdf={BUILD_DIR / MAIN_TEX.with_suffix('.pdf').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
