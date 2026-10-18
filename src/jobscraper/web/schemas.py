"""Schémas d'entrée/sortie de l'API web.

La requête de recherche hérite directement de ``SearchCriteria`` :
les critères sont donc *exactement* ceux de la CLI, plus la liste
des sources à interroger.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.services.search import SourceInfo  # réexporté pour l'API


class SearchRequest(SearchCriteria):
    """Corps de ``POST /api/search``."""

    sources: List[str] = Field(
        default_factory=lambda: ["all"],
        description="Sources à interroger (linkedin, hellowork, francetravail, adzuna, wttj ou all)",
    )
    use_cache: bool = Field(
        default=True, description="Autoriser le cache mémoire court"
    )

    def to_criteria(self) -> SearchCriteria:
        return SearchCriteria(**self.model_dump(exclude={"sources", "use_cache"}))


class SearchResponse(BaseModel):
    """Réponse de ``POST /api/search``."""

    jobs: List[JobOffer]
    total: int
    counts: Dict[str, int] = Field(default_factory=dict)
    errors: Dict[str, str] = Field(default_factory=dict)
    duration_ms: int = 0
    cached: bool = False


class HealthResponse(BaseModel):
    """Réponse de ``GET /api/health``."""

    status: str = "ok"
    version: str
    demo: bool = False
    sources: List[str] = Field(default_factory=list)


__all__ = ["HealthResponse", "SearchRequest", "SearchResponse", "SourceInfo"]
