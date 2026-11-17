"""Tools that ship inside Anexis. Outside tools come through MCP (see mcp_client.py)."""

from anexis.tools.builtin import core, desktop, system, web
from anexis.tools.registry import Registry


def register_builtin(registry: Registry) -> None:
    for module in (core, system, web):
        for tool in module.TOOLS:
            registry.add(tool)
    for tool in desktop.tools():
        registry.add(tool)
