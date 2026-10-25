"""Couche service de recherche, partagée entre la CLI et l'interface web.

Responsabilités :
- registre des sources disponibles (une seule source de vérité) ;
- interrogation des scrapers **en parallèle** (un thread par source,
  les scrapers étant limités par le réseau, pas par le CPU) ;
- **isolation des erreurs** : une source en échec ne fait pas échouer
  la recherche entière, elle est signalée dans ``errors`` ;
- **déduplication entre sources** (titre + entreprise + ville normalisés) ;
- cache mémoire à durée de vie courte pour ne pas rescraper à chaque
  requête identique (indispensable côté web).
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional

from loguru import logger
from pydantic import BaseModel

from jobscraper.config import get_config
from jobscraper.models.job import JobOffer, SearchCriteria, SortBy
from jobscraper.scrapers.base import BaseScraper


class SourceInfo(BaseModel):
    """Description d'une source d'offres, exposée par l'API et la CLI."""

    id: str
    label: str
    description: str
    available: bool = True
    unavailable_reason: Optional[str] = None


# Métadonnées des sources, dans l'ordre d'affichage souhaité.
_SOURCE_METADATA: List[Dict[str, str]] = [
    {
        "id": "linkedin",
        "label": "LinkedIn",
        "description": "Offres d'emploi LinkedIn (scraping, peut être bloqué depuis un hébergeur cloud)",
    },
    {
        "id": "hellowork",
        "label": "HelloWork",
        "description": "Portail d'emploi français",
    },
    {
        "id": "francetravail",
        "label": "France Travail",
        "description": "Service public de l'emploi (ex Pôle Emploi)",
    },
    {
        "id": "adzuna",
        "label": "Adzuna",
        "description": "Agrégateur (Indeed, Monster…) — nécessite des clés API gratuites",
    },
    {
        "id": "wttj",
        "label": "Welcome to the Jungle",
        "description": "Startups et scale-ups (via l'API Algolia)",
    },
    {
        "id": "demo",
        "label": "Démo",
        "description": "Données fictives pour tester l'interface sans réseau",
    },
]

REAL_SOURCES: List[str] = [s["id"] for s in _SOURCE_METADATA if s["id"] != "demo"]


def demo_enabled() -> bool:
    """Le mode démo (données fictives) est-il activé ?"""
    return os.getenv("JOBSCRAPER_DEMO", "").strip().lower() in {"1", "true", "yes"}


def make_scraper(source: str) -> BaseScraper:
    """Instancie le scraper d'une source avec la configuration globale."""
    config = get_config()

    if source == "linkedin":
        from jobscraper.scrapers.linkedin import LinkedInScraper

        return LinkedInScraper({"delay": config.linkedin.delay_between_requests})
    if source == "hellowork":
        from jobscraper.scrapers.hellowork import HelloWorkScraper

        return HelloWorkScraper({"delay": config.hellowork.delay_between_requests})
    if source == "francetravail":
        from jobscraper.scrapers.francetravail import FranceTravailScraper

        return FranceTravailScraper(
            {"delay": config.francetravail.delay_between_requests}
        )
    if source == "adzuna":
        from jobscraper.scrapers.adzuna import AdzunaScraper

        return AdzunaScraper(
            {
                "app_id": os.getenv("ADZUNA_APP_ID"),
                "app_key": os.getenv("ADZUNA_APP_KEY"),
            }
        )
    if source == "wttj":
        from jobscraper.scrapers.wttj import WTTJScraper

        return WTTJScraper({"delay": config.wttj.delay_between_requests})
    if source == "demo":
        from jobscraper.scrapers.demo import DemoScraper

        return DemoScraper()

    raise ValueError(f"Source inconnue : {source}")


