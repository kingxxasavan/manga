"""Everyday tools: time, math, memory, tool lookup, notes and deadlines."""

from __future__ import annotations

import ast
import math
import operator
import time
from datetime import date, datetime, timedelta

from anexis.memory.store import KINDS
from anexis.tools.base import SAFE, Tool, ToolContext, params, text

ITEM_TYPES = ("note", "todo", "assignment", "reminder")


async def time_now(args: dict, ctx: ToolContext) -> str:
    now = datetime.now().astimezone()
    return now.strftime("%A %Y-%m-%d %H:%M %Z (week %V)")


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_NAMES = {"pi": math.pi, "e": math.e}
_FUNCS = {
    n: getattr(math, n)
    for n in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "floor", "ceil", "factorial")
}
_FUNCS.update(abs=abs, round=round, min=min, max=max)


def _eval(node):
    """Walks a math expression. Only numbers, math operators and a fixed list
    of functions are allowed, so this can never run code."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("only numbers and math are allowed")


async def calculate(args: dict, ctx: ToolContext) -> str:
    expression = str(args.get("expression", ""))
    try:
        return f"{expression} = {_eval(ast.parse(expression, mode='eval').body)}"
    except Exception as e:
        return f"Error: could not calculate that ({e})"


async def remember(args: dict, ctx: ToolContext) -> str:
    body = str(args.get("text", "")).strip()
    if not body:
        return "Error: nothing to remember"
    kind = args.get("kind") if args.get("kind") in KINDS else "fact"
    existing = ctx.memory.find_duplicate(body)
    if existing:
        ctx.memory.reinforce(existing)
        return f"Already knew that (memory #{existing}), now more sure of it."
    memory_id = ctx.memory.add(kind, body, confidence=0.9, importance=0.7, source="told")
    return f"Saved as memory #{memory_id}."


async def recall(args: dict, ctx: ToolContext) -> str:
    found = ctx.memory.search(str(args.get("query", "")), k=8)
    if not found:
        return "Nothing in memory about that."
    return "\n".join(f"#{m.id} [{m.kind}] {m.text}" for m in found)


async def find_tools(args: dict, ctx: ToolContext) -> str:
    found = ctx.registry.find(str(args.get("query", "")), k=8, stats=ctx.memory.tool_stats())
    if not found:
        return "No tools match that."
    ctx.extra_tools.update(t.name for t in found)
    lines = [f"{t.name}: {t.description[:140]}" for t in found]
    return "These tools are now available to call:\n" + "\n".join(lines)


def parse_due(raw) -> str | None:
    """Turns a due date into YYYY-MM-DD or YYYY-MM-DD HH:MM. Raises ValueError."""
    if raw in (None, ""):
        return None
    value = str(raw).strip().lower()
    today = date.today()
    if value == "today":
        return today.isoformat()
    if value == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    for fmt, out in (("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M"), ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"), ("%Y-%m-%d", "%Y-%m-%d")):
        try:
            return datetime.strptime(value[:16] if "%H" in fmt else value, fmt).strftime(out)
        except ValueError:
            continue
    raise ValueError(raw)


async def add_item(args: dict, ctx: ToolContext) -> str:
    kind = args.get("type") if args.get("type") in ITEM_TYPES else "note"
    title = str(args.get("title", "")).strip()
    if not title:
        return "Error: a title is needed"
    try:
        due = parse_due(args.get("due"))
    except ValueError:
        return "Error: could not read that due date. Use YYYY-MM-DD or YYYY-MM-DD HH:MM."
    cur = ctx.memory.db.execute(
        "INSERT INTO items (type, title, body, due_at, created_at) VALUES (?,?,?,?,?)",
        (kind, title, str(args.get("body", "")), due, time.time()),
    )
    ctx.memory.db.commit()
    return f"Added {kind} #{cur.lastrowid}: {title}" + (f" (due {due})" if due else "")


def due_soon(memory, days: int = 7, limit: int = 10) -> list[dict]:
    horizon = (date.today() + timedelta(days=days)).isoformat() + " 99"
    rows = memory.db.execute(
        "SELECT * FROM items WHERE done=0 AND due_at IS NOT NULL AND due_at<=? ORDER BY due_at LIMIT ?",
        (horizon, limit),
    ).fetchall()
    return [dict(r) for r in rows]


async def list_items(args: dict, ctx: ToolContext) -> str:
    sql, values = "SELECT * FROM items WHERE 1=1", []
    if args.get("type") in ITEM_TYPES:
        sql += " AND type=?"
        values.append(args["type"])
    if not args.get("include_done"):
        sql += " AND done=0"
    rows = ctx.memory.db.execute(
        sql + " ORDER BY due_at IS NULL, due_at, id LIMIT 50", values
    ).fetchall()
    if not rows:
        return "Nothing on the list."
    return "\n".join(
        f"#{r['id']} [{r['type']}] {r['title']}"
        + (f" (due {r['due_at']})" if r["due_at"] else "")
        + (" (done)" if r["done"] else "")
        + (f": {r['body'][:200]}" if r["body"] else "")
        for r in rows
    )


async def complete_item(args: dict, ctx: ToolContext) -> str:
    cur = ctx.memory.db.execute("UPDATE items SET done=1 WHERE id=?", (args.get("id"),))
    ctx.memory.db.commit()
    return "Marked done." if cur.rowcount else "Error: no item with that id"


async def delete_item(args: dict, ctx: ToolContext) -> str:
    cur = ctx.memory.db.execute("DELETE FROM items WHERE id=?", (args.get("id"),))
    ctx.memory.db.commit()
    return "Deleted." if cur.rowcount else "Error: no item with that id"


_ID = params(["id"], id={"type": "integer", "description": "The item number"})

TOOLS = [
    Tool("time_now", "Current date, time, weekday and timezone on the server.", params(), time_now, core=True),
    Tool("calculate", "Do exact math. Supports + - * / ** % and sqrt, sin, cos, log, exp, floor, ceil, factorial, pi, e.",
         params(["expression"], expression=text("Math expression, e.g. (3.5 * 12) / sqrt(2)")), calculate),
    Tool("remember", "Save something lasting about the owner or their world so it is known in future conversations.",
         params(["text"], text=text("One clear sentence"), kind={"type": "string", "enum": list(KINDS)}), remember, core=True),
    Tool("recall", "Search what is remembered about the owner: facts, preferences, habits, classes, projects, people.",
         params(["query"], query=text("What to look for")), recall, core=True),
    Tool("find_tools", "Search for more tools when none of the offered ones fit the job. Describe what you need to do.",
         params(["query"], query=text("What you need to do, e.g. 'read a pdf' or 'search github'")), find_tools, core=True),
    Tool("add_item", "Add a note, todo, homework or school assignment, or reminder to the owner's lists. Use when they say remind me, put that down, write this down, or mention something that is due: an essay, lab, quiz, test, exam or project deadline.",
         params(["type", "title"], type={"type": "string", "enum": list(ITEM_TYPES)}, title=text("Short title"),
                body=text("Details"), due=text("Due date as YYYY-MM-DD or YYYY-MM-DD HH:MM, or today or tomorrow")), add_item),
    Tool("list_items", "List the owner's notes, todos, homework, school assignments and reminders, soonest due first. Use for what is due, what they have to do, deadlines and this week.",
         params(type={"type": "string", "enum": list(ITEM_TYPES)}, include_done={"type": "boolean"}), list_items),
    Tool("complete_item", "Mark a todo, assignment or reminder as done.", _ID, complete_item),
    Tool("delete_item", "Delete a note, todo, assignment or reminder.", _ID, delete_item),
]
assert all(t.tier == SAFE for t in TOOLS)
