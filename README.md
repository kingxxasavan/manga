# Anexis

A personal AI assistant that lives on your own server. You type to it in a simple
terminal chat, voice is the backup. It runs on Ollama or Nvidia, remembers what it
learns about you in a SQL database, carries a big set of tools pulled from GitHub,
and writes code through Claude, switching to its own coder when Claude usage runs
out.

Built for one person, for school, work and talking through projects.

## Set it up

On the server (Linux), clone it and run the setup from that folder:

```bash
git clone <this repo> anexis && cd anexis
bash setup.sh
```

(`bash setup` works too.) It goes in this order, so you answer a few quick
questions, walk away while it downloads, and only get asked for keys at the end:

1. **Your choices.** Three short windows, Enter always takes the suggestion.
   - **Preset.** It looks at your machine and marks the best fit.

     | Preset | What you get |
     |---|---|
     | Max | Biggest local models, widest memory, voice on. Wants a 16 GB GPU. |
     | Balanced | Good local models for an 8 GB GPU, Nvidia as backup. |
     | Light | Small local models for a machine with no GPU. |
     | Cloud | No local model. Everything on Nvidia's hosted models. |

   - **Options.** Name, voice, reaching it from other machines (makes the token
     for you), running in the background.
   - **What to install.** Ollama and the models, Node, Claude Code, the tool
     servers. Say n to skip any. What is already there is not offered again.

   Nothing is saved until you say yes on the summary.
2. **Everything downloads.** Models, Node, Claude Code, voice, tool servers.
3. **Keys, one option at a time.** For each thing that needs a key it says what
   the key turns on and where to get one, then asks for it by itself:
   Nvidia, Claude, GitHub, Notion, Brave, Tavily, Firecrawl, Exa. Paste and press
   Enter, typing stays hidden. Enter alone skips that option. A key already in
   your environment is filled in for you. A single `-` removes a saved one.
4. **Checkup.** `anexis doctor` runs and tells you what works.

```bash
bash setup.sh --yes               # ask nothing: best preset, keys from your environment
bash setup.sh --preset cloud      # pick the preset up front
bash setup.sh --no-setup          # skip the questions, install your last choices again
bash setup.sh --skip-models       # no model downloads this time
bash setup.sh --skip-tools        # no tool server downloads this time
bash setup.sh --skip-keys         # do not ask for keys this time
anexis setup --keys                 # only the keys, any time later
anexis setup                        # redo the choices and the keys
anexis stop                         # restart is: stop, then open the chat again
```

Hands free, with keys from the environment (never pass a key as an argument, those
land in your shell history):

```bash
NVIDIA_API_KEY=nvapi-... ANTHROPIC_API_KEY=sk-ant-... bash setup.sh --yes
```

Keys are saved to `~/.anexis/.env`, readable only by you. Settings go to
`~/.anexis/anexis.toml`, and an old one is backed up first.

## Start it

```bash
anexis          # from any folder
bash start      # or from the cloned folder, works even before PATH is set up
```

Setup puts the `anexis` command on your PATH for new terminals. `bash start` is
the same thing, and anything after it is passed on (`bash start doctor`).

Other commands:

```bash
anexis doctor      # one line per part: working, or what is missing and the fix
anexis aboutme     # tell Anexis who you are
anexis train       # practice run: talk to it your way and see what it learns
anexis             # chat
```

You need at least one model source:

| | How |
|---|---|
| **Ollama** (local, private) | Install from ollama.com. The install script pulls the default models. |
| **Nvidia** (hosted) | Get a key at build.nvidia.com and put `NVIDIA_API_KEY=...` in `~/.anexis/.env`. |

With both, Ollama is tried first and Nvidia takes over if it is down, and back again.

Ollama's default context window is small, and when it overflows the model quietly
loses its instructions. If you have the memory for it, start Ollama with a bigger
one, for example `OLLAMA_CONTEXT_LENGTH=16384 ollama serve`. Anexis also caps how
much history it sends (`history_chars` in `anexis.toml`).

For code creation through Claude: `npm install -g @anthropic-ai/claude-code`, then
either put `ANTHROPIC_API_KEY=...` in `~/.anexis/.env` or run `claude` once to log in.
Without it Anexis still codes, using its own model.

The installer puts `uv` and Node 24 in your home folder when they are missing. No
root needed, except for Ollama's own installer.

## Using it

```
 anexis   ollama   memory 214   tools 162   mode school
 ________________________________________________________________

 you   whats due this week

 anexis  Two things. The chem lab writeup is due Thursday and ...
       used: list_items, 3 memories
```

