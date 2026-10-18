"""Application web JobScraper : API FastAPI + front React compilé.

Lancement en développement ::

    pip install -e ".[web]"
    jobscraper-web            # http://localhost:8000 (doc API : /docs)

Endpoints :

- ``GET  /api/health``         — état du service
- ``GET  /api/sources``        — sources connues et leur disponibilité
- ``POST /api/search``         — recherche agrégée (parallèle, cache court)
- ``GET  /api/search/stream``  — même recherche en streaming SSE : les offres
  arrivent source par source, sans attendre la fin du scraping

Si le front est compilé (``frontend/dist``), il est servi à la racine :
une seule application à déployer pour l'API et l'interface.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from jobscraper import __version__
from jobscraper.models.job import (
    ContractType,
    DatePosted,
    ExperienceLevel,
    SearchCriteria,
    SortBy,
    WorkplaceType,
)
from jobscraper.services import search as search_service
from jobscraper.web.schemas import HealthResponse, SearchRequest, SearchResponse


def _frontend_dist() -> Optional[Path]:
    """Localise le front compilé (variable d'env. prioritaire, sinon dépôt)."""
    env = os.getenv("JOBSCRAPER_FRONTEND_DIST")
    if env:
        path = Path(env)
        return path if (path / "index.html").exists() else None
    # src/jobscraper/web/app.py -> racine du dépôt -> frontend/dist
    path = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return path if (path / "index.html").exists() else None


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobScraper",
        description="Agrégateur d'offres d'emploi en France (LinkedIn, HelloWork, "
        "France Travail, Welcome to the Jungle, Adzuna).",
        version=__version__,
    )

    # Usage personnel / développement : le front de dev (Vite) tourne sur un
    # autre port. Restreindre cette liste avant toute exposition publique.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(
            version=__version__,
            demo=search_service.demo_enabled(),
            sources=[s.id for s in search_service.get_sources()],
        )

    @app.get(
        "/api/sources", response_model=List[search_service.SourceInfo], tags=["meta"]
    )
    def sources() -> List[search_service.SourceInfo]:
        return search_service.get_sources()

    @app.post("/api/search", response_model=SearchResponse, tags=["search"])
    def search(request: SearchRequest) -> SearchResponse:
        try:
            resolved = search_service.resolve_sources(request.sources)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        outcome = search_service.search_all(
            request.to_criteria(), resolved, use_cache=request.use_cache
        )
        return SearchResponse(
            jobs=outcome.jobs,
            total=len(outcome.jobs),
            counts=outcome.counts,
            errors=outcome.errors,
            duration_ms=outcome.duration_ms,
            cached=outcome.cached,
        )

    @app.get("/api/search/stream", tags=["search"])
    def search_stream(
        keywords: List[str] = Query(default_factory=list),
        title: Optional[str] = None,
        location: str = "France",
        radius_km: Optional[int] = None,
        contract_types: List[ContractType] = Query(default_factory=list),
        experience_levels: List[ExperienceLevel] = Query(default_factory=list),
        workplace_types: List[WorkplaceType] = Query(default_factory=list),
        date_posted: Optional[DatePosted] = None,
        sort_by: SortBy = SortBy.RELEVANCE,
        max_results: int = 50,
        sources_param: str = Query(default="all", alias="sources"),
    ) -> StreamingResponse:
        """Recherche en Server-Sent Events.

        Événements émis : ``start``, ``job``, ``source_done``,
        ``source_error``, ``done`` (compteurs, erreurs, durée).
        """
        try:
            resolved = search_service.resolve_sources(
                [s for s in sources_param.split(",") if s.strip()]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        criteria = SearchCriteria(
            keywords=keywords,
            title=title,
            location=location,
            radius_km=radius_km,
            contract_types=contract_types,
            experience_levels=experience_levels,
            workplace_types=workplace_types,
            date_posted=date_posted,
            sort_by=sort_by,
            max_results=max_results,
        )

        def event_stream():
            started = time.monotonic()
            counts = {s: 0 for s in resolved}
            errors = {}
            total = 0
            yield _sse("start", {"sources": resolved})
            for event in search_service.iter_search_events(criteria, resolved):
                if event.type == "job" and event.job is not None:
                    total += 1
                    counts[event.source] = counts.get(event.source, 0) + 1
                    yield _sse("job", {"job": event.job.model_dump(mode="json")})
                elif event.type == "source_done":
                    yield _sse(
                        "source_done",
                        {"source": event.source, "count": counts.get(event.source, 0)},
                    )
                elif event.type == "source_error":
                    errors[event.source] = event.error or "Erreur inconnue"
                    yield _sse(
                        "source_error",
                        {"source": event.source, "error": errors[event.source]},
                    )
            yield _sse(
                "done",
                {
                    "total": total,
                    "counts": counts,
                    "errors": errors,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    dist = _frontend_dist()
    if dist is not None:
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
        logger.info(f"Front compilé servi depuis {dist}")
    else:
        logger.info(
            "Front non compilé (frontend/dist absent) : API seule. "
            "Lancez `npm --prefix frontend run build` pour servir l'interface."
        )

    return app


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


app = create_app()


def run() -> None:
    """Point d'entrée de la commande ``jobscraper-web``."""
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"JobScraper web sur http://{host}:{port} (doc API : /docs)")
    uvicorn.run("jobscraper.web.app:app", host=host, port=port)


if __name__ == "__main__":
    run()
