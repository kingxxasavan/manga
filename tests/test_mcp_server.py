from mcp import Client

from greg.mcp_server import build_server
from greg.profile.about import import_profile


async def ask(settings, tool, **args):
    async with Client(build_server(settings)) as client:
        result = await client.call_tool(tool, args)
        return result.content[0].text


async def test_claude_can_read_who_the_owner_is(settings, memory):
    import_profile(memory, {"name": "Sam", "talk_style": "short and blunt"})
    out = await ask(settings, "about_owner")
    assert "Name: Sam" in out and "short and blunt" in out


async def test_claude_can_search_memory_for_preferences(settings, memory):
    memory.add("lesson", "When writing Python always add type hints")
    memory.add("fact", "Favorite food is ramen")
    out = await ask(settings, "search_memory", query="python style")
    assert "type hints" in out and "ramen" not in out


async def test_before_any_memory_exists_it_says_so(settings):
    assert "nothing" in (await ask(settings, "about_owner")).lower()
    assert "nothing" in (await ask(settings, "search_memory", query="x")).lower()


async def test_the_memory_server_cannot_change_anything(settings, memory):
    async with Client(build_server(settings)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"about_owner", "search_memory"}
