"""Canvas, the school site: what is missing, what is coming up, and the files
of every class.

Needs two things in the keys: CANVAS_URL (your school's Canvas address) and
CANVAS_TOKEN (made in Canvas under Account, Settings, New Access Token).
The token can only read what you can see when you are logged in yourself.

Assignments are also copied into Anexis's own list (`sync`), so they show up
under "due soon", in reminders and in every reply without asking Canvas again.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from anexis.tools.base import SAFE, WRITE, Tool, ToolContext, params, text

SYNC_KEY = "canvas_items"         # canvas id -> item id, so nothing is added twice
SYNCED_AT = "canvas_synced_at"
SLIDES = (".pptx", ".ppt", ".pdf", ".key", ".odp", ".ppsx", ".pps")
MAX_PAGES = 20
NOT_SET = ("Error: Canvas is not set up. In the app open Keys and fill in the Canvas address "
           "(like https://yourschool.instructure.com) and a Canvas token (in Canvas: Account, Settings, New Access Token).")


class CanvasError(Exception):
    """Canvas could not answer. The text is for the owner."""


class Canvas:
    def __init__(self, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        base = url.strip().rstrip("/")
        if not base.startswith("http"):
            base = "https://" + base
        self.base = re.sub(r"/api/v1$", "", base)
        self._transport = transport  # only ever set by tests
        self.http = httpx.AsyncClient(
            base_url=self.base, headers={"Authorization": f"Bearer {token.strip()}"},
            timeout=httpx.Timeout(40, connect=10), transport=transport, follow_redirects=True,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def get(self, path: str, **query) -> list:
        """Every row of a listing, following Canvas's "next page" links."""
        rows: list = []
        url: str | None = f"/api/v1/{path.lstrip('/')}"
        pairs = [("per_page", "100")]
        for key, value in query.items():
            pairs += [(key, str(v)) for v in (value if isinstance(value, (list, tuple)) else [value])]
        for _ in range(MAX_PAGES):
            try:
                # The next page's link already carries its own query. An empty list would wipe it.
                resp = await self.http.get(url, params=pairs or None)
            except httpx.HTTPError as e:
                raise CanvasError(f"Could not reach Canvas at {self.base} ({type(e).__name__}). Check the Canvas address in Keys.") from e
            if resp.status_code == 401:
                raise CanvasError("Canvas refused the token. Make a new one in Canvas (Account, Settings, New Access Token) and put it in Keys.")
            if resp.status_code in (403, 404):
                raise CanvasError(f"Canvas would not show that (HTTP {resp.status_code}). The class may hide it from students.")
            if resp.status_code >= 400:
                raise CanvasError(f"Canvas answered HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                data = resp.json()
            except ValueError:
                raise CanvasError(f"{self.base} did not answer like Canvas. Check the Canvas address in Keys.") from None
            rows += data if isinstance(data, list) else [data]
            url, pairs = resp.links.get("next", {}).get("url"), []
            if not url:
                break
        return rows

    async def courses(self) -> list[dict]:
        rows = await self.get("courses", enrollment_state="active", **{"include[]": "term"})
        return [{"id": c["id"], "name": c.get("name") or c.get("course_code") or str(c["id"]), "code": c.get("course_code") or ""}
                for c in rows if isinstance(c, dict) and c.get("id") and not c.get("access_restricted_by_date")]

    async def missing(self) -> list[dict]:
        rows = await self.get("users/self/missing_submissions", **{"include[]": "course", "filter[]": "submittable"})
        return [_assignment(a, (a.get("course") or {}).get("name", ""), missing=True) for a in rows if isinstance(a, dict)]

    async def upcoming(self, days: int = 14) -> list[dict]:
        """Things with a due date in the next `days` that are not handed in yet."""
        now = datetime.now(UTC)
        rows = await self.get(
            "planner/items", start_date=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_date=(now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"), order="asc",
        )
        out = []
        for item in rows:
            kind = item.get("plannable_type")
            plannable = item.get("plannable") or {}
            if kind not in ("assignment", "quiz", "discussion_topic") or not (plannable.get("due_at") or plannable.get("todo_date")):
                continue
            state = item.get("submissions") if isinstance(item.get("submissions"), dict) else {}
            if state.get("submitted") or state.get("graded") or state.get("excused") or (item.get("planner_override", {}) and (item["planner_override"] or {}).get("marked_complete")):
                continue
            link = item.get("html_url") or ""
            out.append({
                "key": f"{kind}:{item.get('plannable_id') or plannable.get('id')}",
                "title": plannable.get("title") or plannable.get("name") or "untitled",
                "course": item.get("context_name") or "",
                "due": _local(plannable.get("due_at") or plannable.get("todo_date")),
                "url": link if link.startswith("http") else self.base + link,
                "points": plannable.get("points_possible"), "missing": bool(state.get("missing")), "kind": kind,
            })
        return out

    async def files(self, course_id: int) -> list[dict]:
        """A class's files. Some classes hide the Files page from students, so
        when that is refused the files linked from the class's modules are used."""
        try:
            rows = await self.get(f"courses/{course_id}/files", sort="updated_at", order="desc")
            return [_file(f) for f in rows if isinstance(f, dict) and f.get("url")]
        except CanvasError as first:
            try:
                modules = await self.get(f"courses/{course_id}/modules", **{"include[]": "items"})
            except CanvasError:
                raise first from None
        ids = [item["content_id"] for module in modules for item in (module.get("items") or [])
               if item.get("type") == "File" and item.get("content_id")]
        found = await asyncio.gather(*(self.get(f"courses/{course_id}/files/{i}") for i in dict.fromkeys(ids)), return_exceptions=True)
        return [_file(rows[0]) for rows in found if isinstance(rows, list) and rows and rows[0].get("url")]

    async def download(self, file: dict, folder: Path) -> tuple[Path, bool]:
        """Saves one file. Returns (where, was it new). A file that is already
        there with the same size is left alone."""
        target = folder / safe_name(file["name"])
        if target.exists() and file.get("size") and target.stat().st_size == file["size"]:
            return target, False
        folder.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        try:
            # The download link carries its own pass, and may live on another host.
            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(300, connect=10),
                                         transport=self._transport) as plain, plain.stream("GET", file["url"]) as resp:
                if resp.status_code >= 400:
                    raise CanvasError(f"Could not download {file['name']} (HTTP {resp.status_code})")
                with part.open("wb") as out:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        out.write(chunk)
        except httpx.HTTPError as e:
            part.unlink(missing_ok=True)
            raise CanvasError(f"Could not download {file['name']} ({type(e).__name__})") from e
        part.replace(target)
        return target, True


def safe_name(name: str) -> str:
    """A file or folder name that is fine on Windows and everywhere else."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .")
    return (cleaned or "file")[:150]


def _local(stamp: str | None) -> str | None:
    """Canvas gives UTC. Anexis keeps due dates in the owner's own time."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _assignment(a: dict, course: str, missing: bool = False) -> dict:
    return {
        "key": f"assignment:{a.get('id')}", "title": a.get("name") or "untitled", "course": course,
        "due": _local(a.get("due_at")), "url": a.get("html_url") or "", "points": a.get("points_possible"),
        "missing": missing, "kind": "assignment",
    }


def _file(f: dict) -> dict:
    return {"id": f.get("id"), "name": f.get("display_name") or f.get("filename") or str(f.get("id")),
            "size": f.get("size") or 0, "url": f["url"], "updated": _local(f.get("updated_at")) or ""}


def client_for(settings, transport=None) -> Canvas | None:
    url, token = settings.env.get("CANVAS_URL", ""), settings.env.get("CANVAS_TOKEN", "")
    return Canvas(url, token, transport) if url and token else None


_transport = None  # tests put a stand in for the Canvas website here


def _open(ctx: ToolContext) -> Canvas | None:
    return client_for(ctx.settings, _transport)


def find_course(courses: list[dict], wanted: str) -> dict | None:
    """A class by its id, or by part of its name, with typos forgiven."""
    wanted = str(wanted).strip().lower()
    if not wanted:
        return None
    for course in courses:
        if wanted == str(course["id"]):
            return course
    hits = [c for c in courses if wanted in c["name"].lower() or wanted in c["code"].lower()]
    if hits:
        return min(hits, key=lambda c: len(c["name"]))
    names = {c["name"].lower(): c for c in courses} | {c["code"].lower(): c for c in courses if c["code"]}
    words = {word: c for c in courses for word in re.findall(r"[a-z]{4,}", c["name"].lower())}
    close = difflib.get_close_matches(wanted, [*names, *words], n=1, cutoff=0.72)
    return ({**words, **names}).get(close[0]) if close else None


def _line(a: dict) -> str:
    when = f"due {a['due']}" if a["due"] else "no due date"
    points = f", {a['points']:g} points" if isinstance(a.get("points"), (int, float)) and a["points"] else ""
    return f"- {a['course'] + ': ' if a['course'] else ''}{a['title']} ({when}{points}){'  MISSING' if a['missing'] else ''}\n  {a['url']}"


# ---- keeping Anexis's own list in step with Canvas ------------------------

async def sync(memory, canvas: Canvas, days: int = 21) -> dict:
    """Copies missing and upcoming work into the assignment list. New work is
    added, changed due dates are updated, and work that is no longer missing
    or upcoming (handed in, or past) is marked done."""
    missing, upcoming = await asyncio.gather(canvas.missing(), canvas.upcoming(days))
    wanted = {a["key"]: a for a in upcoming}
    wanted.update({a["key"]: a for a in missing})  # missing wins, it carries the flag
    known: dict = memory.kv_get(SYNC_KEY, {})
    report = {"added": 0, "updated": 0, "done": 0, "missing": len(missing), "upcoming": len(upcoming)}
    db = memory.db
    for key, a in wanted.items():
        title = f"{a['course']}: {a['title']}" if a["course"] else a["title"]
        body = f"{'MISSING on Canvas. ' if a['missing'] else 'From Canvas. '}{a['url']}"
        row = db.execute("SELECT * FROM items WHERE id=?", (known.get(key),)).fetchone() if key in known else None
        if row is None:
            cur = db.execute("INSERT INTO items (type, title, body, due_at, created_at) VALUES ('assignment',?,?,?,?)",
                             (title, body, a["due"], time.time()))
            known[key] = cur.lastrowid
            report["added"] += 1
        elif (row["title"], row["body"], row["due_at"]) != (title, body, a["due"]) and not row["done"]:
            db.execute("UPDATE items SET title=?, body=?, due_at=? WHERE id=?", (title, body, a["due"], row["id"]))
            report["updated"] += 1
    for key in [k for k in known if k not in wanted]:
        changed = db.execute("UPDATE items SET done=1 WHERE id=? AND done=0", (known.pop(key),)).rowcount
        report["done"] += changed
    db.commit()
    memory.kv_set(SYNC_KEY, known)
    memory.kv_set(SYNCED_AT, time.time())
    return report


# ---- the tools ------------------------------------------------------------

async def _with_canvas(ctx: ToolContext, work) -> str:
    canvas = _open(ctx)
    if canvas is None:
        return NOT_SET
    try:
        return await work(canvas)
    except CanvasError as e:
        return f"Error: {e}"
    finally:
        await canvas.close()


async def canvas_courses(args: dict, ctx: ToolContext) -> str:
    async def work(canvas: Canvas) -> str:
        courses = await canvas.courses()
        if not courses:
            return "Canvas shows no active classes."
        return "Your classes on Canvas:\n" + "\n".join(f"- {c['name']} (id {c['id']}{', ' + c['code'] if c['code'] and c['code'] != c['name'] else ''})" for c in courses)

    return await _with_canvas(ctx, work)


async def canvas_missing(args: dict, ctx: ToolContext) -> str:
    async def work(canvas: Canvas) -> str:
        rows = sorted(await canvas.missing(), key=lambda a: a["due"] or "9")
        if not rows:
            return "Nothing is missing on Canvas."
        return f"{len(rows)} missing on Canvas, oldest first:\n" + "\n".join(_line(a) for a in rows)

    return await _with_canvas(ctx, work)


async def canvas_upcoming(args: dict, ctx: ToolContext) -> str:
    try:
        days = max(1, min(int(args.get("days") or 14), 120))
    except (TypeError, ValueError):
        days = 14

    async def work(canvas: Canvas) -> str:
        rows = sorted(await canvas.upcoming(days), key=lambda a: a["due"] or "9")
        if not rows:
            return f"Nothing is due on Canvas in the next {days} days."
        return f"{len(rows)} due on Canvas in the next {days} days, soonest first:\n" + "\n".join(_line(a) for a in rows)

    return await _with_canvas(ctx, work)


async def canvas_sync(args: dict, ctx: ToolContext) -> str:
    async def work(canvas: Canvas) -> str:
        r = await sync(ctx.memory, canvas)
        return (f"Canvas is in step with your assignment list: {r['missing']} missing, {r['upcoming']} upcoming. "
                f"{r['added']} added, {r['updated']} changed, {r['done']} marked done. Ask what is due any time.")

    return await _with_canvas(ctx, work)


def _is_wanted(file: dict, kind: str, match: str) -> bool:
    name = file["name"].lower()
    if kind == "slides" and not name.endswith(SLIDES):
        return False
    return match in name if match else True


async def canvas_files(args: dict, ctx: ToolContext) -> str:
    kind = "all" if str(args.get("kind") or "slides").lower() == "all" else "slides"
    match = str(args.get("match") or "").strip().lower()

    async def work(canvas: Canvas) -> str:
        courses = await canvas.courses()
        course = find_course(courses, args.get("course", ""))
        if course is None:
            return "Error: no class like that. Your classes: " + ", ".join(c["name"] for c in courses)
        files = [f for f in await canvas.files(course["id"]) if _is_wanted(f, kind, match)]
        if not files:
            return f"No {'slides' if kind == 'slides' else 'files'} found in {course['name']}" + (f" matching {match}." if match else ".")
        lines = [f"- {f['name']}  ({f['size'] / 1024**2:.1f} MB, {f['updated']})" for f in files[:80]]
        more = f"\n... and {len(files) - 80} more" if len(files) > 80 else ""
        return f"{len(files)} {'slide files' if kind == 'slides' else 'files'} in {course['name']}:\n" + "\n".join(lines) + more

    return await _with_canvas(ctx, work)


async def canvas_download(args: dict, ctx: ToolContext) -> str:
    kind = "all" if str(args.get("kind") or "slides").lower() == "all" else "slides"
    match = str(args.get("match") or "").strip().lower()
    wanted = str(args.get("course") or "").strip()
    root = ctx.settings.workspace / "canvas"

    async def work(canvas: Canvas) -> str:
        courses = await canvas.courses()
        if wanted.lower() in ("", "all", "every", "everything", "all classes"):
            chosen = courses
        else:
            course = find_course(courses, wanted)
            if course is None:
                return "Error: no class like that. Your classes: " + ", ".join(c["name"] for c in courses)
            chosen = [course]
        lines, total_new, total_had = [], 0, 0
        for course in chosen:
            try:
                files = [f for f in await canvas.files(course["id"]) if _is_wanted(f, kind, match)]
            except CanvasError as e:
                lines.append(f"- {course['name']}: {e}")
                continue
            folder = root / safe_name(course["name"])
            new = had = failed = 0
            for file in files:
                ctx.emit({"type": "status", "text": f"Canvas: {course['name']}, {file['name']}"})
                try:
                    _, fresh = await canvas.download(file, folder)
                    new, had = new + fresh, had + (not fresh)
                except CanvasError:
                    failed += 1
            total_new, total_had = total_new + new, total_had + had
            if files:
                lines.append(f"- {course['name']}: {new} downloaded, {had} already there" + (f", {failed} failed" if failed else "") + f"\n  {folder}")
            else:
                lines.append(f"- {course['name']}: nothing to download")
        what = "slides" if kind == "slides" else "files"
        return f"Downloaded {total_new} new {what} ({total_had} were already there). They are in {root}:\n" + "\n".join(lines)

    return await _with_canvas(ctx, work)


_COURSE = text("Part of the class name, or its Canvas id")

TOOLS = [
    Tool("canvas_courses", "List the owner's classes on Canvas (the school site).", params(), canvas_courses, tier=SAFE),
    Tool("canvas_missing", "Missing assignments on Canvas: work that is past due and not handed in, across every class.",
         params(), canvas_missing, tier=SAFE),
    Tool("canvas_upcoming", "Assignments, quizzes and discussions due soon on Canvas that are not handed in yet.",
         params(days={"type": "number", "description": "How many days ahead to look, default 14"}), canvas_upcoming, tier=SAFE),
    Tool("canvas_sync", "Copy missing and upcoming Canvas work into the owner's assignment list so it shows in reminders and what is due. Runs by itself every hour too.",
         params(), canvas_sync, tier=SAFE),
    Tool("canvas_files", "List the slides (or all files) of one class on Canvas.",
         params(["course"], course=_COURSE, kind=text("slides (default: pptx, ppt, pdf, key) or all"), match=text("Only files with this word in the name")),
         canvas_files, tier=SAFE),
    Tool("canvas_download", "Download the slides (or all files) of one class, or of every class, from Canvas into the workspace. Files already downloaded are skipped.",
         params(course=text("Part of the class name, its Canvas id, or all for every class"),
                kind=text("slides (default: pptx, ppt, pdf, key) or all"), match=text("Only files with this word in the name")),
         canvas_download, tier=WRITE),
]
