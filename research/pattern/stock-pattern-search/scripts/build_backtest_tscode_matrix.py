from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _find_final_candidates_path(day_dir: Path) -> Path | None:
    dated_path = day_dir / f"{day_dir.name}_final_candidates.csv"
    if dated_path.exists():
        return dated_path
    legacy_path = day_dir / "final_candidates.csv"
    if legacy_path.exists():
        return legacy_path
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a date-column ts_code matrix from cached range final candidates.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--code-format", choices=["ts_code", "stock_code"], default="ts_code")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    rows: dict[int, dict[str, str]] = {rank: {"rank": str(rank)} for rank in range(1, args.top_n + 1)}
    target_dates: list[str] = []

    for day_dir in sorted(path for path in input_dir.iterdir() if path.is_dir()):
        final_path = _find_final_candidates_path(day_dir)
        if final_path is None:
            continue
        target_date = day_dir.name
        final = pd.read_csv(final_path).head(args.top_n)
        target_dates.append(target_date)
        values = final["ts_code"].astype(str).tolist()
        if args.code_format == "stock_code":
            values = [value.split(".")[0] for value in values]
        for rank in range(1, args.top_n + 1):
            rows[rank][target_date] = values[rank - 1] if rank <= len(values) else ""

    matrix = pd.DataFrame([rows[rank] for rank in range(1, args.top_n + 1)])
    ordered = ["rank", *target_dates]
    matrix = matrix[ordered] if target_dates else pd.DataFrame(columns=["rank"])

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_csv, index=False)
    print(output_csv)


if __name__ == "__main__":
    main()
