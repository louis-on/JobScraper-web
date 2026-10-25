"""Tests du provider Apollo (parsing, pagination, démo) — aucun réseau réel."""

import pytest

from jobscraper.services import apollo as apollo_service
from jobscraper.services.apollo import (
    ApolloError,
    ApolloPeopleProvider,
    DemoPeopleProvider,
    to_apollo_locations,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _raw_person(pid: str, company: str, title: str = "Data Engineer") -> dict:
    return {
        "id": pid,
        "first_name": "Camille",
        "last_name_obfuscated": "Du***d",
        "title": title,
        "has_email": True,
        "has_city": True,
        "organization": {"name": company},
    }


def test_to_apollo_locations():
    assert to_apollo_locations("France") == ["France"]
    assert to_apollo_locations("") == ["France"]
    assert to_apollo_locations("Paris") == ["Paris, France"]
    assert to_apollo_locations("Paris, Île-de-France") == ["Paris, Île-de-France"]


def test_parse_search_person_masked():
    person = ApolloPeopleProvider._parse_search_person(_raw_person("1", "Capgemini"))
    assert person.display_name.startswith("Camille") and "***" in person.display_name
    assert person.company == "Capgemini"
    assert person.linkedin_url is None and person.location is None
    assert person.revealed is False


def test_parse_search_person_without_company_skipped():
    assert ApolloPeopleProvider._parse_search_person({"id": "1"}) is None


def test_search_people_paginates_and_sends_titles(monkeypatch):
    calls = []

    def fake_post(url, headers=None, params=None, timeout=None):
        calls.append(params)
        page = dict((k, v) for k, v in params if k in ("page",))["page"]
        if page == 1:
            return FakeResponse(
                {
                    "total_entries": 3,
                    "people": [
                        _raw_person("1", "Capgemini"),
                        _raw_person("2", "Akeneo"),
                    ],
                }
            )
        return FakeResponse(
            {"total_entries": 3, "people": [_raw_person("3", "Doctolib")]}
        )

    monkeypatch.setattr(apollo_service.requests, "post", fake_post)
    provider = ApolloPeopleProvider("test-key")
    result = provider.search_people(
        titles=["Data Engineer", "Ingénieur Data"],
        locations=["Paris, France"],
        max_people=10,
    )

    assert result.total_entries == 3
    assert [p.id for p in result.people] == ["1", "2", "3"]
    sent_titles = [v for k, v in calls[0] if k == "person_titles[]"]
    assert sent_titles == ["Data Engineer", "Ingénieur Data"]


def test_reveal_parses_full_profile_and_masks_locked_email(monkeypatch):
    def fake_post(url, headers=None, params=None, timeout=None):
        assert ("reveal_phone_number", "false") in params
        return FakeResponse(
            {
                "person": {
                    "id": "42",
                    "name": "Camille Durand",
                    "first_name": "Camille",
                    "last_name": "Durand",
                    "title": "Data Engineer",
                    "linkedin_url": "https://www.linkedin.com/in/camille-durand/",
                    "email": "email_not_unlocked@Capgemini",
                    "city": "Paris",
                    "state": "Ile-de-France",
                    "country": "France",
                    "organization": {
                        "name": "Capgemini",
                        "primary_domain": "Capgemini",
                    },
                }
            }
        )

    monkeypatch.setattr(apollo_service.requests, "post", fake_post)
    person = ApolloPeopleProvider("k").reveal_person("42")
    assert person.display_name.endswith("Durand") and "***" not in person.display_name
    assert person.linkedin_url is not None
    assert person.location == "Paris, Ile-de-France, France"
    assert person.email is None  # e-mail verrouillé par Apollo
    assert person.revealed is True


def test_demo_provider_masks_then_reveals():
    provider = DemoPeopleProvider()
    result = provider.search_people(titles=["Développeur Python"], locations=["Nantes"])
    assert result.total_entries >= 2
    claires = [p for p in result.people if p.company == "Capgemini"]
    assert claires and "***" in claires[0].display_name
    assert claires[0].location is None  # comme Apollo avant révélation

    revealed = provider.reveal_person(claires[0].id)
    assert revealed.display_name == "Claire Bernard"
    assert revealed.location == "Nantes, France"
    assert revealed.linkedin_url and "example.com" in revealed.linkedin_url

    with pytest.raises(ApolloError):
        provider.reveal_person("inconnu")


def test_demo_provider_filters_by_city():
    provider = DemoPeopleProvider()
    paris = provider.search_people(titles=["Data"], locations=["Paris, France"])
    assert paris.people and all(
        p.company in {"Doctolib", "BlaBlaCar", "Contentsquare"} for p in paris.people
    )
