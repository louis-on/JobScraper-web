"""Tests de l'API web FastAPI (scrapers remplacés par des doubles)."""

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper
from jobscraper.services import search as service
from jobscraper.web.app import create_app


class FakeScraper(BaseScraper):
    name = "fake"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield JobOffer(
            id="fake_1",
            source="linkedin",
            url="https://example.com/fake-1",
            title="Développeur Python",
            company="TechCorp",
            location="Nantes, France",
        )

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(service, "make_scraper", lambda source: FakeScraper({}))
    service.clear_cache()
    with TestClient(create_app()) as test_client:
        yield test_client
    service.clear_cache()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "linkedin" in body["sources"]


def test_sources_lists_availability(client):
    response = client.get("/api/sources")
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert {"linkedin", "hellowork", "francetravail", "adzuna", "wttj"} <= set(ids)


def test_search_post(client):
    response = client.post(
        "/api/search",
        json={"keywords": ["python"], "location": "Nantes", "sources": ["linkedin"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["jobs"][0]["title"] == "Développeur Python"
    assert body["errors"] == {}


def test_search_unknown_source_rejected(client):
    response = client.post("/api/search", json={"sources": ["indeed"]})
    assert response.status_code == 422


def test_search_stream_emits_events(client):
    with client.stream(
        "GET", "/api/search/stream?keywords=python&sources=linkedin"
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())
    assert "event: start" in payload
    assert "event: job" in payload
    assert "Développeur Python" in payload
    assert "event: done" in payload
