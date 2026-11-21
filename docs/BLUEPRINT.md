# Anexis / JARVIS: how it was built, and how to build it cleaner

This is everything the first version of Anexis does and how each part works,
written so a clean rebuild can keep the good ideas and skip the mess. The
first version lives in this repo (kingxxasavan/manga). Section 9 says what to
do differently, section 10 is a build order for the rebuild.

---

## 1. What it is

A personal assistant that lives on your own PC (Windows) and also on a school
server, with one memory between them. You talk to it by voice ("Jarvis, ...")
or text. It knows you, remembers what matters, uses tools on your computer,
watches your school work, and checks in on its own.

What it can do today (keep all of this):

* **Chat** with memory of you, in your own style, with past chats, new chat, clear chat.
* **JARVIS voice**: say "Jarvis" and talk, it answers out loud, you can talk over it, it asks out loud before risky stuff ("Jarvis, go ahead").
* **The JARVIS circle**: home screen, black with a blue circle that lights with whoever is talking.
* **Memory** that learns from every chat, ranks what it knows, forgets slowly, and never loses pinned facts.
* **About Me**: things about you that are always known.
* **Tools**: files, shell, Python, desktop control (apps, windows, keyboard, mouse, screen), web search, GitHub, plus any MCP tool server.
* **Coding**: hands code tasks to Claude Code on your Pro plan, switches to Opus at 85% usage, own fallback coder when Claude is out.
* **Canvas** (school site): missing and upcoming work, reminders, download slides. Sign in through a browser window, no password stored.
* **On its own** (autonomy): every hour it looks at what is due, the PC's health, what it does not know about you, and maybe says something, asks one question or does a task.
* **School server + Jarvis CLI**: same brain on a server, a plain terminal chat at school, memory synced with the PC when it starts and every 15 minutes.
* **Desktop app**: one installer, tray, start with Windows, full screen, notifications, live editing without rebuilding.
* **Models**: Nvidia, Ollama local, Ollama cloud, live model lists, a model per job, a fast model just for tool calls.
* **Game mode**: with a full screen game in front, JARVIS only answers to its name and keeps check ins to itself.

---

## 2. The big picture

```
 Electron window (desktop/frame.js)          school server
   |  starts, keeps alive, tray, notifications       (same brain, `anexis serve`, Jarvis CLI)
   v                                                   ^
 Supervisor  (anexis desktop)                          | memory sync (HTTP, every 15 min)
   |  restarts the brain when a .py file changes       |
   v                                                   |
 Brain  (anexis serve, FastAPI on 127.0.0.1) ----------+
   |-- agent loop ------- model router --> Nvidia / Ollama / Ollama cloud (OpenAI style API)
   |-- memory (one SQLite file)
   |-- tools: built in + MCP tool servers (node, stdio) + Claude Code (subprocess)
   |-- voice engine (JARVIS, from Hail Mary)
   |-- background loops: learning upkeep, Canvas sync, school sync, check ins, game check
   |-- event bus --> /events (one JSON per line) --> the deck
   v
 Deck  (ui/: plain HTML, CSS, JS modules, no build step, served at /ui)
```

Three processes on the PC (window, supervisor, brain) plus children of the
brain (tool servers, Claude Code). Everything talks HTTP on localhost.

---

## 3. The brain, part by part

### Settings (`anexis/config.py`)
Defaults, then `anexis.toml`, then `.env` files, then real environment
variables. Sections: providers (with a model per role), memory, agent, coder,
voice, llm, tools. Keys live only in `.env`.

### Server and safety (`anexis/server/app.py`)
* Only answers on loopback, and checks Host and Origin are loopback too, so a
  web page cannot talk to it.
* Every route needs the token (Bearer), except the static deck files at /ui.
  The terminal websocket sends the token in its first message.
* `/chat` streams the reply, `/chat/stop` ends a running turn, `/events` is the
  live feed (one JSON object per line).

### Event bus (`anexis/core/events.py`)
One place every part reports what it is doing (tool started, reply done,
voice heard, check in said, game started). The deck and the voice log just
listen. Keeps the last 200 activity events for a deck that opens late.

### The agent loop (`anexis/core/agent.py`)
Each turn:
1. Build the system prompt: name, time, mode (general, school, work, project),
   control level, **About you** (pinned memories, up to 3000 chars),
   **lessons** (standing instructions, up to 1500 chars), **how you talk**
   (style), **recalled memories** (search on the message), **due soon**, and
   the summary of this chat so far.
