"""Modèles pour la recherche croisée annonces × personnes (Apollo)."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from jobscraper.models.job import JobOffer


class PersonCandidate(BaseModel):
    """Une personne identifiée (ou partiellement identifiée) chez une entreprise.

    Avant révélation (recherche Apollo gratuite), seuls le prénom, le nom
    masqué, le poste et l'entreprise sont connus. Le nom complet, le lieu,
    l'URL LinkedIn et l'e-mail éventuels n'arrivent qu'après l'enrichissement
    (1 crédit Apollo) — d'où le drapeau ``revealed``.
    """

    id: str = Field(..., description="Identifiant Apollo (ou démo) de la personne")
    provider: str = Field(default="apollo", description="apollo ou apollo-demo")

    first_name: Optional[str] = None
    last_name_obfuscated: Optional[str] = None
    display_name: str = Field(
        ..., description="Nom affichable (masqué avant révélation)"
    )
    title: Optional[str] = Field(None, description="Poste actuel")

    company: str = Field(..., description="Entreprise actuelle (nom Apollo)")
    company_domain: Optional[str] = None
    location: Optional[str] = Field(
        None, description="Lieu de la personne (connu seulement après révélation)"
    )

    linkedin_url: Optional[str] = None
    email: Optional[str] = None

    has_email: bool = False
    has_city: bool = False
    revealed: bool = False


class CompanyGroup(BaseModel):
    """Une entreprise et ses deux colonnes : annonces et personnes."""

    key: str = Field(..., description="Clé de regroupement (nom normalisé)")
    name: str = Field(..., description="Nom affichable de l'entreprise")
    match_type: str = Field(
        ...,
        description="both (recrute + emploie), hiring_only (recrute) ou employing_only (emploie déjà)",
    )
    jobs: List[JobOffer] = Field(default_factory=list)
    people: List[PersonCandidate] = Field(default_factory=list)


class CrossSearchSummary(BaseModel):
    """Compteurs d'une recherche croisée."""

    companies: int = 0
    matching_companies: int = Field(
        0, description="Entreprises qui recrutent ET emploient"
    )
    hiring_companies: int = 0
    employing_companies: int = 0
    jobs_total: int = 0
    people_returned: int = 0
    people_total_entries: int = Field(
        0,
        description="Total Apollo correspondant aux filtres (peut dépasser le retour)",
    )
    job_counts: Dict[str, int] = Field(default_factory=dict)
    job_errors: Dict[str, str] = Field(default_factory=dict)
