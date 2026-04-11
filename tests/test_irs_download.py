"""
tests/test_irs_download.py

Unit tests for the IRS publication download pipeline.

No actual network calls — all HTTP requests are mocked.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from taxflow_kb.ingestion.irs_download import (
    IRSDownloader,
    DownloadResult,
    download_publication,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_pub_dir(tmp_path):
    """Create a temp directory for publication downloads."""
    pub_dir = tmp_path / "publications"
    pub_dir.mkdir()
    return pub_dir


@pytest.fixture
def downloader(tmp_pub_dir):
    """Create an IRSDownloader pointing at the temp directory."""
    return IRSDownloader(output_dir=tmp_pub_dir, force=False)


# Minimal valid PDF header for mocking
FAKE_PDF = b"%PDF-1.4 fake content for testing " + b"x" * 100


# ── URL building tests ───────────────────────────────────────────────────────

class TestURLBuilding:

    def test_current_year_uses_irs_pdf(self, downloader):
        """Current year should use the irs-pdf/ URL."""
        url = downloader._build_url("523", 2025)
        assert "irs-pdf" in url
        assert "p523.pdf" in url

    def test_prior_year_uses_irs_prior(self, downloader):
        """Prior years should use the irs-prior/ URL with year."""
        url = downloader._build_url("523", 2023)
        assert "irs-prior" in url
        assert "p523--2023.pdf" in url

    def test_url_includes_pub_number(self, downloader):
        """URL should contain the publication number."""
        url = downloader._build_url("590a", 2024)
        assert "p590a" in url

    def test_pdf_path_naming(self, downloader, tmp_pub_dir):
        """Local path should follow p{number}_{year}.pdf convention."""
        path = downloader._pdf_path("527", 2024)
        assert path == tmp_pub_dir / "p527_2024.pdf"


# ── Download logic tests ────────────────────────────────────────────────────

class TestDownloadLogic:

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_successful_download(self, mock_fetch, downloader, tmp_pub_dir):
        """Successful download should create file and return success."""
        result = downloader.download_publication("523", 2024)
        assert result.success is True
        assert result.skipped is False
        assert result.file_size > 0
        assert result.sha256 != ""
        assert (tmp_pub_dir / "p523_2024.pdf").exists()

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_skip_existing_file(self, mock_fetch, downloader, tmp_pub_dir):
        """Should skip download if file already exists (force=False)."""
        # Create the file first
        (tmp_pub_dir / "p523_2024.pdf").write_bytes(FAKE_PDF)
        result = downloader.download_publication("523", 2024)
        assert result.success is True
        assert result.skipped is True
        mock_fetch.assert_not_called()

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_force_redownload(self, mock_fetch, tmp_pub_dir):
        """force=True should re-download even if file exists."""
        (tmp_pub_dir / "p523_2024.pdf").write_bytes(b"old content")
        dl = IRSDownloader(output_dir=tmp_pub_dir, force=True)
        result = dl.download_publication("523", 2024)
        assert result.success is True
        assert result.skipped is False
        mock_fetch.assert_called_once()

    @patch.object(IRSDownloader, "_fetch", side_effect=FileNotFoundError("404"))
    def test_failed_download(self, mock_fetch, downloader):
        """Failed download should return success=False with error."""
        result = downloader.download_publication("9999", 2024)
        assert result.success is False
        assert "404" in result.error

    @patch.object(IRSDownloader, "_fetch", return_value=b"<html>Not a PDF</html>")
    def test_invalid_pdf_rejected(self, mock_fetch, downloader):
        """Non-PDF content should be detected and rejected."""
        result = downloader.download_publication("523", 2024)
        assert result.success is False
        assert "not a valid PDF" in result.error

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_manifest_updated(self, mock_fetch, downloader, tmp_pub_dir):
        """Download should update the manifest JSON."""
        downloader.download_publication("523", 2024)
        manifest_path = tmp_pub_dir / "download_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert "p523_2024.pdf" in manifest
        entry = manifest["p523_2024.pdf"]
        assert entry["pub_number"] == "523"
        assert entry["tax_year"] == 2024
        assert entry["sha256"] != ""
        assert "downloaded_at" in entry


# ── Batch download tests ────────────────────────────────────────────────────

class TestBatchDownload:

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_download_tier(self, mock_fetch, downloader):
        """download_tier should download pubs for the specified tier."""
        results = downloader.download_tier(1, years=[2025])
        assert len(results) > 0
        # All tier-1 pubs should succeed
        for r in results:
            assert r.success, f"Failed: {r}"

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_download_missing_only_fetches_new(self, mock_fetch, downloader, tmp_pub_dir):
        """download_missing should only fetch files not already on disk."""
        # Pre-create one file
        (tmp_pub_dir / "p17_2025.pdf").write_bytes(FAKE_PDF)
        results = downloader.download_missing(years=[2025])
        # p17_2025 should not appear as a new download
        new_downloads = [r for r in results if not r.skipped and r.success]
        p17_new = [r for r in new_downloads if r.pub_number == "17" and r.tax_year == 2025]
        assert len(p17_new) == 0, "p17_2025 was already on disk, should not re-download"


# ── Status report tests ─────────────────────────────────────────────────────

class TestStatus:

    def test_status_returns_dict(self, downloader):
        """get_status should return a dict with expected keys."""
        status = downloader.get_status()
        assert "total_registered" in status
        assert "downloaded" in status
        assert "missing" in status
        assert "tiers" in status
        assert status["total_registered"] > 0

    @patch.object(IRSDownloader, "_fetch", return_value=FAKE_PDF)
    def test_status_tracks_downloads(self, mock_fetch, downloader, tmp_pub_dir):
        """Downloaded files should appear in status count."""
        before = downloader.get_status()["downloaded"]
        downloader.download_publication("523", 2024)
        after = downloader.get_status()["downloaded"]
        assert after == before + 1


# ── DownloadResult tests ────────────────────────────────────────────────────

class TestDownloadResult:

    def test_repr_success(self):
        r = DownloadResult(
            pub_number="523", tax_year=2024, success=True,
            file_size=12345,
        )
        assert "OK" in repr(r)
        assert "12,345" in repr(r)

    def test_repr_failure(self):
        r = DownloadResult(
            pub_number="523", tax_year=2024, success=False,
            error="HTTP 404",
        )
        assert "FAIL" in repr(r)

    def test_repr_skipped(self):
        r = DownloadResult(
            pub_number="523", tax_year=2024, success=True,
            skipped=True,
        )
        assert "SKIP" in repr(r)
