# The desktop app

The window around Anexis and the Windows installer. All of the assistant's work
is the Python code in `../anexis` and the deck in `../ui`. This folder only
starts it, shows it and packs it.

| File | Job |
|---|---|
| `bootstrap.js` | First thing that runs. Puts the live copy of the app's files in place, then loads `frame.js` from it. |
| `seed.js` | The live copy: first copy, version change with a backup, fallback when an edited frame is broken. Plain Node, tested by `npm test`. |
| `frame.js` | The window. Starts `python -m anexis desktop`, waits for it to answer, shows the deck, stops everything on quit. |
| `build.ps1` | Builds `dist\AnexisSetup.exe` on Windows. |
| `update.ps1` | Updates an installed Anexis from this repo. No rebuild, no reinstall. |
| `assets/` | The icon. |

## Build the installer

On Windows, with Node 20 or newer:

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

It downloads uv, a standalone Python and Node, installs the exact packages from
`uv.lock` into that Python, copies the app's files, and runs electron builder.
The first build downloads about 400 MB and takes a few minutes.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -SkipRuntime
```

reuses the Python and Node from the last build, for when only the app changed.

The installer is not code signed, so Windows SmartScreen shows a warning the
first time. Choose More info, then Run anyway.

## Update without rebuilding

```powershell
powershell -ExecutionPolicy Bypass -File update.ps1
```

Pulls the newest code and copies it over the live copy (after backing it up).
Use this for normal updates. Build the installer again only when `uv.lock`
changed, since the Python packages live inside the installer.

## Where things go on the PC

| Path | What |
|---|---|
| `%LOCALAPPDATA%\Programs\Anexis` | The installed program and the bundled runtime. Replaced by each install. |
| `%LOCALAPPDATA%\Anexis\app` | The live copy: the files the app runs from. Edit these. |
| `%LOCALAPPDATA%\Anexis\app-backup-*` | Earlier live copies, kept when a new version was installed. |
| `%USERPROFILE%\.anexis` | Your data: memory, keys, settings, logs. Never touched by an install. |
| `%USERPROFILE%\anexis\workspace` | Where Anexis makes files and projects. |

Uninstalling removes the first one only.

## Run it from source

```bash
npm install
npm start
```

This uses the repo itself as the live copy and the Python in `../.venv`
(`uv sync --extra desktop` in the repo root first). Set `ANEXIS_PYTHON` to use
another Python.

Without the window at all: `anexis ui` runs the same supervised brain and opens
the deck in your browser.

## Keys in the window

F5 reloads the screen, F11 is full screen, F12 opens the inspector, Ctrl+Q quits.

## If it will not start

The starting screen says what went wrong and shows the last lines of the log.
The full log is `%USERPROFILE%\.anexis\server.log`. If an edit to the live copy
broke it, rename `%LOCALAPPDATA%\Anexis\app` to anything else and start the app:
it puts a fresh copy in place.
