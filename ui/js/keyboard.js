// The on screen keyboard along the bottom. Keys light up as you type on the
// real keyboard, and clicking one types it: into the terminal when that tab
// is showing, into the chat box otherwise.

import { $, h } from "./dom.js";

// [what the key shows, its KeyboardEvent.code, the character it types, shifted character, width]
const ROWS = [
  [["esc", "Escape", "\x1b"], ["`", "Backquote", "`", "~"], ...digits(), ["-", "Minus", "-", "_"], ["=", "Equal", "=", "+"], ["back", "Backspace", "\x7f", "", 18]],
  [["tab", "Tab", "\t", "", 15], ...letters("qwertyuiop"), ["[", "BracketLeft", "[", "{"], ["]", "BracketRight", "]", "}"], ["\\", "Backslash", "\\", "|", 15]],
  [["caps", "CapsLock", "", "", 18], ...letters("asdfghjkl"), [";", "Semicolon", ";", ":"], ["'", "Quote", "'", '"'], ["enter", "Enter", "\r", "", 22]],
  [["shift", "ShiftLeft", "", "", 22], ...letters("zxcvbnm"), [",", "Comma", ",", "<"], [".", "Period", ".", ">"], ["/", "Slash", "/", "?"], ["shift", "ShiftRight", "", "", 22]],
  [["ctrl", "ControlLeft", "", "", 15], ["alt", "AltLeft", "", "", 15], ["", "Space", " ", "", 62], ["alt", "AltRight", "", "", 15],
    ["◄", "ArrowLeft", "\x1b[D"], ["▲", "ArrowUp", "\x1b[A"], ["▼", "ArrowDown", "\x1b[B"], ["►", "ArrowRight", "\x1b[C"]],
];

function digits() {
  const shifted = ")!@#$%^&*(";
  return [1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map((d) => [String(d), `Digit${d}`, String(d), shifted[d]]);
}
function letters(row) {
  return [...row].map((c) => [c, `Key${c.toUpperCase()}`, c, c.toUpperCase()]);
}

let hooks = {}, shift = false, caps = false, ctrl = false;
const keys = new Map();

function typeInto(input, text, code) {
  const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
  if (code === "Backspace") {
    const from = start === end ? Math.max(0, start - 1) : start;
    input.setRangeText("", from, end, "end");
  } else if (code === "Enter") {
    input.form?.requestSubmit();
    return;
  } else if (code === "ArrowLeft" || code === "ArrowRight") {
    const at = Math.max(0, Math.min(input.value.length, start + (code === "ArrowLeft" ? -1 : 1)));
    input.setSelectionRange(at, at);
  } else if (text && !text.startsWith("\x1b")) {
    input.setRangeText(text, start, end, "end");
  }
  input.dispatchEvent(new Event("input"));
}

function press([, code, plain, shifted]) {
  if (code.startsWith("Shift")) { shift = !shift; return mark(); }
  if (code === "CapsLock") { caps = !caps; return mark(); }
  if (code.startsWith("Control")) { ctrl = !ctrl; return mark(); }
  if (code.startsWith("Alt")) return;
  const letter = code.startsWith("Key");
  let text = shift && shifted ? shifted : letter && caps ? plain.toUpperCase() : plain;
  if (hooks.terminalShowing?.()) {
    // Ctrl with a letter is how a terminal gets Ctrl+C, Ctrl+D and friends.
    if (ctrl && letter) text = String.fromCharCode(plain.toUpperCase().charCodeAt(0) - 64);
    hooks.toTerminal?.(text);
  } else {
    const input = $("#input");
    input.focus();
    typeInto(input, text, code);
  }
  shift = ctrl = false;  // like a phone keyboard: they apply to the next key only
  mark();
}

function mark() {
  for (const [code, el] of keys) {
    el.classList.toggle("held", (shift && code.startsWith("Shift")) || (caps && code === "CapsLock") || (ctrl && code.startsWith("Control")));
  }
}

export function initKeyboard(options) {
  hooks = options;
  $("#keyboard").replaceChildren(...ROWS.map((row) => h("div.kb-row", row.map((key) => {
    const el = h("button", {
      type: "button", tabIndex: -1, dataset: key[4] ? { w: String(key[4]) } : {}, "aria-label": key[0] || "space",
      // mousedown, not click, and no focus change: the box being typed into keeps the cursor
      onmousedown: (e) => { e.preventDefault(); press(key); },
    }, key[0]);
    keys.set(key[1], el);
    return el;
  }))));
  addEventListener("keydown", (e) => keys.get(e.code)?.classList.add("on"));
  addEventListener("keyup", (e) => keys.get(e.code)?.classList.remove("on"));
  addEventListener("blur", () => keys.forEach((el) => el.classList.remove("on")));
}
