"""Provider de recherche de personnes : API Apollo réelle, ou données démo.

Stratégie « gratuit d'abord » (voir docs/identification-interlocuteurs.md) :

- ``search_people`` utilise People API Search : **0 crédit**, mais résultats
  masqués (prénom, nom crypté, poste, entreprise — pas de lieu ni de LinkedIn) ;
- ``reveal_person`` appelle l'enrichissement (**1 crédit** si trouvé, sans
  demander le téléphone qui coûterait +8) pour obtenir nom complet, lieu,
  URL LinkedIn et e-mail éventuel.

Sans clé ``APOLLO_API_KEY``, le provider démo (``JOBSCRAPER_DEMO=1``) simule
exactement ce comportement avec des personnes fictives, pour développer et
présenter l'interface sans compte Apollo.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from loguru import logger

from jobscraper.models.prospecting import PersonCandidate
from jobscraper.services.search import demo_enabled

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"


class ApolloError(RuntimeError):
    """Échec d'un appel à l'API Apollo."""


@dataclass
class PeopleSearchResult:
    people: List[PersonCandidate] = field(default_factory=list)
    total_entries: int = 0


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _mask_last_name(last_name: str) -> str:
    """Reproduit le masque Apollo : « Durand » -> « Du***d »."""
    if len(last_name) <= 2:
        return last_name[0] + "***"
    return f"{last_name[:2]}***{last_name[-1]}"


def to_apollo_locations(location: str) -> List[str]:
    """Adapte la localisation libre de l'utilisateur au format Apollo.

    Apollo accepte villes et pays (pas les codes postaux français, pas de
    rayon) : « Paris » devient « Paris, France », « France » reste « France ».
    """
    location = (location or "France").strip()
    if not location or location.lower() == "france":
        return ["France"]
    if "," in location:
        return [location]
    return [f"{location}, France"]


# --------------------------------------------------------------------------- #
# Provider réel (API Apollo)
# --------------------------------------------------------------------------- #


class ApolloPeopleProvider:
    """Client minimal de l'API Apollo (recherche gratuite + révélation)."""

    name = "apollo"
    is_demo = False

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _post(self, path: str, params: Sequence[Tuple[str, object]]) -> Dict:
        try:
            response = requests.post(
                f"{APOLLO_BASE_URL}{path}",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "x-api-key": self.api_key,
                },
                params=list(params),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise ApolloError(f"Apollo a répondu HTTP {status} sur {path}") from exc
        except requests.RequestException as exc:
            raise ApolloError(f"Appel Apollo impossible ({path}) : {exc}") from exc

    def search_people(
        self,
        titles: Sequence[str],
        locations: Sequence[str],
        max_people: int = 100,
        verified_email_only: bool = False,
    ) -> PeopleSearchResult:
        """Recherche gratuite (0 crédit) paginée jusqu'à ``max_people`` profils."""
        people: List[PersonCandidate] = []
        total_entries = 0
        per_page = max(1, min(100, max_people))
        page = 1
        seen_ids: set = set()
        raw_fetched = 0

        while len(people) < max_people and page <= 500:
            params: List[Tuple[str, object]] = [
                ("per_page", per_page),
                ("page", page),
            ]
            params += [("person_titles[]", t) for t in titles if t.strip()]
            params += [("person_locations[]", loc) for loc in locations if loc.strip()]
            if verified_email_only:
                params.append(("contact_email_status[]", "verified"))

            data = self._post("/mixed_people/api_search", params)
            total_entries = int(data.get("total_entries") or 0)
            batch = data.get("people") or []
            if not batch:
                break
            raw_fetched += len(batch)

            new_on_page = 0
            for raw in batch:
                person = self._parse_search_person(raw)
                if person and person.id not in seen_ids:
                    seen_ids.add(person.id)
                    people.append(person)
                    new_on_page += 1

            # Arrêt si la page n'apporte rien de neuf ou si tout est récupéré.
            if new_on_page == 0:
                break
            if total_entries and raw_fetched >= total_entries:
                break
            page += 1

        logger.info(
            f"Apollo People Search : {len(people)} profils retournés "
            f"(total correspondant : {total_entries})"
        )
        return PeopleSearchResult(
            people=people[:max_people], total_entries=total_entries
        )

    def reveal_person(self, person_id: str) -> PersonCandidate:
        """Enrichissement (1 crédit si trouvé) : nom complet, lieu, LinkedIn."""
        data = self._post(
            "/people/match",
            [
                ("id", person_id),
                # Ne jamais demander le téléphone : +8 crédits, inutile ici.
                ("reveal_personal_emails", "false"),
                ("reveal_phone_number", "false"),
            ],
        )
        raw = data.get("person")
        if not raw:
            raise ApolloError("Apollo n'a pas retourné de profil pour cet identifiant.")
        return self._parse_enriched_person(raw, fallback_id=person_id)

    @staticmethod
    def _parse_search_person(raw: Dict) -> Optional[PersonCandidate]:
        person_id = raw.get("id")
        organization = raw.get("organization") or {}
        company = (organization.get("name") or "").strip()
        if not person_id or not company:
            return None

        first_name = (raw.get("first_name") or "").strip() or None
        last_obfuscated = (raw.get("last_name_obfuscated") or "").strip() or None
        display = (
            " ".join(p for p in [first_name, last_obfuscated] if p) or "Profil masqué"
        )

        return PersonCandidate(
            id=str(person_id),
            provider="Apollo",
            first_name=first_name,
            last_name_obfuscated=last_obfuscated,
            display_name=display,
            title=(raw.get("title") or "").strip() or None,
            company=company,
            has_email=bool(raw.get("has_email")),
            has_city=bool(raw.get("has_city")),
            revealed=False,
        )

    @staticmethod
    def _parse_enriched_person(raw: Dict, fallback_id: str) -> PersonCandidate:
        organization = raw.get("organization") or {}
        first_name = (raw.get("first_name") or "").strip()
        last_name = (raw.get("last_name") or "").strip()
        full_name = (raw.get("name") or "").strip() or " ".join(
            p for p in [first_name, last_name] if p
        )

        email = (raw.get("email") or "").strip() or None
        if email and email.startswith("email_not_unlocked@"):
            email = None  # Apollo masque ainsi les e-mails non débloqués

        location_parts = [
            (raw.get(key) or "").strip() for key in ("city", "state", "country")
        ]
        location = ", ".join(p for p in location_parts if p) or None

        return PersonCandidate(
            id=str(raw.get("id") or fallback_id),
            provider="Apollo",
            first_name=first_name or None,
            last_name_obfuscated=None,
            display_name=full_name or "Nom indisponible",
            title=(raw.get("title") or "").strip() or None,
            company=(organization.get("name") or "").strip() or "Entreprise inconnue",
            company_domain=(organization.get("primary_domain") or "").strip() or None,
            location=location,
            linkedin_url=(raw.get("linkedin_url") or "").strip() or None,
            email=email,
            has_email=bool(email),
            has_city=bool(location),
            revealed=True,
        )


