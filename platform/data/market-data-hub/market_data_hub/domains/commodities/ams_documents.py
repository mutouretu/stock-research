"""Download public USDA AMS report PDFs without using the authenticated MARS API."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

import certifi
import ssl


REPORT_ID = "3195"
LATEST_URL = "https://www.ams.usda.gov/mnreports/ams_3195.pdf"
ARCHIVE_URL = "https://mymarketnews.ams.usda.gov/filerepo/reports"
USER_AGENT = "stock-research/0.1 USDA-AMS-public-document-archiver"


@dataclass(frozen=True)
class ArchivedDocument:
    filename: str
    source_url: str
    report_date: str | None
    sha256: str
    bytes: int
    downloaded_at: str


@dataclass(frozen=True)
class ArchiveSummary:
    downloaded: int
    skipped: int
    discovered: int
    errors: tuple[str, ...]
    output_dir: Path

    def summary_text(self) -> str:
        return (
            f"AMS {REPORT_ID} PDFs: discovered={self.discovered}, downloaded={self.downloaded}, "
            f"skipped={self.skipped}, errors={len(self.errors)}, output={self.output_dir}"
        )


def download_ams_3195_pdfs(
    output_dir: str | Path,
    *,
    max_pages: int = 20,
    latest_only: bool = False,
    fetcher: Callable[[str], tuple[bytes, str, str]] | None = None,
) -> ArchiveSummary:
    """Archive latest and discoverable historical Illinois production-cost PDFs."""
    fetch = fetcher or fetch_url
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    manifest = _load_manifest(manifest_path)
    errors: list[str] = []
    urls = {LATEST_URL}
    if not latest_only:
        try:
            urls.update(discover_archive_urls(max_pages=max_pages, fetcher=fetch))
        except Exception as exc:
            errors.append(f"archive discovery failed: {exc}")

    downloaded = 0
    skipped = 0
    for url in sorted(urls):
        try:
            payload, final_url, content_type = fetch(url)
            if not _is_pdf(payload, final_url, content_type):
                raise ValueError(f"response is not a PDF: content_type={content_type}")
            digest = hashlib.sha256(payload).hexdigest()
            report_date = _date_from_url(final_url) or _date_from_pdf(payload)
            filename = _filename(report_date, digest)
            existing = manifest.get(digest)
            existing_path = output / existing["filename"] if existing else None
            path = existing_path if existing_path and existing_path.exists() else output / filename
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                skipped += 1
            else:
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(payload)
                temporary.replace(path)
                downloaded += 1
            record = asdict(
                ArchivedDocument(
                    filename=path.name,
                    source_url=final_url,
                    report_date=report_date,
                    sha256=digest,
                    bytes=len(payload),
                    downloaded_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            if existing and existing.get("report_date") and not record["report_date"]:
                record["report_date"] = existing["report_date"]
            manifest[digest] = record
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    _write_manifest(manifest_path, manifest)
    return ArchiveSummary(downloaded, skipped, len(urls), tuple(errors), output)


def discover_archive_urls(
    *,
    max_pages: int,
    fetcher: Callable[[str], tuple[bytes, str, str]],
) -> set[str]:
    urls: set[str] = set()
    for page in range(max_pages):
        query = urlencode({"field_slug_id_value": REPORT_ID, "page": page})
        index_url = f"{ARCHIVE_URL}?{query}"
        payload, final_url, _ = fetcher(index_url)
        parser = _LinkParser()
        parser.feed(payload.decode("utf-8", errors="replace"))
        page_urls = {
            urljoin(final_url, href)
            for href in parser.links
            if _looks_like_document_link(href)
        }
        urls.update(page_urls)
        if page > 0 and not page_urls:
            break
    return urls


def fetch_url(url: str, *, attempts: int = 3, timeout: int = 90) -> tuple[bytes, str, str]:
    context = ssl.create_default_context(cafile=certifi.where())
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urlopen(request, timeout=timeout, context=context) as response:
                return (
                    response.read(),
                    response.geturl(),
                    response.headers.get_content_type(),
                )
        except (OSError, URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed after {attempts} attempts: {last_error}")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _looks_like_document_link(href: str) -> bool:
    lowered = href.lower()
    if lowered.endswith(".pdf") and ("3195" in lowered or "ams_3195" in lowered):
        return True
    return "/filerepo/" in lowered and any(
        token in lowered for token in ("document", "download", "sites/default/files/3195/")
    )


def _is_pdf(payload: bytes, final_url: str, content_type: str) -> bool:
    return payload.startswith(b"%PDF-") and (
        content_type == "application/pdf" or final_url.lower().endswith(".pdf")
    )


def _date_from_url(url: str) -> str | None:
    match = re.search(r"/((?:19|20)\d{2}-\d{2}-\d{2})/", url)
    return match.group(1) if match else None


def _date_from_pdf(payload: bytes) -> str | None:
    text = payload[:200_000].decode("latin-1", errors="ignore")
    match = re.search(r"((?:19|20)\d{2})[-/]([01]\d)[-/]([0-3]\d)", text)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def _filename(report_date: str | None, digest: str) -> str:
    return f"ams_3195_{report_date or 'undated'}_{digest[:12]}.pdf"


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    values = json.loads(path.read_text(encoding="utf-8"))
    return values if isinstance(values, dict) else {}


def _write_manifest(path: Path, manifest: dict[str, dict]) -> None:
    ordered = dict(
        sorted(manifest.items(), key=lambda item: (item[1].get("report_date") or "", item[0]))
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