2. Pick tools: the core tools plus the 12 best matches for the message
   (words and meaning). The model can call `find_tools` for more. A local
   model gets lost with 150 tools, this keeps it sharp.
3. Ask the model. Tool calls go to the fast **tools** model when one is set.
   Calls that do not need asking run in parallel.
4. Repeat until it answers in words. Then the learn step runs in the background.

### Control and asking first (`anexis/tools/permissions.py`)
Two levels: **full** (tools just run) and **ask** (risky tools wait for a yes,
in the deck or out loud). Every tool says if it is risky.

### Models (`anexis/llm/router.py`, `anexis/desktop/models.py`)
* Any server that speaks the OpenAI chat API is a provider. Providers are tried in order, the next one takes over when one fails.
* Roles: **chat** (main), **tools** (fast tool picker), **coder**, **small** (background jobs), **embed** (meaning search), **vision**. An empty role falls back to chat, except vision.
* Model lists come live from each provider. Retired models get swapped for the closest one that exists ("heal"), because a fixed model name breaks the day it gets retired.
* Detects "this model does not support tools" and retries without tools.

### Tools (`anexis/tools/`)
* Built in: time, math, memory (remember, search, forget), notes and deadlines, files, shell, Python, desktop control, web search, page fetch, GitHub, Canvas, code_task.
* MCP tool servers from `tools/manifest.yaml`. Lesson from Windows: install each npm server once into its own folder and run it with node, instead of `npx` every start (which kept failing).
* Every call is timed and counted (`tool_stats`), which helps pick tools later.

### Coding (`anexis/coder/`)
Runs Claude Code headless (`claude -p`, stream-json output) on your Pro plan,
not an API key. Reads usage from `claude /usage` and rate limit events, and
switches to Opus at 85% used. If Claude is out or missing, Anexis's own coder
does the task with the coder model.

---

## 4. Memory (the part to keep and grow)

One SQLite file (`memory.db`). Nothing in the store talks to a model:
learning is a separate step, so a confused model can never wreck the memory.

### Tables
| table | what it holds |
| --- | --- |
| sessions | each chat: mode, summary so far, how far the summary got |
| messages | every message, role, content, meta |
| memories | what it learned: kind, text, confidence, importance, source, key, pinned, used when, how often, replaced by |
| memories_fts | full text index (FTS5, porter stemming) kept in step by triggers |
| memory_vectors | one embedding per memory, per embed model |
| items | deadlines, tasks, Canvas assignments (type, title, due, done) |
| kv | small settings and state (style notes, check in history) |
| tool_stats | calls, failures, time per tool |
| events | a log of what happened (synced, failed, learned) |
| tombstones, kv_times | for sync: what was deleted, when a value changed |

Memory kinds: fact, preference, habit, project, class, person, task, lesson.
A **lesson** is how you told it to behave ("stop using dashes"), always shown.

### Learning after each chat (`anexis/memory/learn.py`)
The small model reads the exchange plus the related memories it already has,
and answers JSON ops only:
* `add` a new memory (kind, one sentence, importance)
* `reinforce` an existing one that was confirmed again
* `replace` one that changed (the old one is kept, marked replaced)

The code checks every op: unknown ids are ignored, repeats reinforce instead
of piling up, unreadable answers are dropped. Most chats add nothing, that is
on purpose (skip small talk, one time questions, things only true right now).

### Finding the right memories (`store.search`)
Word match (FTS5) and meaning match (vectors, cosine at least 0.3) each give a
ranked list. They are fused (each hit scores 1 / (10 + rank), summed), then
multiplied by **quality**:

```
quality = (0.4 + 0.6 * confidence) * (0.7 + 0.3 * importance)
          * recency (0.75 + 0.25 * e^(-days since used / 30))
          * usage   (1 + 0.15 * ln(1 + times used))
          * 1.3 if it is a lesson
```

So sure, important, recently and often useful memories win. Typos are helped
by matching close words from its own vocabulary.

### Upkeep when idle (`anexis/memory/consolidate.py`)
* Summaries of chats with 8+ new messages (4 sentences, keeps decisions and open questions).
* Vectors for memories that have none yet.
* Merging near duplicates.
* Decay: a memory nobody needed for 30 days loses 3% confidence each run, never below 0.2, pinned never decays. Decay only changes ranking, it never deletes.

