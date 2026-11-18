// The window around Anexis. It starts the brain, waits for it to answer,
// and shows the deck. This file is loaded from the live copy of the app, so
// it can be edited in place: close the app and open it again to see a change.
//
// What it does not do: any of the assistant's work. That is all in the Python
// code under anexis/, which this file only starts and stops.

const { app, BrowserWindow, Menu, Notification, Tray, dialog, ipcMain, nativeImage, shell, session } = require("electron");
const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const BG = "#000000";
let win = null, brain = null, deckUrl = "", deckToken = "", quitting = false, lastLog = "", tray = null, toldAboutTray = false;

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
    deckToken = data.token;
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
  // For smoke tests: ANEXIS_FRAME_CANVAS=<address> runs the Canvas sign in at
  // once and prints how it went.
  if (process.env.ANEXIS_FRAME_CANVAS) {
    canvasSignIn(process.env.ANEXIS_FRAME_CANVAS).then((result) => {
      console.log("ANEXIS_CANVAS " + JSON.stringify(result));
      if (!process.env.ANEXIS_FRAME_SHOT) app.quit();
    });
  }
  // For smoke tests: ANEXIS_FRAME_TRAY=1 closes the window, checks Anexis is still
  // running in the tray, goes full screen and checks the top bar stepped aside.
  if (process.env.ANEXIS_FRAME_TRAY) {
    setTimeout(async () => {
      win.close();
      await new Promise((r) => setTimeout(r, 1500));
      const afterClose = { running: !win.isDestroyed(), visible: win.isVisible(), tray: Boolean(tray), brain: Boolean(brain) };
      showWindow();
      win.setFullScreen(true);
      await new Promise((r) => setTimeout(r, 2500));
      const bar = await win.webContents.executeJavaScript(
        `({ fullscreen: document.documentElement.dataset.fullscreen, barTop: Math.round(document.querySelector(".top").getBoundingClientRect().bottom) })`);
      console.log("ANEXIS_TRAY " + JSON.stringify({ afterClose, back: win.isVisible(), ...bar }));
      app.quit();
    }, 5000);
  }
  // For smoke tests: ANEXIS_FRAME_EVAL=<js> runs in the deck once it loaded and prints the answer.
  if (process.env.ANEXIS_FRAME_EVAL) {
    win.webContents.once("did-finish-load", () => setTimeout(async () => {
      try {
        console.log("ANEXIS_EVAL " + JSON.stringify(await win.webContents.executeJavaScript(process.env.ANEXIS_FRAME_EVAL)));
      } catch (error) {
        console.log("ANEXIS_EVAL " + JSON.stringify({ error: error.message }));
      }
      if (!process.env.ANEXIS_FRAME_SHOT) app.quit();
    }, 3000));
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
    webPreferences: {
      contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false,
      preload: path.join(__dirname, "preload.js"),
      // Keeps the deck awake while the window is hidden in the tray, so it
      // still hears "hey Jarvis", reminders and finished work.
      backgroundThrottling: false,
    },
  });
  win.once("ready-to-show", () => {
    if (!startedAtLogin) win.show();  // started with Windows: stays in the tray until wanted
  });
  // Closing the window keeps Anexis running in the tray. Quit from the tray menu or Ctrl+Q.
  win.on("close", (event) => {
    if (quitting) return;
    event.preventDefault();
    win.hide();
    if (!toldAboutTray && Notification.isSupported()) {
      toldAboutTray = true;
      new Notification({ title: "Anexis is still running", body: "It is in the tray. Click its icon, or say hey Jarvis, to bring it back." }).show();
    }
  });
  win.on("closed", () => { win = null; });
  // Full screen: the deck hides its top bar until the mouse touches the top edge.
  const fullscreen = (on) => win?.webContents.executeJavaScript(
    `document.documentElement.dataset.fullscreen = ${JSON.stringify(on ? "on" : "off")}`).catch(() => {});
  win.on("enter-full-screen", () => fullscreen(true));
  win.on("leave-full-screen", () => fullscreen(false));
  win.webContents.on("did-finish-load", () => fullscreen(win.isFullScreen()));
  win.loadURL(notePage("Starting...", context.seeded.action === "seeded" ? "First start. Setting up the app's files." : ""));

  // The deck is the only thing this window ever shows. Links go to the real browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    // The deck's second way to ask for the Canvas sign in, for when the bridge
    // (preload.js) is missing: it opens about:blank#anexis-canvas=<address>.
    if (url === "about:blank#anexis-show") { showWindow(); return { action: "deny" }; }
    const ask = url.match(/^about:blank#anexis-canvas=(.*)$/);
    if (ask) {
      const tell = (detail) => win?.webContents.executeJavaScript(
        `window.dispatchEvent(new CustomEvent("anexis-canvas", { detail: ${JSON.stringify(detail)} }))`).catch(() => {});
      tell({ started: true });
      canvasSignIn(decodeURIComponent(ask[1])).then(tell);
      return { action: "deny" };
    }
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

// ---- Canvas: sign in with the browser ------------------------------------
// The school's own Canvas login opens in a window of its own. Anexis never
// sees the username or password, only the signed in session afterwards, and
// only the cookies of the Canvas site itself. The window keeps its own
// storage, so the next sign in is often one click.

const CANVAS = "persist:canvas";
const GUARD = "while(1);";

async function whoAmI(ses, base) {
  try {
    const resp = await ses.fetch(`${base}/api/v1/users/self`, { headers: { Accept: "application/json" }, redirect: "manual" });
    if (resp.status !== 200) return null;
    const text = (await resp.text()).trim();
    const me = JSON.parse(text.startsWith(GUARD) ? text.slice(GUARD.length) : text);
    return me && me.id ? me : null;
  } catch {
    return null;
  }
}

function canvasSignIn(address) {
  let base;
  try {
    const url = new URL(/^https?:\/\//i.test(address) ? address : `https://${address}`);
    const testing = process.env.ANEXIS_CANVAS_ALLOW_LOCAL_HTTP && ["127.0.0.1", "localhost"].includes(url.hostname);
    if (url.protocol !== "https:" && !testing) throw new Error("not https");
    base = url.origin;
  } catch {
    return Promise.resolve({ ok: false, error: "That is not a Canvas address. It looks like https://yourschool.instructure.com" });
  }
  const ses = session.fromPartition(CANVAS);
  return new Promise((resolve) => {
    let done = false, checking = false;
    const login = new BrowserWindow({
      width: 980, height: 820, parent: win || undefined, title: "Sign in to Canvas", backgroundColor: "#ffffff", autoHideMenuBar: true,
      webPreferences: { partition: CANVAS, contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    login.webContents.setWindowOpenHandler(({ url }) => {
      login.loadURL(url);  // a school login that opens a new tab stays in this one window
      return { action: "deny" };
    });
    const finish = (result) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      clearTimeout(limit);
      if (!login.isDestroyed()) login.close();
      resolve(result);
    };
    const check = async () => {
      if (done || checking) return;
      checking = true;
      try {
        const me = await whoAmI(ses, base);
        if (!me) return;
        const cookies = (await ses.cookies.get({ url: base })).map((c) => ({ name: c.name, value: c.value, domain: c.domain, path: c.path }));
        const resp = await fetch(`${deckUrl}/canvas/session`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${deckToken}` },
          body: JSON.stringify({ url: base, cookies }),
        });
        const reply = await resp.json().catch(() => ({}));
        finish(resp.ok ? { ok: true, user: reply.user || me.short_name || me.name || "", url: base }
                       : { ok: false, error: reply.detail || `Anexis said HTTP ${resp.status}` });
      } catch (error) {
        finish({ ok: false, error: `Could not finish the sign in: ${error.message}` });
      } finally {
        checking = false;
      }
    };
    login.webContents.on("did-navigate", check);
    login.webContents.on("did-navigate-in-page", check);
    const timer = setInterval(check, 2500);
    const limit = setTimeout(() => finish({ ok: false, error: "The sign in took longer than 15 minutes, so it was stopped." }), 15 * 60 * 1000);
    login.on("closed", () => finish({ ok: false, error: "The sign in window was closed before it finished." }));
    login.loadURL(`${base}/login`).catch(() => {
      // Some schools send /login straight on to their own sign in page. A failed
      // first load is only a problem when nothing loads at all.
      setTimeout(() => { if (!done && login.webContents.getURL() === "") finish({ ok: false, error: `Could not open ${base}. Check the address.` }); }, 8000);
    });
  });
}

// ---- open when Windows starts ---------------------------------------------
// On by default, once: Anexis syncs with the school server as it starts, so it
// has to start with the computer. Started this way it opens minimized.
const AT_LOGIN = "--at-login";
const startedAtLogin = process.argv.includes(AT_LOGIN);

function loginItem(on) {
  if (!app.isPackaged) return false;  // running from source: not something to start with Windows
  if (on !== null && on !== undefined) app.setLoginItemSettings({ openAtLogin: on, args: [AT_LOGIN] });
  return app.getLoginItemSettings({ args: [AT_LOGIN] }).openAtLogin;
}

function loginItemOnce() {
  const marker = path.join(app.getPath("userData"), "start-at-login-set");
  if (!app.isPackaged || fs.existsSync(marker)) return;
  loginItem(true);
  try { fs.writeFileSync(marker, "on\n"); } catch { /* asked again next time, no harm */ }
}

ipcMain.handle("start-at-login", (event, on) => {
  if (!win || event.sender !== win.webContents || !local(event.senderFrame.url)) return false;
  return loginItem(on);
});

// ---- the tray ---------------------------------------------------------------
function showWindow() {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function makeTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, "assets", "icon.png")).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("Anexis");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Anexis", click: showWindow },
    { type: "separator" },
    { label: "Quit Anexis", click: () => app.quit() },
  ]));
  tray.on("click", showWindow);
}

ipcMain.handle("show-window", (event) => {
  if (win && event.sender === win.webContents) showWindow();
  return true;
});

ipcMain.handle("canvas-sign-in", (event, address) => {
  // Only the deck may ask, never a page that ended up in some other window.
  if (!win || event.sender !== win.webContents || !local(event.senderFrame.url)) return { ok: false, error: "Not allowed from here." };
  return canvasSignIn(address);
});

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
  app.on("second-instance", showWindow);  // opening Anexis again brings the running one back
  app.on("window-all-closed", () => { if (quitting) app.quit(); });
  app.on("before-quit", () => { quitting = true; stopBrain(); });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(menu(context));
    loginItemOnce();
    makeTray();
    createWindow(context);
    startBrain(context);
  });
}

module.exports = { start };
