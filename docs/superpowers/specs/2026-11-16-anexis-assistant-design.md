# Anexis: personal AI assistant server

Date: 2026-11-16
Status: approved and built. See "What changed during the build" at the end.

## What this is and why

Anexis is a personal assistant that lives on the owner's own server. The owner uses
it every day for school, for work, and to talk through random projects. Typing is
the main way to talk to it. Voice is the backup. It remembers what it learns about
the owner in a SQL database and gets more useful over time. It carries a large set
of tools pulled from GitHub, and it can write code by handing the job to Claude,
falling back to its own model when Claude usage runs out.

The repo should be clone and go: clone it on the server, run one install script,
type `anexis`.

## Assumptions to confirm

These came from a short message, so they are marked as guesses.

1. "Delete everything" means remove the Craftline site (the Next.js app, its tests
   and config) from this repo so the repo is only Anexis. It happens on the branch
   `claude/intelligent-lamport-p4fxk8`. The site stays in git history and on any
   other branch. If this branch later gets merged into whatever branch the live
   site deploys from, the live site goes away.
2. The assistant is called Anexis. The name is one config value, so it is cheap to
   change.

## Goals

1. Chat first CLI with streamed replies.
2. Voice as a backup way in and out, in the same CLI.
3. Model runs on Ollama (local) or Nvidia (hosted API), with automatic failover
   between them.
4. Adaptive SQL memory: learns facts, preferences, habits and corrections from
   every conversation and uses them in later ones.
5. A big tool belt sourced from GitHub, installed by script.
6. Code creation through Claude Code. When Claude usage is full, Anexis writes the
   code itself with its own model plus GitHub as reference.
7. A complete About Me (age, areas, projects, habits, classes and more) that Anexis
   always knows.
8. Simple CLI UI.
9. One command health check that says what works and what is missing.

## Not doing

1. Web or phone app.
2. More than one user.
3. Always listening wake word. Voice is push to talk.
4. Training or fine tuning model weights. "Learning" here means memory.
5. Keeping the Craftline site.
6. Email, calendar and other account connectors that need OAuth are listed in the
   tool manifest but switched off until the owner adds keys.

## Things that would make this a failure even if it runs

1. Anexis runs a destructive command, pushes code or sends something without asking.
2. The About Me or the memory database ends up in git or gets sent to an outside
   service the owner did not choose.
3. Anexis forgets things silently, or remembers wrong things with no way to see or
   fix them.
4. Hundreds of unreviewed tools get copied into the repo and run with full access.
5. Anexis says Claude wrote some code when the fallback did, or the other way round.

## Constraints

1. One Linux server. Must work with CPU only (slow but working) and better with an
   Nvidia GPU.
2. Python 3.11 or newer, installed with `uv`. Node is needed only for the tool
   servers that ship as npm packages.
3. No secrets, personal data or model files in the repo.
4. The build machine has no GPU, no Ollama and no Nvidia key. Everything is tested
   against stand ins there. The live check happens on the owner's server with
   `anexis doctor`.

## Approaches considered

**A. Own lean core, tools plugged in through MCP (picked).** A small Python
service owns the chat loop, the memory and the model routing. Tools from GitHub
are MCP servers named in a manifest file and pulled down by the install script.
Trade off: more code to write, but every part is small, the memory works exactly
the way described here, and adding a tool is one entry in a file.

**B. Stand on an existing assistant app** (Open WebUI and similar) and configure
it. Fastest to something that talks. But the memory would be whatever that app
does, it is web first not CLI first, the Claude with fallback coding flow does not
fit, and the owner ends up maintaining someone else's large app.

**C. Build on an agent framework** (LangChain style). Saves some loop code, costs
a heavy dependency that changes often and hides what the model is actually sent,
which makes small local models harder to debug.

A was picked because the owner asked for a server they own that keeps learning,
and the memory and the coding fallback are the special parts. Those need to be
ours. The owner talked about outcomes not stacks, so the picks in this document
are the designer's calls, open to correction.

## Shape

```
anexis serve   one long running process on the server (HTTP API on localhost)
anexis         the CLI, a thin client that talks to that API
```

