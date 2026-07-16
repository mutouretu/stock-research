"""Archive and normalize CF quarterly operating metrics from SEC 8-K exhibits."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import certifi
import pandas as pd
from bs4 import BeautifulSoup
import ssl


CIK = "1324404"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001324404.json"
ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data/1324404"


def download_cf_product_operations(
    raw_dir: str | Path,
    *,
    user_agent: str,
    start_year: int = 2013,
) -> pd.DataFrame:
    """Download CF earnings exhibits, archive them, and return current-quarter metrics."""
    raw = Path(raw_dir).expanduser().resolve()
    raw.mkdir(parents=True, exist_ok=True)
    filings = _discover_filings(user_agent, start_year)
    manifest_path = raw / "manifest.json"
    manifest = _read_manifest(manifest_path)
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    retrieved_at = datetime.now(timezone.utc)

    for filing in filings:
        accession = filing["accessionNumber"]
        try:
            existing = manifest.get(accession, {})
            existing_path = raw / str(existing.get("filename", ""))
            if (
                existing.get("source_url")
                and existing_path.is_file()
                and int(existing.get("parsed_rows", 0)) > 0
            ):
                exhibit_url = str(existing["source_url"])
                payload = existing_path.read_bytes()
            else:
                exhibit_url = _find_earnings_exhibit(accession, user_agent)
                payload = _get(exhibit_url, user_agent)
            digest = hashlib.sha256(payload).hexdigest()
            filename = f"{accession}_{Path(exhibit_url).name}"
            path = raw / filename
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(payload)
                temporary.replace(path)
            frame = parse_cf_earnings_exhibit(
                payload.decode("utf-8", errors="replace"),
                accession=accession,
                filing_date=filing["filingDate"],
                source_url=exhibit_url,
                retrieved_at=retrieved_at,
            )
            if not frame.empty:
                frames.append(frame)
            manifest[accession] = {
                "filename": filename,
                "filing_date": filing["filingDate"],
                "report_date": filing.get("reportDate"),
                "source_url": exhibit_url,
                "sha256": digest,
                "bytes": len(payload),
                "parsed_rows": len(frame),
                "downloaded_at": retrieved_at.isoformat(),
            }
            time.sleep(0.12)
        except Exception as exc:
            errors.append(f"{accession}: {exc}")

    _write_manifest(manifest_path, manifest, errors)
    if not frames:
        raise ValueError(f"No CF product operations parsed; errors={errors[:3]}")
    result = pd.concat(frames, ignore_index=True)
    keys = ["period_end", "scope", "product", "metric"]
    result = result.sort_values([*keys, "filing_date", "accession"])
    return result.drop_duplicates(keys, keep="last").reset_index(drop=True)


def parse_cf_earnings_exhibit(
    html: str,
    *,
    accession: str,
    filing_date: str,
    source_url: str,
    retrieved_at: datetime,
) -> pd.DataFrame:
    """Parse the latest three-month column from a CF earnings exhibit."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for table in soup.find_all("table"):
        text = " ".join(table.stripped_strings)
        if "Three months ended" not in text:
            continue
        period = _period_end(text)
        if period is None:
            continue
        product = _table_product(table, text)
        if product == "unknown":
            continue
        scope = "consolidated" if product == "all_products" else "segment"
        for row in table.find_all("tr"):
            cells = _dedupe_cells(
                [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            )
            if len(cells) < 2:
                continue
            label = _clean_label(cells[0])
            metric = _metric(label, scope)
            if metric is None:
                continue
            value = _first_number(cells[1:])
            if value is None:
                continue
            rows.append(
                {
                    "ticker": "CF",
                    "period_end": period,
                    "fiscal_year": period.year,
                    "fiscal_quarter": f"Q{period.quarter}",
                    "scope": scope,
                    "product": product,
                    "metric": metric[0],
                    "value": value,
                    "unit": metric[1],
                    "filing_date": pd.Timestamp(filing_date),
                    "available_time": pd.Timestamp(filing_date),
                    "accession": accession,
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                }
            )
    return pd.DataFrame(rows)


def _discover_filings(user_agent: str, start_year: int) -> list[dict]:
    root = json.loads(_get(SUBMISSIONS_URL, user_agent))
    batches = [root["filings"]["recent"]]
    for item in root["filings"].get("files", []):
        batches.append(json.loads(_get(f"https://data.sec.gov/submissions/{item['name']}", user_agent)))
    filings: dict[str, dict] = {}
    for batch in batches:
        for row in _records(batch):
            accession = str(row.get("accessionNumber", ""))
            if (
                row.get("form") == "8-K"
                and "2.02" in str(row.get("items", ""))
                and accession.startswith("0001324404-")
                and int(str(row["filingDate"])[:4]) >= start_year
            ):
                filings[accession] = row
    return sorted(filings.values(), key=lambda row: row["filingDate"])


def _records(columns: dict) -> list[dict]:
    keys = list(columns)
    return [dict(zip(keys, values)) for values in zip(*(columns[key] for key in keys))]


def _find_earnings_exhibit(accession: str, user_agent: str) -> str:
    accession_compact = accession.replace("-", "")
    directory = f"{ARCHIVES_ROOT}/{accession_compact}"
    index = json.loads(_get(f"{directory}/index.json", user_agent))
    items = index["directory"]["item"]
    candidates = [
        item
        for item in items
        if re.search(r"(?:earnings|ex(?:hibit)?[-_]?99(?:1|\.1)|ex99).*\.html?$", item["name"], re.I)
    ]
    if not candidates:
        raise FileNotFoundError("no earnings/EX-99.1 HTML exhibit")
    selected = max(candidates, key=lambda item: int(item.get("size") or 0))
    return f"{directory}/{selected['name']}"


def _get(url: str, user_agent: str, attempts: int = 3) -> bytes:
    context = ssl.create_default_context(cafile=certifi.where())
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
            with urlopen(request, timeout=90, context=context) as response:
                return response.read()
        except OSError as exc:
            error = exc
            time.sleep(attempt + 1)
    raise RuntimeError(f"SEC request failed: {url}: {error}")


def _period_end(text: str) -> pd.Timestamp | None:
    match = re.search(
        r"Three months ended\s+([A-Z][a-z]+)\s+(\d{1,2}),?.{0,160}?(20\d{2})",
        text,
    )
    if not match:
        return None
    return pd.Timestamp(f"{match.group(1)} {match.group(2)}, {match.group(3)}")


def _table_product(table, text: str) -> str:
    if any(
        marker in text
        for marker in (
            "Natural gas supplemental data",
            "Natural gas costs in cost of sales",
            "Production volume by product",
        )
    ):
        return "all_products"
    node = table
    for _ in range(20):
        node = node.find_previous(string=True)
        if node is None:
            break
        value = " ".join(str(node).split()).lower()
        for label, product in (
            ("granular urea segment", "granular_urea"),
            ("ammonia segment", "ammonia"),
            ("uan segment", "uan"),
            ("ammonium nitrate segment", "ammonium_nitrate"),
            ("an segment", "ammonium_nitrate"),
            ("other segment", "other"),
        ):
            if label in value:
                return product
    return "unknown"


def _metric(label: str, scope: str) -> tuple[str, str] | None:
    mappings = {
        "sales volume by product tons": ("sales_volume", "thousand_short_tons"),
        "average selling price per product ton": ("average_selling_price", "USD_per_short_ton"),
        "gross margin per product ton": ("gross_margin_per_ton", "USD_per_short_ton"),
        "cost of natural gas used for production in cost of sales": (
            "realized_natural_gas_cost",
            "USD_per_MMBtu",
        ),
        "natural gas costs in cost of sales": ("realized_natural_gas_cost", "USD_per_MMBtu"),
        "ammonia": ("production_volume_ammonia", "thousand_short_tons"),
        "granular urea": ("production_volume_granular_urea", "thousand_short_tons"),
        "uan": ("production_volume_uan32", "thousand_short_tons"),
        "an": ("production_volume_ammonium_nitrate", "thousand_short_tons"),
    }
    normalized = label.lower()
    for prefix, metric in mappings.items():
        if normalized == prefix or normalized.startswith(prefix + " "):
            if scope == "segment" and prefix in {"ammonia", "granular urea", "uan", "an"}:
                continue
            return metric
    return None


def _clean_label(value: str) -> str:
    return re.sub(r"\(\d+\)", "", value).strip().rstrip(":")


def _dedupe_cells(values: list) -> list[str]:
    result: list[str] = []
    for value in values:
        if pd.isna(value):
            continue
        text = " ".join(str(value).split())
        if text and (not result or text != result[-1]):
            result.append(text)
    return result


def _first_number(values: list[str]) -> float | None:
    for value in values:
        if value in {"$", "%", "—", "–", "-"}:
            continue
        cleaned = value.replace(",", "").replace("$", "").strip()
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = cleaned.strip("()")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            number = float(cleaned)
            return -number if negative else number
    return None


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value.get("documents", value) if isinstance(value, dict) else {}


def _write_manifest(path: Path, documents: dict, errors: list[str]) -> None:
    payload = {"documents": dict(sorted(documents.items())), "errors": errors}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