# --------------------------------------------------------------------------- #
# Provider de démonstration (données fictives, aucun réseau)
# --------------------------------------------------------------------------- #

# (id, prénom, nom, poste, entreprise, ville, alias de recherche)
_DEMO_PEOPLE = [
    (
        "demo_p1",
        "Claire",
        "Bernard",
        "Développeuse Python Senior",
        "Capgemini",
        "Nantes",
        ["développeur python", "python developer", "développeuse python"],
    ),
    (
        "demo_p2",
        "Hugo",
        "Martin",
        "Lead Developer Python",
        "Akeneo",
        "Nantes",
        ["développeur python", "lead developer", "python"],
    ),
    (
        "demo_p3",
        "Léa",
        "Dubois",
        "Data Analyst",
        "Harmonie Mutuelle",
        "Nantes",
        ["data analyst", "analyste data", "data"],
    ),
    (
        "demo_p4",
        "Noah",
        "Laurent",
        "Développeur Python",
        "iAdvize",
        "Nantes",
        ["développeur python", "python developer"],
    ),
    (
        "demo_p5",
        "Emma",
        "Petit",
        "Talent Acquisition Manager",
        "Doctolib",
        "Paris",
        ["talent acquisition", "recruteur", "recrutement"],
    ),
    (
        "demo_p6",
        "Lucas",
        "Moreau",
        "Développeur Python",
        "Doctolib",
        "Paris",
        ["développeur python", "python developer"],
    ),
    (
        "demo_p7",
        "Chloé",
        "Leroy",
        "Data Scientist",
        "BlaBlaCar",
        "Paris",
        ["data scientist", "data"],
    ),
    (
        "demo_p8",
        "Ethan",
        "Roy",
        "Data Engineer",
        "Contentsquare",
        "Paris",
        ["data engineer", "ingénieur data", "data"],
    ),
    (
        "demo_p9",
        "Jade",
        "Fontaine",
        "Data Engineer",
        "Decathlon Digital",
        "Lille",
        ["data engineer", "ingénieur data"],
    ),
    (
        "demo_p10",
        "Louis",
        "Fabre",
        "Ingénieur Data",
        "OVHcloud",
        "Roubaix",
        ["ingénieur data", "data engineer", "devops"],
    ),
    (
        "demo_p11",
        "Manon",
        "Gauthier",
        "Chargée de recrutement",
        "Capgemini",
        "Nantes",
        ["chargé de recrutement", "recruteur", "recrutement"],
    ),
    (
        "demo_p12",
        "Nathan",
        "Rousseau",
        "DevOps / SRE",
        "OVHcloud",
        "Roubaix",
        ["devops", "sre"],
    ),
]


