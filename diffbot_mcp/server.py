"""Composition root: importing the tool modules registers them, and the prompt bodies are loaded from disk."""

import pathlib

from .app import mcp
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

PROMPT_DIR = pathlib.Path(__file__).parent / "prompts"

# One prompt per diffbot-skills skill. Names are bare because MCP prompts are already
# namespaced by server; the skills carry a diffbot- prefix only for the flat plugin namespace.
PROMPTS = [
    ("news", "Search news and articles in the Diffbot Knowledge Graph by mentioned company, person, topic, publisher, language, date range, or sentiment. The workflow for all news, including breaking and developing stories."),
    ("organizations", "Search companies in the Diffbot Knowledge Graph by industry, headquarters, headcount, revenue, funding, ownership, or leadership, plus lookalike lists. The workflow when the answer is a list of companies."),
    ("people", "Search people in the Diffbot Knowledge Graph by job title, employer, employer industry, skills, education, location, or nationality. The workflow when the answer is a list of people; covers public professional presence only."),
    ("places", "Search cities, counties, states, countries, and points of interest in the Diffbot Knowledge Graph by population, prominence, containing place, or proximity."),
    ("deals", "Search funding rounds, investments, and acquisitions in the Diffbot Knowledge Graph by date, size, series, investor, acquirer, or industry. The workflow when the answer is a list of deals."),
    ("dql", "Query the Diffbot Knowledge Graph directly with DQL: operators, field lookup, probing, and export for any entity type or query shape the typed tools do not cover."),
    ("web-search", "Search the web with ranked, scored, dated results, and read a known URL from Diffbot's index before reaching for a live fetch."),
    ("extract", "Extract markdown or structured content from a URL with a live fetch, and when to prefer the index lookup instead."),
    ("entities", "Identify and resolve named entities in text to Diffbot Knowledge Graph records, then use their ids in DQL."),
    ("crawl", "Crawl a website for structured content and manage crawler jobs."),
]


def _register_prompt(name: str, description: str) -> None:
    body = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()

    def prompt(request: str = "") -> str:
        if request:
            return f"{body}\n\n---\n\nUser request: {request}"
        return body

    prompt.__name__ = name.replace("-", "_")
    prompt.__doc__ = description
    mcp.prompt(name=name, description=description)(prompt)


for _name, _description in PROMPTS:
    _register_prompt(_name, _description)

__all__ = ["mcp"]
