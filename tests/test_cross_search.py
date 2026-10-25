"""Tests du croisement annonces × personnes (regroupement, API) — hors réseau."""

from typing import Optional

import pytest
from fastapi.testclient import TestClient

from jobscraper.models.job import JobOffer
from jobscraper.models.prospecting import PersonCandidate
from jobscraper.services import cross_search as cross
from jobscraper.services import search as search_service
from jobscraper.services.cross_search import group_by_company, normalize_company
from jobscraper.web.app import create_app


def _job(company: str, jid: str = "1") -> JobOffer:
    return JobOffer(
        id=f"jobs_{jid}",
        source="linkedin",
        url=f"https://example.com/{jid}",
        title="Développeur Python",
        company=company,
        location="Paris, France",
    )


def _person(company: str, pid: str = "p1") -> PersonCandidate:
    return PersonCandidate(
        id=pid,
        provider="Apollo",
        first_name="Claire",
        last_name_obfuscated="Be***d",
        display_name="Claire Be***d",
        title="Développeuse Python Senior",
        company=company,
    )


def test_normalize_company_legal_forms_and_accents():
    assert normalize_company("CAPGEMINI TECHNOLOGY SERVICES") != ""
    assert normalize_company("Société Générale SAS") == normalize_company(
        "Société Générale"
    )
    assert normalize_company("L'Oréal Groupe") == normalize_company("L'Oréal")
    assert normalize_company("Akeneo") == "akeneo"


def test_group_by_company_types_and_order():
    groups = group_by_company(
        jobs=[_job("Capgemini SAS", "1"), _job("Annonce Seule", "2")],
        people=[_person("Capgemini", "p1"), _person("Personne Seule", "p2")],
    )
    by_type = {g.match_type: g for g in groups}
    assert set(by_type) == {"both", "hiring_only", "employing_only"}
    # Les entreprises qui recrutent ET emploient arrivent en premier.
    assert groups[0].match_type == "both"
    assert len(groups[0].jobs) == 1 and len(groups[0].people) == 1


@pytest.fixture()
def client(monkeypatch):
    """API avec provider démo + recherche d'annonces simulée sur Paris."""

    class _Outcome:
        jobs = [_job("Capgemini", "c1"), _job("Akeneo", "a1")]
        counts = {"linkedin": 2}
        errors = {}

    monkeypatch.setattr(search_service, "search_all", lambda *a, **k: _Outcome())
    monkeypatch.setattr(cross.search_service, "search_all", lambda *a, **k: _Outcome())
    monkeypatch.setenv("JOBSCRAPER_DEMO", "1")
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    search_service.clear_cache()
    with TestClient(create_app()) as test_client:
        yield test_client
    search_service.clear_cache()


def test_prospects_status_demo(client):
    response = client.get("/api/prospects/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True and body["demo"] is True


def test_cross_search_endpoint(client):
    response = client.post(
        "/api/cross-search",
        json={
            "metier": "Développeur Python",
            "title_variants": ["Lead Developer Python"],
            "location": "Nantes",
            "sources": ["linkedin"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["apollo_demo"] is True
    assert body["summary"]["matching_companies"] >= 2

    by_name = {c["name"]: c for c in body["companies"]}
    assert by_name["Capgemini"]["match_type"] == "both"
    assert by_name["Capgemini"]["people"][0]["display_name"].startswith("Claire")
    assert by_name["Akeneo"]["match_type"] == "both"
    # iAdvize emploie un développeur Python à Paris sans annonce simulée.
    assert by_name["iAdvize"]["match_type"] == "employing_only"


def test_cross_search_requires_metier(client):
    response = client.post("/api/cross-search", json={"metier": "  "})
    assert response.status_code == 422


def test_reveal_endpoint_demo(client):
    response = client.post("/api/prospects/reveal", json={"person_id": "demo_p1"})
    assert response.status_code == 200
    person = response.json()["person"]
    assert person["display_name"] == "Claire Bernard"
    assert person["revealed"] is True
    assert "example.com" in person["linkedin_url"]
