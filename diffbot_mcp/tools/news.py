from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, date_range, or_clause, subquery

DESCRIPTION = (
    "Searches news and articles in the Diffbot Knowledge Graph by mentioned company, person or product, topic, "
    "publisher, language, date range, or sentiment, and returns dated, sourced, linkable results, newest first. "
    "USE THIS for all news, including breaking and developing stories; the article index is continuously updated "
    "and search_web is the wrong tool for news. Rows are articles: coverage of an entity over time, sentiment "
    "trends, who said what. mentions is the strongest lever (tags.label); if it returns nothing, retry the same "
    "words as text. topic is looked up in the ArticleCategory taxonomy. Set facet for distribution questions such "
    "as which outlets cover an entity. Returns the DQL it ran; refine with dql when the shape is outside these "
    "parameters."
)

Sort = Literal["newest", "relevance", "oldest"]
Facet = Literal["siteName", "categories.name", "publisherCountry", "date"]


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
    sort: Optional[Sort] = None,
    facet: Optional[Facet] = None,
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

    if facet:
        clauses.append(f"facet:{facet}")
        return build(clauses), notes

    # newest first is the default, unless a date window already scopes recency, in
    # which case relevance ordering picks the best articles inside it
    if sort is None:
        sort = "relevance" if (since or until) else "newest"
    if sort == "newest":
        clauses.append("sortBy:date")
    elif sort == "oldest":
        clauses.append("revSortBy:date")
    return build(clauses), notes


@mcp.tool(name="search_news", description=DESCRIPTION)
async def search_news(
    mentions: Annotated[Optional[List[str]], "Entities the article must mention (company, person, product, place), OR-ed."] = None,
    topic: Annotated[Optional[str], "ArticleCategory value, e.g. 'Artificial Intelligence'. Free text is resolved; ambiguous text returns candidates."] = None,
    text: Annotated[Optional[str], "Full-text phrase match on the body; the fallback when no tag or category fits."] = None,
    title: Annotated[Optional[str], "Headline-only phrase match; much tighter than text."] = None,
    publisher: Annotated[Optional[str], "Publisher site name, e.g. 'Reuters'."] = None,
    language: Annotated[Optional[str], "ISO language code, e.g. 'en'."] = None,
    publisher_country: Annotated[Optional[str], "Publisher's country, full name, e.g. 'Norway'."] = None,
    quoted_speaker: Annotated[Optional[str], "Articles quoting this person, e.g. 'Sam Altman'."] = None,
    since: Annotated[Optional[str], "Earliest publication date, YYYY-MM-DD."] = None,
    until: Annotated[Optional[str], "Latest publication date, YYYY-MM-DD."] = None,
    sentiment_min: Annotated[Optional[float], "Minimum document sentiment, -1 to 1."] = None,
    sentiment_max: Annotated[Optional[float], "Maximum document sentiment, -1 to 1; e.g. -0.5 for negative coverage."] = None,
    mention_sentiment_max: Annotated[Optional[float], "Maximum sentiment toward the single entity in mentions, for negative coverage of X specifically."] = None,
    sort: Annotated[Optional[Sort], "Defaults to newest without a date range and relevance with one."] = None,
    facet: Annotated[Optional[Facet], "Aggregate into buckets instead of rows; size becomes the bucket count."] = None,
    size: Annotated[int, "Maximum number of articles (or buckets) to return."] = 10,
    offset: Annotated[int, "Number of articles to skip, for paging."] = 0,
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
        sort=sort, facet=facet,
    )
    notes.extend(build_notes)

    result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Article"])
    if result.get("hits") == 0 and mentions and not text:
        notes.append("No article carries that tag. Tag values are entity names that may not match; retry with the same words in text.")
    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
