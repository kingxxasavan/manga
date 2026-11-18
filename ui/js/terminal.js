// The terminal panel: a real shell on this machine, through xterm.js.

import * as api from "./api.js";
import { $, toast } from "./dom.js";
import { FitAddon } from "../vendor/xterm/addon-fit.mjs";
import { Terminal } from "../vendor/xterm/xterm.mjs";

let term = null, fit = null, socket = null, started = false;
const encoder = new TextEncoder();

function colours() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    background: "#00000000", foreground: v("--text"), cursor: v("--accent"), cursorAccent: v("--bg"),
    selectionBackground: v("--accent") + "55",
    black: "#0b1118", brightBlack: v("--dim"), red: v("--bad"), brightRed: v("--bad"),
    green: v("--ok"), brightGreen: v("--ok"), yellow: v("--warn"), brightYellow: v("--warn"),
    blue: v("--accent"), brightBlue: v("--accent"), cyan: v("--accent-2"), brightCyan: v("--accent-2"),
    magenta: "#c792ea", brightMagenta: "#e2b6ff", white: v("--text"), brightWhite: "#ffffff",
  };
}

function resize() {
  if (!term || !$("#term-host").clientWidth) return;
  try { fit.fit(); } catch { return; }
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ resize: [term.cols, term.rows] }));
}

/** Opens a shell. `cwd` is where it starts, `run` is typed into it once it is up. */
export function openShell({ cwd = "", run = "" } = {}) {
  if (!term) {
    term = new Terminal({
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--mono"),
      fontSize: 13, lineHeight: 1.25, cursorBlink: true, allowTransparency: true, scrollback: 5000, theme: colours(),
    });
    fit = new FitAddon();
    term.loadAddon(fit);
    term.open($("#term-host"));
    term.onData((data) => socket?.readyState === WebSocket.OPEN && socket.send(encoder.encode(data)));
    new ResizeObserver(resize).observe($("#term-host"));
  }
  socket?.close();
  term.reset();
  resize();
  const mine = (socket = api.terminalSocket());
  mine.binaryType = "arraybuffer";
  mine.onopen = () => mine.send(JSON.stringify({ token: api.token, cwd, cols: term.cols, rows: term.rows }));
  mine.onmessage = (event) => {
    if (typeof event.data !== "string") return term.write(new Uint8Array(event.data));
    const hello = JSON.parse(event.data);
    if (!hello.ready) return;
    $("#term-where").textContent = hello.kind === "pipes"
      ? "plain shell (no terminal device here, full screen programs will not work)"
      : cwd || "your workspace";
    if (run) mine.send(encoder.encode(run + "\r"));
    term.focus();
  };
  mine.onclose = (event) => {
    if (socket !== mine) return;
    const why = event.code === 4401 ? "The token was refused." : event.code === 4403 ? "Refused." : "The shell ended.";
    term.write(`\r\n\x1b[2m${why} Press New shell to start another.\x1b[0m\r\n`);
  };
  mine.onerror = () => toast("Could not open the terminal. Is Anexis still running?", "bad");
  started = true;
}

/** Called when the terminal tab is shown: starts the first shell, fits the size. */
export function showTerminal() {
  if (!started) openShell();
  requestAnimationFrame(() => { resize(); term?.focus(); });
}

/** Types into the running shell, as if on the keyboard. */
export function sendKeys(data) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(encoder.encode(data));
  term?.focus();
}

export function retheme() {
  if (term) term.options.theme = colours();
}

export function initTerminal() {
  $("#term-new").addEventListener("click", () => openShell());
}
