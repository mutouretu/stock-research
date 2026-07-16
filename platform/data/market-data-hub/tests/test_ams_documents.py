from pathlib import Path

from market_data_hub.domains.commodities.ams_documents import (
    LATEST_URL,
    discover_archive_urls,
    download_ams_3195_pdfs,
)


PDF = b"%PDF-1.4\nfixture"


def test_discover_archive_urls() -> None:
    html = b'<a href="/filerepo/sites/default/files/3195/2026-01-02/1/ams_3195.pdf">PDF</a>'

    def fetcher(url: str):
        return html, url, "text/html"

    urls = discover_archive_urls(max_pages=1, fetcher=fetcher)

    assert urls == {
        "https://mymarketnews.ams.usda.gov/filerepo/sites/default/files/3195/"
        "2026-01-02/1/ams_3195.pdf"
    }


def test_download_latest_pdf_and_skip_duplicate(tmp_path: Path) -> None:
    def fetcher(url: str):
        assert url == LATEST_URL
        return PDF, "https://example.test/3195/2026-07-10/1/ams_3195.pdf", "application/pdf"

    first = download_ams_3195_pdfs(tmp_path, latest_only=True, fetcher=fetcher)
    second = download_ams_3195_pdfs(tmp_path, latest_only=True, fetcher=fetcher)

    assert first.downloaded == 1
    assert second.skipped == 1
    assert len(list(tmp_path.glob("*.pdf"))) == 1
    assert (tmp_path / "manifest.json").is_file()