Split this way because voice needs the microphone and speakers of the machine the
owner is sitting at, while the model, memory and tools sit on the server. When the
CLI runs on the server itself it uses localhost and nothing else is needed. From
another machine it uses `ANEXIS_URL` plus a bearer token. The server binds to
localhost unless told otherwise.

```
anexis/
  config.py        anexis.toml plus .env, one place
  server/          FastAPI: chat (streamed), voice, memory, health
  core/            the agent loop and context builder
  llm/             provider router: Ollama, Nvidia
  memory/          SQLite schema, recall, learn, consolidate
  tools/           registry, built in tools, MCP client, permissions, tool picker
  coder/           Claude Code runner and the fallback coder
  voice/           speech to text, text to speech
  profile/         About Me interview and import
  cli/             the terminal UI
  mcp_server.py    read only memory server for Claude Code
tools/manifest.yaml       every outside tool server, pinned
profile/about_me.example.yaml
setup.sh                one shot setup, opens the setup window
scripts/anexis.service      systemd unit
tests/
```

## Models

Both Ollama and Nvidia speak the OpenAI style chat API, so one client covers both.
Ollama is at `localhost:11434/v1`. Nvidia is at `integrate.api.nvidia.com/v1` with
a key from build.nvidia.com.

1. Config holds an ordered provider list. Default: Ollama first if it is running,
   Nvidia second if `NVIDIA_API_KEY` is set.
2. If a provider errors or times out, the router moves to the next one and marks
   the first as down for a short while.
3. Three model roles in config: `chat`, `coder`, `small` (used for memory
   extraction), plus `embed`. Default model names are chosen at build time from
   models that support tool calling, and are plain config so the owner can swap.
4. Final answers stream. For turns where tools are offered, if a streamed reply
   comes back empty with no tool call, the router retries that turn without
   streaming. (There are field reports of Ollama dropping tool calls when
   streaming.)

## Memory

SQLite, one file under `~/.anexis/`, WAL mode. Picked over Postgres because it needs
nothing installed and one person uses it. Tables:

| Table | Holds |
|---|---|
| `sessions` | each conversation, its mode (school, work, project, general), a summary |
| `messages` | the full transcript |
| `memories` | one learned thing per row: kind, text, confidence, importance, source, created, last used, use count, pinned, superseded by |
| `memories_fts` | full text index over memories |
| `memory_vectors` | an embedding per memory, when an embedding model is available |
| `tool_stats` | per tool: calls, failures, average time |
| `events` | a log of what the learner did, so changes can be explained |

Memory kinds: fact, preference, habit, project, class, person, task, lesson.
A lesson is a correction ("no, do it this way") and ranks high.

How it adapts:

1. **Recall.** Before each reply Anexis searches memories by text match and by
   embedding, then ranks by relevance, confidence, how recently and how often the
   memory was useful. Pinned About Me items always go in, in compact form.
   Without an embedding model it runs on text search alone.
2. **Learn.** After each turn, in the background, the small model reads the
   exchange and returns new things worth keeping as JSON. Each is compared with
   similar existing memories and then one of three things happens: reinforce
   (same thing again, confidence goes up), replace (it changed, the old row is
   marked superseded and kept), or add.
3. **Consolidate.** On a timer when idle: write session summaries, merge
   duplicates, and lower the rank of weak memories that never get used. Nothing
   is deleted by the machine. Pinned and About Me rows never decay.
4. **Tool learning.** `tool_stats` feeds the tool picker so tools that keep
   failing drop down the list.
5. **Owner control.** `/memory` to list and search, `/remember <text>`,
   `/forget <id>`, and `/why` to show which memories shaped the last reply.

## Tools

Three sources.

**Built in (Python, in this repo):** shell, read and write files, run Python, web
search, fetch a page, GitHub search and read, notes, todos, assignments and
deadlines, reminders, time and math, memory tools.

**From GitHub, through MCP:** `tools/manifest.yaml` lists each server with its
source repo, how to launch it, a pinned version, the keys it needs, a risk tier
and an on or off switch. `setup.sh` pulls them onto the server. The
starting set is the maintained reference servers (filesystem, git, fetch,
sequential thinking, time), the GitHub server, a browser automation server, a
library docs server, and school and research ones (papers, Wikipedia, video
transcripts). Target is about 25 to 30 servers. The exact list is settled during
the build, with one rule: an entry only goes in if the repo exists, its license
allows the use, and it is pinned to a version. Servers that need account logins
are in the file, switched off.

