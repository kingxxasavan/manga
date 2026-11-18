"""Anexis has to work for how its owner really types: fast, no punctuation,
misspelled, several asks in one breath."""

import pytest

from anexis.coder.claude import ClaudeRunner
from anexis.coder.fallback import FallbackCoder
from anexis.coder.task import make_code_tool
from anexis.core.agent import Agent
from anexis.memory.consolidate import consolidate
from anexis.memory.style import analyze, describe, distill_style
from anexis.tools.base import Tool
from anexis.tools.builtin import register_builtin
from anexis.tools.registry import Registry
from tests.fakes import FakeRouter

# Lines in the owner's real voice.
OWNER = [
    "I need to create the most elite code for my server side for my ai for things like tools form GitHub "
    "gather the most shunt of amount of different tool put in the repo I can clone it into the server l, "
    "including the actual assistant main method would be chatbot but voice as backup using a ollama or "
    "Nvidia with a adaptive sql memory database to constantly learn",
    "Delete everything Greg, daily for school, work and to just walk to for random projects which I want "
    "to also include a Claude mcp for code creation if usage is full use the model and GitHub repo to "
    "crate a best code it can also upload a complete about me you have form age to areas to projects "
    "habits, class , create a simple cli ui",
    "We are using api key so just get to bulding",
    "Do a system check fix error improve the code make it max run a training test by talking like me "
    "and my way of thinking",
    "Try again",
]
FORMAL = [
    "Good morning. Could you please summarize the attached report?",
    "Thank you. I would also appreciate a short list of the key risks.",
    "Is it possible to schedule this for Tuesday? I am not available on Monday.",
    "Please confirm that you have received my previous message.",
    "I have reviewed the draft. It looks good, but the second section needs work.",
    "Would you mind checking the figures in the appendix as well?",
]


def texts(rows):
    return [r.text for r in rows]


# ---- recall ------------------------------------------------------------------


def test_recall_survives_misspelled_words(memory):
    memory.add("task", "Chemistry assignment is due Friday")
    memory.add("fact", "Favorite food is ramen")
    assert texts(memory.search("whens my chemestry assigment")) == ["Chemistry assignment is due Friday"]


def test_a_shortened_word_finds_the_full_one(memory):
    memory.add("class", "Chemistry lab is on Thursday afternoons")
    assert texts(memory.search("when is chem")) == ["Chemistry lab is on Thursday afternoons"]


def test_an_exact_match_ranks_above_a_near_miss(memory):
    memory.add("fact", "Hikes the canyon trail on weekends")
    exact = memory.add("fact", "Takes the train to campus")
    assert memory.search("train")[0].id == exact


def test_loose_matching_does_not_drag_in_unrelated_memories(memory):
    memory.add("fact", "Favorite food is ramen")
    memory.add("fact", "Works at the bike shop")
    assert memory.search("whats the weather like today") == []


def test_newly_learned_words_are_matchable_right_away(memory):
    memory.search("anything")  # warms the word list
    memory.add("project", "Building a Discord bot in Python")
    assert texts(memory.search("my discrod bot")) == ["Building a Discord bot in Python"]


# ---- picking tools -----------------------------------------------------------

DECOYS = [
    ("excel_write_data_to_excel", "Write data to an Excel worksheet"),
    ("excel_read_data_from_excel", "Read data from an Excel worksheet"),
    ("excel_create_chart", "Create a chart in a worksheet"),
    ("word_add_paragraph", "Add a paragraph to a Word document"),
    ("word_create_document", "Create a new Word document"),
    ("slides_add_slide", "Add a slide to a PowerPoint presentation"),
    ("wikipedia_search_wikipedia", "Search Wikipedia for articles"),
    ("wikipedia_get_summary", "Get a summary of a Wikipedia article"),
    ("arxiv_search_papers", "Search arXiv for research papers"),
    ("arxiv_read_paper", "Read the full text of a paper"),
    ("papers_search_pubmed", "Search PubMed for medical papers"),
    ("git_git_status", "Shows the working tree status"),
    ("git_git_commit", "Records changes to the repository"),
    ("git_git_diff", "Shows differences between branches or commits"),
    ("files_read_text_file", "Read the complete contents of a file from the file system as text"),
    ("files_search_files", "Recursively search for files and directories matching a pattern"),
    ("files_move_file", "Move or rename files and directories"),
    ("browser_browser_click", "Perform click on a web page"),
    ("browser_browser_navigate", "Navigate to a URL"),
    ("browser_browser_type", "Type text into editable element"),
    ("chart_generate_bar_chart", "Generate a bar chart to show data for numerical comparisons"),
    ("chart_generate_pie_chart", "Generate a pie chart to show the proportion of parts"),
    ("youtube_get_transcript", "Extract transcript from a YouTube video URL"),
    ("docs_resolve_library_id", "Resolves a package name to a library ID for documentation"),
    ("docs_query_docs", "Retrieves up to date documentation and code examples for any library"),
    ("deepwiki_ask_question", "Ask any question about a GitHub repository"),
    ("ddg_search", "Search DuckDuckGo and return formatted results"),
    ("fetch_fetch", "Fetches a URL from the internet and extracts its contents as markdown"),
    ("think_sequentialthinking", "A detailed tool for dynamic and reflective problem solving through thoughts"),
    ("time_convert_time", "Convert time between timezones"),
    ("convert_convert_to_markdown", "Convert a resource described by an http, https, file or data URI to markdown"),
]


