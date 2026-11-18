"""Jarvis: Anexis as a plain chat in a terminal. No deck, no panels, no
commands to learn. Made for talking to the school server over SSH, or from
any terminal that can reach it.

    jarvis            (or: anexis jarvis)

Type and press Enter. Ctrl+C stops a reply. /new starts a fresh chat,
/clear deletes this one, /quit leaves (or Ctrl+D).
"""

from __future__ import annotations

import asyncio

import httpx
from rich.console import Console
from rich.markup import escape

from anexis.cli.client import AnexisClient
from anexis.cli.repl import INDENT, ChatSession

HELP = "type to talk · ctrl+c stops a reply · /new fresh chat · /clear delete this chat · /quit leave"


def greeting(health: dict) -> list[str]:
    sources = health.get("providers") or []
    model = f"{sources[0]} · {health.get('chat_models', {}).get(sources[0], '')}".strip(" ·") if sources else "no model set up"
    lines = [f"jarvis online   {model}   {health.get('memories', 0)} memories   control {health.get('control', 'ask')}"]
    lines += [f"due soon: {item}" for item in health.get("due", [])[:5]]
    return lines


async def run_jarvis(client: AnexisClient, console: Console | None = None) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout

    console = console or Console()
    prompt = PromptSession()

    async def yes_no(question: str) -> bool:
        return (await prompt.prompt_async(question)).strip().lower() in ("y", "yes")

    chat = ChatSession(client, console, yes_no)
    chat.name = "jarvis"
    health = await client.health()
    for line in greeting(health):
        console.print(f"[bold cyan]{INDENT}{escape(line)}[/bold cyan]" if line.startswith("jarvis") else f"[yellow]{INDENT}{escape(line)}[/yellow]", highlight=False)
    console.print(f"[dim]{INDENT}{HELP}[/dim]")

    while True:
        try:
            with patch_stdout():
                line = (await prompt.prompt_async("\n you   ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        word = line.lower()
        if word in ("/quit", "/exit", "/q", "exit", "quit"):
            break
        if word == "/new":
            chat.session_id = None
            console.print(f"[dim]{INDENT}fresh chat. I still remember you.[/dim]")
            continue
        if word == "/clear":
            if chat.session_id:
                await client.clear(chat.session_id)
            chat.session_id = None
            console.print(f"[dim]{INDENT}cleared. what I learned from it stays.[/dim]")
            continue
        if word in ("/help", "?"):
            console.print(f"[dim]{INDENT}{HELP}[/dim]")
            continue
        turn = asyncio.ensure_future(chat.send(line))
        try:
            await asyncio.shield(turn)
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Ctrl+C: stop the work on the server too, not just the printing.
            try:
                await client.stop(chat.session_id)
            except httpx.HTTPError:
                pass
            turn.cancel()
            me = asyncio.current_task()
            if me is not None and me.cancelling():
                me.uncancel()  # Ctrl+C stopped the reply, not Jarvis itself
            console.print(f"\n[dim]{INDENT}stopped[/dim]")
    console.print(f"[dim]{INDENT}later.[/dim]")
