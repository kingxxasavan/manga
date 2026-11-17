# Anexis Windows App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Anexis as a Windows app: one installer, a control deck UI, full PC control, setup in the app, and live editing with no rebuild.

**Architecture:** The existing FastAPI server grows the deck (static files under `/ui`) and the routes it needs. A Python supervisor (`anexis desktop`) runs the server and restarts it on code changes. A thin Electron frame starts the supervisor, opens a window on the deck, and packs the installer with Python, Node and uv inside.

**Tech Stack:** Python 3.11+, FastAPI, psutil, pywinpty (Windows), pyautogui, pyperclip, plain ES modules + CSS, xterm.js 6, Electron 45, electron builder 26 (NSIS).

**Spec:** `docs/superpowers/specs/2026-11-17-anexis-windows-app-design.md`

## Global Constraints

- The Linux terminal chat and its 288 tests keep passing.
- No dashes in owner facing copy. Plain words.
- Server default stays `control = "ask"`. Only setup in the app writes `full`.
- Every new route sits behind the token. Only `/ui/*` and `/` are public.
- A Host header that is not `127.0.0.1`, `localhost` or `[::1]` (any port) is refused with 403 while the server listens on loopback.
- The deck has no build step. Third party browser code lives in `ui/vendor/`.
- Windows only code is imported lazily and never at module import on Linux.
- Keys never go in `anexis.toml`, a URL query, or a log line.

## Review Focus

1. A page from another site calls the local server (wrong Host, no token): refused, nothing runs. Test in Task 3.
2. Stop is pressed while a tool is running: the turn ends, the child process is dead, the next chat works. Test in Task 2.
3. Setup is applied twice, or with a pasted key that has spaces or quotes: `.env` stays valid and the old `anexis.toml` is backed up. Test in Task 6.
4. A path with spaces or non English letters in the files panel and in `open_path`: listed and opened, never passed through a shell string. Test in Tasks 4 and 7.
5. A Python edit with a syntax error: the supervisor keeps the deck reachable with a clear message instead of a restart loop. Test in Task 8.

---

### Task 1: Core runs on Windows

**Files:** Modify `anexis/tools/builtin/system.py`, `anexis/cli/main.py`, `anexis/cli/setup.py`, `anexis/tools/mcp_client.py`, `anexis/profile/about.py`, `pyproject.toml`. Create `anexis/platform.py`. Test `tests/test_platform.py`.

**Produces:**
- `anexis.platform.IS_WINDOWS: bool`
- `anexis.platform.spawn_kwargs() -> dict` (new process group on either OS)
- `anexis.platform.kill_tree(pid: int) -> None` (psutil, children first)
- `anexis.platform.shell_argv(command: str) -> list[str]` (`powershell -NoProfile -Command` on Windows, `/bin/sh -c` elsewhere)
- `anexis.platform.private_file(path) -> None` (chmod 600, no op on Windows)
- `anexis.platform.is_anexis_server(pid: int) -> bool`

- [ ] Tests: `kill_tree` ends a child and its grandchild; `shell_argv("echo hi")` runs and prints `hi`; `run_process` timeout leaves no child alive; `stop_server` ignores a pid that is not an Anexis server.
- [ ] Implement, swap `os.killpg`, `/proc` reads and `start_new_session` for the helpers. `tool_path` joins with `os.pathsep`. `detect_machine` reads RAM with psutil.
- [ ] Add `psutil>=6` to dependencies and a `desktop` extra: `pyautogui`, `pyperclip`, `pillow`, `pywinpty; sys_platform == "win32"`, `pygetwindow; sys_platform == "win32"`.
- [ ] `uv run pytest -q` all pass. Commit.

### Task 2: Control level, activity feed, stop

**Files:** Modify `anexis/config.py`, `anexis/tools/permissions.py`, `anexis/core/agent.py`, `anexis/core/app.py`, `anexis/server/app.py`. Create `anexis/core/events.py`. Test `tests/test_control.py`.

**Produces:**
- `Settings.control: str = "ask"` (`[agent] control` in toml, env `ANEXIS_CONTROL`)
- `decide()` returns `("allow", "full control is on")` when `control == "full"` and no per tool override says `ask`
- `EventBus.publish(event: dict)`, `EventBus.subscribe() -> AsyncIterator[dict]`, `EventBus.recent(n) -> list[dict]`; `AnexisApp.events`
- Agent publishes `{"type": "activity", "tool", "args", "status", "ok", "preview", "at", "session_id"}` for every tool call
- `POST /chat/stop {session_id}` -> `{"stopped": bool}`; `GET /events` ndjson stream; `GET /activity` last 200

