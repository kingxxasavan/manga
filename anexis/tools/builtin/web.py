"""Web search, page fetch and GitHub lookups."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from anexis.tools.base import Tool, ToolContext, params, text

UA = {"User-Agent": "anexis-assistant/0.1"}


async def web_search(args: dict, ctx: ToolContext) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "Error: no search words given"
    count = min(int(args.get("max_results") or 6), 15)

    def search() -> list[dict]:
        from ddgs import DDGS

        return list(DDGS().text(query, max_results=count))

    try:
        results = await asyncio.wait_for(asyncio.to_thread(search), 30)
    except Exception as e:
        return f"Error: search failed ({type(e).__name__}: {e})"
    if not results:
        return "No results."
    return "\n\n".join(
        f"{r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}" for r in results
    )


class _Text(HTMLParser):
    SKIP = frozenset({"script", "style", "noscript", "svg", "head", "nav", "footer"})
    BLOCK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "article"})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping and data.strip():
            self.parts.append(data.strip() + " ")


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def public_address(host: str) -> bool:
    """False for localhost and private networks. A fetch tool that could reach
    those would let a web page trick Anexis into reading the server's own
    services."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


async def web_fetch(args: dict, ctx: ToolContext) -> str:
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=30, headers=UA) as client:
            for _ in range(6):  # follow redirects by hand so every hop is checked
                host = urlparse(url).hostname or ""
                if not await asyncio.to_thread(public_address, host):
                    return f"Error: {host or url} is not a public web address, so it is not fetched."
                resp = await client.get(url)
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                break
            else:
                return "Error: too many redirects"
    except httpx.HTTPError as e:
        return f"Error: could not fetch the page ({type(e).__name__}: {e})"
    if resp.status_code >= 400:
        return f"Error: the site answered HTTP {resp.status_code}"
    kind = resp.headers.get("content-type", "")
    body = html_to_text(resp.text) if "html" in kind else resp.text
    return body[: ctx.settings.tool_output_chars * 2] or "The page had no readable text."


async def _github(ctx: ToolContext, path: str, query: dict | None = None, raw: bool = False):
    headers = {**UA, "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    token = ctx.settings.env.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30, headers=headers, base_url="https://api.github.com") as client:
        return await client.get(path, params=query)


async def github_search_repos(args: dict, ctx: ToolContext) -> str:
    try:
        resp = await _github(ctx, "/search/repositories", {"q": args.get("query", ""), "per_page": 8})
    except httpx.HTTPError as e:
        return f"Error: GitHub could not be reached ({e})"
    if resp.status_code != 200:
        return f"Error: GitHub answered HTTP {resp.status_code}: {resp.text[:200]}"
    items = resp.json().get("items", [])
    if not items:
        return "No repositories found."
    return "\n".join(
        f"{r['full_name']} ({r['stargazers_count']} stars, {r.get('language') or 'n/a'}, "
        f"license {(r.get('license') or {}).get('spdx_id') or 'none'}): {r.get('description') or ''}"
        for r in items
    )


async def github_search_code(args: dict, ctx: ToolContext) -> str:
    if not ctx.settings.env.get("GITHUB_TOKEN"):
        return "Error: GitHub code search needs GITHUB_TOKEN in your .env file. Repository search works without it."
    try:
        resp = await _github(ctx, "/search/code", {"q": args.get("query", ""), "per_page": 8})
    except httpx.HTTPError as e:
        return f"Error: GitHub could not be reached ({e})"
    if resp.status_code != 200:
        return f"Error: GitHub answered HTTP {resp.status_code}: {resp.text[:200]}"
    items = resp.json().get("items", [])
    return "\n".join(f"{i['repository']['full_name']}: {i['path']}" for i in items) or "No code found."


async def github_read_file(args: dict, ctx: ToolContext) -> str:
    repo, path = str(args.get("repo", "")).strip("/"), str(args.get("path", "")).strip("/")
    if repo.count("/") != 1:
        return "Error: repo must look like owner/name"
    try:
        resp = await _github(ctx, f"/repos/{repo}/contents/{path}", raw=True)
    except httpx.HTTPError as e:
        return f"Error: GitHub could not be reached ({e})"
    if resp.status_code != 200:
        return f"Error: GitHub answered HTTP {resp.status_code} for {repo}/{path}"
    if resp.headers.get("content-type", "").startswith("application/json"):
        return "Folder contents:\n" + "\n".join(
            f"  {e['name']}{'/' if e['type'] == 'dir' else ''}" for e in resp.json()
        )
    return resp.text[: ctx.settings.tool_output_chars * 2]


TOOLS = [
    Tool("web_search", "Search the web. Returns titles, links and short summaries.",
         params(["query"], query=text("Search words"), max_results={"type": "integer"}), web_search),
    Tool("web_fetch", "Open a link or URL and read the web page or site. Returns what the page says as readable text.",
         params(["url"], url=text("Page address")), web_fetch),
    Tool("github_search_repos", "Search GitHub for repositories. Good for finding reference projects and libraries.",
         params(["query"], query=text("Search words, GitHub search syntax allowed")), github_search_repos),
    Tool("github_search_code", "Search code across GitHub for examples of how something is done.",
         params(["query"], query=text("Code search query, e.g. 'fastapi websocket language:python'")), github_search_code),
    Tool("github_read_file", "Read a file or list a folder from a GitHub repository.",
         params(["repo"], repo=text("owner/name"), path=text("Path inside the repo, empty for the top folder")), github_read_file),
]
