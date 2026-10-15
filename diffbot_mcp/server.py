"""Composition root: importing the tool modules registers them."""

from .app import mcp
from .schema import SlimSchemas
from .tools import (  # noqa: F401  (imported for their registration side effects)
    crawl,
    deals,
    dql,
    dql_ontology,
    dql_probe,
    extract,
    news,
    organizations,
    people,
    places,
    resolve_entities,
    search_web,
)

mcp.add_middleware(SlimSchemas())

__all__ = ["mcp"]
