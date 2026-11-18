from typing import Annotated, Optional

from ..api import diffbot
from ..app import READ_ONLY, mcp

DESCRIPTION = (
    "Named entity recognition and linking. Finds people, organizations, places, and products mentioned in text. "
    "Each resolves to a Diffbot Knowledge Graph entity with confidence, salience, and sentiment. Prefer for "
    "post-processing plain text for entity mentions. The response includes dql_filter, an id:or(...) clause for "
    "dql to fetch the full records. Entities without an id were recognized but not matched."
    " API docs: https://www.diffbot.com/docs/natural-language/"
)


def entity_id(entity: dict) -> Optional[str]:
    uri = entity.get("id") or entity.get("diffbotUri") or ""
    return uri.rstrip("/").rsplit("/", 1)[-1] or None


@mcp.tool(name="resolve_entities", title="Resolve Entities", description=DESCRIPTION, annotations=READ_ONLY)
async def resolve_entities(
    text: Annotated[str, "Plain text to analyze"],
    lang: Annotated[Optional[str], "ISO code, e.g. en; default auto"] = None,
) -> dict:
    # fields=entities,sentiment; the SDK unwraps the one-document batch
    async with diffbot() as db:
        data = await db.entities(text, lang=lang or "auto")

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