Nothing from those repos is copied into this repo. The manifest plus the script
gives the same result on the server and keeps the repo small and reviewable.

**Tool picker.** A local model cannot handle 150 tool descriptions at once. Each
turn Anexis offers only the handful that fit the message (matched by text and
embedding, weighted by `tool_stats`), plus one `find_tools` tool the model can
call to look for more.

**Permissions.** Every tool has a tier:

| Tier | Examples | Behavior |
|---|---|---|
| safe | search, read, time, notes | runs |
| write | create or edit files | runs inside the workspace folder, asks outside it |
| danger | shell, delete, git push, anything that sends | always asks y or n in the CLI |

The owner can loosen a tool in config. Default is the table above.

## Code creation

A `code_task` tool. Each project gets a folder under `~/anexis/workspace/`.

1. **Claude first.** Anexis runs Claude Code in headless mode inside the project
   folder with JSON output. Claude Code is installed and logged in once by the
   owner on the server (`anexis doctor` checks this).
2. **Knowing when usage is full.** Anexis reads the result envelope: the error
   flag, the error category (rate limit, billing) and the message text. Exit code
   alone is not trusted, since there are reports of limit errors that exit clean.
   When the limit is hit Anexis marks Claude unavailable until the stated reset
   time, or for 30 minutes if none is given.
3. **Fallback.** Anexis's own coder model does the job in a loop: plan, look up
   reference code with GitHub search and library docs, write, run the tests or
   the program, fix, repeat up to a set number of rounds.
4. **Honesty.** Every code result says which path made it.
5. **Claude MCP.** `anexis mcp` is a small read only MCP server that exposes the
   owner's About Me and memory search. The install script registers it with
   Claude Code, so when Claude writes code it can look up how the owner likes
   things done.

## Voice

1. Speech to text and text to speech both run on the server with local open
   models (Whisper family for hearing, Piper for speaking). No audio leaves the
   owner's machines.
2. In the CLI, `/voice` turns it on. Press Enter to start talking, Enter to stop.
   The words show up as text first, the reply streams as text and is spoken.
3. The CLI records and plays on the machine it runs on. If that machine has no
   microphone or speakers (a plain SSH session), Anexis says voice is not available
   here and carries on in text.
4. Voice packages are an optional install so text chat works without them.

## About Me

1. `profile/about_me.example.yaml` is committed as the template: name, age,
   where they live and the areas they move around in, school, classes and
   schedule, work, projects, habits, goals, interests, and how they want Anexis to
   talk to them.
2. The real `about_me.yaml` is gitignored.
3. `anexis aboutme` walks through the sections as a short interview in the CLI and
   can be rerun to update. `anexis aboutme import <file>` loads a filled in file.
4. Each item becomes a pinned memory with source `about_me`.

The designer has none of the owner's details. The owner fills this in on first
run.

## CLI

```
 anexis   ollama   memory 214   tools 28 of 162   mode school
 ________________________________________________________________

 you   whats due this week

 anexis  Two things. The chem lab writeup is due Thursday and ...
       used: assignments.list, 3 memories

 you   _

 /help  /voice  /mode  /memory  /tools  /code  /aboutme  /quit
```

Replies stream. A tool that needs permission shows what it wants to run and waits
for y or n. `anexis doctor` prints one line per part (model providers, memory,
each tool server, Claude Code, voice) with working or what is missing.

## Testing

1. Unit tests for the provider router, memory ranking and the learn step, the
   tool picker and the permission tiers.
2. A scripted fake model and a small stand in HTTP server that speaks the OpenAI
   style API, so the whole chat loop runs with no real model.
3. Memory tests use real SQLite.
4. MCP is tested against a tiny test server in the repo.
5. The Claude runner is tested with a fake `claude` program that returns a normal
   result, a limit result with an error exit, and a limit result with a clean
   exit.
6. What cannot be proven on the build machine (real Ollama, real Nvidia, real
   microphone) is listed in the README as "check with `anexis doctor` on your
   server".

## Build order

