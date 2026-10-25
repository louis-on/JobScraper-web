"""Scraper de démonstration : offres fictives, sans aucun accès réseau.

Activable via la variable d'environnement ``JOBSCRAPER_DEMO=1``. Utile pour
développer et tester l'interface web sans dépendre des jobboards (et sans
les solliciter), ou pour une démo hébergée.
"""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, Iterator, List, Optional

from jobscraper.models.job import (
    ContractType,
    ExperienceLevel,
    JobOffer,
    SearchCriteria,
)
from jobscraper.scrapers.base import BaseScraper

# (titre, entreprise, lieu, contrat, expérience, remote, salaire min, salaire max,
#  compétences, jours depuis publication)
_SAMPLE = [
    (
        "Développeur Python / FastAPI",
        "Capgemini",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.MID,
        True,
        38000,
        48000,
        ["Python", "FastAPI", "PostgreSQL", "Docker"],
        1,
    ),
    (
        "Développeuse Full-Stack Vue.js / Node",
        "Lumio",
        "Paris, Île-de-France",
        ContractType.CDI,
        ExperienceLevel.SENIOR,
        True,
        50000,
        62000,
        ["Vue.js", "TypeScript", "Node.js"],
        2,
    ),
    (
        "Data Engineer",
        "Decathlon Digital",
        "Lille, Hauts-de-France",
        ContractType.CDI,
        ExperienceLevel.SENIOR,
        False,
        52000,
        65000,
        ["Python", "Spark", "GCP", "dbt"],
        3,
    ),
    (
        "Développeur React (H/F)",
        "Doctolib",
        "Paris, Île-de-France",
        ContractType.CDI,
        ExperienceLevel.MID,
        True,
        45000,
        58000,
        ["React", "TypeScript", "Ruby on Rails"],
        1,
    ),
    (
        "Stage — Développeur web",
        "Ouest Digital",
        "La Roche-sur-Yon, Pays de la Loire",
        ContractType.STAGE,
        ExperienceLevel.INTERNSHIP,
        False,
        None,
        None,
        ["HTML", "CSS", "JavaScript", "PHP"],
        5,
    ),
    (
        "Alternance — Data Analyst",
        "Harmonie Mutuelle",
        "Nantes, Pays de la Loire",
        ContractType.ALTERNANCE,
        ExperienceLevel.JUNIOR,
        False,
        None,
        None,
        ["SQL", "Python", "Power BI"],
        4,
    ),
    (
        "DevOps / SRE",
        "OVHcloud",
        "Roubaix, Hauts-de-France",
        ContractType.CDI,
        ExperienceLevel.SENIOR,
        True,
        55000,
        70000,
        ["Kubernetes", "Terraform", "Go", "Linux"],
        6,
    ),
    (
        "Ingénieur QA automatisation",
        "Ubisoft",
        "Montpellier, Occitanie",
        ContractType.CDD,
        ExperienceLevel.MID,
        False,
        36000,
        44000,
        ["Python", "Selenium", "CI/CD"],
        8,
    ),
    (
        "Chef de projet IT",
        "Sopra Steria",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.LEAD,
        True,
        48000,
        58000,
        ["Agile", "Scrum", "Gestion de projet"],
        7,
    ),
    (
        "Développeur Python junior",
        "Akeneo",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.JUNIOR,
        True,
        32000,
        38000,
        ["Python", "Django", "API REST"],
        2,
    ),
    (
        "UX/UI Designer",
        "Back Market",
        "Bordeaux, Nouvelle-Aquitaine",
        ContractType.CDI,
        ExperienceLevel.MID,
        True,
        42000,
        52000,
        ["Figma", "Design System", "Accessibilité"],
        9,
    ),
    (
        "Administrateur Systèmes Linux",
        "CHU de Nantes",
        "Nantes, Pays de la Loire",
        ContractType.CDD,
        ExperienceLevel.MID,
        False,
        34000,
        42000,
        ["Linux", "Ansible", "Virtualisation"],
        12,
    ),
    (
        "Data Scientist",
        "BlaBlaCar",
        "Paris, Île-de-France",
        ContractType.CDI,
        ExperienceLevel.SENIOR,
        True,
        58000,
        75000,
        ["Python", "Machine Learning", "SQL"],
        3,
    ),
    (
        "Développeur mobile Flutter — Freelance",
        "Studio Nantais",
        "Remote, France",
        ContractType.FREELANCE,
        ExperienceLevel.MID,
        True,
        None,
        None,
        ["Flutter", "Dart", "Firebase"],
        4,
    ),
    (
        "Technicien de maintenance industrielle (H/F)",
        "Manitou Group",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.MID,
        False,
        30000,
        38000,
        ["Maintenance préventive", "Électromécanique", "GMAO"],
        2,
    ),
    (
        "Technicien maintenance SAV",
        "Armor Groupe",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.JUNIOR,
        False,
        27000,
        33000,
        ["Maintenance corrective", "Pneumatique", "Lecture de plans"],
        5,
    ),
    (
        "Responsable maintenance",
        "Manitou Group",
        "Nantes, Pays de la Loire",
        ContractType.CDI,
        ExperienceLevel.LEAD,
        False,
        42000,
        52000,
        ["Management d'équipe", "GMAO", "Amélioration continue"],
        6,
    ),
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


class DemoScraper(BaseScraper):
    """Renvoie des offres fictives filtrées approximativement par les critères."""

    name = "demo"
    base_url = "https://example.com"

    def _all_jobs(self) -> List[JobOffer]:
        now = datetime.now()
        jobs: List[JobOffer] = []
        for i, (
            title,
            company,
            location,
            contract,
            level,
            remote,
            sal_min,
            sal_max,
            skills,
            days_ago,
        ) in enumerate(_SAMPLE, 1):
            jobs.append(
                JobOffer(
                    id=f"demo_{i}",
                    source="demo",
                    url=f"https://example.com/offres/demo-{i}",
                    title=title,
                    company=company,
                    location=location,
                    description=(
                        f"Offre fictive de démonstration : {title} chez {company} "
                        f"({location}). Activez les vraies sources pour des résultats réels."
                    ),
                    salary_min=sal_min,
                    salary_max=sal_max,
                    contract_type=contract,
                    experience_level=level,
                    remote=remote,
                    posted_at=now - timedelta(days=days_ago),
                    skills=skills,
                )
            )
        return jobs

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        jobs = self._all_jobs()

        if criteria.keywords or criteria.title:
            terms = [_norm(k) for k in (criteria.keywords or [])]
            if criteria.title:
                terms.append(_norm(criteria.title))

            def _term_matches(term: str, job: JobOffer) -> bool:
                # Correspondance souple : la phrase exacte, ou tous ses mots
                # significatifs présents (ex. "technicien maintenance" trouve
                # "Technicien de maintenance industrielle").
                haystack = _norm(
                    " ".join(
                        [
                            job.title,
                            job.company or "",
                            job.description or "",
                            *job.skills,
                        ]
                    )
                )
                if term in haystack:
                    return True
                words = [w for w in term.split() if len(w) >= 3]
                return bool(words) and all(w in haystack for w in words)

            jobs = [
                j
                for j in jobs
                if any(_term_matches(t, j) for t in terms if t)
            ]

        location = _norm(criteria.location)
        if location and location not in {"france", "remote", "teletravail"}:
            jobs = [j for j in jobs if location in _norm(j.location)]

        if criteria.contract_types:
            jobs = [j for j in jobs if j.contract_type in criteria.contract_types]
        if criteria.experience_levels:
            jobs = [j for j in jobs if j.experience_level in criteria.experience_levels]

        for job in jobs[: criteria.max_results]:
            time.sleep(0.05)  # rend le streaming visible dans l'interface
            yield job

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        for job in self._all_jobs():
            if job.id == job_id or job.id.replace("demo_", "") == job_id:
                return job
        return None
