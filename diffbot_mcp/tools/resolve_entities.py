from typing import Annotated, Optional

from ..api import request, resolve_token
from ..app import mcp

NLP_ENDPOINT = "https://nl.diffbot.com/v1/"

DESCRIPTION = (
    "Identifies the named entities (people, organizations, places, products) mentioned in a block of text and "
    "resolves each one to a Diffbot Knowledge Graph entity, with confidence (is this the right record?), salience "
    "(how central is it to the text?), and sentiment scores. Use for named entity recognition, to find which "
    "companies or people a document is actually about, or to turn unstructured text into canonical entity ids. "
    "The response includes dql_filter, an id:or(...) clause that can be pasted straight into dql, e.g. "
    "'type:Organization id:or(...)', to fetch the full records; id lookups bypass full-text search and are much "
    "faster than matching by name. Entities without an id were recognized but not matched to a KG record."
)


def entity_id(entity: dict) -> Optional[str]:
    uri = entity.get("id") or entity.get("diffbotUri") or ""
    return uri.rstrip("/").rsplit("/", 1)[-1] or None


@mcp.tool(name="resolve_entities", description=DESCRIPTION)
async def resolve_entities(
    text: Annotated[str, "The text to analyze. Plain text, not HTML or markdown."],
    lang: Annotated[Optional[str], "Optional. Language code of the text (e.g. 'en', 'es', 'fr'). Defaults to auto-detection. Set explicitly for better accuracy on non-English text."] = None,
) -> dict:
    params = {"token": resolve_token(), "fields": "entities,sentiment"}
    payload = [{"lang": lang or "auto", "format": "plain text", "content": text}]

    data = await request(NLP_ENDPOINT, method="POST", params=params, json_body=payload)
    # the NLP API answers with one result object per submitted document
    if isinstance(data, list):
        data = data[0] if data else {}

    entities = []
    for entity in data.get("entities", []):
        entities.append({
            "name": entity.get("name"),
            "types": [t.get("name") for t in entity.get("allTypes") or [] if t.get("name")],
            "confidence": entity.get("confidence"),
            "salience": entity.get("salience"),
            "sentiment": entity.get("sentiment"),
            "id": entity_id(entity),
            "mentions": len(entity.get("mentions") or []),
        })

    ids = [e["id"] for e in entities if e["id"]]
    return {
        "sentiment": data.get("sentiment"),
        "entities": entities,
        "dql_filter": "id:or(" + ",".join(f'"{i}"' for i in ids) + ")" if ids else None,
    }