1. Remove the Craftline site. Project skeleton, config, provider router, CLI
   chat with streaming.
2. Memory: schema, recall, learn, consolidate, the memory commands.
3. Tools: registry, built ins, MCP client, manifest, picker, permissions.
4. Code creation: Claude runner, limit detection, fallback coder, `anexis mcp`.
5. Voice.
6. About Me, `anexis doctor`, install script, systemd unit, README.

Each step leaves something that runs and is tested.

## Left to the builder

1. Exact default model names for each role.
2. The final tool manifest, under the rule above.
3. Web search backend that needs no key.
4. Ranking weights for recall and the tool picker.
5. Library picks inside each part.

## What changed during the build

1. The owner confirmed both assumptions and said Claude runs on an API key.
   `ANTHROPIC_API_KEY` in `.env` is passed to Claude Code. A Claude login works too.
2. The real About Me answers live in `~/.anexis/` next to the database, not in the
   repo folder. A filled in `profile/about_me.yaml` is still ignored by git.
3. Piper (text to speech) is licensed GPL, so Anexis runs it as a separate program
   instead of importing it.
4. Reading files is fenced the same way as writing them: free inside the
   workspace, asks outside. Otherwise a web page could talk Anexis into reading
   keys off the server.
5. One approval covers a whole code task (writing files and running commands
   inside that project folder) instead of one question per command.
6. The manifest has 30 servers: 19 with no setup, 6 that turn on with a key, 5
   switched off. Only permissively licensed or first party servers were kept.
7. The official file and thinking servers need Node 24 or newer. The install
   script and `anexis doctor` check for it.
8. Nvidia defaults to one confirmed tool calling model for every role. Other
   model names could not be confirmed from the build machine.
9. The tool servers were verified against the package registries but not
   started on the build machine. `anexis tools sync` does that on the server.

## Second pass: system check and training

1. Fixed after a system check: Claude's real five hour limit wording, tool calls
   that share a stream index, models with no tool support, broken tool
   arguments, empty replies, history overflowing a small context window, and
   paths hidden under unusual argument names.
2. Standing instructions (lessons) are sent with every message instead of only
   when a search finds them.
3. Recall and tool picking tolerate misspelled and shortened words.
4. Anexis learns the owner's writing style from their own messages, and the upkeep
   writes a note on how they think.
5. `anexis train` plays a pack of owner style messages through the real chat and
   learn steps and scores the result. `training/like_me.yaml` holds what the
   owner said they want, plus made up practice facts that are never kept.
6. Ollama's default context window is small. `history_chars` bounds what is
   sent, and raising `OLLAMA_CONTEXT_LENGTH` on the server is worth doing.

## Third pass: installer and setup window

1. `setup.sh` at the top of the repo installs everything in six steps and can
   be run again safely. `--yes` asks nothing.
2. `anexis setup` is the setup window: preset (max, balanced, light, cloud, with
   the best fit for the machine marked), keys with hidden input and auto fill
   from the environment, options, and what to install. Every step can be
   skipped and nothing is written until the summary is confirmed.
3. The window writes a plan file of plain values. The script reads it line by
   line and never runs it as code.
4. Node 24 is installed into the home folder when missing, with its checksum
   verified, and tool servers prefer it.
5. `anexis stop` stops the server. A switch turns the outside tool servers off.
6. Three tool servers that did not start in a test run are off by default.

## Fourth pass: setup.sh and keys last

1. The installer is `setup.sh` in the top folder (`bash setup.sh`, and plain
   `bash setup` works too).
2. Order changed on the owner's request: choices, then every download, then the
   keys. Each option that needs a key is asked about on its own with what it
   turns on and where to get one. `anexis setup --keys` runs just that step.
3. Keys typed ahead during the downloads are thrown away before the key step,
   so a stray Enter cannot skip the first question.

## Fifth pass: the name and a simple start

1. The assistant is now called Anexis (it was Greg while it was being built).
   The command, the Python package, the home folder (`~/.anexis`), the settings
   file and the environment variables all use the new name. Nothing was
   deployed under the old name, so there is no migration.
2. `anexis` starts the chat from any folder. Setup adds its folder to PATH in
   the shell startup files, once.
3. `bash start` in the cloned folder does the same and works even before PATH
   is set up.