- [ ] Tests: full control runs `run_shell` with no confirm event; a per tool `ask` still asks under full; stop during a sleeping shell tool ends the stream and kills the child; `/events` delivers an activity event.
- [ ] Implement. Running turns are kept in a dict by session id so stop can cancel the task.
- [ ] Pass, commit.

### Task 3: Lock on the local server and the public deck mount

**Files:** Modify `anexis/server/app.py`, `anexis/config.py`. Create `ui/index.html` (placeholder until Task 9). Test `tests/test_lock.py`.

**Produces:**
- `Settings.ui_dir: Path` (default `REPO_ROOT / "ui"`)
- Host check middleware as in Global Constraints
- Token accepted from `Authorization: Bearer` or, for the socket only, `?token=`
- `GET /` redirects to `/ui/`; `/ui/*` served with `Cache-Control: no-store`
- `anexis.desktop.token.ensure_token(home) -> str` writes `ANEXIS_TOKEN` to `.env` once

- [ ] Tests: `Host: evil.example` gets 403; `/ui/` answers 200 with no token while `/health` answers 401; `ensure_token` is stable across calls.
- [ ] Implement, pass, commit.

### Task 4: Deck data routes

**Files:** Create `anexis/desktop/__init__.py`, `anexis/desktop/system.py`, `anexis/desktop/files.py`, `anexis/desktop/routes.py`. Modify `anexis/server/app.py` to include the router. Test `tests/test_deck_routes.py`.

**Produces:**
- `GET /system/stats` -> `{cpu, cores[], memory{used,total}, disks[], net{up,down}, gpu?, uptime, processes[top 8], host, os}`
- `GET /files?path=` -> `{path, parent, entries[{name, dir, size, modified}]}`; empty path means the workspace; `GET /files/roots`
- `POST /files/open {path}` opens with the OS default app (never through a shell string)
- `GET /settings`, `POST /settings {control?, name?}` (writes `anexis.toml` through `anexis.desktop.config_file.set_values`)
- `GET /app` -> `{version, folder, live, platform, python}`; `POST /app/restart` exits with code 75
- `POST /sessions/new` -> `{session_id}`; `GET /sessions/{id}/messages`

- [ ] Tests: stats has every key and sane numbers; files lists a folder named `my föld er`; a missing path is 404; settings round trip keeps other toml content.
- [ ] Implement, pass, commit.

### Task 5: Terminal

**Files:** Create `anexis/desktop/terminal.py`. Modify `anexis/desktop/routes.py`. Test `tests/test_terminal.py`.

**Produces:**
- `open_terminal(cwd, cols, rows) -> Terminal` with `read() -> bytes` (async), `write(data)`, `resize(cols, rows)`, `close()`; `pty` on POSIX, `winpty.PtyProcess` on Windows, plain pipes when neither loads
- `WS /terminal?token=&cwd=`: binary frames are terminal bytes, text frames are JSON `{"resize": [cols, rows]}`

- [ ] Tests: `echo deck-ok` through the socket comes back; resize does not raise; closing the socket ends the shell; a wrong token is refused.
- [ ] Implement, pass, commit.

### Task 6: Setup in the app

**Files:** Create `anexis/desktop/setup_api.py`, `anexis/desktop/install.py`. Modify `anexis/cli/setup.py` (expose `apply_choices`), `anexis/desktop/routes.py`. Test `tests/test_setup_api.py`.

**Produces:**
- `apply_choices(home, preset, name, control, voice, env_changes) -> dict` shared by the wizard and the API
- `GET /setup` -> `{done, machine, presets[], best, keys[{env,title,turns_on,get_it,set,ends}], control, name}`
- `POST /setup {preset, name, control, voice, keys{env: value}}` -> `{saved, warnings{}, restart: true}`
- `POST /setup/install {ollama, models[], claude, tools}` -> ndjson `{step, state, line?, percent?}`; each step is a function in `install.py` taking an `emit` callback and a `run` function so tests script it

- [ ] Tests: apply writes toml with `control = "full"` and backs up the old file; a key with a quote survives a `.env` round trip; `-` removes a key; install emits `done` or `failed` per step with a scripted runner; `done` is true once `anexis.toml` exists.
- [ ] Implement, pass, commit.