| Command | What it does |
|---|---|
| `/mode school` | general, school, work or project |
| `/memory [words]` | what Anexis remembers, or search it |
| `/remember <text>` | save something on purpose |
| `/forget <id>` | delete a memory for real |
| `/why` | which memories shaped the last reply |
| `/code <what>` | build something |
| `/tools` | tool servers and their state |
| `/aboutme` | tell Anexis about yourself, or update it |
| `/voice` | voice on or off |
| `/doctor` | check every part |
| `/new` | fresh conversation (memory stays) |
| `/quit` | leave |

Outside the chat: `anexis ask "question"` for one answer in a script, `anexis memory`,
`anexis tools list`, `anexis tools sync`, `anexis aboutme import file.yaml`, `anexis train`.

## How the memory learns

Everything is in one SQLite file, `~/.anexis/anexis.db`.

1. **Recall.** Before each reply Anexis searches its memories by words and by
   meaning, then ranks them by how sure it is, how important, and how recently and
   often each one was useful. Your About Me is always included.
2. **Learn.** After each exchange a small model looks at what you said and proposes
   changes. Something new is added. Something said again makes Anexis more sure.
   Something that changed replaces the old memory, and the old one is kept as
   history. When you correct Anexis ("no, do it this way") that is saved as a lesson
   and ranks above ordinary facts.
3. **Upkeep.** Every hour: long conversations get summarized, duplicates are
   merged, and memories nobody has needed for a month slowly drop in rank. Anexis
   never deletes a memory on its own. Only `/forget` deletes.
4. **Tools too.** Anexis tracks which tools work and which keep failing, and prefers
   the ones that work.
5. **Standing instructions are always on.** Anything you told Anexis about how to
   behave ("no dashes", "dont ask a bunch of questions") is sent with every
   message, strongest first. It does not depend on a search finding it.
6. **Typos are fine.** Recall and tool picking both guess what a misspelled word
   meant ("chemestry assigment", "serach") and match shortened words ("chem").
7. **It learns how you talk and think.** From your own messages Anexis works out
   your style (casual or formal, short or long, orders or questions) and tells
   the model to answer to match. Once you have sent about 20 messages, the upkeep
   also writes a short note on how you think and what you value, and keeps it up
   to date. That note is a normal memory, so `/memory` shows it and `/forget`
   removes it.

You stay in control with `/memory`, `/why`, `/remember` and `/forget`.

## Train it to talk like you

`anexis train` talks to Anexis the way you talk (fast, no punctuation, misspelled, a
few asks at once) and then checks what stuck. It uses `training/like_me.yaml`:

1. **Teach.** Things you said you want: no dashes, casual, type first and voice as
   backup, Claude first for code, build instead of asking questions, always the
   maxed out version.
2. **Practice.** Made up sample facts (a chem lab, a work shift) to test recall.
   These are never kept.
3. **Probes.** Sloppy questions asked afterwards.

The report scores six things: what was learned, whether repeating something made
Anexis more sure without a second copy, whether a change replaced the old fact,
whether a typo filled question recalled the right memory, whether your standing
instructions reach the model on an unrelated topic, and whether the right tool was
offered.

```bash
anexis train             # practice on a throwaway memory with your real model
anexis train --keep      # the same teaching, written into Anexis's real memory
anexis train --offline   # no model needed, checks everything around the model
```

Edit the pack to add your own lines. Anything in `teach` is safe to keep, so only
put true things there.

## About Me

`anexis aboutme` asks about you: name, age, where you live and move around, school
and classes, work, schedule, projects, habits, goals, interests, people, tools, how
you want to be talked to, and what to never do. Enter keeps an answer, a single `-`
clears it, and lists use `;` between items.

Or fill in a file: copy `profile/about_me.example.yaml` to `profile/about_me.yaml`
and run `anexis aboutme import profile/about_me.yaml`. Any extra section you add to
the file is kept too.

Your answers are stored in `~/.anexis/` on your server only. The filled in file is
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

None of that code is copied into this repo. `anexis tools sync` downloads each
server at its pinned version and checks that it starts. To add a tool, add an
entry to the manifest.

**Code creation:** see below.

A local model cannot handle hundreds of tool descriptions at once, so each turn
Anexis offers the model only the dozen that best fit your message. The model can ask
for more with `find_tools`.

### What runs without asking

| Kind of tool | Behavior |
|---|---|
| Reading, searching, notes, math | runs |
| File tools | run freely inside `~/anexis/workspace`, ask outside it |
| Shell, Python, code tasks, browser, anything that sends or deletes | always asks y or n |

