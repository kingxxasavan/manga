"""Tools that ship inside Anexis. Outside tools come through MCP (see mcp_client.py)."""

from anexis.tools.builtin import canvas, core, desktop, system, web
from anexis.tools.registry import Registry


def register_builtin(registry: Registry, settings=None) -> None:
    for module in (core, system, web):
        for tool in module.TOOLS:
            registry.add(tool)
    for tool in desktop.tools():
        registry.add(tool)
    # The Canvas tools are always there. Before the owner signs in to Canvas
    # they answer "sign in from Keys", which is far better than the model
    # hunting for the school's login page on the web on its own.
    for tool in canvas.TOOLS:
        registry.add(tool)
