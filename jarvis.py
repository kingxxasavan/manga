#!/usr/bin/env python3
"""Jarvis: chat with your Anexis from any computer. One file, nothing to install.

Needs Python 3.8 or newer, which most school and lab computers have. Copy this
file anywhere (a USB stick works) and run:

    python jarvis.py --setup     once: the server's address and its token
    python jarvis.py             then just this

The address and token are kept in .jarvis.json in your home folder. Use
--forget to remove them before you leave a shared computer.

Type and press Enter. Ctrl+C stops a reply. /new fresh chat, /clear delete
this chat, /quit leave.
"""

import getpass
import json
import os
import sys
import urllib.error
import urllib.request

CONFIG = os.path.join(os.path.expanduser("~"), ".jarvis.json")
HELP = "type to talk · ctrl+c stops a reply · /new fresh chat · /clear delete this chat · /quit leave"

if os.name == "nt":
    os.system("")  # lets the Windows terminal show colours
COLOUR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOUR else text


def dim(text):
    print(paint("  " + text, "2"))


class Jarvis:
    def __init__(self, url, token):
        self.url, self.token, self.session = url.rstrip("/"), token, None

    def call(self, method, path, body=None, timeout=30):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        return urllib.request.urlopen(request, timeout=timeout)

    def json(self, method, path, body=None):
        with self.call(method, path, body) as resp:
            return json.loads(resp.read().decode())

    def send(self, text):
        said = False
        resp = self.call("POST", "/chat", {"text": text, "session_id": self.session}, timeout=600)
        try:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                event = json.loads(line)
                kind = event.get("type")
                if kind == "text":
                    if not said:
                        print("\n" + paint(" jarvis ", "1;36"), end="")
                        said = True
                    print(event["delta"], end="", flush=True)
                elif kind == "tool" and event.get("status") == "running":
                    if said:
                        print()
                        said = False
                    dim(f"using {event['name']}")
                elif kind == "confirm":
                    if said:
                        print()
                        said = False
                    print(paint(f"\n  it wants to run {event['tool']} {json.dumps(event['args'])[:300]}", "33"))
                    allow = input("  allow? [y/N] ").strip().lower() in ("y", "yes")
                    self.json("POST", "/confirm", {"id": event["id"], "allow": allow})
                elif kind == "status":
                    dim(event.get("text", ""))
                elif kind == "error":
                    print(paint("\n  " + event.get("message", "error"), "31"))
                elif kind == "stopped":
                    dim("stopped")
                elif kind == "done":
                    self.session = event.get("session_id") or self.session
        finally:
            resp.close()
        if said:
            print()


def setup():
    url = input("Server address (like http://100.64.0.5:8765): ").strip()
    token = getpass.getpass("Token (hidden while typing): ").strip()
    with open(CONFIG, "w") as f:
        json.dump({"url": url, "token": token}, f)
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass
    print("Saved to " + CONFIG)


def main():
    args = sys.argv[1:]
    if "--forget" in args:
        if os.path.exists(CONFIG):
            os.remove(CONFIG)
        print("Forgot the address and token on this computer.")
        return
    if "--setup" in args or not os.path.exists(CONFIG):
        setup()
    with open(CONFIG) as f:
        saved = json.load(f)
    jarvis = Jarvis(os.environ.get("JARVIS_URL") or saved["url"], os.environ.get("JARVIS_TOKEN") or saved.get("token", ""))
    try:
        health = jarvis.json("GET", "/health")
    except urllib.error.HTTPError as e:
        sys.exit("The server refused the token. Run: python jarvis.py --setup" if e.code == 401 else f"The server said HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"Cannot reach {jarvis.url} ({e}). Is the server on, and is this computer on its network (Tailscale)?")
    sources = health.get("providers") or []
    model = f"{sources[0]} · {health.get('chat_models', {}).get(sources[0], '')}" if sources else "no model set up"
    print(paint(f"  jarvis online   {model}   {health.get('memories', 0)} memories", "1;36"))
    for item in health.get("due", [])[:5]:
        print(paint("  due soon: " + item, "33"))
    dim(HELP)
    while True:
        try:
            line = input("\n" + paint(" you ", "1") + "  ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        word = line.lower()
        if word in ("/quit", "/exit", "/q", "exit", "quit"):
            break
        if word == "/new":
            jarvis.session = None
            dim("fresh chat. I still remember you.")
            continue
        if word == "/clear":
            if jarvis.session:
                jarvis.json("DELETE", "/sessions/" + jarvis.session)
            jarvis.session = None
            dim("cleared. what I learned from it stays.")
            continue
        if word in ("/help", "?"):
            dim(HELP)
            continue
        try:
            jarvis.send(line)
        except KeyboardInterrupt:
            try:
                jarvis.json("POST", "/chat/stop", {"session_id": jarvis.session} if jarvis.session else {})
            except (urllib.error.URLError, OSError):
                pass
            print()
            dim("stopped")
        except (urllib.error.URLError, OSError) as e:
            print(paint(f"\n  lost the server: {e}", "31"))
    dim("later.")


if __name__ == "__main__":
    main()
