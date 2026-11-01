"""Clientes de Semantic Scholar, Crossref y OpenAlex. Viven en labels.py."""

from rrm.search.labels import fetch_crossref, fetch_openalex, fetch_s2, parse_s2

__all__ = ["fetch_crossref", "fetch_openalex", "fetch_s2", "parse_s2"]
