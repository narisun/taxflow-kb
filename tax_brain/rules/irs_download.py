"""
tax_brain/ingestion/irs_download.py

Automated IRS publication PDF download pipeline.

Downloads publication PDFs from IRS.gov and stores them with a
consistent naming convention that integrates with the Layer 3 PDF
parsing pipeline.

URL patterns:
  Current year:  https://www.irs.gov/pub/irs-pdf/p{number}.pdf
  Prior years:   https://www.irs.gov/pub/irs-prior/p{number}--{year}.pdf

Naming convention:
  data/publications/p{number}_{year}.pdf     (e.g., p523_2024.pdf)

Usage:
    from tax_brain.rules.irs_download import IRSDownloader

    dl = IRSDownloader()
    dl.download_publication("523", 2024)           # single pub + year
    dl.download_tier(1)                             # all Tier-1 pubs, current year
    dl.download_all_registered(years=[2023, 2024, 2025])  # everything
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tax_brain.config import get_settings
from tax_brain.publications.registry import get_registry, PublicationMeta

logger = logging.getLogger(__name__)

# ── IRS URL templates ────────────────────────────────────────────────────────

_IRS_CURRENT_URL = "https://www.irs.gov/pub/irs-pdf/p{number}.pdf"
_IRS_PRIOR_URL = "https://www.irs.gov/pub/irs-prior/p{number}--{year}.pdf"

# User-Agent header — IRS blocks bare urllib requests
_USER_AGENT = (
    "Mozilla/5.0 (compatible; TaxFlowAI/1.0; "
    "+https://github.com/taxflow-ai/taxflow-kb)"
)

# Polite delay between downloads (seconds)
_DOWNLOAD_DELAY = 1.0

# HTTP timeout (seconds)
_HTTP_TIMEOUT = 60


# ── Download result model ────────────────────────────────────────────────────

class DownloadResult:
    """Result of a single publication download attempt."""

    def __init__(
        self,
        pub_number: str,
        tax_year: int,
        success: bool,
        file_path: str = "",
        file_size: int = 0,
        sha256: str = "",
        url: str = "",
        error: str = "",
        skipped: bool = False,
    ):
        self.pub_number = pub_number
        self.tax_year = tax_year
        self.success = success
        self.file_path = file_path
        self.file_size = file_size
        self.sha256 = sha256
        self.url = url
        self.error = error
        self.skipped = skipped

    def __repr__(self) -> str:
        status = "SKIP" if self.skipped else ("OK" if self.success else "FAIL")
        size = f" ({self.file_size:,} bytes)" if self.file_size else ""
        return f"<DownloadResult pub={self.pub_number} year={self.tax_year} {status}{size}>"


# ── Main downloader class ────────────────────────────────────────────────────

class IRSDownloader:
    """
    Downloads IRS publication PDFs and stores them locally.

    Integrates with the publication registry to know which pubs exist
    and what tier they belong to. Stores a download manifest (JSON)
    alongside the PDFs for tracking what was downloaded and when.

    Args:
        output_dir: Directory to store downloaded PDFs.
                    Defaults to data/publications/ relative to project root.
        force: If True, re-download even if the file already exists.
    """

    def __init__(
        self,
        output_dir: Optional[str | Path] = None,
        force: bool = False,
    ):
        if output_dir is None:
            # Default: project_root/data/publications/
            output_dir = Path(__file__).parent.parent.parent / "data" / "publications"
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._force = force
        self._registry = get_registry()
        self._manifest = self._load_manifest()
        self._settings = get_settings()

    # ── Public API ───────────────────────────────────────────────────────────

    def download_publication(
        self,
        pub_number: str,
        tax_year: Optional[int] = None,
    ) -> DownloadResult:
        """
        Download a single IRS publication PDF.

        Args:
            pub_number: Publication number (e.g., "523", "590a").
            tax_year: Tax year to download. If None, downloads the
                      current year version from irs-pdf/.

        Returns:
            DownloadResult with success/failure details.
        """
        if tax_year is None:
            tax_year = self._settings.default_tax_year

        dest = self._pdf_path(pub_number, tax_year)
        url = self._build_url(pub_number, tax_year)

        # Check if already downloaded (unless force=True)
        if not self._force and dest.exists():
            existing_hash = self._manifest.get(dest.name, {}).get("sha256", "")
            logger.info(
                "Skipping p%s_%d — already exists (%s)",
                pub_number, tax_year, dest.name,
            )
            return DownloadResult(
                pub_number=pub_number,
                tax_year=tax_year,
                success=True,
                file_path=str(dest),
                file_size=dest.stat().st_size,
                sha256=existing_hash,
                url=url,
                skipped=True,
            )

        # Download
        logger.info("Downloading p%s_%d from %s ...", pub_number, tax_year, url)
        try:
            data = self._fetch(url)
        except Exception as exc:
            logger.error("Failed to download p%s_%d: %s", pub_number, tax_year, exc)
            return DownloadResult(
                pub_number=pub_number,
                tax_year=tax_year,
                success=False,
                url=url,
                error=str(exc),
            )

        # Validate it's actually a PDF
        if not data[:5] == b"%PDF-":
            error_msg = (
                f"Downloaded file is not a valid PDF "
                f"(starts with {data[:20]!r})"
            )
            logger.error("p%s_%d: %s", pub_number, tax_year, error_msg)
            return DownloadResult(
                pub_number=pub_number,
                tax_year=tax_year,
                success=False,
                url=url,
                error=error_msg,
            )

        # Write to disk
        dest.write_bytes(data)
        sha256 = hashlib.sha256(data).hexdigest()

        # Update manifest
        self._manifest[dest.name] = {
            "pub_number": pub_number,
            "tax_year": tax_year,
            "url": url,
            "sha256": sha256,
            "file_size": len(data),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_manifest()

        logger.info(
            "Downloaded p%s_%d — %s (%d bytes, sha256=%s...)",
            pub_number, tax_year, dest.name, len(data), sha256[:12],
        )

        return DownloadResult(
            pub_number=pub_number,
            tax_year=tax_year,
            success=True,
            file_path=str(dest),
            file_size=len(data),
            sha256=sha256,
            url=url,
        )

    def download_tier(
        self,
        tier: int,
        years: Optional[list[int]] = None,
    ) -> list[DownloadResult]:
        """
        Download all publications in a specific tier.

        Args:
            tier: Publication tier (1 = currently ingested, 2 = Tier-1 additions,
                  3 = Tier-2 additions).
            years: Tax years to download. Defaults to settings.supported_tax_years.

        Returns:
            List of DownloadResult objects.
        """
        pubs = self._registry.get_by_tier(tier)
        if not pubs:
            logger.warning("No publications found for tier %d", tier)
            return []

        if years is None:
            years = self._settings.supported_tax_years

        logger.info(
            "Downloading tier-%d publications: %d pubs x %d years = %d downloads",
            tier, len(pubs), len(years), len(pubs) * len(years),
        )

        return self._download_batch(pubs, years)

    def download_all_registered(
        self,
        years: Optional[list[int]] = None,
    ) -> list[DownloadResult]:
        """
        Download all registered publications for all specified years.

        Args:
            years: Tax years to download. Defaults to settings.supported_tax_years.

        Returns:
            List of DownloadResult objects.
        """
        all_pub_numbers = self._registry.all_pub_numbers()
        pubs = [
            self._registry.get(pn)
            for pn in all_pub_numbers
            if self._registry.get(pn) is not None
        ]

        if years is None:
            years = self._settings.supported_tax_years

        logger.info(
            "Downloading all registered publications: %d pubs x %d years = %d downloads",
            len(pubs), len(years), len(pubs) * len(years),
        )

        return self._download_batch(pubs, years)

    def download_missing(
        self,
        years: Optional[list[int]] = None,
    ) -> list[DownloadResult]:
        """
        Download only publications that are not yet on disk.

        Scans the registry vs. local files and downloads what's missing.

        Args:
            years: Tax years to check. Defaults to settings.supported_tax_years.

        Returns:
            List of DownloadResult objects (only for newly downloaded files).
        """
        if years is None:
            years = self._settings.supported_tax_years

        all_pub_numbers = self._registry.all_pub_numbers()
        missing: list[tuple[str, int]] = []

        for pn in all_pub_numbers:
            pub = self._registry.get(pn)
            for year in years:
                # Skip years outside the pub's declared tax_years
                if pub and pub.tax_years and year not in pub.tax_years:
                    continue
                # Skip pubs with empty tax_years (discontinued)
                if pub and not pub.tax_years:
                    continue
                dest = self._pdf_path(pn, year)
                if not dest.exists():
                    missing.append((pn, year))

        if not missing:
            logger.info("All registered publications are already downloaded.")
            return []

        logger.info(
            "Found %d missing publication PDFs — downloading ...", len(missing),
        )

        results = []
        for pub_number, tax_year in missing:
            result = self.download_publication(pub_number, tax_year)
            results.append(result)
            if result.success and not result.skipped:
                time.sleep(_DOWNLOAD_DELAY)

        return results

    def get_status(self) -> dict:
        """
        Report download coverage status.

        Returns a dict with counts of registered, downloaded, and missing
        publications broken down by tier.
        """
        years = self._settings.supported_tax_years
        status = {
            "total_registered": len(self._registry.all_pub_numbers()),
            "years": years,
            "tiers": {},
            "downloaded": 0,
            "missing": 0,
            "missing_details": [],
        }

        for tier in [1, 2, 3]:
            pubs = self._registry.get_by_tier(tier)
            tier_downloaded = 0
            tier_missing = 0

            for pub in pubs:
                for year in years:
                    # Skip years outside the pub's declared tax_years
                    if pub.tax_years and year not in pub.tax_years:
                        continue
                    # Skip pubs with empty tax_years (discontinued)
                    if not pub.tax_years:
                        continue
                    dest = self._pdf_path(pub.pub_number, year)
                    if dest.exists():
                        tier_downloaded += 1
                    else:
                        tier_missing += 1
                        status["missing_details"].append(
                            f"p{pub.pub_number}_{year}"
                        )

            status["tiers"][tier] = {
                "publications": len(pubs),
                "downloaded": tier_downloaded,
                "missing": tier_missing,
            }
            status["downloaded"] += tier_downloaded
            status["missing"] += tier_missing

        return status

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _pdf_path(self, pub_number: str, tax_year: int) -> Path:
        """Build the local file path for a publication PDF."""
        return self._output_dir / f"p{pub_number}_{tax_year}.pdf"

    def _build_url(self, pub_number: str, tax_year: int) -> str:
        """
        Build the IRS download URL for a publication.

        IRS URL convention:
          Current year (latest): https://www.irs.gov/pub/irs-pdf/p{number}.pdf
          Prior years:           https://www.irs.gov/pub/irs-prior/p{number}--{year}.pdf

        We always use the prior-year URL with explicit year for consistency
        and reproducibility, except for the current year where we try the
        irs-pdf URL first (most up-to-date version).
        """
        current_year = self._settings.default_tax_year

        if tax_year >= current_year:
            # Current year — use irs-pdf/ (always the latest version)
            return _IRS_CURRENT_URL.format(number=pub_number)
        else:
            # Prior year — use irs-prior/ with explicit year
            return _IRS_PRIOR_URL.format(number=pub_number, year=tax_year)

    def _fetch(self, url: str) -> bytes:
        """Download a URL and return raw bytes."""
        request = Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urlopen(request, timeout=_HTTP_TIMEOUT) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(
                    f"Publication not found at {url} (HTTP 404). "
                    f"The publication may not exist for this year."
                ) from exc
            raise RuntimeError(
                f"HTTP {exc.code} downloading {url}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Network error downloading {url}: {exc.reason}"
            ) from exc

    def _download_batch(
        self,
        pubs: list[PublicationMeta],
        years: list[int],
    ) -> list[DownloadResult]:
        """Download a batch of publications across multiple years."""
        results = []
        total = len(pubs) * len(years)
        done = 0

        for pub in pubs:
            for year in years:
                # Skip years outside the pub's declared tax_years (if specified)
                if pub.tax_years and year not in pub.tax_years:
                    logger.debug(
                        "Skipping p%s_%d — not in declared tax_years %s",
                        pub.pub_number, year, pub.tax_years,
                    )
                    done += 1
                    continue

                result = self.download_publication(pub.pub_number, year)
                results.append(result)
                done += 1

                if result.success and not result.skipped:
                    time.sleep(_DOWNLOAD_DELAY)

                # Progress logging every 10 downloads
                if done % 10 == 0:
                    logger.info("Progress: %d/%d downloads processed", done, total)

        # Summary
        success_count = sum(1 for r in results if r.success and not r.skipped)
        skip_count = sum(1 for r in results if r.skipped)
        fail_count = sum(1 for r in results if not r.success)
        logger.info(
            "Batch complete: %d downloaded, %d skipped, %d failed (total %d)",
            success_count, skip_count, fail_count, len(results),
        )

        return results

    # ── Manifest management ──────────────────────────────────────────────────

    def _manifest_path(self) -> Path:
        """Path to the download manifest JSON."""
        return self._output_dir / "download_manifest.json"

    def _load_manifest(self) -> dict:
        """Load the download manifest from disk."""
        path = self._manifest_path()
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt manifest at %s — starting fresh", path)
                return {}
        return {}

    def _save_manifest(self) -> None:
        """Persist the download manifest to disk."""
        path = self._manifest_path()
        path.write_text(json.dumps(self._manifest, indent=2, sort_keys=True))


# ── Convenience functions ────────────────────────────────────────────────────

def download_publication(
    pub_number: str,
    tax_year: Optional[int] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
) -> DownloadResult:
    """Download a single publication. Convenience wrapper."""
    dl = IRSDownloader(output_dir=output_dir, force=force)
    return dl.download_publication(pub_number, tax_year)


def download_tier(
    tier: int,
    years: Optional[list[int]] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
) -> list[DownloadResult]:
    """Download all pubs in a tier. Convenience wrapper."""
    dl = IRSDownloader(output_dir=output_dir, force=force)
    return dl.download_tier(tier, years)


def download_all(
    years: Optional[list[int]] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
) -> list[DownloadResult]:
    """Download all registered publications. Convenience wrapper."""
    dl = IRSDownloader(output_dir=output_dir, force=force)
    return dl.download_all_registered(years)
