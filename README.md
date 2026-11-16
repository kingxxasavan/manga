# Greg

A personal AI assistant that lives on your own server. You type to it in a simple
terminal chat, voice is the backup. It runs on Ollama or Nvidia, remembers what it
learns about you in a SQL database, carries a big set of tools pulled from GitHub,
and writes code through Claude, switching to its own coder when Claude usage runs
out.

Built for one person, for school, work and talking through projects.

## Set it up

On the server (Linux):

```bash
git clone <this repo> greg && cd greg
./install.sh
```

That installs Greg and opens the setup window. Four short steps, and Enter always
takes the suggestion or skips:

1. **Preset.** It looks at your machine and marks the best fit.

   | Preset | What you get |
   |---|---|
   | Max | Biggest local models, widest memory, voice on. Wants a 16 GB GPU. |
   | Balanced | Good local models for an 8 GB GPU, Nvidia as backup. |
   | Light | Small local models for a machine with no GPU. |
   | Cloud | No local model. Everything on Nvidia's hosted models. |

2. **Keys.** Paste and press Enter, typing stays hidden. A key already in your
   environment is filled in for you. Enter skips or keeps, a single `-` removes.
3. **Options.** Name, voice, reaching it from other machines (makes the token
   for you), running in the background.
4. **What to install.** Ollama and the models, Node, Claude Code, the tool
   servers. Say n to skip any. What is already there is not offered again.

Nothing is saved until you say yes on the summary. Then the script installs what
you picked and finishes with a checkup.

```bash
./install.sh --yes               # ask nothing: best preset, keys from your environment
./install.sh --preset cloud      # pick the preset up front
./install.sh --no-setup          # skip the window, install your last choices again
./install.sh --skip-models       # no model downloads this time
./install.sh --skip-tools        # no tool server downloads this time
greg setup                       # just the window, to change settings later
greg stop                        # restart is: stop, then open the chat again
```

Hands free, with keys from the environment (never pass a key as an argument, those
land in your shell history):

```bash
NVIDIA_API_KEY=nvapi-... ANTHROPIC_API_KEY=sk-ant-... ./install.sh --yes
```

Keys are saved to `~/.greg/.env`, readable only by you. Settings go to
`~/.greg/greg.toml`, and an old one is backed up first.

Then:

```bash
greg doctor      # one line per part: working, or what is missing and the fix
greg aboutme     # tell Greg who you are
greg train       # practice run: talk to it your way and see what it learns
greg             # chat
```

You need at least one model source:

| | How |
|---|---|
| **Ollama** (local, private) | Install from ollama.com. The install script pulls the default models. |
| **Nvidia** (hosted) | Get a key at build.nvidia.com and put `NVIDIA_API_KEY=...` in `~/.greg/.env`. |

With both, Ollama is tried first and Nvidia takes over if it is down, and back again.

Ollama's default context window is small, and when it overflows the model quietly
loses its instructions. If you have the memory for it, start Ollama with a bigger
one, for example `OLLAMA_CONTEXT_LENGTH=16384 ollama serve`. Greg also caps how
much history it sends (`history_chars` in `greg.toml`).

For code creation through Claude: `npm install -g @anthropic-ai/claude-code`, then
either put `ANTHROPIC_API_KEY=...` in `~/.greg/.env` or run `claude` once to log in.
Without it Greg still codes, using its own model.

The installer puts `uv` and Node 24 in your home folder when they are missing. No
root needed, except for Ollama's own installer.

## Using it

```
 greg   ollama   memory 214   tools 162   mode school
 ________________________________________________________________

 you   whats due this week

 greg  Two things. The chem lab writeup is due Thursday and ...
       used: list_items, 3 memories
```

| Command | What it does |
|---|---|
| `/mode school` | general, school, work or project |
| `/memory [words]` | what Greg remembers, or search it |
| `/remember <text>` | save something on purpose |
| `/forget <id>` | delete a memory for real |
| `/why` | which memories shaped the last reply |
| `/code <what>` | build something |
| `/tools` | tool servers and their state |
| `/aboutme` | tell Greg about yourself, or update it |
| `/voice` | voice on or off |
| `/doctor` | check every part |
| `/new` | fresh conversation (memory stays) |
| `/quit` | leave |

Outside the chat: `greg ask "question"` for one answer in a script, `greg memory`,
`greg tools list`, `greg tools sync`, `greg aboutme import file.yaml`, `greg train`.

## How the memory learns

