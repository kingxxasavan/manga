// Everything that talks to the Anexis server goes through here.
//
// The token arrives once in the page link (…/ui/#token=…), is kept for this
// window only, and is taken out of the address bar straight away.

const KEY = "anexis-token";

function takeToken() {
  const found = location.hash.match(/token=([^&]+)/);
  if (found) {
    sessionStorage.setItem(KEY, decodeURIComponent(found[1]));
    history.replaceState(null, "", location.pathname + location.search);
  }
  return sessionStorage.getItem(KEY) || "";
}

export let token = takeToken();
export function setToken(value) {
  token = value.trim();
  sessionStorage.setItem(KEY, token);
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status; // 0 means the server did not answer at all
  }
}

function headers(extra = {}) {
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function failure(resp) {
  let detail = resp.statusText;
  try {
    const body = await resp.json();
    detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch { /* not JSON, keep the status text */ }
  return new ApiError(resp.status, detail);
}

async function send(method, path, body, raw) {
  let resp;
  try {
    resp = await fetch(path, {
      method,
      headers: headers(body !== undefined && !raw ? { "Content-Type": "application/json" } : {}),
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Anexis is not answering.");
  }
  if (!resp.ok) throw await failure(resp);
  return resp;
}

export const get = async (path) => (await send("GET", path)).json();
export const post = async (path, body = {}) => (await send("POST", path, body)).json();
export const del = async (path) => (await send("DELETE", path)).json();
export const postRaw = async (path, bytes) => (await send("POST", path, bytes, true)).json();
export const postForBlob = async (path, body) => (await send("POST", path, body)).blob();

/** Reads a stream of JSON lines, calling onEvent for each. Resolves when the
 *  stream ends. Pass an AbortSignal to hang up. */
export async function stream(method, path, body, onEvent, signal) {
  let resp;
  try {
    resp = await fetch(path, {
      method, signal,
      headers: headers(body !== undefined ? { "Content-Type": "application/json" } : {}),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    throw new ApiError(0, "Anexis is not answering.");
  }
  if (!resp.ok) throw await failure(resp);
  const reader = resp.body.getReader(), decoder = new TextDecoder();
  let pending = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    }
    if (pending.trim()) onEvent(JSON.parse(pending));
  } catch (e) {
    if (e.name !== "AbortError") throw new ApiError(0, "The connection to Anexis dropped.");
  }
}

/** The live feed of everything Anexis does. Reconnects by itself and tells
 *  the caller when the link goes down and comes back. */
export function follow(onEvent, onLink) {
  let stopped = false, up = null;
  (async () => {
    while (!stopped) {
      try {
        await stream("GET", "/events", undefined, (event) => {
          if (up !== true) onLink((up = true));
          onEvent(event);
        });
        if (up !== true) onLink((up = true));
      } catch (e) {
        if (e.status === 401) { onLink("locked"); return; }
      }
      if (stopped) return;
      if (up !== false) onLink((up = false));
      await new Promise((r) => setTimeout(r, 1000));
    }
  })();
  return () => { stopped = true; };
}

export function terminalSocket() {
  return new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/terminal`);
}
