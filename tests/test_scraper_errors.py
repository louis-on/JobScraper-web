"""Erreurs de sources : remontées lisibles au lieu d'échecs silencieux."""

import pytest

from jobscraper.models.job import SearchCriteria
from jobscraper.scrapers.adzuna import AdzunaScraper
from jobscraper.scrapers.linkedin import LinkedInScraper
from jobscraper.services.search import friendly_error


def _boom(url):
    raise RuntimeError("SSLError(SSLZeroReturnError(6, 'TLS fermé'))")


def test_friendly_error_network_is_human_readable():
    raw = RuntimeError(
        "RetryError[<Future raised SSLError(SSLZeroReturnError(6, 'EOF'))>]"
    )
    message = friendly_error(raw)
    assert "injoignable" in message
    assert "SSLError" not in message


def test_friendly_error_http_block():
    assert "403" in friendly_error(RuntimeError("HTTP 403 Forbidden"))


def test_friendly_error_passthrough_short_messages():
    assert friendly_error(RuntimeError("erreur métier simulée")) == "erreur métier simulée"


def test_linkedin_first_page_failure_raises(monkeypatch):
    scraper = LinkedInScraper({"delay": 0})
    monkeypatch.setattr(scraper, "_fetch_page", _boom)
    with pytest.raises(RuntimeError):
        list(scraper.search(SearchCriteria(keywords=["python"])))


def test_adzuna_without_keys_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    scraper = AdzunaScraper({})
    with pytest.raises(RuntimeError, match="ADZUNA_APP_ID"):
        list(scraper.search(SearchCriteria(keywords=["python"])))
