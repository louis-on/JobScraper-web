"""Scrapers pour les différents sites d'emploi."""

from jobscraper.scrapers.adzuna import AdzunaScraper
from jobscraper.scrapers.base import AsyncBaseScraper, BaseScraper
from jobscraper.scrapers.demo import DemoScraper
from jobscraper.scrapers.francetravail import FranceTravailScraper
from jobscraper.scrapers.hellowork import HelloWorkScraper
from jobscraper.scrapers.linkedin import LinkedInScraper
from jobscraper.scrapers.wttj import WTTJScraper

__all__ = [
    "AdzunaScraper",
    "AsyncBaseScraper",
    "BaseScraper",
    "DemoScraper",
    "FranceTravailScraper",
    "HelloWorkScraper",
    "LinkedInScraper",
    "WTTJScraper",
]
