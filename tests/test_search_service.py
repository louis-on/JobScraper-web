"""Tests de la couche service de recherche (sans réseau)."""

from typing import Iterator, List, Optional

import pytest

from jobscraper.models.job import ContractType, JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper
from jobscraper.services import search as service


def make_job(
    job_id: str, source: str, title: str, company: str, location: str
) -> JobOffer:
    return JobOffer(
        id=job_id,
        source=source,
        url=f"https://example.com/{job_id}",
        title=title,
        company=company,
        location=location,
    )


class FakeScraper(BaseScraper):
    name = "fake"

    def __init__(self, jobs: List[JobOffer], error: Optional[Exception] = None):
        super().__init__({})
        self._jobs = jobs
        self._error = error

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        if self._error:
            raise self._error
        yield from self._jobs

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


@pytest.fixture(autouse=True)
def _clean_cache():
    service.clear_cache()
    yield
    service.clear_cache()


@pytest.fixture()
def fake_factory(monkeypatch):
    """Remplace les scrapers réels par des doubles : linkedin OK, hellowork en échec."""
    calls = {"count": 0}

    jobs_linkedin = [
        make_job(
            "li_1", "linkedin", "Développeur Python", "TechCorp", "Nantes, France"
        ),
        make_job("li_2", "linkedin", "Data Engineer", "DataCo", "Paris, France"),
    ]
    # Même offre republiée sur WTTJ (accents/casse différents) -> doit être dédupliquée.
    jobs_wttj = [
        make_job("wj_1", "wttj", "Developpeur Python", "techcorp", "Nantes"),
        make_job("wj_2", "wttj", "Product Manager", "StartupX", "Lyon, France"),
    ]

    def _make(source: str) -> BaseScraper:
        calls["count"] += 1
        if source == "linkedin":
            return FakeScraper(jobs_linkedin)
        if source == "wttj":
            return FakeScraper(jobs_wttj)
        if source == "hellowork":
            return FakeScraper([], error=RuntimeError("HTTP 403 simulée"))
        return FakeScraper([])

    monkeypatch.setattr(service, "make_scraper", _make)
    return calls


def test_resolve_sources_all_and_unknown():
    assert service.resolve_sources(None) == service.REAL_SOURCES
    assert service.resolve_sources(["all"]) == service.REAL_SOURCES
    assert service.resolve_sources(["WTTJ", "wttj"]) == ["wttj"]
    with pytest.raises(ValueError):
        service.resolve_sources(["indeed"])


def test_search_all_parallel_error_isolation_and_dedupe(fake_factory):
    outcome = service.search_all(
        SearchCriteria(keywords=["python"]),
        ["linkedin", "wttj", "hellowork"],
    )
    # 2 LinkedIn + 1 WTTJ (le doublon inter-sources est écarté), HelloWork en erreur.
    assert len(outcome.jobs) == 3
    assert outcome.counts["linkedin"] == 2
    assert outcome.counts["hellowork"] == 0
    assert "403" in outcome.errors["hellowork"]
    assert not outcome.cached


def test_search_all_uses_cache(fake_factory):
    criteria = SearchCriteria(keywords=["python"])
    first = service.search_all(criteria, ["linkedin"])
    calls_after_first = fake_factory["count"]
    second = service.search_all(criteria, ["linkedin"])

    assert second.cached is True
    assert len(second.jobs) == len(first.jobs) == 2
    assert fake_factory["count"] == calls_after_first  # aucun rescraping


def test_iter_search_events_emits_done_and_error(fake_factory):
    events = list(
        service.iter_search_events(SearchCriteria(), ["linkedin", "hellowork"])
    )
    types = [e.type for e in events]
    assert types.count("job") == 2
    assert "source_done" in types
    assert "source_error" in types


def test_demo_scraper_filters():
    from jobscraper.scrapers.demo import DemoScraper

    criteria = SearchCriteria(keywords=["python"], location="Nantes", max_results=50)
    jobs = list(DemoScraper().search(criteria))
    assert jobs, "la démo doit renvoyer des offres python à Nantes"
    assert all("nantes" in j.location.lower() for j in jobs)
    assert all(
        "python" in j.title.lower() or "python" in " ".join(j.skills).lower()
        for j in jobs
    )

    stage = list(
        DemoScraper().search(
            SearchCriteria(location="France", contract_types=[ContractType.STAGE])
        )
    )
    assert stage and all(j.contract_type == ContractType.STAGE for j in stage)
