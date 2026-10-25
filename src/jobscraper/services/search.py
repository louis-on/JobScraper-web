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


def unwrap_error(exc: BaseException) -> BaseException:
    """Retrouve l'exception d'origine sous les enveloppes (tenacity…).

    Un ``RetryError`` de tenacity ne contient pas le message de l'erreur qui
    a réellement échoué (403, SSL…) : sans déballage, tout ressemble à un
    problème réseau générique.
    """
    seen: set = set()
    while True:
        last_attempt = getattr(exc, "last_attempt", None)
        if last_attempt is None or not hasattr(last_attempt, "exception"):
            return exc
        try:
            inner = last_attempt.exception()
        except Exception:
            return exc
        if inner is None or id(inner) in seen:
            return exc
        seen.add(id(inner))
        exc = inner


def _http_status_of(exc: BaseException) -> Optional[int]:
    """Statut HTTP porté par une exception requests/curl_cffi, si présent."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status
    match = re.search(r"\b(\d{3}) (?:Client|Server) Error", str(exc))
    return int(match.group(1)) if match else None


def friendly_error(exc: BaseException) -> str:
    """Traduit une erreur technique de scraper en message affichable.

    Le message reste lisible, mais il se termine toujours par le détail
    technique (type + message d'origine) : sans lui, impossible de
    distinguer un 403 anti-robot d'une coupure réseau — les deux étaient
    auparavant affichés « source injoignable ».
    """
    real = unwrap_error(exc)
    text = str(real)
    low = text.lower()
    detail = f"{type(real).__name__} : {text}".strip()
    if len(detail) > 220:
        detail = f"{detail[:220]}…"
    suffix = f" (Détail technique : {detail})"

    status = _http_status_of(real)
    if status in (401, 403, 429) or "forbidden" in low:
        return (
            "Accès refusé par le site (HTTP 403/429) : blocage anti-robot "
            "probable. Réessayez plus tard, réduisez le nombre de résultats, "
            "ou basculez sur une source API (Adzuna)." + suffix
        )
    if status is not None:
        return f"Le site a répondu une erreur HTTP {status}." + suffix
    if "certificate" in low or "certificat" in low:
        return (
            "Échec de vérification du certificat TLS : un antivirus ou un "
            "proxy local intercepte probablement les connexions HTTPS. "
            "Désactivez l'analyse HTTPS de l'antivirus ou testez depuis un "
            "autre réseau." + suffix
        )

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
        "curl: (",
    )
    if any(marker in low for marker in network_markers):
        return (
            "Source injoignable (le site n'a pas répondu). "
            "Depuis un aperçu hébergé, l'accès sortant aux jobboards peut "
            "être bloqué ; en exécution locale, vérifiez la connexion ou "
            "un éventuel blocage du site (pare-feu, DNS filtrant type "
            "Pi-hole, anti-robot qui coupe la connexion)." + suffix
        )
    return text if len(text) < 300 else f"{type(real).__name__} : {text[:200]}…"


def probe_sources(sources: Iterable[str]) -> Dict[str, Dict]:
    """Teste chaque source par une mini-recherche réelle (1 offre max).

    Contrairement à la recherche normale, les erreurs sont rendues **brutes**
    (type + message d'origine, non traduites) : c'est l'outil de diagnostic
    à consulter quand une source « ne marche pas » — on y voit le vrai
    statut HTTP ou la vraie erreur réseau, par source.
    """
    criteria = SearchCriteria(keywords=["technicien"], location="France", max_results=1)
    results: Dict[str, Dict] = {}
    lock = threading.Lock()

    def run(source: str) -> None:
        started = time.monotonic()
        entry: Dict = {"ok": False, "jobs": 0, "duration_ms": None, "error": None}
        try:
            with make_scraper(source) as scraper:
                for _job in scraper.search(criteria):
                    entry["jobs"] += 1
                    break  # une seule offre suffit à prouver que ça répond
            entry["ok"] = True
        except Exception as exc:  # diagnostic : on veut l'erreur, pas la cacher
            real = unwrap_error(exc)
            entry["error"] = f"{type(real).__name__} : {real}"[:400]
        entry["duration_ms"] = int((time.monotonic() - started) * 1000)
        with lock:
            results[source] = entry

    threads = [
        threading.Thread(target=run, args=(source,), daemon=True) for source in sources
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


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
