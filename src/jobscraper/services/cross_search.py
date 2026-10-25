"""Recherche croisée annonces × personnes, regroupée par entreprise.

Lance **en parallèle** la recherche d'annonces (couche service existante) et
la recherche de personnes Apollo, puis fusionne les résultats par entreprise :

- ``both``          : l'entreprise recrute pour ce métier ET emploie déjà ce profil ;
- ``hiring_only``   : elle recrute (aucune personne trouvée chez elle) ;
- ``employing_only``: elle emploie ce profil sans annonce correspondante.

Le rapprochement se fait sur le nom d'entreprise normalisé (accents, casse et
formes juridiques écartées), aucun des jobboards ne fournissant de domaine.
"""

from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from loguru import logger

from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.models.prospecting import (
    CompanyGroup,
    CrossSearchSummary,
    PersonCandidate,
)
from jobscraper.services import search as search_service
from jobscraper.services.apollo import (
    PeopleSearchResult,
    get_people_provider,
    to_apollo_locations,
)

# Formes juridiques et mots parasites pour le rapprochement d'entreprises.
_LEGAL_SUFFIXES = {
    "sas",
    "sasu",
    "sarl",
    "sa",
    "sci",
    "eurl",
    "snc",
    "scop",
    "gie",
    "inc",
    "ltd",
    "llc",
    "corp",
    "gmbh",
    "bv",
    "nv",
    "plc",
    "co",
    "groupe",
    "group",
    "holding",
}


def normalize_company(name: str) -> str:
    """Clé de rapprochement d'une entreprise entre jobboards et Apollo."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    tokens = [t for t in text.split() if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens).strip() or _fallback(name)


def _fallback(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").lower()).strip()


def group_by_company(
    jobs: Iterable[JobOffer], people: Iterable[PersonCandidate]
) -> List[CompanyGroup]:
    """Regroupe annonces et personnes par entreprise, triées par intérêt."""
    groups: Dict[str, CompanyGroup] = {}
    display_names: Dict[str, Dict[str, int]] = {}

    def _group_for(company: str) -> CompanyGroup:
        key = normalize_company(company)
        if key not in groups:
            groups[key] = CompanyGroup(key=key, name=company, match_type="hiring_only")
            display_names[key] = {}
        display_names[key][company] = display_names[key].get(company, 0) + 1
        return groups[key]

    for job in jobs:
        _group_for(job.company).jobs.append(job)
    for person in people:
        _group_for(person.company).people.append(person)

    for key, group in groups.items():
        # Nom affichable : orthographe la plus fréquente (Apollo tend à
        # fournir la forme canonique, les jobboards la plus courante).
        group.name = max(display_names[key].items(), key=lambda kv: kv[1])[0]
        group.jobs.sort(
            key=lambda j: j.posted_at.timestamp() if j.posted_at else 0.0, reverse=True
        )
        group.people.sort(key=lambda p: (p.title or "", p.display_name))
        if group.jobs and group.people:
            group.match_type = "both"
        elif group.people:
            group.match_type = "employing_only"
        else:
            group.match_type = "hiring_only"

    order = {"both": 0, "hiring_only": 1, "employing_only": 2}
    return sorted(
        groups.values(),
        key=lambda g: (
            order[g.match_type],
            -(len(g.jobs) + len(g.people)),
            g.name.lower(),
        ),
    )


@dataclass
class CrossSearchOutcome:
    companies: List[CompanyGroup] = field(default_factory=list)
    summary: CrossSearchSummary = field(default_factory=CrossSearchSummary)
    apollo_available: bool = False
    apollo_demo: bool = False
    apollo_error: Optional[str] = None
    duration_ms: int = 0


def _search_jobs(
    metier: str,
    variants: Sequence[str],
    location: str,
    radius_km: Optional[int],
    sources: Sequence[str],
    max_jobs_per_source: int,
    include_variants: bool,
):
    """Annonces pour le métier (et, sur option, chaque variante)."""
    queries = (
        [metier] + [v for v in variants if v.strip()] if include_variants else [metier]
    )
    all_jobs: List[JobOffer] = []
    counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    seen: set = set()

    for query in queries:
        criteria = SearchCriteria(
            keywords=[query],
            location=location,
            radius_km=radius_km,
            max_results=max_jobs_per_source,
        )
        outcome = search_service.search_all(criteria, sources)
        for job in outcome.jobs:
            marker = (job.source, job.id)
            if marker not in seen:
                seen.add(marker)
                all_jobs.append(job)
        for src, n in outcome.counts.items():
            counts[src] = counts.get(src, 0) + n
        errors.update(outcome.errors)

    return all_jobs, counts, errors


def run_cross_search(
    metier: str,
    variants: Sequence[str] = (),
    location: str = "France",
    radius_km: Optional[int] = None,
    sources: Optional[Sequence[str]] = None,
    max_jobs_per_source: int = 50,
    max_people: int = 100,
    include_job_variants: bool = False,
    verified_email_only: bool = False,
    provider=None,
) -> CrossSearchOutcome:
    """Croise annonces et personnes Apollo pour un métier + une localisation.

    Les deux recherches tournent en parallèle ; chacune peut échouer sans
    bloquer l'autre (l'erreur Apollo est rapportée dans le résultat).

    Raises:
        ValueError: source d'annonce inconnue (propage la validation du service).
    """
    started = time.monotonic()
    resolved_sources = search_service.resolve_sources(
        list(sources) if sources else None
    )
    if provider is None:
        provider = get_people_provider()

    titles = list(dict.fromkeys([metier] + [v for v in variants if v.strip()]))
    apollo_locations = to_apollo_locations(location)

    def _jobs_task():
        return _search_jobs(
            metier,
            variants,
            location,
            radius_km,
            resolved_sources,
            max_jobs_per_source,
            include_job_variants,
        )

    def _people_task() -> PeopleSearchResult:
        if provider is None:
            return PeopleSearchResult()
        return provider.search_people(
            titles=titles,
            locations=apollo_locations,
            max_people=max_people,
            verified_email_only=verified_email_only,
        )

    jobs: List[JobOffer] = []
    job_counts: Dict[str, int] = {}
    job_errors: Dict[str, str] = {}
    people_result = PeopleSearchResult()
    apollo_error: Optional[str] = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs_future = executor.submit(_jobs_task)
        people_future = executor.submit(_people_task)
        try:
            jobs, job_counts, job_errors = jobs_future.result()
        except (
            Exception
        ) as exc:  # search_all isole déjà les sources ; filet de sécurité
            logger.exception("Recherche d'annonces en échec")
            job_errors = {"annonces": str(exc)}
        try:
            people_result = people_future.result()
        except Exception as exc:
            logger.exception("Recherche de personnes en échec")
            apollo_error = str(exc)

    companies = group_by_company(jobs, people_result.people)
    summary = CrossSearchSummary(
        companies=len(companies),
        matching_companies=sum(1 for c in companies if c.match_type == "both"),
        hiring_companies=sum(1 for c in companies if c.jobs),
        employing_companies=sum(1 for c in companies if c.people),
        jobs_total=len(jobs),
        people_returned=len(people_result.people),
        people_total_entries=people_result.total_entries,
        job_counts=job_counts,
        job_errors=job_errors,
    )

    return CrossSearchOutcome(
        companies=companies,
        summary=summary,
        apollo_available=provider is not None and apollo_error is None,
        apollo_demo=bool(provider is not None and getattr(provider, "is_demo", False)),
        apollo_error=apollo_error
        or (
            None
            if provider is not None
            else "Apollo non configuré (APOLLO_API_KEY manquante)."
        ),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
