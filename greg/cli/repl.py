"""The chat screen."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from rich.console import Console
from rich.markup import escape

from greg.cli.client import GregClient
from greg.core.agent import MODES
from greg.profile.about import SECTIONS, Section

INDENT = "       "
HELP = """
 /help              this list
 /mode <name>       general, school, work or project
 /memory [words]    what I remember, or search it
 /remember <text>   save something on purpose
 /forget <id>       delete a memory
 /why               which memories shaped my last reply
 /tools             tool servers and how many tools each has
 /code <what>       build something (Claude first, my own coder as backup)
 /aboutme           tell me about yourself, or update it
 /voice             turn voice on or off (Enter to talk, Enter to stop)
 /doctor            check that every part works
 /new               start a fresh conversation
 /quit              leave
"""


def parse_command(line: str) -> tuple[str | None, str]:
    line = line.strip()
    if not line.startswith("/") or len(line) < 2:
        return None, line
    name, _, arg = line[1:].partition(" ")
    return name.lower(), arg.strip()


def header(health: dict, mode: str | None) -> str:
    providers = " + ".join(health.get("providers") or ["no model"])
    return (
        f" {health.get('name', 'Greg').lower()}   {providers}   memory {health.get('memories', 0)}   "
        f"tools {health.get('tools', 0)}   mode {mode or 'general'}"
    )


def short_args(args: dict, limit: int = 100) -> str:
    text = ", ".join(f"{k}={' '.join(str(v).split())}" for k, v in args.items())
    return text if len(text) <= limit else text[: limit - 3] + "..."


async def interview(
    ask: Callable[[Section, str], Awaitable[str]], current: dict, sections: list[Section] = SECTIONS
) -> dict:
    """Walks the About Me sections. Enter keeps the old answer, a single - clears it,
    and lists are typed with ; between items."""
    result: dict = {}
    for section in sections:
        old = current.get(section.key)
        shown = "; ".join(str(v) for v in old) if isinstance(old, list) else str(old or "")
        answer = (await ask(section, shown)).strip()
        if answer == "-":
            result[section.key] = [] if section.many else ""
        elif not answer:
            if old not in (None, "", []):
                result[section.key] = old
        elif section.many:
            result[section.key] = [part.strip() for part in answer.split(";") if part.strip()]
        else:
            result[section.key] = answer
    return result


class ChatSession:
    """One conversation with the server. Printing and asking are passed in, so
    the same code drives the real terminal and the tests."""

    def __init__(
        self,
        client: GregClient,
        console: Console,
        yes_no: Callable[[str], Awaitable[bool]],
        ask_line: Callable[[str, str], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.console = console
        self.yes_no = yes_no
        self.ask_line = ask_line
        self.session_id: str | None = None
        self.mode: str | None = None
        self.voice = False
        self.name = "greg"

    def _dim(self, text: str) -> None:
        self.console.print(f"[dim]{INDENT}{escape(text)}[/dim]", highlight=False)

    async def send(self, text: str) -> str:
        reply: list[str] = []
        mid_line = False

        def break_line() -> None:
            nonlocal mid_line
            if mid_line:
                self.console.print()
                mid_line = False

        try:
            async for event in self.client.chat(text, self.session_id, self.mode):
                kind = event["type"]
                if kind == "text":
                    if not mid_line:
                        self.console.print(f"\n [bold cyan]{self.name:<5}[/bold cyan] ", end="")
                        mid_line = True
                    reply.append(event["delta"])
                    self.console.print(event["delta"], end="", markup=False, highlight=False, soft_wrap=True)
                elif kind == "tool" and event.get("status") == "running":
                    break_line()
                    self._dim(f"using {event['name']}({short_args(event['args'])})")
                elif kind == "confirm":
                    break_line()
                    self.console.print(
                        f"\n{INDENT}[yellow]{self.name.capitalize()} wants to run "
                        f"{escape(event['tool'])}({escape(short_args(event['args'], 400))})[/yellow]",
                        highlight=False,
                    )
                    if event.get("reason"):
                        self._dim(event["reason"])
                    await self.client.confirm(event["id"], await self.yes_no(f"{INDENT}Allow? [y/N] "))
                elif kind == "tool_result" and not event.get("ok"):
                    self._dim(f"{event['name']} failed: {event.get('preview', '')[:120]}")
                elif kind == "status":
                    break_line()
                    self._dim(event["text"])
                elif kind == "done":
                    break_line()
                    self.session_id = event["session_id"]
                    used = sorted(set(event.get("tools_used") or []))
                    memories = len(event.get("memories_used") or [])
                    notes = used + ([f"{memories} memories"] if memories else [])
                    if notes:
                        self._dim("used: " + ", ".join(notes))
                elif kind == "error":
                    break_line()
                    self.console.print(f"\n{INDENT}[red]{escape(event['message'])}[/red]", highlight=False)
        except (httpx.HTTPError, OSError) as e:
            break_line()
            self.console.print(f"\n{INDENT}[red]Lost the server: {escape(str(e) or type(e).__name__)}[/red]")
        return "".join(reply)

    def _memories(self, rows: list[dict], empty: str) -> None:
        if not rows:
            self._dim(empty)
        for m in rows:
            pin = " (about me)" if m.get("pinned") else ""
            self.console.print(
                f"{INDENT}[dim]#{m['id']:<4} {m['kind']:<10}[/dim] {escape(m['text'])}[dim]{pin}[/dim]",
                highlight=False,
            )

    async def command(self, name: str, arg: str) -> bool:
        """Runs a slash command. False means quit."""
        c = self.client
        if name in ("quit", "exit", "q"):
            return False
        if name == "help":
            self.console.print(HELP, highlight=False)
        elif name == "new":
            self.session_id = None
            self._dim("Fresh conversation. I still remember you.")
        elif name == "mode":
            if arg in MODES:
                self.mode = arg
                self._dim(f"Mode is now {arg}.")
            else:
                self._dim(f"Modes: {', '.join(MODES)}")
        elif name == "memory":
            self._memories(await c.memories(arg), "Nothing found." if arg else "Nothing remembered yet.")
        elif name == "remember":
            if arg:
                saved = await c.remember(arg)
                self._dim(f"Saved as #{saved['id']}.")
            else:
                self._dim("Usage: /remember <something about you>")
        elif name == "forget":
            if arg.lstrip("#").isdigit():
                gone = (await c.forget(int(arg.lstrip("#"))))["forgotten"]
                self._dim("Forgotten." if gone else "No memory with that number.")
            else:
                self._dim("Usage: /forget <number from /memory>")
        elif name == "why":
            rows = await c.why(self.session_id) if self.session_id else []
            self._memories(rows, "No memories were used for the last reply.")
        elif name == "tools":
            info = await c.tools()
            builtin = sum(1 for t in info["tools"] if t["source"] == "builtin")
            self._dim(f"built in: {builtin} tools")
            for server, s in sorted(info["servers"].items()):
                extra = f"{s['tools']} tools" if s["state"] == "running" else s.get("error") or ", ".join(s.get("needs") or [])
                self._dim(f"{server:<10} {s['state']:<10} {extra}")
        elif name == "doctor":
            show_doctor(self.console, await c.doctor())
        elif name == "code":
            if arg:
                await self.send(f"Use the code_task tool to build this: {arg}")
            else:
                self._dim("Usage: /code <what to build>")
        elif name == "aboutme":
            await self.about_me()
        elif name == "voice":
            await self.toggle_voice()
        else:
            self._dim(f"No command /{name}. Try /help.")
        return True

    async def about_me(self) -> None:
        if not self.ask_line:
            return
        self._dim("Enter keeps what is there, a single - clears it, use ; between list items.")

        async def ask(section: Section, shown: str) -> str:
            hint = "  (list, use ; between)" if section.many else ""
            return await self.ask_line(f"\n{INDENT}{section.question}{hint}\n{INDENT}> ", shown)

        answers = await interview(ask, await self.client.about())
        report = await self.client.set_about(answers)
        self._dim(f"Got it. {report['added']} new, {report['changed']} changed, {report['removed']} removed.")

    async def toggle_voice(self) -> None:
        from greg.cli.audio import audio_ready

        if self.voice:
            self.voice = False
            self._dim("Voice off.")
            return
        ok, why = audio_ready()
        if not ok:
            self._dim(why)
            return
        self.voice = True
        self._dim("Voice on. Press Enter on an empty line to talk, Enter again to stop. Typing still works.")

    async def listen(self) -> str:
        """Record, transcribe, show what was heard. Empty string if it failed."""
        from greg.cli.audio import record

        self._dim("listening... press Enter to stop")
        wav = await asyncio.to_thread(record, input)
        try:
            heard = await self.client.transcribe(wav)
        except httpx.HTTPStatusError as e:
            self._dim(e.response.json().get("detail", "The server could not transcribe that."))
            self.voice = False
            return ""
        if heard:
            self.console.print(f" [bold]you  [/bold] {escape(heard)} [dim](voice)[/dim]", highlight=False)
        else:
            self._dim("Did not catch anything.")
        return heard

    async def say(self, text: str) -> None:
        from greg.cli.audio import play

        try:
            await asyncio.to_thread(play, await self.client.speak(text))
        except httpx.HTTPStatusError as e:
            self._dim(e.response.json().get("detail", "The server could not speak that."))
        except Exception as e:
            self._dim(f"Could not play audio here ({type(e).__name__}).")


def show_doctor(console: Console, checks: list[dict]) -> bool:
    """Prints the checkup. True when every required part works."""
    for c in checks:
        if c["ok"]:
            mark = "[green]ok  [/green]"
        elif c.get("optional"):
            mark = "[yellow]opt [/yellow]"
        else:
            mark = "[red]FIX [/red]"
        console.print(f" {mark} [bold]{escape(c['part']):<18}[/bold] {escape(c['detail'])}", highlight=False)
        if c.get("fix"):
            console.print(f"      [dim]{'':<18} -> {escape(c['fix'])}[/dim]", highlight=False)
    return all(c["ok"] or c.get("optional") for c in checks)


async def run_repl(client: GregClient) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout

    console = Console()
    prompt = PromptSession()

    async def yes_no(question: str) -> bool:
        return (await prompt.prompt_async(question)).strip().lower() in ("y", "yes")

    async def ask_line(question: str, default: str) -> str:
        return await prompt.prompt_async(question, default=default)

    chat = ChatSession(client, console, yes_no, ask_line)
    health = await client.health()
    chat.name = health["name"].lower()
    console.print(f"\n[bold]{escape(header(health, chat.mode))}[/bold]", highlight=False)
    console.print(" " + "_" * 64, highlight=False)
    if health.get("tool_servers_starting"):
        console.print(f"[dim]{INDENT}tool servers still starting: {', '.join(health['tool_servers_starting'])}[/dim]")
    for item in health.get("due", []):
        console.print(f"[dim]{INDENT}due soon: {escape(item)}[/dim]", highlight=False)
    if not (await client.about()):
        console.print(f"[dim]{INDENT}I know nothing about you yet. Type /aboutme to fix that.[/dim]")
    console.print(f"[dim]{INDENT}/help for commands[/dim]")

    while True:
        try:
            with patch_stdout():
                line = await prompt.prompt_async("\n you   ")
        except (EOFError, KeyboardInterrupt):
            break
        name, arg = parse_command(line)
        try:
            if name:
                if not await chat.command(name, arg):
                    break
                continue
            spoken = False
            if not arg:
                if not chat.voice:
                    continue
                arg, spoken = await chat.listen(), True
                if not arg:
                    continue
            reply = await chat.send(arg)
            if spoken and reply and chat.voice:
                await chat.say(reply)
        except KeyboardInterrupt:
            console.print(f"\n[dim]{INDENT}stopped[/dim]")
        except httpx.HTTPError as e:
            console.print(f"[red]{INDENT}Server problem: {escape(str(e) or type(e).__name__)}[/red]")
    console.print(f"[dim]{INDENT}bye[/dim]")
