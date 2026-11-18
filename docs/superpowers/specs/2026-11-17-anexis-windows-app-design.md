# Anexis for Windows: one installer, a control deck, live editing

## Intent

Anexis runs on a Linux server today and is used through a terminal, which means
opening a cloud shell wherever the owner is. The owner wants it as a normal
Windows app: one installer with everything inside, no scripts, a setup screen for
keys and choices, control of the PC from the first launch, a futuristic control
deck in the spirit of eDEX UI that shows everything Anexis can do, and a way for
Claude to change the app without building a new installer each time.

## Goals

1. One `AnexisSetup.exe`. After it, Anexis starts from the Start menu.
2. Python, the Python packages, Node and uv ship inside the installer.
3. First launch opens a setup screen: preset, options, keys, then downloads.
4. Full control of the PC by default: shell, files anywhere, apps, windows,
   clipboard, screenshots, mouse and keyboard. Every action is shown live and
   one button stops the running job. A switch brings back "ask first".
5. A control deck with a panel for each thing Anexis does: chat, terminal,
   system stats, files, memory, tools, coder, checkup, voice, keys, About Me.
6. Editing a file changes the running app. UI files reload the window, Python
   files restart the brain. No new installer for either.
7. The same deck works on Linux in a browser (`anexis ui`), which is also how it
   is tested here.

## Not goals

1. A hosted build pipeline. The owner builds the installer on their own PC with
   one command.
2. Code signing, auto update, macOS packaging.
3. Changing how memory, learning or the tool servers work.

## What would make it a failure

1. A web page in the owner's browser being able to drive the PC through the
   local server. The server is the thing with full control, so it must only
   answer the app.
2. Edits by Claude being lost without a trace when a new installer runs.
3. The Linux terminal chat breaking.

## Constraints

1. This build machine is Linux. The Windows installer cannot be built or run
   here. What is checked here: the Python side with tests, the deck in a real
   browser against a real server, the frame under a virtual display on Linux.
2. The Windows only paths (ConPTY terminal, Ollama installer, desktop control)
   are written against documented behaviour and are not run here.
3. Local chat models cannot see images, so mouse work needs a vision model.

## Approaches

1. **Electron frame, deck served by the Python server (picked).** The deck is
   plain HTML, CSS and JS that the Anexis server serves. The frame only starts
   the brain, opens a window on it and packs the installer. Everything that
   matters is testable in a browser on Linux, real terminal panels work through
   xterm.js, and plain files give live editing for free.
2. **Tauri.** Smaller installer, but cross building is harder, the frame logic
   moves to Rust, and it adds nothing the picked approach lacks.
3. **pywebview with PyInstaller.** One language, but live editing fights the
   frozen bundle and there is no good installer story.

The owner approved approach 1 on 2026 11 17.

## How it fits together

```
AnexisSetup.exe (NSIS, per user, no admin)
  Anexis.exe            Electron frame: bootstrap.js -> frame.js
  resources/runtime/    python/  node/  uv.exe
  resources/source/     anexis/ ui/ desktop/frame.js tools/ training/ profile/

First launch copies resources/source to  %LOCALAPPDATA%\Anexis\app   (the live copy)
The frame runs:  runtime\python\python.exe -m anexis desktop   (cwd = live copy)

anexis desktop  = supervisor: starts `anexis serve`, restarts it when a .py file
                  changes or when the server asks, prints one ready line with the URL
anexis serve    = the existing server, plus the deck at /ui and the new routes
```

**Live editing.** The live copy is ordinary files. The server watches `ui/` and
tells the page to reload. The supervisor watches `anexis/` and restarts the
brain. `frame.js` is loaded from the live copy too, with the packed copy as the
fallback when the live one fails to load. The deck has an App panel that shows
the folder, opens Claude Code in it and restarts or reloads on demand. A new
installer version moves the old live copy to `app-backup-<version>` before it
puts the new one in place, and says so.

**Lock on the local server.** In desktop mode a token is always made and kept in
`.env`. Every route needs it, the terminal socket needs it, and the server
rejects a Host header that is not loopback, which stops DNS rebinding. The deck
files themselves are public, they hold no secrets. The frame hands the token to
the page in the URL fragment.

**Control level.** A new `control` setting: `full` or `ask`. With `full` every
tool runs without asking. Setup in the app writes `full` unless the owner turns
it off. The terminal chat on a server keeps `ask` as its default. Every tool
call goes to an activity feed, and `/chat/stop` cancels the running turn.

**Windows versions of Linux only code.** Process groups, the shell tool
(PowerShell on Windows), stopping the server, the tool path separator, file
permissions, machine detection.

**New tools** (group `desktop`, loaded only when their packages are there):
open an app, file or link; list, focus and close windows; clipboard read and
write; screenshot; type text, press keys, move and click the mouse; list and
end processes; `see_screen`, which sends a screenshot to a vision model when a
`vision` role is set.

**New routes.** `/ui` (static), `/events` (activity and reload stream),
`/system/stats`, `/files`, `/files/open`, `/terminal` (socket), `/chat/stop`,
`/setup` (state, apply, install with progress), `/settings`, `/app` (info,
restart), `/sessions/new`.

**The deck.** No build step: ES modules, one stylesheet, xterm.js and two fonts
kept in `ui/vendor`. A boot sequence, a top bar with status and the stop
button, system stats on the left, chat with tabs for terminal and coder in the
middle, memory, tools and due items on the right, files and the activity feed
along the bottom. Overlays for setup, keys, checkup, About Me and the App
panel. Four colour themes. Its own look, not a copy of eDEX UI.

**Building the installer** (on Windows): `desktop\build.ps1`. It downloads a
relocatable Python, installs the packages into it, downloads Node and uv, then
runs electron builder. Output: `desktop\dist\AnexisSetup.exe`.

## Left to the builder

File names inside `ui/`, the exact panel layout, polling intervals, theme
colours, the wording of every message, and test layout.

## Calls made without asking

1. Reading "4 I can do myself" as: the owner builds the installer on Windows.
2. Token on by default in desktop mode, because of full control.
3. A version change backs up the live copy instead of merging it.
4. `see_screen` ships with no vision model set, since model names differ per
   provider.
