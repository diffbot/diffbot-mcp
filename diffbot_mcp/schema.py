"""Slims tool schemas on the way out of tools/list.

Pydantic renders every Optional parameter as anyOf:[{type:X},{type:null}] with default:null, roughly
55 bytes of structure per parameter that tells the model nothing it does not already know from the
parameter being optional. Collapsing it is the largest single saving on the always-on schema cost.
Validation of incoming arguments still runs against the function signature, so None stays accepted.
"""

from typing import Any, Sequence

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool


def slim(node: Any) -> Any:
    if isinstance(node, list):
        return [slim(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: slim(value) for key, value in node.items() if not (key == "default" and value is None)}
    options = node.get("anyOf")
    if isinstance(options, list):
        non_null = [option for option in options if option != {"type": "null"}]
        if len(non_null) == 1 and len(non_null) < len(options):
            merged = dict(non_null[0])
            merged.update({key: value for key, value in node.items() if key != "anyOf"})
            return merged
    return node


class SlimSchemas(Middleware):
    async def on_list_tools(self, context: MiddlewareContext, call_next: CallNext) -> Sequence[Tool]:
        tools = await call_next(context)
        return [tool.model_copy(update={"parameters": slim(tool.parameters)}) for tool in tools]
