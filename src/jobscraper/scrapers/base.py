"""Classe de base abstraite pour tous les scrapers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Iterator, Optional

import requests
from loguru import logger
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from jobscraper.models.job import JobOffer, SearchCriteria

# Transport HTTP des scrapers HTML.
#
# Beaucoup de jobboards (HelloWork/DataDome, LinkedIn, France Travail…)
# rejettent les requêtes dont l'empreinte TLS (JA3/JA4) ne ressemble pas à
# celle d'un navigateur : avec `requests` seul, ils répondent 403 ou coupent
# la connexion. `curl_cffi` imite l'empreinte d'un vrai Chrome et lève la
# plupart de ces blocages. Le paquet est optionnel : s'il n'est pas installé,
# on retombe sur `requests` classique (comportement historique).
try:
    from curl_cffi import requests as _cffi_requests
except Exception:  # pragma: no cover - dépend de l'environnement
    _cffi_requests = None

#: Profil d'impersonation navigateur utilisé par curl_cffi.
IMPERSONATE_PROFILE = "chrome"

# Noms des erreurs réseau *transitoires* qui justifient une nouvelle tentative
# (mêmes noms chez requests et chez curl_cffi, qui mime son API). Une erreur
# HTTP (403, 404…) n'est volontairement PAS retentée : elle remonte tout de
# suite, avec son vrai statut, au lieu d'être masquée après 3 essais.
_TRANSIENT_ERROR_NAMES = {
    "ConnectionError",
    "ConnectTimeout",
    "ReadTimeout",
    "Timeout",
    "DNSError",
    "ChunkedEncodingError",
}


def _is_transient_network_error(exc: BaseException) -> bool:
    return type(exc).__name__ in _TRANSIENT_ERROR_NAMES


def transport_name() -> str:
    """Nom du transport HTTP actif pour les scrapers HTML (diagnostic)."""
    if _cffi_requests is not None:
        return f"curl_cffi (impersonation {IMPERSONATE_PROFILE})"
    return "requests (curl_cffi non installé)"


class BaseScraper(ABC):
    """Classe de base pour tous les scrapers d'offres d'emploi."""

    # Nom du scraper (à définir dans les sous-classes)
    name: str = "base"

    # URL de base du site
    base_url: str = ""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialise le scraper.

        Args:
            config: Configuration optionnelle du scraper
        """
        self.config = config or {}
        self._session = None
        logger.info(f"Scraper {self.name} initialisé")

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        """
        Recherche des offres d'emploi selon les critères donnés.

        Args:
            criteria: Critères de recherche

        Yields:
            JobOffer: Les offres d'emploi trouvées
        """
        pass

    @abstractmethod
    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        """
        Récupère les détails complets d'une offre d'emploi.

        Args:
            job_id: Identifiant de l'offre

        Returns:
            JobOffer ou None si non trouvée
        """
        pass

    def _make_session(self):
        """Crée une session HTTP (imitation Chrome si curl_cffi présent)."""
        if _cffi_requests is not None:
            return _cffi_requests.Session(impersonate=IMPERSONATE_PROFILE)
        return requests.Session()

    def _prepare_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Adapte les en-têtes au transport utilisé.

        Avec l'impersonation Chrome, curl_cffi fournit déjà un User-Agent et
        un Accept-Encoding cohérents avec le profil émulé (et sait décoder le
        Brotli) : renvoyer les nôtres créerait une empreinte incohérente, on
        les retire donc. Sans curl_cffi, on garde tels quels les en-têtes du
        scraper (qui n'annoncent jamais `br`, indécodable sans le paquet
        `brotli`).
        """
        if _cffi_requests is None:
            return headers
        return {
            k: v
            for k, v in headers.items()
            if k.lower() not in {"user-agent", "accept-encoding"}
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_transient_network_error),
        reraise=True,
    )
    def _fetch_page(self, url: str) -> str:
        """
        Récupère le contenu d'une page (nouvelle tentative si erreur réseau
        transitoire ; les erreurs HTTP remontent immédiatement).

        Args:
            url: URL de la page à récupérer

        Returns:
            Contenu HTML de la page
        """
        headers = self._prepare_headers(self._get_headers())
        if _cffi_requests is not None:
            response = _cffi_requests.get(
                url, headers=headers, timeout=30, impersonate=IMPERSONATE_PROFILE
            )
        else:
            response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text

    def _get_headers(self) -> dict:
        """
        Retourne les headers HTTP à utiliser pour les requêtes.

        Returns:
            Dictionnaire des headers
        """
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            # Jamais "br" ici : sans le paquet brotli, requests ne sait pas
            # décoder les réponses Brotli que les sites enverraient alors.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Ferme les ressources du scraper."""
        if self._session:
            self._session.close()
            self._session = None
        logger.info(f"Scraper {self.name} fermé")


class AsyncBaseScraper(BaseScraper):
    """Classe de base pour les scrapers asynchrones."""

    @abstractmethod
    async def search_async(self, criteria: SearchCriteria) -> AsyncIterator[JobOffer]:
        """
        Recherche asynchrone des offres d'emploi.

        Args:
            criteria: Critères de recherche

        Yields:
            JobOffer: Les offres d'emploi trouvées
        """
        pass

    @abstractmethod
    async def get_job_details_async(self, job_id: str) -> Optional[JobOffer]:
        """
        Récupère les détails d'une offre de manière asynchrone.

        Args:
            job_id: Identifiant de l'offre

        Returns:
            JobOffer ou None si non trouvée
        """
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_async()

    async def close_async(self):
        """Ferme les ressources de manière asynchrone."""
        self.close()
