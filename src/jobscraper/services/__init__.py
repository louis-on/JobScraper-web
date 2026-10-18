"""Services métier partagés entre la CLI et l'interface web."""

from jobscraper.services.search import (
    SearchOutcome,
    get_sources,
    resolve_sources,
    search_all,
)

__all__ = ["SearchOutcome", "get_sources", "resolve_sources", "search_all"]