### How you talk (`anexis/memory/style.py`)
Two parts. Plain counting over your own messages (casual words, length,
punctuation, no model needed, cannot be talked into anything), plus a short
note on how you think written by the small model every 20 new messages.
Both go into every prompt so answers sound like they fit you.

### About Me and the first start (`anexis/profile/`)
About Me is what you tell it up front (name, school, classes, schedule,
goals, work, projects). Stored as pinned memories, always in the prompt. On
the first start it is seeded with what is already known about you so it never
starts as a stranger.

### Sync between PC and school server (`anexis/memory/sync.py`)
Every memory, item and message gets a uid. Deletes leave a tombstone.
Each side sends what changed since last time, the newer `updated_at` wins.
Runs when the app starts and every 15 minutes.

---

## 5. JARVIS, the voice

The voice engine is from your Hail Mary project, moved in with only its
imports changed (`anexis/voice/hailmary/`). The path of one sentence:

```
mic (48 kHz, 10 ms blocks)
 -> echo cancelling (LiveKit APM, with what JARVIS is playing as the reference)
 -> resample to 16 kHz (soxr)
 -> Silero VAD: is someone talking
 -> Smart Turn v3.2: are they done talking, or just pausing
 -> Parakeet TDT 0.6B v2 (onnx-asr, GPU when there is one): speech to text
 -> attention: is this for JARVIS?
 -> Anexis agent (same memory, tools, models as chat), session "voice"
 -> reply cut into sentences as it streams
 -> Piper with the JARVIS voice (jgkawell/jarvis, jarvis-high)
 -> speakers (talk over it and it stops: barge in)
```

### Attention (is this for me?)
* Wake words: jarvis, j, jay, with lead ins like "hey", "ok", "yo".
* **wake** mode: only with the name. **smart** (default): the name, or something that clearly asks an assistant, or the judge model says yes. **always**: everything.
* Saying only "Jarvis" arms it for 6 seconds: the next thing you say is for it, and it says "Yes, sir?" if you pause.
* For 8 seconds after it speaks, a short answer counts (follow up).
* The judge is a tiny prompt ("was this spoken to JARVIS? yes or no") on the fast model, with 1.5 seconds to answer. A slow judge means no.
* Its own voice coming back through the mic is filtered: if 60% of the words heard match what it is saying, it is an echo.

### Asking out loud before risky tools
"Sir, I would like to use run shell dir. Shall I proceed?" The answer only
counts with the name in it ("Jarvis, go ahead" / "Jarvis, cancel"), so a TV
saying "yes" can never approve anything. The deck shows buttons too.

### What we learned the hard way
* What it says on its own (check ins) must go into the voice conversation, or it does not know it asked "how was your day" and ignores your answer.
* A full screen game means game sounds: switch to wake mode while a game is in front, hold check ins.
* Setup must check for the real voice (packages AND models), not some older package, or it skips installing it.
* Models are big (Parakeet fp32 about 2.4 GB): on the GPU it eats VRAM a game wants. Consider int8 on the CPU for gaming.
* Keep a voice log of every sentence heard, taken or ignored and why. Without it "what set it off?" has no answer.

---

## 6. The desktop app

* **Electron frame** (`desktop/frame.js`): starts the supervisor, shows the
  deck, tray icon, close to tray, start with Windows (hidden), full screen,
  notifications, the Canvas sign in window (its own browser session, cookies
  handed to the brain).
* **Live copy**: the installed app runs from plain files in
  `%LOCALAPPDATA%\Anexis\app`. `update.ps1` copies new code over it, the deck
  reloads and the brain restarts by itself. No rebuild for code changes, only
  for new bundled runtimes.
* **Installer**: NSIS via electron-builder, bundles Python, Node and uv.
* **Supervisor** (`anexis/desktop/supervisor.py`): restarts the brain when a
  .py file changes, holds back a file that does not parse and tells the deck
  why, backs off when the brain keeps crashing, exit code 75 means "restart me".
* **Setup in the app**: preset (max, balanced, light, cloud), name, control,
  voice, keys, then downloads with progress (Ollama, models, Claude Code, tool
  servers, voice).

### The deck (`ui/`)
Black eDEX style: system panel, chat, terminal (real shell), memory, tools,
files, on screen keyboard, globe, activity feed, and the JARVIS circle as home.
Screens: Setup, Models, Keys, Checkup, About me, App. Plain JS modules, live
reload when a file changes.

---

## 7. School side

