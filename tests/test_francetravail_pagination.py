"""Non-régression : pagination France Travail via « Afficher les 20 suivantes ».

Le site pagine avec un lien événement (...:afficherplusderesultats/20-39/0)
et 20 offres par page — l'ancien code ajoutait &page=N (ignoré du site),
relisait la page 1 et s'arrêtait donc à 20 offres. Ces tests simulent les
pages HTML (aucun réseau) et vérifient que le vrai lien est suivi.
"""

import pytest

from jobscraper.models.job import SearchCriteria
from jobscraper.scrapers.francetravail import FranceTravailScraper

NEXT_HREF = (
    "/offres/recherche.rechercheoffre:afficherplusderesultats/20-39/0"
    "?motsCles=python"
)


def _card(job_id: str, title: str) -> str:
    return (
        f'<li class="result" data-id-offre="{job_id}">'
        f'<h2 class="media-heading"><span class="media-heading-title">{title}</span></h2>'
        f'<p class="subtext">ACME - Nantes</p>'
        f'<p class="description">Description de {title}</p>'
        f"</li>"
    )


PAGE_1 = (
    "<html><body><ul>"
    + _card("FT001", "Développeur Python")
    + _card("FT002", "Data Engineer")
    + "</ul>"
    + f'<a href="{NEXT_HREF}">Afficher les 20 offres suivantes</a>'
    + "</body></html>"
)

# La page « afficher plus » peut renvoyer le cumul (anciens + nouveaux) :
# FT002 y figure déjà — il ne doit pas être compté deux fois, ni arrêter la boucle.
PAGE_2 = (
    "<html><body><ul>"
    + _card("FT001", "Développeur Python")
    + _card("FT002", "Data Engineer")
    + _card("FT003", "DevOps")
    + "</ul></body></html>"
)


@pytest.fixture()
def scraper(monkeypatch):
    instance = FranceTravailScraper({"delay": 0})
    requested = []

    def fake_get_html(url: str) -> str:
        requested.append(url)
        if "afficherplusderesultats" in url:
            return PAGE_2
        return PAGE_1

    monkeypatch.setattr(instance, "_get_html", fake_get_html)
    instance.requested_urls = requested
    return instance


def test_follows_afficher_plus_link(scraper):
    jobs = list(scraper.search(SearchCriteria(keywords=["python"], max_results=50)))

    assert [j.id for j in jobs] == [
        "francetravail_FT001",
        "francetravail_FT002",
        "francetravail_FT003",
    ]
    assert len(scraper.requested_urls) == 2
    assert "afficherplusderesultats/20-39/0" in scraper.requested_urls[1]
    # Surtout pas l'ancien paramètre, ignoré par le site :
    assert "&page=" not in scraper.requested_urls[1]


def test_respects_max_results(scraper):
    jobs = list(scraper.search(SearchCriteria(keywords=["python"], max_results=1)))
    assert len(jobs) == 1
    assert len(scraper.requested_urls) == 1  # pas de page suivante demandée