If nobody answers within five minutes the answer is no. You can loosen a single
tool in `anexis.toml` under `[permissions]`.

Each tool server only receives the environment variables its manifest entry names.
Your other keys are not shared with it.

## Code creation

Ask for something to be built, or use `/code`. Each project gets its own folder in
`~/anexis/workspace/`. You approve once per task, and that covers writing files and
running commands inside that project folder.

1. **Claude first.** Anexis runs Claude Code in the project folder.
2. **When Claude usage is full,** Anexis notices (it reads what Claude reports, not
   just the exit code), rests Claude until the reset time Claude gives, or 30
   minutes when it gives none, and does the job with its own coder model. That
   coder looks up reference code on GitHub and library docs, writes files, runs
   them, and fixes what fails. It cannot write outside the project folder and
   refuses sudo, pushing, and piping downloads into a shell.
3. **Every result says who wrote it**, Claude or Anexis's own coder, and why.

The install script also registers `anexis mcp` with Claude Code. It is a small read
only server that lets Claude look up your About Me and your preferences while it
writes your code.

## Voice

Say yes to voice in the setup window. In the chat, `/voice` turns it on.
Press Enter on an empty line to talk, Enter again to stop. What Anexis heard shows
as text, the reply streams as text and is read aloud.

Speech to text (Whisper) and text to speech (Piper) both run on your server. No
audio goes to an outside service. The microphone and speakers are the ones on the
machine the `anexis` chat runs on. Over a plain SSH session there are none, so Anexis
says so and stays in text.

## Reaching Anexis from another machine

By default the server only listens on the server itself. To chat from a laptop:

On the server, in `~/.anexis/.env`:

```
ANEXIS_HOST=0.0.0.0
ANEXIS_TOKEN=<long random string>
```

On the laptop, install the repo the same way and set:

```
ANEXIS_URL=http://your-server:8765
ANEXIS_TOKEN=<the same string>
```

Anexis refuses to listen beyond localhost without a token. The connection is plain
HTTP, so use it on a network you trust or through a tunnel (Tailscale, SSH port
forward).

## Keep it running

`scripts/anexis.service` is a systemd user unit with the steps at the top of the
file. Without it, the `anexis` chat starts the server for you when it is not running.

## Settings

Copy `anexis.toml.example` to `anexis.toml` to change models, limits and permissions.
Keys go in `.env` (see `.env.example`), never in `anexis.toml`.

## Development

```bash
uv sync
uv run pytest        # 288 tests
uv run ruff check anexis tests
```

The tests use a scripted stand in for the model and a real SQLite database, a real
HTTP server, a real MCP test server, and fake `claude` and `piper` programs.

### What was and was not checked on the build machine

Checked: the whole test suite, plus a real run of `anexis serve`, `anexis ask`,
`anexis doctor`, `anexis aboutme` and the interactive chat against a stand in model
server speaking the same API as Ollama. One real Claude Code run through Anexis's
own runner (it wrote and ran a file). `anexis train --offline`, 32 of 32.

Not checked there, so check with `anexis doctor` on your server:

1. A real Ollama or Nvidia model. The default model names are in
   `anexis.toml.example`. `anexis doctor` tells you if one is missing.
2. The outside tool servers, properly. 15 of them started in one test run. Three
   did not (file conversion, PowerPoint, paper search) and are switched off in the
   manifest. DeepWiki could not be reached from the build machine. Run
   `anexis tools sync` to see how they do on yours.
3. `anexis train` with a real model. Offline mode proves the storage, recall and
   tool picking. Only a real model shows how well the learn step pulls facts out
   of what you say, so run `anexis train` once on your server.
4. A real microphone.
5. Installing Ollama, pulling models, voice and the background service. The rest
   of `setup.sh` was run for real in a throwaway home folder, including the
   Node 24 download.

## Layout

```
anexis/config.py        settings
anexis/llm/             Ollama and Nvidia client, failover
anexis/memory/          SQLite store, ranking, learning, style, upkeep
anexis/core/            the chat loop, app wiring, doctor, training run
anexis/tools/           registry, picker, permissions, built ins, MCP client
anexis/coder/           Claude runner, limit detection, fallback coder
anexis/voice/           speech in and out
anexis/profile/         About Me
anexis/server/          HTTP API
anexis/cli/             the chat screen and the anexis command
anexis/mcp_server.py    read only memory server for Claude Code
tools/manifest.yaml   the outside tools, pinned
training/like_me.yaml the training pack
docs/                 the design
```
