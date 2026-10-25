"""Catalogue démo : les recherches d'exemple de l'interface doivent répondre."""

from jobscraper.models.job import SearchCriteria
from jobscraper.scrapers.demo import DemoScraper
from jobscraper.services.apollo import DemoPeopleProvider


def _demo_jobs(keywords, location):
    scraper = DemoScraper({})
    return list(
        scraper.search(SearchCriteria(keywords=keywords, location=location))
    )


def test_demo_finds_technicien_maintenance_in_Nantes():
    # Formulation exacte testée par l'utilisateur (sans le mot "de").
    jobs = _demo_jobs(["technicien maintenance"], "nantes")
    assert jobs, "la démo doit répondre à 'technicien maintenance' / Nantes"
    assert all("nantes" in j.location.lower() for j in jobs)


def test_demo_finds_python_in_nantes():
    jobs = _demo_jobs(["python"], "Nantes")
    assert jobs


def test_demo_finds_data_engineer_in_Lille():
    jobs = _demo_jobs(["data engineer"], "Lille")
    assert jobs


def test_demo_people_find_technicien_maintenance_in_nantes():
    provider = DemoPeopleProvider()
    result = provider.search_people(["Technicien de maintenance"], ["Nantes, France"])
    assert result.people, "les personnes démo doivent croiser avec les annonces démo"
    companies = {p.company for p in result.people}
    assert "Manitou Group" in companies


def test_demo_cross_has_matching_company_for_maintenance():
    jobs = _demo_jobs(["technicien de maintenance"], "nantes")
    provider = DemoPeopleProvider()
    people = provider.search_people(
        ["Technicien de maintenance"], ["Nantes, France"]
    ).people
    job_companies = {j.company for j in jobs}
    people_companies = {p.company for p in people}
    assert job_companies & people_companies, "au moins une entreprise doit croiser"
