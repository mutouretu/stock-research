"""Parse USDA AMS 3195 fertilizer prices from archived PDFs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pypdf import PdfReader


PRODUCT_PATTERNS = {
    "anhydrous_ammonia": re.compile(r"^Anhydrous Ammonia\b", re.IGNORECASE),
    "urea_46": re.compile(r"^Urea\s*\(?46-0-0\)?(?:\s|$)", re.IGNORECASE),
    "uan_28": re.compile(r"^Liquid Nitrogen\s*\(?28-0-0\)?(?:\s|$)", re.IGNORECASE),
    "uan_32": re.compile(r"^Liquid Nitrogen\s*\(?32-0-0\)?(?:\s|$)", re.IGNORECASE),
}
NUMBER = r"[0-9][0-9,]*(?:\.\d+)?"


@dataclass(frozen=True)
class ParseSummary:
    documents: int
    parsed_documents: int
    rows: int
    errors: tuple[str, ...]
    output_path: Path

    def summary_text(self) -> str:
        return (
            f"AMS 3195 fertilizer prices: documents={self.documents}, "
            f"parsed_documents={self.parsed_documents}, rows={self.rows}, "
            f"errors={len(self.errors)}, output={self.output_path}"
        )


def parse_ams_3195_archive(
    archive_dir: str | Path,
    output_path: str | Path,
) -> ParseSummary:
    archive = Path(archive_dir).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    manifest = _load_manifest(archive / "manifest.json")
    rows: list[dict] = []
    errors: list[str] = []
    seen_hashes: set[str] = set()
    documents = 0
    parsed_documents = 0
    for path in sorted(archive.glob("*.pdf")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        documents += 1
        metadata = manifest.get(digest) or {}
        try:
            text = "\n".join(
                page.extract_text(extraction_mode="layout") or "" for page in PdfReader(path).pages
            )
            frame = parse_ams_3195_text(
                text,
                report_date=metadata.get("report_date"),
                source_document=path.name,
                source_url=metadata.get("source_url"),
                sha256=digest,
            )
            if frame.empty:
                raise ValueError("no target fertilizer rows found")
            rows.extend(frame.to_dict("records"))
            parsed_documents += 1
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"No AMS fertilizer prices parsed from {archive}")
    frame = frame.sort_values(["report_date", "product"]).drop_duplicates(
        ["report_date", "product", "sha256"], keep="last"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.stem}.tmp{output.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(output)
    return ParseSummary(documents, parsed_documents, len(frame), tuple(errors), output)


def parse_ams_3195_text(
    text: str,
    *,
    report_date: str | None,
    source_document: str,
    source_url: str | None,
    sha256: str,
) -> pd.DataFrame:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    effective_report_date = _try_extract_report_date(lines)
    if effective_report_date is None:
        if not report_date:
            raise ValueError("report date not found")
        effective_report_date = pd.Timestamp(report_date)
    available_time = _extract_publication_date(lines) or effective_report_date
    rows = _parse_old_layout(lines)
    extraction_layout = "legacy_table"
    if not rows:
        rows = _parse_aligned_rows(lines)
        extraction_layout = "aligned_table"
    if not rows:
        rows = _parse_modern_layout(lines)
        extraction_layout = "modern_table"
    normalized = []
    retrieved_at = datetime.now(timezone.utc)
    for row in rows:
        normalized.append(
            {
                "series_id": f"AMS_3195_{row['product'].upper()}",
                "product": row["product"],
                "grade": row["grade"],
                "geography": "ILLINOIS_US",
                "market_level": "distributor",
                "price_basis": "ask_fob_current",
                "price_low": row["price_low"],
                "price_high": row["price_high"],
                "price_average": row["price_average"],
                "unit": "USD_per_short_ton",
                "currency": "USD",
                "report_date": effective_report_date,
                "available_time": available_time,
                "source": "USDA_AMS_3195_PDF",
                "source_document": source_document,
                "source_url": source_url,
                "sha256": sha256,
                "extraction_layout": extraction_layout,
                "retrieved_at": retrieved_at,
            }
        )
    return pd.DataFrame(normalized)


def _parse_old_layout(lines: list[str]) -> list[dict]:
    rows = []
    row_pattern = re.compile(
        rf"^(?P<label>.+?)\s+Per ton\s+(?P<low>{NUMBER})\s*-\s*(?P<high>{NUMBER})"
        rf"\s+(?P<average>{NUMBER})(?:\s+|$)",
        re.IGNORECASE,
    )
    for line in lines:
        match = row_pattern.search(line)
        if not match:
            continue
        product = _match_product(match.group("label"))
        if product:
            rows.append(
                _price_row(
                    product,
                    match.group("low"),
                    match.group("high"),
                    match.group("average"),
                )
            )
    return rows


def _parse_modern_layout(lines: list[str]) -> list[dict]:
    rows = []
    for index, line in enumerate(lines):
        product = _match_product(line)
        if not product:
            continue
        numeric_lines = []
        for candidate in lines[index + 1 : index + 8]:
            if candidate.lower() in {"ask", "f.o.b.", "current"}:
                continue
            if re.fullmatch(rf"\(?{NUMBER}(?:\s*-\s*{NUMBER})?\)?", candidate):
                numeric_lines.append(candidate)
            if len(numeric_lines) >= 2:
                break
        if len(numeric_lines) < 2:
            continue
        low, high = _parse_range(numeric_lines[0])
        average = _to_float(numeric_lines[1].strip("()"))
        rows.append(_price_row(product, low, high, average))
    return rows


def _parse_aligned_rows(lines: list[str]) -> list[dict]:
    rows = []
    row_pattern = re.compile(
        rf"^(?P<label>.+?)\s+Ask(?:\s*-\s*FOB)?\s+(?:N/A\s+)?(?P<low>{NUMBER})"
        rf"(?:\s*-\s*(?P<high>{NUMBER}))?\s+(?P<average>{NUMBER})"
        rf"(?:\s+(?:\(?{NUMBER}\)?|(?:UP|DN)\s+{NUMBER}|UNCH))?"
        rf"\s+(?:F\.O\.B\.|Current)(?:\s|$)",
        re.IGNORECASE,
    )
    for line in lines:
        match = row_pattern.search(line)
        if not match:
            continue
        product = _match_product(match.group("label"))
        if product:
            low = match.group("low")
            rows.append(
                _price_row(
                    product,
                    low,
                    match.group("high") or low,
                    match.group("average"),
                )
            )
    return rows


def _match_product(label: str) -> str | None:
    for product, pattern in PRODUCT_PATTERNS.items():
        if pattern.search(label):
            return product
    return None


def _price_row(product: str, low: str | float, high: str | float, average: str | float) -> dict:
    grades = {
        "anhydrous_ammonia": "NH3",
        "urea_46": "46-0-0",
        "uan_28": "28-0-0",
        "uan_32": "32-0-0",
    }
    return {
        "product": product,
        "grade": grades[product],
        "price_low": _to_float(low),
        "price_high": _to_float(high),
        "price_average": _to_float(average),
    }


def _parse_range(value: str) -> tuple[float, float]:
    parts = re.split(r"\s*-\s*", value.strip("()"), maxsplit=1)
    low = _to_float(parts[0])
    return low, _to_float(parts[1]) if len(parts) == 2 else low


def _to_float(value: str | float) -> float:
    return float(str(value).replace(",", ""))


def _extract_report_date(lines: list[str]) -> pd.Timestamp:
    text = "\n".join(lines[:20])
    match = re.search(r"Report for(?: week ending)?\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    if not match:
        raise ValueError("report date not found")
    return pd.Timestamp(match.group(1))


def _try_extract_report_date(lines: list[str]) -> pd.Timestamp | None:
    try:
        return _extract_report_date(lines)
    except ValueError:
        return None


def _extract_publication_date(lines: list[str]) -> pd.Timestamp | None:
    text = "\n".join(lines[:15])
    match = re.search(
        r"(?:Mon|Tue|Wed|Thu|Fri)\s+([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
        text,
    )
    return pd.Timestamp(match.group(1)) if match else None


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    values = json.loads(path.read_text(encoding="utf-8"))
    return values if isinstance(values, dict) else {}