def get_sources() -> List[SourceInfo]:
    """Liste les sources connues et leur disponibilité actuelle."""
    config = get_config()
    enabled_by_config = {
        "linkedin": config.linkedin.enabled,
        "hellowork": config.hellowork.enabled,
        "francetravail": config.francetravail.enabled,
        "wttj": config.wttj.enabled,
    }

    sources: List[SourceInfo] = []
    for meta in _SOURCE_METADATA:
        source_id = meta["id"]
        available, reason = True, None

        if source_id == "demo" and not demo_enabled():
            continue
        if source_id == "adzuna" and not (
            os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY")
        ):
            available = False
            reason = "Clés API manquantes (ADZUNA_APP_ID / ADZUNA_APP_KEY dans .env)"
        elif enabled_by_config.get(source_id) is False:
            available = False
            reason = "Désactivée dans la configuration"

        sources.append(
            SourceInfo(
                id=source_id,
                label=meta["label"],
                description=meta["description"],
                available=available,
                unavailable_reason=reason,
            )
        )
    return sources


def resolve_sources(requested: Optional[Iterable[str]] = None) -> List[str]:
    """Normalise la liste des sources demandées.

    ``None``, vide ou contenant ``"all"`` → toutes les sources réelles.
    Lève ``ValueError`` en cas de source inconnue.
    """
    known = REAL_SOURCES + (["demo"] if demo_enabled() else [])
    if not requested:
        return list(REAL_SOURCES)

    requested = [s.strip().lower() for s in requested if s and s.strip()]
    if not requested or "all" in requested:
        return list(REAL_SOURCES)

    unknown = [s for s in requested if s not in known]
    if unknown:
        raise ValueError(
            f"Source(s) inconnue(s) : {', '.join(unknown)}. "
            f"Sources valides : {', '.join(known)} (ou all)"
        )
    # Déduplique en gardant l'ordre demandé.
    return list(dict.fromkeys(requested))


# --------------------------------------------------------------------------- #
# Déduplication inter-sources
# --------------------------------------------------------------------------- #


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def dedupe_key(job: JobOffer) -> str:
    """Clé de rapprochement d'une même offre publiée sur plusieurs sites."""
    city = _normalize((job.location or "").split(",")[0])
    return "|".join([_normalize(job.title), _normalize(job.company), city])


def dedupe(jobs: Iterable[JobOffer]) -> List[JobOffer]:
    """Supprime les doublons évidents entre sources (premier vu conservé)."""
    seen: set = set()
    unique: List[JobOffer] = []
    for job in jobs:
        key = dedupe_key(job)
        if key in seen:
            logger.debug(f"Doublon inter-sources ignoré : {job.title} ({job.source})")
            continue
        seen.add(key)
        unique.append(job)
    return unique


# --------------------------------------------------------------------------- #
# Recherche (streaming + agrégée) et cache
# --------------------------------------------------------------------------- #


@dataclass
class SearchEvent:
    """Événement émis pendant une recherche en streaming."""

    type: str  # source_start | job | source_done | source_error
    source: str
    job: Optional[JobOffer] = None
    count: int = 0
    error: Optional[str] = None


@dataclass
class SearchOutcome:
    """Résultat agrégé d'une recherche multi-sources."""

    jobs: List[JobOffer] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0
    cached: bool = False


def friendly_error(exc: BaseException) -> str:
    """Traduit une erreur technique de scraper en message affichable.

    Les erreurs réseau brutes (SSL, timeouts, RetryError de tenacity…) sont
    illisibles pour l'utilisateur final ; elles restent dans les logs.
    """
    text = str(exc)
    low = text.lower()
    network_markers = (
        "ssl",
        "connection",
        "connexion",
        "max retries",
        "timed out",
        "timeout",
        "name resolution",
        "failed to resolve",
        "eof occurred",
        "retryerror",
        "remote disconnected",
        "connection reset",
    )
    if any(marker in low for marker in network_markers):
        return (
            "Source injoignable (le site n'a pas répondu). "
            "Depuis un aperçu hébergé, l'accès sortant aux jobboards peut "
            "être bloqué ; en exécution locale, vérifiez la connexion ou "
            "un éventuel blocage anti-robot du site."
        )
    if "403" in text or "429" in text or "forbidden" in low:
        return (
            "Accès refusé par le site (HTTP 403/429) : blocage anti-robot "
            "probable, réessayez plus tard ou réduisez le nombre de résultats."
        )
    return text if len(text) < 300 else f"{type(exc).__name__} : {text[:200]}…"


