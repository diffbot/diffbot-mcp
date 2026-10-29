"""Composition root: importing the tool modules registers them."""

from .app import mcp
from .schema import SlimSchemas
from .tools import (  # noqa: F401  (imported for their registration side effects)
    extract,
    search_web,
    news,
    organizations,
    people,
    places,
    deals,
    crawl,
    resolve_entities,
    dql,
    dql_ontology,
    dql_probe,
)

mcp.add_middleware(SlimSchemas())

__all__ = ["mcp"]