class DemoPeopleProvider:
    """Simule Apollo (masquage inclus) avec des personnes fictives."""

    name = "apollo-demo"
    is_demo = True

    def _matches(self, record, titles: Sequence[str], locations: Sequence[str]) -> bool:
        _id, _first, _last, title, _company, city, aliases = record

        wanted_cities = []
        for loc in locations:
            head = _norm(loc.split(",")[0])
            if head and head != "france":
                wanted_cities.append(head)
        if wanted_cities and _norm(city) not in wanted_cities:
            return False

        if not titles:
            return True
        haystacks = [_norm(title)] + [_norm(a) for a in aliases]
        for wanted in titles:
            w = _norm(wanted)
            if any(w in h or h in w for h in haystacks):
                return True
        return False

    def search_people(
        self,
        titles: Sequence[str],
        locations: Sequence[str],
        max_people: int = 100,
        verified_email_only: bool = False,
    ) -> PeopleSearchResult:
        matched = [r for r in _DEMO_PEOPLE if self._matches(r, titles, locations)]
        people = [
            PersonCandidate(
                id=r[0],
                provider="Apollo-demo",
                first_name=r[1],
                last_name_obfuscated=_mask_last_name(r[2]),
                display_name=f"{r[1]} {_mask_last_name(r[2])}",
                title=r[3],
                company=r[4],
                has_email=True,
                has_city=True,
                revealed=False,
            )
            for r in matched[:max_people]
        ]
        return PeopleSearchResult(people=people, total_entries=len(matched))

    def reveal_person(self, person_id: str) -> PersonCandidate:
        for r in _DEMO_PEOPLE:
            if r[0] == person_id:
                slug = _norm(f"{r[1]}-{r[2]}").replace(" ", "-")
                return PersonCandidate(
                    id=r[0],
                    provider="Apollo-demo",
                    first_name=r[1],
                    last_name_obfuscated=None,
                    display_name=f"{r[1]} {r[2]}",
                    title=r[3],
                    company=r[4],
                    company_domain=f"{_norm(r[4]).replace(' ', '')}.example",
                    location=f"{r[5]}, France",
                    linkedin_url=f"https://example.com/linkedin/{slug}",
                    email=f"{_norm(r[1])}.{_norm(r[2])}@{_norm(r[4]).replace(' ', '')}.example",
                    has_email=True,
                    has_city=True,
                    revealed=True,
                )
        raise ApolloError("Personne de démonstration introuvable.")


# --------------------------------------------------------------------------- #
# Sélection du provider
# --------------------------------------------------------------------------- #


def get_people_provider():
    """Retourne le provider actif : Apollo réel si clé, démo si activée, sinon None."""
    api_key = os.getenv("APOLLO_API_KEY", "").strip()
    if api_key:
        return ApolloPeopleProvider(api_key)
    if demo_enabled():
        return DemoPeopleProvider()
    return None


def provider_status() -> Dict:
    """État du provider de personnes pour l'API et l'interface."""
    provider = get_people_provider()
    if provider is None:
        return {
            "available": False,
            "provider": None,
            "demo": False,
            "reason": (
                "Apollo non configuré : définissez APOLLO_API_KEY dans .env "
                "(compte Apollo gratuit, e-mail professionnel requis), "
                "ou activez le mode démo avec JOBSCRAPER_DEMO=1."
            ),
        }
    return {
        "available": True,
        "provider": provider.name,
        "demo": provider.is_demo,
        "reason": None,
    }
