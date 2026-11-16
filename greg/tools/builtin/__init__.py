"""Tools that ship inside Greg. Outside tools come through MCP (see mcp_client.py)."""

from greg.tools.builtin import core, system, web
from greg.tools.registry import Registry


def register_builtin(registry: Registry) -> None:
    for module in (core, system, web):
        for tool in module.TOOLS:
            registry.add(tool)
