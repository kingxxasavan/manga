"""The `greg` command."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time

import httpx
from rich.console import Console

from greg.cli.client import GregClient
from greg.config import LOOPBACK, Settings, load_settings

console = Console()


def _client(settings: Settings) -> GregClient:
    url = settings.env.get("GREG_URL") or settings.url
    return GregClient(url, settings.token)


async def _up(client: GregClient) -> bool:
    try:
        await client.health()
        return True
    except httpx.HTTPStatusError:
        raise
    except (httpx.HTTPError, OSError):
        return False


async def ensure_server(settings: Settings) -> GregClient:
    """The server if it is running. On this machine it is started when it is not."""
    client = _client(settings)
    try:
        if await _up(client):
            return client
    except httpx.HTTPStatusError as e:
        sys.exit(f"The server refused the connection ({e.response.status_code}). Check GREG_TOKEN.")
    if settings.env.get("GREG_URL") or settings.host not in LOOPBACK | {"0.0.0.0"}:
        sys.exit(f"Cannot reach the Greg server at {client.url}. Start it there with `greg serve`.")

    settings.home.mkdir(parents=True, exist_ok=True)
    # Detached on purpose: the server keeps running after this chat window closes.
    with open(settings.home / "server.log", "a") as log:
        subprocess.Popen(  # noqa: ASYNC220
            [sys.executable, "-m", "greg", "serve"], stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    console.print("[dim] starting the server...[/dim]")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        if await _up(client):
            return client
    sys.exit(f"The server did not come up. See {settings.home / 'server.log'}")


def cmd_serve(settings: Settings, args) -> None:
    import uvicorn

    from greg.core.app import GregApp
    from greg.server.app import create_app

    problems = settings.problems()
    if problems:
        sys.exit("Cannot start:\n" + "\n".join(f"  {p}" for p in problems))
    uvicorn.run(create_app(GregApp(settings)), host=settings.host, port=settings.port, log_level="warning")


async def cmd_chat(settings: Settings, args) -> None:
    from greg.cli.repl import run_repl

    await run_repl(await ensure_server(settings))


async def cmd_ask(settings: Settings, args) -> None:
    """One question, one answer, for scripts. Nothing that needs a yes can run here."""
    from greg.cli.repl import ChatSession

    async def no(question: str) -> bool:
        console.print(f"{question}no (use the chat to approve things)", markup=False, highlight=False)
        return False

    chat = ChatSession(await ensure_server(settings), console, no)
    await chat.send(" ".join(args.text))
    console.print()


async def cmd_doctor(settings: Settings, args) -> None:
    from greg.cli.repl import show_doctor

    client = await ensure_server(settings)
    for _ in range(120):  # give tool servers time to finish their first start
        if not (await client.health()).get("tool_servers_starting"):
            break
        await asyncio.sleep(1)
    if not show_doctor(console, await client.doctor()):
        sys.exit(1)


async def cmd_aboutme(settings: Settings, args) -> None:
    from greg.cli.repl import ChatSession
    from greg.profile.about import load_profile_file

    client = await ensure_server(settings)
    if args.action == "import":
        if not args.file:
            sys.exit("Usage: greg aboutme import <file.yaml>")
        report = await client.set_about(load_profile_file(args.file))
        console.print(f" About Me updated: {report['added']} new, {report['changed']} changed, "
                      f"{report['same']} the same, {report['removed']} removed.")
    elif args.action == "show":
        import yaml

        console.print(yaml.safe_dump(await client.about(), sort_keys=False, allow_unicode=True) or "(empty)", highlight=False)
    else:
        from prompt_toolkit import PromptSession

        prompt = PromptSession()

        async def ask_line(question: str, default: str) -> str:
            return await prompt.prompt_async(question, default=default)

        async def no(question: str) -> bool:
            return False

        await ChatSession(client, console, no, ask_line).about_me()


async def cmd_tools(settings: Settings, args) -> None:
    """`greg tools sync` downloads every usable tool server and checks it starts."""
    from greg.tools.mcp_client import MCPManager, load_manifest
    from greg.tools.registry import Registry

    if args.action == "list":
        for spec in load_manifest(settings):
            console.print(f" {spec.name:<10} {spec.state(settings):<10} {spec.about}", highlight=False)
        return
    settings.workspace.mkdir(parents=True, exist_ok=True)
    registry = Registry()
    manager = MCPManager(settings, registry, start_timeout=600)
    console.print("[dim] downloading and starting tool servers, the first time takes a few minutes...[/dim]")
    await manager.start()
    failed = 0
    for name, info in manager.status.items():
        state = info["state"]
        if state == "running":
            console.print(f" [green]ok  [/green] {name:<10} {info['tools']} tools", highlight=False)
        elif state == "failed":
            failed += 1
            console.print(f" [red]FAIL[/red] {name:<10} {info.get('error', '')}", highlight=False)
        else:
            why = "add " + ", ".join(info["needs"]) + " to .env" if state == "needs key" else "off in manifest"
            console.print(f" [dim]off  {name:<10} {why}[/dim]", highlight=False)
    console.print(f"\n {len(registry)} tools from {sum(1 for i in manager.status.values() if i['state'] == 'running')} servers.")
    await manager.stop()
    if failed:
        sys.exit(1)


async def cmd_train(settings: Settings, args) -> None:
    """Talk to Greg the way its owner talks, then check what stuck."""
    import shutil
    import tempfile
    from pathlib import Path

    from rich.markup import escape

    from greg.config import REPO_ROOT
    from greg.core.app import GregApp
    from greg.core.train import OfflineRouter, load_pack, practice_settings, run_training

    if args.keep and args.offline:
        sys.exit("--keep needs a real model, so it cannot be used with --offline.")
    try:
        pack = load_pack(Path(args.pack) if args.pack else REPO_ROOT / "training" / "like_me.yaml")
    except (OSError, ValueError) as e:
        sys.exit(f"Could not read the training pack: {e}")

    scratch = None if args.keep else tempfile.mkdtemp(prefix="greg-train-")
    target = settings if args.keep else practice_settings(settings, Path(scratch))
    greg = GregApp(target, router=OfflineRouter(pack) if args.offline else None)
    kind = "for keeps, into the real memory" if args.keep else "practice, on a throwaway memory"
    model = "no model (offline stand in)" if args.offline else " + ".join(p.name for p in greg.router.providers) or "no model"
    console.print(f"\n[bold] training run[/bold]   {kind}   {escape(model)}\n", highlight=False)
    try:
        report = await run_training(
            greg, pack, keep=args.keep,
            say=lambda line: console.print(f"[dim] {escape(line)}[/dim]", highlight=False),
        )
    finally:
        await greg.stop()
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    names = {"learned": "learned from what was said", "reinforced": "got more sure when repeated",
             "replaced": "updated when something changed", "recall": "recalled later from a sloppy question",
             "prompt": "standing instructions reach the model", "tools": "right tool offered"}
    for group, (done, total) in report.counts().items():
        console.print(f"\n [bold]{names[group]}[/bold]   {done} of {total}", highlight=False)
        for c in (c for c in report.checks if c.group == group):
            mark = "[green]ok  [/green]" if c.ok else "[red]MISS[/red]"
            console.print(f"  {mark} {escape(c.label)}  [dim]{escape(c.detail)}[/dim]", highlight=False)
    if report.style:
        console.print("\n [bold]how it reads you[/bold]", highlight=False)
        for line in report.style:
            console.print(f"  [dim]{escape(line)}[/dim]", highlight=False)
    for error in dict.fromkeys(report.errors):
        console.print(f"\n [red]{escape(error)}[/red]", highlight=False)
    done, total = report.score()
    console.print(f"\n [bold]score {done} of {total}[/bold]", highlight=False)
    if args.offline:
        console.print("[dim] Offline run: this checked everything around the model, not the model itself.[/dim]")
    elif not args.keep:
        console.print("[dim] Nothing was kept. Happy with it? Run `greg train --keep`.[/dim]")
    if report.failures():
        sys.exit(1)


async def cmd_memory(settings: Settings, args) -> None:
    client = await ensure_server(settings)
    for m in await client.memories(" ".join(args.query)):
        console.print(f" #{m['id']:<4} {m['kind']:<10} {m['text']}", highlight=False, markup=False)


def cmd_mcp(settings: Settings, args) -> None:
    from greg.mcp_server import build_server

    build_server(settings).run("stdio")


def main() -> None:
    parser = argparse.ArgumentParser(prog="greg", description="Your personal assistant. Run with no arguments to chat.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (the chat starts it for you on this machine)")
    ask = sub.add_parser("ask", help="one question, one answer")
    ask.add_argument("text", nargs="+")
    sub.add_parser("doctor", help="check that every part works")
    about = sub.add_parser("aboutme", help="tell Greg about yourself")
    about.add_argument("action", nargs="?", choices=["import", "show"])
    about.add_argument("file", nargs="?")
    tools = sub.add_parser("tools", help="outside tool servers")
    tools.add_argument("action", choices=["sync", "list"])
    memory = sub.add_parser("memory", help="list or search what Greg remembers")
    memory.add_argument("query", nargs="*")
    train = sub.add_parser("train", help="talk to Greg your way and check what it learns")
    train.add_argument("--keep", action="store_true", help="write what is taught into the real memory")
    train.add_argument("--offline", action="store_true", help="no model, checks everything around it")
    train.add_argument("--pack", help="another training pack file")
    sub.add_parser("mcp", help="memory server for Claude Code (used by `claude mcp add`)")
    args = parser.parse_args()

    try:
        settings = load_settings()
    except (ValueError, OSError) as e:
        sys.exit(f"Config problem: {e}")

    if args.command == "serve":
        return cmd_serve(settings, args)
    if args.command == "mcp":
        return cmd_mcp(settings, args)
    handler = {
        None: cmd_chat, "ask": cmd_ask, "doctor": cmd_doctor, "aboutme": cmd_aboutme,
        "tools": cmd_tools, "memory": cmd_memory, "train": cmd_train,
    }[args.command]
    try:
        asyncio.run(handler(settings, args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
