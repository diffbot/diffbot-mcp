from typing import Annotated, List, Optional

from fastmcp.exceptions import ToolError

from ..app import READ_ONLY, mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, date_range, or_clause, subquery

DESCRIPTION = (
    "News and article structured search over the Diffbot Knowledge Graph. Prefer for highly relevant results on "
    "named entities or uncommon keywords. Filter by mentioned organization/person/brand/product, topic, publisher, "
    "language, country, date range, or sentiment. Results are chronological newest first, with no semantic "
    "reranking. Prefer over a generic web search for any news, including breaking stories. mentions is the "
    "strongest signal filter; if it returns nothing, retry the same words as text."
    " API docs: https://www.diffbot.com/docs/dql/"
)


def build_news_query(
    *,
    mentions: Optional[List[str]] = None,
    topic: Optional[str] = None,
    text: Optional[str] = None,
    title: Optional[str] = None,
    publisher: Optional[str] = None,
    language: Optional[str] = None,
    publisher_country: Optional[str] = None,
    quoted_speaker: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    sentiment_min: Optional[float] = None,
    sentiment_max: Optional[float] = None,
    mention_sentiment_max: Optional[float] = None,
) -> tuple:
    """Return (dql, notes). topic must already be an exact ArticleCategory value."""
    clauses = ["type:Article"]
    notes: List[str] = []

    if mentions:
        if mention_sentiment_max is not None and len(mentions) == 1:
            # per-entity sentiment lives on the tag, so co-constrain label and score on one tag
            clauses.append(subquery("tags", [clause("label", mentions[0]), compare("sentiment", "<", mention_sentiment_max)]))
        else:
            clauses.append(or_clause("tags.label", mentions))
            if mention_sentiment_max is not None:
                notes.append("mention_sentiment_max applies only with exactly one mention and was ignored; use sentiment_max for the document-level score.")
    elif mention_sentiment_max is not None:
        notes.append("mention_sentiment_max needs a mention and was ignored.")

    if topic:
        clauses.append(clause("categories.name", topic))
    if text:
        clauses.append(clause("text", text))
    if title:
        clauses.append(clause("title", title))
    if publisher:
        clauses.append(clause("siteName", publisher))
    if language:
        clauses.append(clause("language", language))
    if publisher_country:
        clauses.append(clause("publisherCountry", publisher_country))
    if quoted_speaker:
        clauses.append(clause("quotes.speaker", quoted_speaker))
    clauses.extend(date_range("date", since, until))
    if sentiment_min is not None:
        clauses.append(compare("sentiment", ">=", sentiment_min))
    if sentiment_max is not None:
        clauses.append(compare("sentiment", "<=", sentiment_max))

    if len(clauses) == 1:
        raise ToolError("search_news needs at least one narrowing parameter (mentions, topic, text, title, publisher, quoted_speaker, or a date range); an unfiltered article query times out.")

    clauses.append("sortBy:date")
    return build(clauses), notes


@mcp.tool(name="search_news", title="Search News", description=DESCRIPTION, annotations=READ_ONLY)
async def search_news(
    mentions: Annotated[Optional[List[str]], "Organizations, people, brand, product or entities the article must mention (OR)"] = None,
    topic: Annotated[Optional[str], "Topic category; free text ok"] = None,
    text: Annotated[Optional[str], "Phrase in article body. Use for uncommon phrases or as a fallback to mentions"] = None,
    title: Annotated[Optional[str], "Phrase in the headline"] = None,
    publisher: Annotated[Optional[str], "Publisher site, e.g. Reuters"] = None,
    language: Annotated[Optional[str], "ISO code, e.g. en"] = None,
    publisher_country: Annotated[Optional[str], "Publisher's country, e.g. United States"] = None,
    quoted_speaker: Annotated[Optional[str], "Person quoted in the article"] = None,
    since: Annotated[Optional[str], "Earliest date, YYYY-MM-DD"] = None,
    until: Annotated[Optional[str], "Latest date, YYYY-MM-DD"] = None,
    sentiment_min: Annotated[Optional[float], "Document sentiment floor, -1..1"] = None,
    sentiment_max: Annotated[Optional[float], "Document sentiment ceiling, -1..1"] = None,
    mention_sentiment_max: Annotated[Optional[float], "Sentiment ceiling toward the one mention"] = None,
    size: Annotated[int, "Max rows"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
) -> dict:
    notes: List[str] = []
    if topic:
        resolved = await resolve_value("ArticleCategory", topic)
        if resolved.value is None:
            if resolved.candidates:
                return {"dql": None, "candidates": {"topic": resolved.candidates}, "notes": [resolved.note]}
            notes.append(f"{resolved.note}; searched the article text for '{topic}' instead.")
            text = f"{text} {topic}".strip() if text else topic
            topic = None
        else:
            topic = resolved.value
            if resolved.note:
                notes.append(resolved.note)

    query, build_notes = build_news_query(
        mentions=mentions, topic=topic, text=text, title=title, publisher=publisher, language=language,
        publisher_country=publisher_country, quoted_speaker=quoted_speaker, since=since, until=until,
        sentiment_min=sentiment_min, sentiment_max=sentiment_max, mention_sentiment_max=mention_sentiment_max,
    )
    notes.extend(build_notes)

    result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Article"])
    if result.get("hits") == 0 and mentions and not text:
        notes.append("No article carries that tag. Tag values are entity names that may not match; retry with the same words in text.")
    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