### Task 7: Desktop control tools

**Files:** Create `anexis/tools/builtin/desktop.py`. Modify `anexis/tools/builtin/__init__.py`, `anexis/llm/provider.py` (image parts), `anexis/config.py` (`vision` role passes through). Test `tests/test_desktop_tools.py`.

**Produces:** tools `open_path`, `list_windows`, `focus_window`, `close_window`, `clipboard_read`, `clipboard_write`, `screenshot`, `type_text`, `press_keys`, `mouse_move`, `mouse_click`, `list_processes`, `end_process`, `see_screen`. All tier `DANGER` except the read only ones. Each returns `Error: ...` with the fix when its package or a display is missing. `Backend` protocol so tests inject a fake.

- [ ] Tests with a fake backend: each tool calls the backend with the right arguments; missing backend gives the install hint; `open_path` with spaces; `see_screen` with no vision role says how to set one.
- [ ] Implement, pass, commit.

### Task 8: Supervisor, `anexis desktop`, `anexis ui`, reload

**Files:** Create `anexis/desktop/supervisor.py`, `anexis/desktop/watch.py`. Modify `anexis/cli/main.py`, `anexis/desktop/routes.py` (reload events from the ui watcher). Test `tests/test_supervisor.py`.

**Produces:**
- `watch.snapshot(root, suffixes) -> dict[str, float]`, `watch.changed(a, b) -> list[str]`
- `Supervisor(settings, on_ready).run()`: starts `python -m anexis serve`, prints one line `ANEXIS_READY {"url", "token"}` when `/health` answers, restarts on exit code 75 and on `.py` changes under `anexis/`, compiles changed files first and holds the restart with a published `brain_error` event when one fails
- `anexis desktop` runs the supervisor; `anexis ui` does the same and opens the browser
- `/events` carries `{"type": "reload", "files": [...]}` when `ui/` changes

- [ ] Tests: snapshot diff; a syntax error file blocks the restart and reports the file; exit code 75 restarts; a ui file touch produces a reload event.
- [ ] Implement, pass, commit.

### Task 9: The deck

**Files:** Create `ui/index.html`, `ui/deck.css`, `ui/themes.css`, `ui/js/*.js` (`api`, `main`, `boot`, `chat`, `terminal`, `stats`, `files`, `memory`, `tools`, `activity`, `setup`, `overlays`, `voice`, `appPanel`), `ui/vendor/` (xterm, fonts). Test `tests/ui/deck.spec.mjs` (Playwright against a real server with the scripted model).

- [ ] Vendor xterm 6 and two OFL fonts with their licence files.
- [ ] Build the layout and each panel against the routes above.
- [ ] Playwright: boot ends, setup overlay shows on a fresh home and saves, a chat round trip streams text, a tool call shows in the activity feed, stop works, the terminal echoes, files lists, themes switch, no console errors, phone width has no sideways scroll.
- [ ] Screenshots reviewed by eye. Commit.

### Task 10: The frame and the installer build

**Files:** Create `desktop/package.json`, `desktop/bootstrap.js`, `desktop/frame.js`, `desktop/preload.js`, `desktop/build.ps1`, `desktop/build/icon.*`, `desktop/README.md`. Test `desktop/test/seed.test.js` (node test runner).

**Produces:** `bootstrap.js` seeds and versions the live copy then loads `frame.js` from it with the packed copy as fallback; `frame.js` spawns the supervisor with the bundled runtime first on PATH, waits for `ANEXIS_READY`, opens the window at `url + "/ui/#token=..."`, tray icon, single instance, kills the process tree on quit.

- [ ] Tests: seeding into an empty folder; a version change backs up the old copy; a broken live `frame.js` falls back.
- [ ] Run the frame on Linux under xvfb against the dev checkout and take a screenshot.
- [ ] `build.ps1` steps are each checked on Linux where they have a Linux twin (relocatable Python plus packages runs from a moved folder).
- [ ] Commit.

### Task 11: Docs, final check, push

- [ ] README: a Windows section, the deck, live editing, control level, what was and was not run on the build machine.
- [ ] `uv run pytest -q`, `uv run ruff check anexis tests`, the Playwright run, all green.
- [ ] Push the branch, then fast forward `main` (the owner asked for main).
