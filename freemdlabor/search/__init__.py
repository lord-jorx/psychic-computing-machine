from .clinicaltrials import search_clinicaltrials
from .crossref import resolve_doi, search_crossref
from .europepmc import search_europepmc
from .openalex import search_openalex
from .pubmed import search_pubmed

SOURCES = {
    "pubmed": search_pubmed,
    "europepmc": search_europepmc,
    "crossref": search_crossref,
    "clinicaltrials": search_clinicaltrials,
    "openalex": search_openalex,
}

__all__ = [
    "search_pubmed",
    "search_europepmc",
    "search_crossref",
    "search_clinicaltrials",
    "search_openalex",
    "resolve_doi",
    "SOURCES",
]
