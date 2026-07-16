#!/usr/bin/env python3
"""Generate the M4.3 state-timeline PGFPlots fragment from its JSON report."""

from __future__ import annotations

import json
from pathlib import Path


PUBLICATION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PUBLICATION_ROOT.parents[1]
REPORT_PATH = PROJECT_ROOT / "reports/cycle_analysis/cf_cycle_state_v1.json"
OUTPUT_PATH = PUBLICATION_ROOT / "figures/cf_cycle_state_timeline.tex"

COLORS = {
    "RECOVERY": "stateRecovery",
    "EXPANSION": "stateExpansion",
    "PEAK_RISK": "statePeak",
    "CONTRACTION": "stateContraction",
    "TROUGH": "stateTrough",
    "MIXED": "stateMixed",
}


def main() -> int:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    monthly = report["monthly"]
    episodes = report["episodes"]
    start_year = 2016
    end_year = 2027
    lines = [
        r"\definecolor{stateRecovery}{HTML}{8DD3C7}",
        r"\definecolor{stateExpansion}{HTML}{80B1D3}",
        r"\definecolor{statePeak}{HTML}{FDB462}",
        r"\definecolor{stateContraction}{HTML}{FB8072}",
        r"\definecolor{stateTrough}{HTML}{B3DE69}",
        r"\definecolor{stateMixed}{HTML}{D9D9D9}",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=\textwidth,height=7.1cm,",
        f"  xmin={start_year},xmax={end_year},ymin=-2.1,ymax=2.1,",
        r"  xtick={2016,2018,2020,2022,2024,2026},",
        r"  ytick={-2,-1,0,1,2},",
        r"  xlabel={月份},ylabel={周期分数},",
        r"  axis lines=left,grid=major,grid style={gray!18},",
        r"  tick label style={font=\small},label style={font=\small},",
        r"  clip=false",
        r"]",
    ]
    for episode in episodes:
        start = max(_month_start(episode["start_month"]), start_year)
        end = min(_month_after(episode["end_month"]), end_year)
        if end <= start:
            continue
        color = COLORS[episode["state"]]
        lines.append(
            rf"\path[fill={color},fill opacity=0.32,draw=none] "
            rf"(axis cs:{start:.5f},-2.1) rectangle (axis cs:{end:.5f},2.1);"
        )
    lines.extend(
        [
            r"\addplot[black,very thick] coordinates {",
            *[
                f"  ({_decimal_year(row['month_end']):.5f},"
                f"{_score(row['cycle_score'])})"
                for row in monthly
                if int(row["month_end"][:4]) >= start_year
            ],
            r"};",
            r"\addplot[black!45,densely dashed] coordinates {(2016,0) (2027,0)};",
            r"\end{axis}",
            r"\node[anchor=north,font=\scriptsize,yshift=-3mm] at (current bounding box.south) {",
            r"\textcolor{stateRecovery}{\rule{0.24cm}{0.15cm}} 修复\quad",
            r"\textcolor{stateExpansion}{\rule{0.24cm}{0.15cm}} 扩张\quad",
            r"\textcolor{statePeak}{\rule{0.24cm}{0.15cm}} 高位转弱\quad",
            r"\textcolor{stateContraction}{\rule{0.24cm}{0.15cm}} 收缩\quad",
            r"\textcolor{stateTrough}{\rule{0.24cm}{0.15cm}} 低位转强\quad",
            r"\textcolor{stateMixed}{\rule{0.24cm}{0.15cm}} 混合/缺口};",
            r"\end{tikzpicture}",
            "",
        ]
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"figure={OUTPUT_PATH}")
    return 0


def _decimal_year(timestamp: str) -> float:
    year, month, day = (int(value) for value in timestamp[:10].split("-"))
    return year + (month - 1 + (day - 1) / 31) / 12


def _month_start(timestamp: str) -> float:
    year, month = (int(value) for value in timestamp[:7].split("-"))
    return year + (month - 1) / 12


def _month_after(timestamp: str) -> float:
    year, month = (int(value) for value in timestamp[:7].split("-"))
    if month == 12:
        return year + 1.0
    return year + month / 12


def _score(value) -> str:
    return "nan" if value is None else f"{float(value):.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