def iter_search_events(
    criteria: SearchCriteria, sources: Iterable[str]
) -> Iterator[SearchEvent]:
    """Interroge les sources en parallèle et émet les offres au fil de l'eau.

    Chaque scraper tourne dans son propre thread et pousse ses offres dans
    une file ; ce générateur les restitue (dédupliquées) dès leur arrivée.
    """
    sources = list(sources)
    events: "queue.Queue[SearchEvent]" = queue.Queue()

    def worker(source: str) -> None:
        events.put(SearchEvent(type="source_start", source=source))
        count = 0
        try:
            with make_scraper(source) as scraper:
                for job in scraper.search(criteria):
                    count += 1
                    events.put(SearchEvent(type="job", source=source, job=job))
            events.put(SearchEvent(type="source_done", source=source, count=count))
        except Exception as exc:  # isolation : une source ne casse pas le reste
            logger.exception(f"Source {source} en échec")
            events.put(
                SearchEvent(
                    type="source_error", source=source, error=friendly_error(exc)
                )
            )

    threads = [
        threading.Thread(target=worker, args=(source,), daemon=True)
        for source in sources
    ]
    for thread in threads:
        thread.start()

    remaining = len(sources)
    seen_keys: set = set()
    while remaining > 0:
        event = events.get()
        if event.type == "job" and event.job is not None:
            key = dedupe_key(event.job)
            if key in seen_keys:
                continue
            seen_keys.add(key)
        if event.type in ("source_done", "source_error"):
            remaining -= 1
        yield event


_CACHE_TTL_SECONDS = int(os.getenv("JOBSCRAPER_CACHE_TTL", "900"))  # 15 min
_cache: Dict[str, tuple] = {}
_cache_lock = threading.Lock()


def _cache_key(criteria: SearchCriteria, sources: List[str]) -> str:
    payload = json.dumps(
        {"criteria": criteria.model_dump(mode="json"), "sources": sorted(sources)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def search_all(
    criteria: SearchCriteria,
    sources: Optional[Iterable[str]] = None,
    use_cache: bool = True,
) -> SearchOutcome:
    """Recherche agrégée sur plusieurs sources, avec cache mémoire court."""
    resolved = resolve_sources(sources)
    key = _cache_key(criteria, resolved)

    if use_cache and _CACHE_TTL_SECONDS > 0:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
            outcome = hit[1]
            return SearchOutcome(
                jobs=list(outcome.jobs),
                counts=dict(outcome.counts),
                errors=dict(outcome.errors),
                duration_ms=outcome.duration_ms,
                cached=True,
            )

    started = time.monotonic()
    jobs: List[JobOffer] = []
    counts: Dict[str, int] = {s: 0 for s in resolved}
    errors: Dict[str, str] = {}

    for event in iter_search_events(criteria, resolved):
        if event.type == "job" and event.job is not None:
            jobs.append(event.job)
            counts[event.source] = counts.get(event.source, 0) + 1
        elif event.type == "source_error":
            errors[event.source] = event.error or "Erreur inconnue"

    if criteria.sort_by == SortBy.DATE:

        def _timestamp(job: JobOffer) -> float:
            if job.posted_at is None:
                return float("-inf")
            try:
                return job.posted_at.timestamp()
            except (OverflowError, OSError, ValueError):
                return float("-inf")

        jobs.sort(key=_timestamp, reverse=True)

    outcome = SearchOutcome(
        jobs=jobs,
        counts=counts,
        errors=errors,
        duration_ms=int((time.monotonic() - started) * 1000),
    )

    # On ne met en cache que si au moins une source a répondu.
    if use_cache and _CACHE_TTL_SECONDS > 0 and len(errors) < len(resolved):
        with _cache_lock:
            _cache[key] = (time.monotonic(), outcome)

    return outcome
