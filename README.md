# JobScraper

Agrégateur d'offres d'emploi en France. Recherchez simultanément sur LinkedIn, HelloWork, France Travail, Welcome to the Jungle et Adzuna (Indeed, Monster...).

## Fonctionnalités

- **5 sources d'emploi** : LinkedIn, HelloWork, France Travail, WTTJ, Adzuna
- **Recherche géolocalisée** : Filtrage par ville et rayon (5-100 km)
- **Filtres avancés** : Type de contrat, expérience, télétravail, date de publication
- **Export flexible** : JSON, CSV ou affichage tableau
- **CLI intuitive** : Interface en ligne de commande avec Rich

## Installation

```bash
# Cloner le repository
git clone https://github.com/zeffut/jobscraper.git
cd jobscraper

# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# ou .venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -e .
```

## Configuration

Copiez le fichier d'exemple et modifiez selon vos besoins :

```bash
cp .env.example .env
```

### Adzuna (optionnel)

Pour utiliser Adzuna (agrégateur Indeed, Monster, etc.), obtenez des clés API gratuites sur [developer.adzuna.com](https://developer.adzuna.com/) et ajoutez-les dans `.env` :

```env
ADZUNA_APP_ID=votre_app_id
ADZUNA_APP_KEY=votre_app_key
```

## Version web

Une interface web (API **FastAPI** + front **React/Vite**) partage le même
code métier que la CLI : sources interrogées **en parallèle**, erreurs isolées
par source, doublons inter-sources supprimés, résultats **streamés** dans le
navigateur au fil du scraping. Voir [`docs/migration-web.md`](docs/migration-web.md)
pour l'analyse et les choix d'architecture.

Les scrapers HTML passent par **curl_cffi** (empreinte TLS d'un vrai Chrome),
ce qui lève la plupart des blocages anti-robot des jobboards ; si le paquet
est absent, `requests` est utilisé en repli. **Source en panne ?** Ouvrez
<http://localhost:8000/api/sources/test> : chaque source y est testée par une
mini-recherche réelle et l'erreur technique exacte y est affichée (statut
HTTP, SSL, DNS…), sans le filtre « aimable » de l'interface.

```bash
# 1. Installer le backend
pip install -e ".[web]"

# 2. Compiler le front (une fois, ou après chaque modification du front)
npm --prefix frontend install
npm --prefix frontend run build

# 3. Lancer — interface : http://localhost:8000 , doc API : http://localhost:8000/docs
jobscraper-web
```

**Développement front** (rechargement à chaud, `/api` proxifié vers le backend) :

```bash
jobscraper-web                 # terminal 1 : API sur le port 8000
npm --prefix frontend run dev  # terminal 2 : front sur http://localhost:5173
```

**Avec Docker** (image unique front + API, déployable sur les offres Docker
gratuites type Hugging Face Spaces ou Render) :

```bash
docker compose up --build      # http://localhost:8000
```

**Mode démo** : `JOBSCRAPER_DEMO=1 jobscraper-web` ajoute une source « Démo »
à données fictives, pour travailler sur l'interface sans accès réseau.

### Recherche croisée « Annonces × Personnes » (Apollo)

L'onglet **« Entreprises »** de l'interface croise, pour un même métier et une
même localisation, les entreprises qui **recrutent** (les annonces ci-dessus)
et celles qui **emploient déjà** ce profil (recherche de personnes Apollo).
Résultats regroupés **par entreprise** : annonces à gauche, personnes à droite,
avec badge « Recrute + emploie déjà » pour les entreprises présentes des deux
côtés. Les deux recherches sont lancées en parallèle côté serveur.

- La recherche de personnes Apollo est **gratuite** (0 crédit) mais masquée :
  prénom, nom crypté, poste, entreprise. Le bouton **« Révéler »** d'un profil
  appelle l'enrichissement Apollo (**1 crédit** si trouvé, jamais le téléphone)
  pour obtenir nom complet, lieu et URL LinkedIn.
- Compte Apollo gratuit sur [apollo.io](https://www.apollo.io/) (inscription
  avec un **e-mail professionnel** obligatoire pour l'API, 75 crédits/mois),
  puis renseignez `APOLLO_API_KEY` dans `.env`.
- Sans clé, `JOBSCRAPER_DEMO=1` fournit des personnes fictives au même format
  (essayez : métier « Développeur Python », localisation « Paris »).
- Nuances : les variantes d'intitulé alimentent Apollo (OR) ; côté annonces,
  seul le métier principal est cherché par défaut (case à cocher pour étendre).
  Le rayon ne s'applique qu'aux annonces — Apollo filtre par ville/pays.
  Voir [`docs/identification-interlocuteurs.md`](docs/identification-interlocuteurs.md).

Endpoints correspondants : `POST /api/cross-search`, `POST /api/prospects/reveal`,
`GET /api/prospects/status` (détails dans `/docs`).

> ⚠️ Hébergé, votre serveur aura une IP de datacenter : certains sites
> (LinkedIn notamment) peuvent bloquer le scraping. Chaque source échoue
> alors indépendamment, sans casser les autres. Pensez à créer vos clés
> Adzuna et, à terme, à utiliser l'API officielle France Travail.

## Utilisation

### Recherche simple

```bash
# Recherche "python" à Paris
jobscraper search -k python -l Paris

# Recherche "data engineer" en CDI
jobscraper search -k "data engineer" -c cdi

# Recherche avec rayon de 25km autour de Lyon
jobscraper search -k développeur -l Lyon -r 25
```

### Options de recherche

```bash
jobscraper search [OPTIONS]

Options:
  -k, --keywords TEXT       Mots-clés de recherche (peut être répété)
  -t, --title TEXT          Titre de poste exact
  -l, --location TEXT       Localisation (ville, région) [défaut: France]
  -r, --radius [5|10|25|50|100]  Rayon de recherche en km
  -c, --contract [cdi|cdd|stage|alternance|interim|freelance]  Type de contrat
  -e, --experience [internship|junior|mid|senior|lead|director]  Niveau d'expérience
  -w, --workplace [on_site|remote|hybrid]  Type de lieu de travail
  --date [past_24h|past_week|past_month|any_time]  Date de publication
  --sort [relevance|date]   Tri des résultats
  -n, --max-results INT     Nombre maximum de résultats [défaut: 50]
  -s, --source [linkedin|hellowork|francetravail|adzuna|wttj|all]  Sources
  -o, --output PATH         Fichier de sortie
  --format [json|csv|table] Format de sortie [défaut: table]
  -d, --details             Récupérer les détails complets
```

### Exemples avancés

```bash
# CDI senior en remote, export JSON
jobscraper search -k "data engineer" -c cdi -e senior -w remote -o jobs.json

# Recherche sur WTTJ uniquement
jobscraper search -k python -l Paris -s wttj

# Recherche sur toutes les sources
jobscraper search -k développeur -l Toulouse -s all

# Offres des 7 derniers jours, triées par date
jobscraper search -k devops --date past_week --sort date

# 100 résultats avec détails complets
jobscraper search -k react -n 100 --details -o react_jobs.json
```

### Lister les sources

```bash
jobscraper sources
```

## Sources supportées

| Source | Statut | Description |
|--------|--------|-------------|
| LinkedIn | Actif | Offres d'emploi LinkedIn |
| HelloWork | Actif | Portail d'emploi français |
| France Travail | Actif | Ex Pôle Emploi |
| WTTJ | Actif | Welcome to the Jungle (startups) |
| Adzuna | Actif* | Agrégateur (Indeed, Monster...) |

\* Nécessite des clés API gratuites

## Structure du projet

```
jobscraper/
├── src/jobscraper/
│   ├── cli.py              # Interface ligne de commande
│   ├── config.py           # Configuration
│   ├── models/
│   │   └── job.py          # Modèles de données
│   ├── scrapers/
│   │   ├── base.py         # Classe de base
│   │   ├── linkedin.py     # Scraper LinkedIn
│   │   ├── hellowork.py    # Scraper HelloWork
│   │   ├── francetravail.py # Scraper France Travail
│   │   ├── wttj.py         # Scraper WTTJ (Algolia)
│   │   ├── adzuna.py       # Client API Adzuna
│   │   └── demo.py         # Données fictives (JOBSCRAPER_DEMO=1)
│   ├── services/
│   │   └── search.py       # Orchestration partagée CLI+web (parallèle, cache, dédup)
│   ├── web/
│   │   ├── app.py          # API FastAPI (+ front compilé servi à la racine)
│   │   └── schemas.py      # Schémas d'API
│   └── utils/
│       └── geocoding.py    # Géocodage pour recherche par rayon
├── frontend/               # Interface React + Vite (npm run build -> dist/)
├── docs/migration-web.md   # Analyse et choix d'architecture web
├── Dockerfile              # Image unique front + API
├── .env.example            # Template de configuration
├── pyproject.toml          # Configuration du projet
└── requirements.txt        # Dépendances
```

## Développement

```bash
# Installer les dépendances de développement
pip install -e ".[dev]"

# Lancer les tests
pytest

# Formater le code
black src/
isort src/
```

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.
