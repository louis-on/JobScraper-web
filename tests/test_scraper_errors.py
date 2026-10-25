"""Erreurs de sources : remontées lisibles au lieu d'échecs silencieux.

Point d'attention historique : les erreurs étaient enveloppées dans un
``RetryError`` de tenacity puis classées « source injoignable », ce qui
masquait la vraie cause (403 anti-robot, certificats…). Ces tests
verrouillent la transparence : statut HTTP reconnu, détail technique
toujours présent, pas de nouvelle tentative sur une erreur HTTP.
"""

import pytest
import requests
from tenacity import Future, RetryError

from jobscraper.models.job import SearchCriteria
from jobscraper.scrapers import base as scrapers_base
from jobscraper.scrapers.adzuna import AdzunaScraper
from jobscraper.scrapers.linkedin import LinkedInScraper
from jobscraper.services.search import friendly_error, probe_sources, unwrap_error


def _boom(url):
    raise RuntimeError("SSLError(SSLZeroReturnError(6, 'TLS fermé'))")


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = "https://example.invalid/recherche"
    return requests.HTTPError(f"{status} Client Error", response=response)


def test_friendly_error_network_mentions_unreachable_and_keeps_detail():
    raw = RuntimeError(
        "RetryError[<Future raised SSLError(SSLZeroReturnError(6, 'EOF'))>]"
    )
    message = friendly_error(raw)
    assert "injoignable" in message
    # Le détail technique doit rester visible (diagnostic par l'utilisateur).
    assert "Détail technique" in message


def test_friendly_error_unwraps_retry_error_to_http_status():
    # Régression : un 403 enveloppé par tenacity était affiché « injoignable ».
    future = Future(attempt_number=3)
    future.set_exception(_http_error(403))
    message = friendly_error(RetryError(future))
    assert "anti-robot" in message
    assert "injoignable" not in message
    assert unwrap_error(RetryError(future)).response.status_code == 403


def test_friendly_error_http_error_status_from_response():
    message = friendly_error(_http_error(404))
    assert "HTTP 404" in message


def test_friendly_error_certificate_problem_is_actionable():
    raw = requests.ConnectionError(
        "HTTPSConnectionPool: Max retries exceeded "
        "(Caused by SSLError(SSLCertVerificationError: certificate verify failed))"
    )
    message = friendly_error(raw)
    assert "certificat" in message.lower()
    assert "antivirus" in message.lower()


def test_friendly_error_http_block():
    assert "403" in friendly_error(RuntimeError("HTTP 403 Forbidden"))


def test_friendly_error_passthrough_short_messages():
    assert (
        friendly_error(RuntimeError("erreur métier simulée")) == "erreur métier simulée"
    )


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


def test_base_headers_never_advertise_brotli():
    # Sans le paquet brotli, annoncer "br" rend les réponses indécodables.
    scraper = LinkedInScraper({"delay": 0})
    assert "br" not in scraper._get_headers()["Accept-Encoding"]


def test_fetch_page_does_not_retry_http_errors(monkeypatch):
    scraper = LinkedInScraper({"delay": 0})
    calls = {"n": 0}

    class _Response:
        text = ""

        def raise_for_status(self):
            raise _http_error(403)

    def fake_get(url, **kwargs):
        calls["n"] += 1
        return _Response()

    # Neutralise curl_cffi pour tester le chemin requests quel que soit l'env.
    monkeypatch.setattr(scrapers_base, "_cffi_requests", None)
    monkeypatch.setattr(scrapers_base.requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        scraper._fetch_page("https://example.invalid/")
    assert calls["n"] == 1, "une erreur HTTP ne doit pas être retentée"


def test_fetch_page_retries_transient_connection_errors(monkeypatch):
    scraper = LinkedInScraper({"delay": 0})
    calls = {"n": 0}

    class _Response:
        text = "<html>ok</html>"

        def raise_for_status(self):
            return None

    def flaky_get(url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("connexion réinitialisée")
        return _Response()

    monkeypatch.setattr(scrapers_base, "_cffi_requests", None)
    monkeypatch.setattr(scrapers_base.requests, "get", flaky_get)
    assert scraper._fetch_page("https://example.invalid/") == "<html>ok</html>"
    assert calls["n"] == 3


def test_probe_sources_demo_reports_ok():
    results = probe_sources(["demo"])
    assert results["demo"]["ok"] is True
    assert results["demo"]["jobs"] == 1
    assert results["demo"]["error"] is None
