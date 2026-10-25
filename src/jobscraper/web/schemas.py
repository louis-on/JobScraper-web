"""Schémas d'entrée/sortie de l'API web.

La requête de recherche hérite directement de ``SearchCriteria`` :
les critères sont donc *exactement* ceux de la CLI, plus la liste
des sources à interroger.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.models.prospecting import (
    CompanyGroup,
    CrossSearchSummary,
    PersonCandidate,
)
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


class CrossSearchRequest(BaseModel):
    """Corps de ``POST /api/cross-search`` (annonces × personnes Apollo)."""

    metier: str = Field(..., description="Intitulé de poste principal")
    title_variants: List[str] = Field(
        default_factory=list,
        description="Variantes d'intitulé (utilisées telles quelles par Apollo)",
    )
    location: str = Field(default="France", description="ville, région ou pays")
    radius_km: Optional[int] = Field(
        default=None,
        description="Rayon autour du lieu — annonces uniquement (Apollo ne gère pas les rayons)",
    )
    sources: List[str] = Field(default_factory=lambda: ["all"])
    max_jobs_per_source: int = Field(default=50, ge=1, le=500)
    max_people: int = Field(default=100, ge=1, le=500)
    include_job_variants: bool = Field(
        default=False,
        description="Chercher aussi chaque variante dans les annonces (plus lent)",
    )
    verified_email_only: bool = Field(
        default=False, description="Apollo : ne garder que les profils à e-mail vérifié"
    )

    @field_validator("metier")
    @classmethod
    def _metier_non_vide(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le métier ne peut pas être vide.")
        return value


class CrossSearchResponse(BaseModel):
    """Réponse de ``POST /api/cross-search`` : entreprises, annonces, personnes."""

    companies: List[CompanyGroup]
    summary: CrossSearchSummary
    apollo_available: bool = False
    apollo_demo: bool = False
    apollo_error: Optional[str] = None
    duration_ms: int = 0


class ProspectsStatusResponse(BaseModel):
    """Réponse de ``GET /api/prospects/status``."""

    available: bool
    provider: Optional[str] = None
    demo: bool = False
    reason: Optional[str] = None


class RevealRequest(BaseModel):
    """Corps de ``POST /api/prospects/reveal`` (1 crédit Apollo si trouvé)."""

    person_id: str


class RevealResponse(BaseModel):
    person: PersonCandidate


__all__ = [
    "CrossSearchRequest",
    "CrossSearchResponse",
    "HealthResponse",
    "PersonCandidate",
    "ProspectsStatusResponse",
    "RevealRequest",
    "RevealResponse",
    "SearchRequest",
    "SearchResponse",
    "SourceInfo",
]