Everything is in one SQLite file, `~/.greg/greg.db`.

1. **Recall.** Before each reply Greg searches its memories by words and by
   meaning, then ranks them by how sure it is, how important, and how recently and
   often each one was useful. Your About Me is always included.
2. **Learn.** After each exchange a small model looks at what you said and proposes
   changes. Something new is added. Something said again makes Greg more sure.
   Something that changed replaces the old memory, and the old one is kept as
   history. When you correct Greg ("no, do it this way") that is saved as a lesson
   and ranks above ordinary facts.
3. **Upkeep.** Every hour: long conversations get summarized, duplicates are
   merged, and memories nobody has needed for a month slowly drop in rank. Greg
   never deletes a memory on its own. Only `/forget` deletes.
4. **Tools too.** Greg tracks which tools work and which keep failing, and prefers
   the ones that work.
5. **Standing instructions are always on.** Anything you told Greg about how to
   behave ("no dashes", "dont ask a bunch of questions") is sent with every
   message, strongest first. It does not depend on a search finding it.
6. **Typos are fine.** Recall and tool picking both guess what a misspelled word
   meant ("chemestry assigment", "serach") and match shortened words ("chem").
7. **It learns how you talk and think.** From your own messages Greg works out
   your style (casual or formal, short or long, orders or questions) and tells
   the model to answer to match. Once you have sent about 20 messages, the upkeep
   also writes a short note on how you think and what you value, and keeps it up
   to date. That note is a normal memory, so `/memory` shows it and `/forget`
   removes it.

You stay in control with `/memory`, `/why`, `/remember` and `/forget`.

## Train it to talk like you

`greg train` talks to Greg the way you talk (fast, no punctuation, misspelled, a
few asks at once) and then checks what stuck. It uses `training/like_me.yaml`:

1. **Teach.** Things you said you want: no dashes, casual, type first and voice as
   backup, Claude first for code, build instead of asking questions, always the
   maxed out version.
2. **Practice.** Made up sample facts (a chem lab, a work shift) to test recall.
   These are never kept.
3. **Probes.** Sloppy questions asked afterwards.

The report scores six things: what was learned, whether repeating something made
Greg more sure without a second copy, whether a change replaced the old fact,
whether a typo filled question recalled the right memory, whether your standing
instructions reach the model on an unrelated topic, and whether the right tool was
offered.

```bash
greg train             # practice on a throwaway memory with your real model
greg train --keep      # the same teaching, written into Greg's real memory
greg train --offline   # no model needed, checks everything around the model
```

Edit the pack to add your own lines. Anything in `teach` is safe to keep, so only
put true things there.

## About Me

`greg aboutme` asks about you: name, age, where you live and move around, school
and classes, work, schedule, projects, habits, goals, interests, people, tools, how
you want to be talked to, and what to never do. Enter keeps an answer, a single `-`
clears it, and lists use `;` between items.

Or fill in a file: copy `profile/about_me.example.yaml` to `profile/about_me.yaml`
and run `greg aboutme import profile/about_me.yaml`. Any extra section you add to
the file is kept too.

Your answers are stored in `~/.greg/` on your server only. The filled in file is
ignored by git.

## Tools

Three kinds.

**Built in:** shell, Python, files, web search, page fetch, GitHub search and read,
calculator, notes, todos, assignments, reminders, memory.

**From GitHub:** `tools/manifest.yaml` lists 30 MCP servers with a pinned version
each. 16 run with no setup: files, git, step by step thinking, time, calculator,
page fetch, DuckDuckGo search, library docs, DeepWiki, Wikipedia, arXiv, YouTube
transcripts, browser automation, Word, Excel and charts. 6 turn on when you add
their key: GitHub, Notion, Brave, Tavily, Firecrawl, Exa. 8 are listed but off
until you flip `enabled`: Google Workspace, Chrome DevTools, Jupyter, Zotero,
Desktop Commander, and three that did not start in a test run (file conversion,
PowerPoint, paper search).

None of that code is copied into this repo. `greg tools sync` downloads each
server at its pinned version and checks that it starts. To add a tool, add an
entry to the manifest.

**Code creation:** see below.

A local model cannot handle hundreds of tool descriptions at once, so each turn
Greg offers the model only the dozen that best fit your message. The model can ask
for more with `find_tools`.

### What runs without asking

| Kind of tool | Behavior |
|---|---|
| Reading, searching, notes, math | runs |
| File tools | run freely inside `~/greg/workspace`, ask outside it |
| Shell, Python, code tasks, browser, anything that sends or deletes | always asks y or n |

