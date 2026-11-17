// The window around Anexis. It starts the brain, waits for it to answer,
// and shows the deck. This file is loaded from the live copy of the app, so
// it can be edited in place: close the app and open it again to see a change.
//
// What it does not do: any of the assistant's work. That is all in the Python
// code under anexis/, which this file only starts and stops.

const { app, BrowserWindow, Menu, dialog, shell, session } = require("electron");
const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const BG = "#000000";
let win = null, brain = null, deckUrl = "", quitting = false, lastLog = "";

// ---- finding Python ------------------------------------------------------
function pythonFor(context) {
  if (process.env.ANEXIS_PYTHON) return process.env.ANEXIS_PYTHON;
  const candidates = context.runtime
    ? [path.join(context.runtime, "python", "python.exe"), path.join(context.runtime, "python", "bin", "python3")]
    : [path.join(context.live, ".venv", "Scripts", "python.exe"), path.join(context.live, ".venv", "bin", "python")];
  return candidates.find((p) => fs.existsSync(p)) || (process.platform === "win32" ? "python" : "python3");
}

function brainEnv(context) {
  const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1", ANEXIS_FRAME: context.version };
  env.PYTHONPATH = [context.live, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  if (context.runtime) {
    // Everything the installer shipped comes first on PATH, so Anexis and its
    // tools use the bundled Python, Node and uv whatever else is installed.
    env.ANEXIS_RUNTIME = context.runtime;
    const shipped = ["node", "python", path.join("python", "Scripts"), ""].map((p) => path.join(context.runtime, p));
    env.PATH = [...shipped, env.PATH || env.Path || ""].join(path.delimiter);
    delete env.Path;
  }
  return env;
}

// ---- the page shown before the deck is up, and when it cannot come up ----
function notePage(title, detail = "", log = "") {
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return "data:text/html;charset=utf-8," + encodeURIComponent(`<!doctype html><meta charset="utf-8"><title>Anexis</title>
<style>
  html,body{height:100%;margin:0;background:${BG};color:#c2dfe1;font:14px/1.6 Consolas,ui-monospace,monospace}
  body{display:grid;place-items:center}
  main{width:min(720px,86vw)}
  h1{font:700 44px/1 "Segoe UI",system-ui,sans-serif;letter-spacing:.34em;color:#aacfd1;text-shadow:0 0 30px #aacfd159;margin:0 0 22px}
  p{color:#6d8a96;margin:0 0 10px;white-space:pre-wrap}
  p b{color:#d5eef6;font-weight:500}
  pre{margin:14px 0 0;padding:12px;border:1px solid #aacfd138;background:#000;color:#6d8a96;white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto;font-size:12px}
</style>
<main><h1>ANEXIS</h1><p><b>${esc(title)}</b></p><p>${esc(detail)}</p>${log ? `<pre>${esc(log)}</pre>` : ""}</main>`);
}

// ---- the brain -----------------------------------------------------------
function startBrain(context) {
  const python = pythonFor(context);
  brain = spawn(python, ["-m", "anexis", "desktop"], {
    cwd: context.live, env: brainEnv(context), windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
  });
  let pending = "";
  brain.stdout.on("data", (chunk) => {
    const lines = (pending + chunk).split(/\r?\n/);
    pending = lines.pop();
    lines.forEach((line) => onBrainLine(line, context));
  });
  brain.stderr.on("data", (chunk) => { lastLog = (lastLog + chunk).slice(-4000); });
  brain.on("error", (error) => {
    win?.loadURL(notePage("Anexis could not start its brain.", `Python was not found at:\n${python}\n\n${error.message}\n\nInstalling Anexis again puts it back.`));
  });
  brain.on("exit", (code) => {
    brain = null;
    if (quitting) return;
    if (code === 0) return app.quit();  // stopped on purpose (anexis stop)
    win?.loadURL(notePage("The brain stopped and could not be started again.",
      "Close this window and open Anexis again. If it keeps happening, the lines below say why.", lastLog));
  });
}

function onBrainLine(line, context) {
  const space = line.indexOf(" ");
  const kind = line.slice(0, space), body = line.slice(space + 1);
  let data;
  try { data = JSON.parse(body); } catch { lastLog = (lastLog + line + "\n").slice(-4000); return; }
  if (kind === "ANEXIS_READY") {
    deckUrl = data.url;
    win?.loadURL(`${data.url}/ui/#token=${encodeURIComponent(data.token)}`);
    afterReady(context);
  } else if (kind === "ANEXIS_STATE" && !deckUrl) {
    // Still on the starting page: say what is going on. Once the deck is up it
    // shows restarts and held back files itself.
    if (data.state === "crashed") win?.loadURL(notePage("The brain stopped while starting. Trying again...", "", data.log || ""));
    if (data.state === "waiting") win?.loadURL(notePage("The brain keeps stopping right after it starts.", data.why || "", data.log || ""));
  }
}

function afterReady(context) {
  if (context.seeded.action === "updated") {
    dialog.showMessageBox(win, {
      type: "info", title: "Anexis was updated",
      message: "This is a new version of Anexis.",
      detail: `The app's files were replaced with the new ones. The copy you had before, with any changes made to it, is kept here:\n\n${context.seeded.backup}`,
    });
  }
  if (context.frameProblem) {
    dialog.showMessageBox(win, {
      type: "warning", title: "Anexis",
      message: "The edited window code has a mistake, so the built in one is running.",
      detail: context.frameProblem,
    });
  }
  // For smoke tests: ANEXIS_FRAME_SHOT=<file.png> saves a picture of the window and quits.
  if (process.env.ANEXIS_FRAME_SHOT) {
    setTimeout(async () => {
      const image = await win.webContents.capturePage();
      fs.writeFileSync(process.env.ANEXIS_FRAME_SHOT, image.toPNG());
      app.quit();
    }, Number(process.env.ANEXIS_FRAME_SHOT_AFTER || 6000));
  }
}

function stopBrain() {
  if (!brain) return;
  const pid = brain.pid;
  if (process.platform === "win32") {
    // /T takes the whole tree: the supervisor, the brain and every tool server it started.
    execFile("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true }, () => {});
  } else {
    brain.kill("SIGINT");  // the supervisor stops the brain and exits
    setTimeout(() => { try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ } }, 6000).unref();
  }
}

// ---- the window ----------------------------------------------------------
function local(url) {
  try {
    const { protocol, hostname } = new URL(url);
    return protocol === "data:" || (deckUrl && new URL(deckUrl).origin === new URL(url).origin) || (protocol === "http:" && hostname === "127.0.0.1" && !deckUrl);
  } catch { return false; }
}

function createWindow(context) {
  win = new BrowserWindow({
    width: 1500, height: 950, minWidth: 420, minHeight: 560,
    backgroundColor: BG, show: false, title: "Anexis", autoHideMenuBar: true,
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  win.once("ready-to-show", () => win.show());
  win.on("closed", () => { win = null; });
  win.loadURL(notePage("Starting...", context.seeded.action === "seeded" ? "First start. Setting up the app's files." : ""));

  // The deck is the only thing this window ever shows. Links go to the real browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!local(url)) {
      event.preventDefault();
      if (/^https?:/.test(url)) shell.openExternal(url);
    }
  });
  // The microphone, for talking to it, and notifications, for reminders about
  // what is due. Nothing else, and only for the deck.
  session.defaultSession.setPermissionRequestHandler((contents, permission, allow, details) => {
    allow(["media", "notifications"].includes(permission) && local(details.requestingUrl || contents.getURL()));
  });
  session.defaultSession.setPermissionCheckHandler((contents, permission, origin) =>
    ["media", "notifications"].includes(permission) && local(origin || contents?.getURL() || ""));
}

function menu(context) {
  const open = (target) => () => shell.openPath(target);
  return Menu.buildFromTemplate([
    { label: "Anexis", submenu: [
      { label: "Open the app folder", click: open(context.live) },
      { label: "Reload the screen", accelerator: "F5", click: () => win?.webContents.reload() },
      { label: "Full screen", accelerator: "F11", click: () => win?.setFullScreen(!win.isFullScreen()) },
      { label: "Inspect the screen", accelerator: "F12", click: () => win?.webContents.toggleDevTools() },
      { type: "separator" },
      { label: "Quit", accelerator: "Ctrl+Q", click: () => app.quit() },
    ] },
    { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" }] },
  ]);
}

function start(context) {
  app.setAppUserModelId("dev.anexis.desktop");  // so Windows shows reminders under the app's own name
  if (!app.requestSingleInstanceLock()) {
    app.quit();  // already open: the first one is brought to the front below
    return;
  }
  app.on("second-instance", () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.focus();
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => { quitting = true; stopBrain(); });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(menu(context));
    createWindow(context);
    startBrain(context);
  });
}

module.exports = { start };
