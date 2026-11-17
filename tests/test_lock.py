import httpx

from anexis.config import read_dotenv
from anexis.desktop.token import ensure_token


async def get(client, path, **headers):
    async with httpx.AsyncClient(base_url=client.url) as http:
        return await http.get(path, headers=headers, follow_redirects=False)


async def test_a_request_meant_for_another_name_is_refused(live):
    _, client = await live()
    assert (await get(client, "/health", Host="evil.example")).status_code == 403
    assert (await get(client, "/health", Host="evil.example:8765")).status_code == 403
    assert (await get(client, "/ui/", Host="evil.example")).status_code == 403


async def test_a_page_from_another_site_cannot_call_in(live):
    _, client = await live()
    assert (await get(client, "/health", Origin="https://evil.example")).status_code == 403
    assert (await get(client, "/health", Origin="null")).status_code == 403  # a sandboxed frame
    assert (await get(client, "/health", Origin=client.url)).status_code == 200


async def test_localhost_names_are_fine(live):
    _, client = await live()
    port = client.url.rsplit(":", 1)[1]
    for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
        assert (await get(client, "/health", Host=host)).status_code == 200


async def test_the_deck_is_public_but_everything_else_needs_the_token(live, settings):
    settings.token = "s3cret"
    _, client = await live()
    deck = await get(client, "/ui/")
    assert deck.status_code == 200 and deck.headers["cache-control"] == "no-store"
    home = await get(client, "/")
    assert home.status_code == 307 and home.headers["location"] == "/ui/"
    for path in ("/health", "/events", "/activity", "/memory", "/tools"):
        assert (await get(client, path)).status_code == 401, path
    assert (await get(client, "/health", Authorization="Bearer s3cret")).status_code == 200


async def test_a_server_opened_to_the_network_skips_the_name_check(live, settings):
    settings.host, settings.token = "0.0.0.0", "s3cret"
    _, client = await live()
    reply = await get(client, "/health", Host="my-server.lan:8765", Authorization="Bearer s3cret")
    assert reply.status_code == 200


def test_the_desktop_token_is_made_once_and_kept(tmp_path):
    first = ensure_token(tmp_path)
    assert len(first) >= 32 and read_dotenv(tmp_path / ".env")["ANEXIS_TOKEN"] == first
    assert ensure_token(tmp_path) == first