If nobody answers within five minutes the answer is no. You can loosen a single
tool in `greg.toml` under `[permissions]`.

Each tool server only receives the environment variables its manifest entry names.
Your other keys are not shared with it.

## Code creation

Ask for something to be built, or use `/code`. Each project gets its own folder in
`~/greg/workspace/`. You approve once per task, and that covers writing files and
running commands inside that project folder.

1. **Claude first.** Greg runs Claude Code in the project folder.
2. **When Claude usage is full,** Greg notices (it reads what Claude reports, not
   just the exit code), rests Claude until the reset time Claude gives, or 30
   minutes when it gives none, and does the job with its own coder model. That
   coder looks up reference code on GitHub and library docs, writes files, runs
   them, and fixes what fails. It cannot write outside the project folder and
   refuses sudo, pushing, and piping downloads into a shell.
3. **Every result says who wrote it**, Claude or Greg's own coder, and why.

The install script also registers `greg mcp` with Claude Code. It is a small read
only server that lets Claude look up your About Me and your preferences while it
writes your code.

## Voice

Say yes to voice in the setup window. In the chat, `/voice` turns it on.
Press Enter on an empty line to talk, Enter again to stop. What Greg heard shows
as text, the reply streams as text and is read aloud.

Speech to text (Whisper) and text to speech (Piper) both run on your server. No
audio goes to an outside service. The microphone and speakers are the ones on the
machine the `greg` chat runs on. Over a plain SSH session there are none, so Greg
says so and stays in text.

## Reaching Greg from another machine

By default the server only listens on the server itself. To chat from a laptop:

On the server, in `~/.greg/.env`:

```
GREG_HOST=0.0.0.0
GREG_TOKEN=<long random string>
```

On the laptop, install the repo the same way and set:

```
GREG_URL=http://your-server:8765
GREG_TOKEN=<the same string>
```

Greg refuses to listen beyond localhost without a token. The connection is plain
HTTP, so use it on a network you trust or through a tunnel (Tailscale, SSH port
forward).

## Keep it running

`scripts/greg.service` is a systemd user unit with the steps at the top of the
file. Without it, the `greg` chat starts the server for you when it is not running.

## Settings

Copy `greg.toml.example` to `greg.toml` to change models, limits and permissions.
Keys go in `.env` (see `.env.example`), never in `greg.toml`.

## Development

```bash
uv sync
uv run pytest        # 279 tests
uv run ruff check greg tests
```

The tests use a scripted stand in for the model and a real SQLite database, a real
HTTP server, a real MCP test server, and fake `claude` and `piper` programs.

### What was and was not checked on the build machine

Checked: the whole test suite, plus a real run of `greg serve`, `greg ask`,
`greg doctor`, `greg aboutme` and the interactive chat against a stand in model
server speaking the same API as Ollama. One real Claude Code run through Greg's
own runner (it wrote and ran a file). `greg train --offline`, 32 of 32.

Not checked there, so check with `greg doctor` on your server:

1. A real Ollama or Nvidia model. The default model names are in
   `greg.toml.example`. `greg doctor` tells you if one is missing.
2. The outside tool servers, properly. 15 of them started in one test run. Three
   did not (file conversion, PowerPoint, paper search) and are switched off in the
   manifest. DeepWiki could not be reached from the build machine. Run
   `greg tools sync` to see how they do on yours.
3. `greg train` with a real model. Offline mode proves the storage, recall and
   tool picking. Only a real model shows how well the learn step pulls facts out
   of what you say, so run `greg train` once on your server.
4. A real microphone.
5. Installing Ollama, pulling models, voice and the background service. The rest
   of `install.sh` was run for real in a throwaway home folder, including the
   Node 24 download.

## Layout

```
greg/config.py        settings
greg/llm/             Ollama and Nvidia client, failover
greg/memory/          SQLite store, ranking, learning, style, upkeep
greg/core/            the chat loop, app wiring, doctor, training run
greg/tools/           registry, picker, permissions, built ins, MCP client
greg/coder/           Claude runner, limit detection, fallback coder
greg/voice/           speech in and out
greg/profile/         About Me
greg/server/          HTTP API
greg/cli/             the chat screen and the greg command
greg/mcp_server.py    read only memory server for Claude Code
tools/manifest.yaml   the outside tools, pinned
training/like_me.yaml the training pack
docs/                 the design
```