* `anexis serve` on the server, token protected.
* `jarvis.py`: one file chat client with no UI, for the school terminal.
* Sync keeps the PC and the server on one memory.

---

## 8. Bugs we hit (rules for the rebuild)

| what happened | the rule |
| --- | --- |
| Quitting the app left the brain running, JARVIS kept talking with no window | On Windows killing a parent never kills its children. Put every child in a Job Object that dies with the app, and have every child watch its parent and exit when it is gone. Never fire and forget a kill on exit. |
| Tool servers failed on Windows with npx | Install once, run with node directly, one at a time. |
| Keys button looked broken | Never wait on something slow (`claude /usage`) before showing a screen. Show it, fill it in later. |
| A retired Nvidia model broke everything | Never trust a fixed model name. Live lists, heal to the closest model. |
| Sign in button greyed out | A new file the updater did not copy. Updater must copy every file it needs, and rerun itself when it changed. |
| Agent hunted for passwords when Canvas was not connected | Tools for a service always exist and say "not connected, here is how". Tell the model never to sign in or look for passwords. |
| Canvas paging lost items | Test paging with more than one page. |
| Setup rewrote settings and dropped the voice part | Change single values, never rewrite the whole settings file. |
| JARVIS ignored the answer to its own question | One conversation thread for everything it says, spoken or typed. |
| Game sounds set it off, check ins mid game | Game mode. |

---

## 9. What to do differently in the clean version

1. **One conversation, many ways in.** Right now chat, voice and check ins
   each have their own session. Make one ongoing thread with you (plus side
   chats you start on purpose). Voice, text, school CLI and check ins all
   read and write it, so it always knows what it just said.
2. **Integrations as plugins with one shape.** Canvas, the school server,
   GitHub and anything new (like Arkia Buzz) should each be one folder with
   the same four things: `status()`, `connect()`, `sync()` (pulls data into
   memory and items on a schedule), and `tools()`. The app finds them by
   folder. Adding a service never touches the core.
3. **People as first class memory.** Add a `people` table (name, how you know
   them, notes) and link memories to people ("me and Andrew did a Python
   practice test" links to Andrew). This is what friend profiles need. Show
   them in the app so you can see, fix and delete what it keeps about anyone.
4. **Keep where each memory came from.** Link every memory to the message or
   sync that made it. Makes "why do you think that?" answerable, and deleting
   a chat can delete what it taught.
5. **Process safety from day one.** Job Object on Windows plus a parent
   watchdog in every child (see section 8, row 1). Or use Tauri, whose
   sidecars are easier to keep tied to the app.
6. **Voice as its own module with a clear protocol.** In: audio. Out: events
   (heard, state, levels, said) and text to the brain. Same as now, but with
   the fixes above built in, the voice log always on, game mode, and a
   choice of GPU or CPU for speech to text.
7. **Typed events.** One list of event types with their fields, shared by the
   brain and the deck, instead of strings scattered around.
8. **Settings with a schema.** One file, validated, edited one value at a
   time, a screen that is generated from the schema.
9. **Smaller deck.** Keep the look, but start from the JARVIS circle, chat and
   memory. Add panels only when they earn their place.
10. **Tests at the edges, like now.** Stand ins for the model (scripted
    replies), the mic (a list of sentences), the speaker and the voice. A real
    browser test for the deck. A test that kills the app and checks nothing is
    left running.

---

## 10. Build order for the rebuild

1. Brain skeleton: settings, server with token and loopback lock, event bus, model router with roles and live lists.
2. Memory: the tables above, learn step, search with the quality formula, upkeep, style, About Me. One conversation thread. People table.
3. Agent loop with tool picking, permissions, the built in tools.
4. Desktop shell: window, tray, start with Windows, child processes tied to the app, live updates.
5. The deck: JARVIS circle home, chat, memory and people views, settings from schema.
6. Voice: the Hail Mary engine as a module, voice log, game mode, approvals.
7. Plugins: Canvas, school sync, Claude Code coder, MCP tool servers, then new ones (Arkia Buzz).
8. On its own: check ins that write to the one thread, quiet hours, game mode hold.

---

## 11. Planned: Arkia Buzz

Connect your Arkia Buzz dev account so it can pull messages and metrics from
your website, and use them for memory and people profiles. As a plugin
(section 9, point 2): `connect()` with your dev key, `sync()` pulls new
messages and metrics on a schedule, `tools()` lets it look things up when you
ask. Needs from you: what the API looks like (docs, or the site's code) and how
the dev account signs in.
