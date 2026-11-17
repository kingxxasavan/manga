import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from anexis.tools.base import ToolContext
from anexis.tools.builtin import canvas
from tests.fakes import FakeRouter

SOON = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:00Z")
LATE = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:00Z")


class School:
    """Stands in for a school's Canvas site."""

    def __init__(self):
        self.asked = []
        self.missing = [{"id": 501, "name": "Lab 3 writeup", "due_at": LATE, "points_possible": 20,
                         "html_url": "https://school.test/courses/1/assignments/501", "course": {"name": "Chemistry 101"}}]
        self.planner = [
            {"plannable_type": "assignment", "plannable_id": 601, "context_name": "Chemistry 101", "html_url": "/courses/1/assignments/601",
             "plannable": {"title": "Problem set 4", "due_at": SOON, "points_possible": 10}, "submissions": {"submitted": False}},
            {"plannable_type": "assignment", "plannable_id": 602, "context_name": "History", "html_url": "/courses/2/assignments/602",
             "plannable": {"title": "Essay draft", "due_at": SOON}, "submissions": {"submitted": True}},
            {"plannable_type": "announcement", "plannable_id": 9, "plannable": {"title": "Welcome"}, "submissions": False},
            {"plannable_type": "quiz", "plannable_id": 603, "context_name": "History", "html_url": "/courses/2/quizzes/603",
             "plannable": {"title": "Quiz 2", "due_at": SOON}, "submissions": False},
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.asked.append(path)
        if request.url.host == "files.test":
            return httpx.Response(200, content=b"slide-bytes-" + path.encode())
        if request.headers.get("authorization") != "Bearer good-token":
            return httpx.Response(401, json={"errors": [{"message": "Invalid access token."}]})
        if path == "/api/v1/courses":
            if request.url.params.get("page") == "2":
                return httpx.Response(200, json=[{"id": 2, "name": "History: 1900 to now", "course_code": "HIST200"}])
            return httpx.Response(200, json=[{"id": 1, "name": "Chemistry 101", "course_code": "CHEM101"}],
                                  headers={"Link": '<https://school.test/api/v1/courses?page=2>; rel="next"'})
        if path == "/api/v1/users/self/missing_submissions":
            return httpx.Response(200, json=self.missing)
        if path == "/api/v1/planner/items":
            return httpx.Response(200, json=self.planner)
        if path == "/api/v1/courses/1/files":
            return httpx.Response(200, json=[
                {"id": 11, "display_name": "Week 1: Atoms?.pptx", "size": 15, "url": "https://files.test/11", "updated_at": SOON},
                {"id": 12, "display_name": "Week 2 Bonds.pdf", "size": 15, "url": "https://files.test/12", "updated_at": SOON},
                {"id": 13, "display_name": "Syllabus.docx", "size": 15, "url": "https://files.test/13", "updated_at": SOON},
            ])
        if path == "/api/v1/courses/2/files":
            return httpx.Response(403, json={"status": "unauthorized"})
        if path == "/api/v1/courses/2/modules":
            return httpx.Response(200, json=[{"items": [{"type": "File", "content_id": 77}, {"type": "Page"}, {"type": "File", "content_id": 77}]}])
        if path == "/api/v1/courses/2/files/77":
            return httpx.Response(200, json={"id": 77, "display_name": "Lecture 5.key", "size": 15, "url": "https://files.test/77"})
        return httpx.Response(404, json={})


@pytest.fixture
def school(settings, monkeypatch):
    site = School()
    monkeypatch.setattr(canvas, "_transport", httpx.MockTransport(site))
    settings.env = {"CANVAS_URL": "school.test/", "CANVAS_TOKEN": "good-token"}
    return site


@pytest.fixture
def ctx(settings, memory):
    return ToolContext(settings=settings, memory=memory, router=FakeRouter(), registry=None, session_id="s")


async def test_classes_are_listed_across_pages(school, ctx):
    said = await canvas.canvas_courses({}, ctx)
    assert "Chemistry 101 (id 1, CHEM101)" in said and "History: 1900 to now (id 2, HIST200)" in said


async def test_missing_and_upcoming_work(school, ctx):
    missing = await canvas.canvas_missing({}, ctx)
    assert "1 missing" in missing and "Chemistry 101: Lab 3 writeup" in missing and "MISSING" in missing and "20 points" in missing
    upcoming = await canvas.canvas_upcoming({"days": 7}, ctx)
    assert "2 due on Canvas in the next 7 days" in upcoming
    assert "Problem set 4" in upcoming and "Quiz 2" in upcoming
    assert "Essay draft" not in upcoming and "Welcome" not in upcoming      # handed in, and not work at all
    assert "https://school.test/courses/1/assignments/601" in upcoming     # a short link is made whole


async def test_due_times_are_in_the_owners_own_time(school, ctx):
    local = datetime.fromisoformat(SOON.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    assert f"due {local}" in await canvas.canvas_upcoming({}, ctx)


async def test_sync_fills_the_assignment_list_once_and_keeps_it_current(school, ctx, memory):
    from anexis.tools.builtin.core import due_soon

    client = canvas.client_for(ctx.settings, canvas._transport)
    first = await canvas.sync(memory, client)
    assert (first["added"], first["updated"], first["done"]) == (3, 0, 0)
    titles = [r["title"] for r in memory.db.execute("SELECT title FROM items WHERE done=0 ORDER BY title")]
    assert titles == ["Chemistry 101: Lab 3 writeup", "Chemistry 101: Problem set 4", "History: Quiz 2"]
    assert any("Problem set 4" in i["title"] for i in due_soon(memory))    # shows under due soon
    assert (await canvas.sync(memory, client))["added"] == 0             # nothing twice

    school.planner[0]["plannable"]["due_at"] = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:00Z")
    school.missing.clear()                                                 # the lab got handed in
    third = await canvas.sync(memory, client)
    assert (third["added"], third["updated"], third["done"]) == (0, 1, 1)
    assert memory.db.execute("SELECT done FROM items WHERE title LIKE '%Lab 3%'").fetchone()["done"] == 1
    await client.close()


async def test_slides_are_listed_and_downloaded_and_not_downloaded_twice(school, ctx, settings):
    listed = await canvas.canvas_files({"course": "chem"}, ctx)
    assert "2 slide files in Chemistry 101" in listed and "Syllabus" not in listed
    assert "3 files" in await canvas.canvas_files({"course": "1", "kind": "all"}, ctx)

    said = await canvas.canvas_download({"course": "chemestry"}, ctx)       # a typo still finds the class
    folder = settings.workspace / "canvas" / "Chemistry 101"
    assert "Downloaded 2 new slides" in said and str(folder) in said
    assert sorted(p.name for p in folder.iterdir()) == ["Week 1_ Atoms_.pptx", "Week 2 Bonds.pdf"]   # safe on Windows
    assert (folder / "Week 2 Bonds.pdf").read_bytes() == b"slide-bytes-/12"
    again = await canvas.canvas_download({"course": "Chemistry"}, ctx)
    assert "Downloaded 0 new slides (2 were already there)" in again


async def test_every_class_at_once_and_a_class_that_hides_its_files_page(school, ctx, settings):
    said = await canvas.canvas_download({"course": "all"}, ctx)
    assert "Downloaded 3 new slides" in said
    assert (settings.workspace / "canvas" / "History_ 1900 to now" / "Lecture 5.key").is_file()   # found through the modules
    assert school.asked.count("/api/v1/courses/2/files/77") == 1


async def test_problems_are_explained(school, ctx, settings):
    assert "no class like that" in await canvas.canvas_files({"course": "underwater basket weaving"}, ctx)
    settings.env = {"CANVAS_URL": "school.test", "CANVAS_TOKEN": "old-token"}
    assert "refused the token" in await canvas.canvas_missing({}, ctx)
    settings.env = {}
    assert (await canvas.canvas_upcoming({}, ctx)).startswith("Error: Canvas is not set up")


def test_the_canvas_tools_only_appear_once_there_is_a_token(settings):
    from anexis.tools.builtin import register_builtin
    from anexis.tools.registry import Registry

    without, with_token = Registry(), Registry()
    register_builtin(without, settings)
    settings.env = {"CANVAS_TOKEN": "x"}
    register_builtin(with_token, settings)
    assert without.get("canvas_missing") is None and with_token.get("canvas_download") is not None


def test_names_are_made_safe_for_windows():
    assert canvas.safe_name('Week 1: "Atoms" <draft>?.pptx') == "Week 1_ _Atoms_ _draft__.pptx"
    assert canvas.safe_name("...") == "file" and canvas.safe_name("ok.pdf") == "ok.pdf"


def test_a_token_and_address_can_be_saved_from_setup(settings):
    from anexis.cli.setup import KEY_OPTIONS, key_warning

    by_env = {o.env: o for o in KEY_OPTIONS}
    assert by_env["CANVAS_URL"].secret is False and by_env["CANVAS_TOKEN"].secret is True
    assert key_warning("CANVAS_URL", "https://school.instructure.com") == ""
    assert "https://" in key_warning("CANVAS_URL", "school.instructure.com")
    assert json.dumps(by_env["CANVAS_TOKEN"].get_it)