@pytest.fixture
def crowded(settings, memory):
    """The built in tools in a crowd about the size of a real install."""
    registry = Registry()
    register_builtin(registry)
    registry.add(make_code_tool(ClaudeRunner(settings, memory), FallbackCoder(settings, memory, None, registry)))

    async def noop(args, ctx):
        return "ok"

    for name, about in DECOYS:
        registry.add(Tool(name, about, {}, noop, source="mcp:decoy"))
    return registry


@pytest.mark.parametrize("said, tool", [
    ("serach the web for cheap gpus", "web_search"),
    ("calculater 15 percent of 240", "calculate"),
    ("whats due this week", "list_items"),
    ("what homework do i got", "list_items"),
    ("remind me to email my boss tmrw", "add_item"),
    ("add milk to my todo list", "add_item"),
    ("i got a history essay due friday put that down", "add_item"),
    ("make me a python script that renames files", "code_task"),
    ("build me a discord bot", "code_task"),
    ("fix the bug in my app", "code_task"),
    ("run ls in the terminal", "run_shell"),
    ("find a github repo for discord bots", "github_search_repos"),
    ("open that link and tell me what it says", "web_fetch"),
    ("whats in my workspace folder", "list_dir"),
])
def test_the_right_tool_is_offered_for_sloppy_asks(crowded, said, tool):
    assert tool in [t.name for t in crowded.pick(said, k=12)]


# ---- style -------------------------------------------------------------------


def test_style_is_read_from_how_the_owner_really_writes():
    said = " ".join(describe(analyze(OWNER))).lower()
    assert "casual" in said and "punctuation" in said
    assert "several" in said  # packs several asks into one message
    assert "ask" in said and "question" in said  # gives orders, so act instead of asking back


def test_a_formal_writer_is_not_told_to_be_casual():
    said = " ".join(describe(analyze(FORMAL))).lower()
    assert "casual" not in said and "several" not in said


def test_a_handful_of_messages_is_not_enough_to_judge():
    assert describe(analyze(OWNER[:3])) == []


def agent_for(settings, memory, *script, **kw):
    settings.workspace.mkdir(parents=True, exist_ok=True)
    settings.learn = False
    registry = Registry()
    register_builtin(registry)
    router = FakeRouter(*script, **kw)
    return Agent(settings, memory, router, registry), router


async def test_the_model_is_told_how_its_owner_talks_once_there_is_enough_to_go_on(settings, memory):
    agent, router = agent_for(settings, memory, *["ok"] * len(OWNER))
    sid = None
    for line in OWNER:
        sid = (await agent.run_turn(sid, line))["session_id"]
    assert "How your owner talks" not in router.system(0)
    assert "How your owner talks" in router.system(-1) and "casual" in router.system(-1).lower()


async def test_upkeep_writes_down_how_the_owner_thinks_and_shows_it_to_the_model(settings, memory):
    agent, router = agent_for(
        settings, memory, "ok",
        roles={"small": ["Wants the best version, not the basic one. Prefers action over questions."]},
    )
    sid = memory.ensure_session(None)
    for line in OWNER * 4:
        memory.add_message(sid, "user", line)
    assert await distill_style(memory, router) is True
    assert memory.by_key("style.thinking").text.startswith("Wants the best version")
    await agent.run_turn(None, "hi")
    assert "Prefers action over questions" in router.system()


async def test_the_thinking_note_is_only_rewritten_after_enough_new_messages(settings, memory):
    router = FakeRouter(roles={"small": ["First take on them.", "Second take on them."]})
    sid = memory.ensure_session(None)
    for line in OWNER * 4:
        memory.add_message(sid, "user", line)
    assert await distill_style(memory, router) is True
    assert await distill_style(memory, router) is False
    for line in OWNER * 4:
        memory.add_message(sid, "user", line)
    assert await distill_style(memory, router) is True
    assert memory.by_key("style.thinking").text == "Second take on them."
    assert len(router.calls) == 2


async def test_upkeep_includes_the_style_step(settings, memory):
    sid = memory.ensure_session(None)
    for line in OWNER * 4:
        memory.add_message(sid, "user", line)
    router = FakeRouter(roles={"small": ["Moves fast and wants the best version.", "A summary."]})
    assert (await consolidate(memory, router))["style"] == 1


def test_a_greeting_is_not_mistaken_for_a_misspelled_tool_word(crowded):
    assert "run_shell" not in [t.name for t in crowded.pick("hello", k=12)]


def test_a_near_word_with_a_different_first_letter_is_not_a_typo(memory):
    memory.add("fact", "Works at the bike shop")
    assert memory.search("what do you like") == []
