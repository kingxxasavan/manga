// The only things the deck may ask of the window: open the Canvas sign in,
// and open Anexis when Windows starts. Nothing else from the desktop is
// reachable from the page.

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("anexisFrame", {
  canvasSignIn: (url) => ipcRenderer.invoke("canvas-sign-in", String(url || "")),
  // Open Anexis when Windows starts, so it syncs with the school server right away.
  startAtLogin: (on) => ipcRenderer.invoke("start-at-login", on === undefined ? null : Boolean(on)),
});
